# ASVZ Enrollment bot
This script allows you to automatically enroll in your ASVZ lesson

## Installation
You need to install the following:
- [Python 3](https://www.python.org/downloads/)
- Chrome or Chromium
- Chromedriver ([Chrome](https://sites.google.com/a/chromium.org/chromedriver/downloads) or [Chromium](https://chromedriver.chromium.org/downloads))

After downloading you need to install the required Packages:
> If you want to automatically create cron jobs, the following steps must be executed 
```bash
python3 -m pip install venv
python3 -m venv .env
source .env/bin/activate
python3 -m pip install -r requirements.txt
```

## Usage
```bash
python3 main.py LESSON_ID -u USERNAME -p PASSWORD
```
