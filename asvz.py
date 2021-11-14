import argparse
import datetime
import re
import os, sys
import yaml

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

    def _login(self, username, password):
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

    def _enroll(self):
        WebDriverWait(self.driver, 5 * 60).until(
            EC.element_to_be_clickable((By.XPATH, "//button[@id='btnRegister']"))
        ).click()

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
            print("successfully enrolled in lesson")
        else:
            print("something went wrong, please check the status of your enrollment")

    def _load_credentials(self, credentials_path):
        yaml_file = open(credentials_path, "r")
        yaml_content = yaml.safe_load(yaml_file)
        return yaml_content.get("username"), yaml_content.get("password")

    def register_for_lesson(self, lesson_id, credentials_path="credentials.yml"):
        username, password = self._load_credentials(credentials_path)

        if not self.interactive and not (username and password):
            sys.exit(
                "If not in interactive mode, a username and password need to be provided"
            )

        try:
            lesson_url = f"https://schalter.asvz.ch/tn/lessons/{lesson_id}"
            self.driver.get(lesson_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//app-lessons-enrollment-button/button")
                )
            ).click()
            self._login(username, password)
            self._enroll()

        except Exception as e:
            print(e)
        finally:
            self.driver.close()

    def get_enrollment_time(self, lesson_id):
        lesson_url = f"https://schalter.asvz.ch/tn/lessons/{lesson_id}"
        self.driver.get(lesson_url)
        enrollment_elem = self.driver.find_element(
            By.XPATH,
            "//app-lesson-properties-display/dl/dt[text()='Anmeldezeitraum']/following-sibling::dd",
        )
        matcher = re.search(r"\d+.\d+.\d+\s\d+:\d+", enrollment_elem)
        return datetime.datetime.strptime(matcher.group(0), "%d.%m.%Y %H:%M")

    def generate_cronjob(self, lesson_id):
        enrollment_time = self.get_enrollment_time(lesson_id)

        cron = CronTab(user=True)
        start_time = enrollment_time + datetime.timedelta(minutes=-3)

        dir_name = os.path.dirname(os.path.abspath(__file__))
        python_path = os.path.join(dir_name, ".env/bin/python3")
        asvz_path = os.path.join(dir_name, "asvz.py")

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
