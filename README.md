# Strava Dashboard PFG

Open-source Strava dashboard workflow for community sports challenges.

This project helps organizers collect Strava activities, validate activity rules, detect duplicate activities, calculate leaderboards, and publish results to Google Sheets or Looker Studio.

## Overview

Strava Dashboard PFG is designed for running and cycling challenges where participants authorize access through Strava OAuth. The system collects activity data, filters activities by challenge rules, stores processed records, and prepares leaderboard data for reporting dashboards.

The project can be used for company fitness campaigns, community sports events, internal running challenges, cycling challenges, and Strava-based leaderboard dashboards.

## Features

* Collect Strava activities from authorized athletes
* Support Strava OAuth authorization workflow
* Filter activities by challenge date range
* Separate Run and Ride activities
* Validate Run distance and pace rules
* Validate Ride distance and speed rules
* Detect duplicate activities
* Store local activity data in SQLite
* Generate Run and Ride leaderboards
* Upload processed data to Google Sheets
* Prepare data for Looker Studio dashboards
* Support daily summary and leaderboard reports

## Use Cases

This project is suitable for:

* Company sports challenges
* Community running and cycling events
* Internal fitness campaigns
* Strava-based leaderboard dashboards
* Charity fitness events
* Team activity tracking

## Tech Stack

* Python
* Strava API
* Strava OAuth
* SQLite
* Google Sheets API
* Google Apps Script
* Looker Studio

## Project Structure

```text
strava-dashboard-pfg/
│
├── docs/
│   └── setup.md
│
├── src/
│   ├── auth_server.py
│   ├── collector_oauth.py
│   ├── upload_sheet_fixed.py
│   ├── leaderboard_fixed.py
│   ├── daily_leaderboard.py
│   ├── check_count.py
│   ├── check_dates.py
│   └── check_duplicate.py
│
├── .env.example
├── .gitignore
├── LICENSE
├── README.md
└── requirements.txt
```

## Installation

Clone the repository:

```bash
git clone https://github.com/vietle09-en/strava-dashboard-pfg.git
cd strava-dashboard-pfg
```

Create a Python virtual environment:

```bash
python -m venv .venv
```

Activate the virtual environment on Windows:

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Copy the environment example file:

```bash
copy .env.example .env
```

Update `.env` with your own credentials and configuration:

```env
STRAVA_CLIENT_ID=your_strava_client_id
STRAVA_CLIENT_SECRET=your_strava_client_secret
STRAVA_REDIRECT_URI=https://your-domain.com/strava/callback

GOOGLE_SHEET_ID=your_google_sheet_id
GOOGLE_SERVICE_ACCOUNT_FILE=credentials.json

CHALLENGE_START_DATE=2026-05-30
CHALLENGE_END_DATE=2026-07-20
TIMEZONE=Asia/Ho_Chi_Minh
```

## Basic Usage

Start the Strava OAuth server:

```bash
python src/auth_server.py
```

Run the Strava activity collector:

```bash
python src/collector_oauth.py
```

Upload processed data to Google Sheets:

```bash
python src/upload_sheet_fixed.py
```

Generate leaderboard data:

```bash
python src/leaderboard_fixed.py
```

Generate daily leaderboard data:

```bash
python src/daily_leaderboard.py
```

## Activity Validation Rules

The project can be configured to validate activities based on challenge rules.

Example rules:

* Run activities must meet minimum distance requirements
* Run activities can be checked by pace range
* Ride activities must meet minimum distance requirements
* Ride activities can be checked by speed range
* Duplicate activities can be detected and excluded
* Activities outside the challenge date range can be ignored

## Security Notice

Do not commit real tokens, API credentials, client secrets, service account files, or local databases.

Never upload these files to a public repository:

```text
.env
token.json
client_secret.json
credentials.json
service_account.json
activities.db
*.db
*.sqlite
```

Use `.env.example` as a template and keep real credentials private.

## Documentation

Setup instructions are available in:

```text
docs/setup.md
```

## Project Status

This project is under active development.

Planned improvements may include:

* Improved dashboard templates
* Better documentation
* More configurable validation rules
* Automated scheduled collection
* Docker deployment
* Webhook support
* More detailed activity audit reports

## Contributing

Contributions, suggestions, and improvements are welcome.

You can contribute by:

* Improving documentation
* Reporting issues
* Suggesting new validation rules
* Improving Google Sheets integration
* Improving dashboard structure
* Adding deployment guides

## License

This project is licensed under the MIT License.

See the `LICENSE` file for details.


MIT License
