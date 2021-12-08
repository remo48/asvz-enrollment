import os, sys
import time
import uuid
import json
from datetime import datetime, timedelta
from urllib import parse
from crontab import CronTab
from dateutil.parser import parse

import argparse
import logging
import requests
import yaml

QUERY_PARAMS = {
    "client_id": "55776bff-ef75-4c9d-9bdd-45e883ec38e0",
    "scope": "openid profile tn-api tn-apiext tn-auth tn-hangfire",
    "response_type": "id_token token",
}


def wait_until(timestamp):
    end = timestamp

    if isinstance(timestamp, datetime):
        end = timestamp.timestamp()
    elif not isinstance(timestamp, (int, float)):
        raise AttributeError(
            "The timestamp parameter is not a number or datetime object"
        )

    while True:
        diff = end - time.time()
        if diff <= 0:
            break
        else:
            time.sleep(diff / 2)


class ASVZ:
    def __init__(self, credentials_file, timeout=3600, frequency=1) -> None:
        self.id_token = None
        self.access_token = None
        self.expires = None

        self.max_retry = 2
        self.login_retry = 0

        self.timeout = timeout
        self.frequency = frequency

        current_dir = os.path.dirname(os.path.abspath(__file__))
        log_file = os.path.join(current_dir, "asvz.log")
        self.credentials_file = os.path.join(current_dir, credentials_file)

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        c_handler = logging.StreamHandler()
        c_handler.setLevel(logging.DEBUG)
        f_handler = logging.FileHandler(log_file)
        f_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        c_handler.setFormatter(formatter)
        f_handler.setFormatter(formatter)
        self.logger.addHandler(c_handler)
        self.logger.addHandler(f_handler)

        self.session = requests.Session()

        if not self._load_identity():
            self.logger.error(
                "Could not load identity token. Please provide a valid credentials file"
            )
            sys.exit()

        self._refresh_access_token()

    def poll_enrollment_possible(self, lesson_id):
        data = self._get_lesson_status(lesson_id)
        enrollment_from, enrollment_until = self._extract_enrollment_time(data)

        current_time = datetime.now()

        if not enrollment_from <= current_time <= enrollment_until:
            return False
        end_time = min(current_time + timedelta(seconds=self.timeout), enrollment_until)

        while datetime.now() < end_time:
            data = self._get_lesson_status(lesson_id)

            if data["participantsMax"] > data["participantCount"]:
                return True
            time.sleep(self.frequency)

        return False

    def enroll(self, lesson_id):
        data = self._get_lesson_status(lesson_id)
        available_places = data["participantsMax"] - data["participantCount"]
        enrollment_from, enrollment_until = self._extract_enrollment_time(data)
        current_time = datetime.now()
        if current_time > enrollment_until:
            self.logger.error("Enrollment period over")
            return
        elif current_time >= enrollment_from and available_places > 0:
            self._enroll_internal(lesson_id)
            return
        elif current_time >= enrollment_from and available_places == 0:
            if self.poll_enrollment_possible(lesson_id):
                self._enroll_internal(lesson_id)
            else:
                self.logger.warning(
                    "There are no places available. Please restart script"
                )
        elif enrollment_from - current_time <= timedelta(minutes=10):
            wait_until(enrollment_from)
            self._enroll_internal(lesson_id)
        else:
            self._create_cronjob(lesson_id, enrollment_from)

    def get_profile_information(self):
        if not self.access_token:
            self._refresh_access_token()

        url = "https://schalter.asvz.ch/tn-api/api/MemberPerson"
        bearer = "Bearer {}".format(self.access_token)
        headers = {"Authorization": bearer}
        res = self.session.get(url, headers=headers)
        res_json = res.json()
        if res.status_code == 200:
            return res_json
        else:
            return None

    def _create_cronjob(self, lesson_id, enrollment_from):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        cron = CronTab(user=True)
        start_time = enrollment_from + timedelta(minutes=-2)

        python_path = os.path.join(current_dir, ".env/bin/python3")
        job = cron.new(
            command=" ".join([python_path, os.path.abspath(__file__), str(lesson_id)]),
            comment=str(lesson_id),
        )
        job.setall(start_time)
        cron.write()

    def _cleanup_crontab(self, lesson_id):
        cron = CronTab(user=True)
        cron.remove_all(comment=str(lesson_id))

    def _enroll_internal(self, lesson_id):
        if not self.access_token or datetime.now() > self.expires:
            self._refresh_access_token()

        url = "https://schalter.asvz.ch/tn-api/api/Lessons/{}/enroll".format(lesson_id)
        bearer = "Bearer {}".format(self.access_token)
        headers = {"Authorization": bearer}
        res = self.session.post(url, headers=headers)
        res_json = res.json()

        if res.status_code == 201:
            self.logger.info(
                "Einschreibung erfolgreich, Platz-Nr. %d",
                res_json["data"]["placeNumber"],
            )
            self._cleanup_crontab(lesson_id)
        elif res.status_code == 401:
            self.logger.warning("Login ungültig - wird aktualisiert")
            self._refresh_access_token()
            self.enroll(lesson_id)
        else:
            self.logger.error("Einschreibung fehlgeschlagen: %s", json.dumps(res_json))

    def _refresh_access_token(self):
        base_url = "https://auth.asvz.ch/connect/authorize"
        nonce = uuid.uuid4().hex
        state = uuid.uuid4().hex
        params = {
            **QUERY_PARAMS,
            "redirect_uri": "https://schalter.asvz.ch/tn/assets/silent-redirect.html",
            "nonce": nonce,
            "state": state,
        }

        if self.id_token:
            params.update({"prompt": "none", "id_token_hint": self.id_token})

        res = self.session.get(base_url, params=params, allow_redirects=False)
        location = res.headers["Location"]
        res_params = dict(parse.parse_qsl(parse.urlsplit(location).fragment))
        self.id_token = res_params.get("id_token")
        self.access_token = res_params.get("access_token")
        if not self.access_token:
            self.logger.error("Unable to log in. Retrying...")
            if self.login_retry >= self.max_retry:
                self.logger.error(
                    "Max retries exceeded. Please check validity of provided identity token."
                )
                sys.exit()
            self.login_retry += 1
            self._refresh_access_token()
        else:
            self.login_retry = 0
        self.expires = datetime.now() + timedelta(seconds=int(res_params["expires_in"]))

    def _get_lesson_status(self, lesson_id):
        url = "https://schalter.asvz.ch/tn-api/api/Lessons/{}".format(lesson_id)
        self.logger.debug("GET %s", url)
        try:
            r = requests.get(url, timeout=2)
        except:
            self.logger.warning("something went wrong during polling")
            return None
        self.logger.debug("Response %d", r.status_code)
        if r.status_code != requests.codes.ok:
            return None

        data = r.json()["data"]
        return data

    def _extract_enrollment_time(self, data):
        enrollment_from = parse(data["enrollmentFrom"]).replace(tzinfo=None)
        enrollment_until = parse(data["enrollmentUntil"]).replace(tzinfo=None)
        return enrollment_from, enrollment_until

    def _load_identity(self):
        try:
            with open(self.credentials_file, "r") as f:
                yaml_content = yaml.safe_load(f)
                identity = yaml_content.get("identity")
        except FileNotFoundError:
            self.logger.error("Could not open file %s", self.credentials_file)

        if identity:
            self.session.cookies.set(
                ".AspNetCore.Identity.Application",
                identity,
                domain="auth.asvz.ch",
                secure=True,
            )
            return True

        return False

    def _update_identity(self):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ASVZ automatic lesson registration")

    parser.add_argument(
        "lesson_id",
        nargs='?',
        type=int,
        help="ID of a particular lesson e.g. 200949 in https://schalter.asvz.ch/tn/lessons/200949",
    )

    parser.add_argument(
        "-c",
        "--credentials",
        default="credentials.yml",
        help="Credentials file",
    )

    parser.add_argument(
        "-t",
        "--timeout",
        default=3600,
        type=int,
        help="Timeout(s) until polling of lesson status is stopped",
    )

    parser.add_argument(
        "-f",
        "--frequency",
        default=1,
        type=float,
        help="Time(s) between lesson status requests",
    )

    parser.add_argument(
        "--test",
        action='store_true',
        help="Test if everything is set up correct"
    )

    args = parser.parse_args()
    lesson_id = args.lesson_id

    asvz = ASVZ(
        credentials_file=args.credentials,
        timeout=args.timeout,
        frequency=args.frequency,
    )

    if args.test:
        profile_data = asvz.get_profile_information()
        if profile_data:
            print("Login erfolgreich: ({} {}, {})".format(profile_data['firstName'], profile_data['lastName'], profile_data['emailPrivate']))
        else:
            print("Irgendetwas scheint nicht zu funktionieren. Überprüfe, ob die Credentials korrekt gesetzt sind")
    elif lesson_id:
        asvz.enroll(lesson_id)
    else:
        parser.print_help()
