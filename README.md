# ASVZ Enrollment bot
This script allows you to automatically enroll in your ASVZ lesson

> **_Note:_** This script is not maintained regularly. It may need some adaptations to be compatible with the latest version of the asvz api. Please reach out to me, if something needs to be changed. 

## Installation
You need to install the following:
- [Python 3](https://www.python.org/downloads/)

After downloading you need to install the required Packages:
```bash
python3 -m pip install venv
python3 -m venv .env
source .env/bin/activate
python3 -m pip install -r requirements.txt
```

## Usage
Before using the script, make sure you store your identity cookie in the file ```credentials.yml```. This is needed to authenticate against the asvz api.

If you want to test if everything is set up correct, run the script with ```--test```
```bash
python3 main.py --test
```

To start the enrollment, provide the lesson id for the desired lesson to the script
> if the enrollment is not yet open and the enrollment time is more than 10 minutes in the future, the script schedules a cronjob. This is currently only supported on unix like operating systems
```bash
python3 main.py LESSON_ID
```

If the enrollment is already open but no places are left, the script can poll the lesson status and submit your enrollment as soon as there is a place left. Per default the script is configured to poll the server every second for an hour. You can specify polling frequency and timeout.

For example
```bash
python3 main.py 200949 -t 7200 -f 2
```
polls the server for available places every two seconds for two hours.
