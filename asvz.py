import argparse
import datetime
import re
import os, sys
import yaml
import logging

from crontab import CronTab
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait


class ASVZ:
    def __init__(self, interactive=False) -> None:
        opts = Options()
        if not interactive:
            opts.headless = True
        opts.add_argument("--lang=en")
        self.driver = Chrome(options=opts)
        self.interactive = interactive

        self.dir_name = os.path.dirname(os.path.abspath(__file__))

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        c_handler = logging.StreamHandler()
        f_handler = logging.FileHandler(os.path.join(self.dir_name, "asvz.log"))

        # Create formatters and add it to handlers
        c_format = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
        f_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        c_handler.setFormatter(c_format)
        f_handler.setFormatter(f_format)

        # Add handlers to the logger
        self.logger.addHandler(c_handler)
        self.logger.addHandler(f_handler)

    def _login(self, username, password):
        self.logger.debug("trying to log in")
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.NAME, "provider"))
        ).click()
        self.driver.find_element(By.ID, "userIdPSelection_iddicon").click()
        self.driver.find_element(
            By.XPATH, "//div[@title='Universities: ETH Zurich']"
        ).click()

        if username and password:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "username"))
            ).send_keys(username)
            self.driver.find_element(By.ID, "password").send_keys(password)
            self.driver.find_element(By.XPATH, "//button[@type='submit']").click()
        self.logger.debug("login successful")

    def _enroll(self):
        self.logger.debug("enroll in lesson")
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//button[@id='btnRegister']"))
        )
        enrollment_elem = self.driver.find_element(
            By.XPATH,
            "//app-lesson-properties-display/dl/dt[text()='Anmeldezeitraum']/following-sibling::dd",
        )
        matcher = re.search(r"\d+.\d+.\d+\s\d+:\d+", enrollment_elem.text)
        enrollment_time =  datetime.datetime.strptime(matcher.group(0), "%d.%m.%Y %H:%M")
        if enrollment_time - datetime.datetime.now() > datetime.timedelta(minutes=10):
            self.logger.error("Cannot enroll in lesson more than 10 minutes before enrollment starts")
            sys.exit("Please start script with -c flag to generate a cronjob")

        self.logger.debug("wait until enrollment is open")
        while enrollment_time > datetime.datetime.now():
            pass

        # self.driver.find_element(By.XPATH, "//button[@id='btnRegister']").click()

        status = (
            WebDriverWait(self.driver, 60)
            .until(
                EC.presence_of_element_located(
                    (By.XPATH, "//app-lessons-enrollment-button//alert")
                ),
                "no response from server received",
            )
            .get_attribute("type")
        )

        if status == "success":
            self.logger.info("successfully enrolled in lesson")
        else:
            self.logger.error("something went wrong, please check the status of your enrollment (status: {})".format(status))

    def _load_credentials(self, credentials_file):
        file_path = os.path.join(os.path.dirname(__file__), credentials_file)
        yaml_file = open(file_path, "r")
        yaml_content = yaml.safe_load(yaml_file)
        return yaml_content.get("username"), yaml_content.get("password")

    def register_for_lesson(self, lesson_id, credentials_file="credentials.yml"):
        username, password = self._load_credentials(credentials_file)

        if not self.interactive and not (username and password):
            sys.exit(
                "If not in interactive mode, a username and password need to be provided"
            )

        try:
            lesson_url = "https://schalter.asvz.ch/tn/lessons/{}".format(lesson_id)
            self.driver.get(lesson_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//app-lessons-enrollment-button/button")
                )
            ).click()
            self._login(username, password)
            self._enroll()

        except Exception as e:
            self.logger.error(e)
        finally:
            self.driver.close()

    def get_enrollment_time(self, lesson_id):
        lesson_url = "https://schalter.asvz.ch/tn/lessons/{}".format(lesson_id)
        self.driver.get(lesson_url)
        enrollment_elem = self.driver.find_element(
            By.XPATH,
            "//app-lesson-properties-display/dl/dt[text()='Anmeldezeitraum']/following-sibling::dd",
        )
        matcher = re.search(r"\d+.\d+.\d+\s\d+:\d+", enrollment_elem.text)
        return datetime.datetime.strptime(matcher.group(0), "%d.%m.%Y %H:%M")

    def generate_cronjob(self, lesson_id):
        enrollment_time = self.get_enrollment_time(lesson_id)

        cron = CronTab(user=True)
        start_time = enrollment_time + datetime.timedelta(minutes=-3)

        python_path = os.path.join(self.dir_name, ".env/bin/python3")
        asvz_path = os.path.join(self.dir_name, "asvz.py")

        job = cron.new(command=" ".join(python_path, asvz_path, lesson_id))
        job.setall(start_time)
        cron.write()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ASVZ automatic lesson registration")

    parser.add_argument(
        "lesson_id",
        type=int,
        help="ID of a particular lesson e.g. 200949 in https://schalter.asvz.ch/tn/lessons/200949",
    )

    parser.add_argument(
        "-i", "--interactive", action="store_true", help="Start bot in interactive mode"
    )

    parser.add_argument(
        "-c", "--crontab", action="store_true", help="Create a cronjob to enroll"
    )

    args = parser.parse_args()
    asvz_enroller = ASVZ(args.interactive)

    if args.crontab:
        asvz_enroller.generate_cronjob(args.lesson_id)
    else:
        asvz_enroller.register_for_lesson(args.lesson_id)
