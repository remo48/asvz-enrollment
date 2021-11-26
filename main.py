import os
import time
import uuid
import json
from datetime import datetime, timedelta
from urllib import parse

import argparse
import logging
import requests
import yaml

QUERY_PARAMS = {
    'client_id': '55776bff-ef75-4c9d-9bdd-45e883ec38e0',
    'scope': 'openid profile tn-api tn-apiext tn-auth tn-hangfire',
    'response_type': 'id_token token'
}


class ASVZ:
    def __init__(self, credentials_file='credentials.yml') -> None:
        self.id_token = None
        self.access_token = None
        self.expires = None

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        c_handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s')
        c_handler.setFormatter(formatter)
        self.logger.addHandler(c_handler)

        self.session = requests.Session()

        self._load_identity(credentials_file)

    def poll_enrollment_possible(self, lesson_id, timeout, frequeny):
        data = self._get_lesson_status(lesson_id)
        enrollment_from = datetime.strptime(
            data['enrollmentFrom'], '%Y-%m-%dT%H:%M:%S%z').replace(tzinfo=None)  # requires python >= 3.7
        enrollment_until = datetime.strptime(
            data['enrollmentUntil'], '%Y-%m-%dT%H:%M:%S%z').replace(tzinfo=None)

        current_time = datetime.now()

        if not enrollment_from <= current_time <= enrollment_until:
            return False
        end_time = min(
            current_time + timedelta(seconds=timeout), enrollment_until)

        while datetime.now() < end_time:
            data = self._get_lesson_status(lesson_id)
            if not data:
                continue

            if data['participantsMax'] > data['participantCount']:
                return True
            time.sleep(frequeny)

        return False

    def enroll(self, lesson_id):
        if not self.access_token or datetime.now() > self.expires:
            self._refresh_access_token()

        url = "https://schalter.asvz.ch/tn-api/api/Lessons/{}/enroll".format(
            lesson_id)
        bearer = 'Bearer {}'.format(self.access_token)
        headers = {'Authorization': bearer}
        res = self.session.post(url, headers=headers)
        res_json = res.json()

        if res.status_code == 201:
            self.logger.info("Einschreibung erfolgreich, Platz-Nr. %d", res_json['data']['placeNumber'])
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
            'redirect_uri': 'https://schalter.asvz.ch/tn/assets/silent-redirect.html',
            'nonce': nonce,
            'state': state,
        }

        if self.id_token:
            params.update({
                'prompt': 'none',
                'id_token_hint': self.id_token
            })

        res = self.session.get(base_url, params=params, allow_redirects=False)
        location = res.headers['Location']
        res_params = dict(parse.parse_qsl(parse.urlsplit(location).fragment))
        self.id_token = res_params['id_token']
        self.access_token = res_params['access_token']
        self.expires = datetime.now() + timedelta(seconds=int(res_params['expires_in']))

    def _get_lesson_status(self, lesson_id):
        url = 'https://schalter.asvz.ch/tn-api/api/Lessons/{}'.format(
            lesson_id)
        self.logger.debug("GET %s", url)
        try:
            r = requests.get(url, timeout=2)
        except:
            self.logger.warning("something went wrong during polling")
            return None
        self.logger.debug("Response %d", r.status_code)
        if r.status_code != requests.codes.ok:
            return None

        data = r.json()['data']
        return data

    def _load_identity(self, credentials_file):
        file_path = os.path.join(os.path.dirname(__file__), credentials_file)
        yaml_file = open(file_path, "r")
        yaml_content = yaml.safe_load(yaml_file)
        identity = yaml_content.get('identity')
        if identity:
            self.session.cookies.set(
                '.AspNetCore.Identity.Application', identity, domain='auth.asvz.ch', secure=True)
            return True

        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="ASVZ automatic lesson registration")

    parser.add_argument(
        "lesson_id",
        type=int,
        help="ID of a particular lesson e.g. 200949 in https://schalter.asvz.ch/tn/lessons/200949",
    )

    args = parser.parse_args()
    lesson_id = args.lesson_id

    asvz = ASVZ()

    asvz._refresh_access_token()

    if (asvz.poll_enrollment_possible(lesson_id, 3600, 1)):
        asvz.enroll(lesson_id)

