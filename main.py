import argparse
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By


class ASVZ:
    def __init__(self, username=None, password=None) -> None:
        opts = Options()
        if username and password:
            opts.headless = True
        opts.add_argument("--lang=en")
        self.driver = Chrome(options=opts)

        self.username = username
        self.password = password

    def _login(self):
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.NAME, "provider"))
        ).click()
        self.driver.find_element(By.ID, "userIdPSelection_iddicon").click()
        self.driver.find_element(
            By.XPATH, "//div[@title='Universities: ETH Zurich']"
        ).click()

        if self.username and self.password:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "username"))
            ).send_keys(self.username)
            self.driver.find_element(By.ID, "password").send_keys(
                self.password
            ).submit()

    def _enroll(self):
        WebDriverWait(self.driver, 5 * 60).until(
            EC.element_to_be_clickable((By.XPATH, "//button[@id='btnRegister']"))
        ).click()

        status = (
            WebDriverWait(self.driver, 60)
            .until(
                EC.presence_of_element_located((By.CLASS_NAME, "alert")),
                "no response from server received",
            )
            .get_attribute("type")
        )
        if status == "success":
            print("successfully enrolled in lesson")
        else:
            print("something went wrong, please check the status of your enrollment")

    def register_for_lesson(self, lesson_id):
        try:
            lesson_url = f"https://schalter.asvz.ch/tn/lessons/{lesson_id}"
            self.driver.get(lesson_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//app-lessons-enrollment-button/button")
                )
            ).click()
            self._login()
            self._enroll()

        except Exception as e:
            print(e)
            self.driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ASVZ automatic lesson registration")

    parser.add_argument(
        "lesson_id",
        type=int,
        help="ID of a particular lesson e.g. 200949 in https://schalter.asvz.ch/tn/lessons/200949",
    )

    parser.add_argument("-u", "--username", type=str, help="Organisation username")
    parser.add_argument("-p", "--password", type=str, help="Organisation password")

    args = parser.parse_args()
    asvz_enroller = ASVZ(args.username, args.password)
    asvz_enroller.register_for_lesson(args.lesson_id)
