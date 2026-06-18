# Setup Guide

## 1. Clone repository

```bash
git clone https://github.com/vietle09-en/strava-dashboard-pfg.git
cd strava-dashboard-pfg
```

## 2. Create Python virtual environment

```bash
python -m venv .venv
```

## 3. Activate environment

Windows:

```bash
.venv\Scripts\activate
```

## 4. Install dependencies

```bash
pip install -r requirements.txt
```

## 5. Configure environment

Copy `.env.example` to `.env` and update your own credentials.

```bash
copy .env.example .env
```

## 6. Run Strava OAuth server

```bash
python src/auth_server.py
```

## 7. Run collector

```bash
python src/collector_oauth.py
```

## 8. Upload data to Google Sheets

```bash
python src/upload_sheet_fixed.py
```

## 9. Generate leaderboard

```bash
python src/leaderboard_fixed.py
```

## Security notes

Do not commit real credentials, tokens, service account files, or local databases.

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
