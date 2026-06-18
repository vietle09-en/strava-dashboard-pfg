# Strava Dashboard PFG

Open-source Strava dashboard workflow for community sports challenges.

This project helps organizers collect Strava activities, validate activity rules, detect duplicates, calculate leaderboards, and publish results to Google Sheets or Looker Studio.

## Features

- Collect Strava activities from authorized athletes
- Support Strava OAuth workflow
- Filter activities by challenge date range
- Separate Run and Ride activities
- Validate Run distance and pace rules
- Validate Ride distance and speed rules
- Detect duplicate activities
- Store local data in SQLite
- Upload processed data to Google Sheets
- Build leaderboard data for dashboards

## Use case

This project is designed for:

- Company sports challenges
- Community running and cycling events
- Internal fitness campaigns
- Strava-based leaderboard dashboards

## Tech stack

- Python
- Strava API
- SQLite
- Google Sheets API
- Google Apps Script
- Looker Studio

## Security notice

Do not commit real tokens, API credentials, client secrets, service account files, or local databases.

Use `.env.example` as a template and keep real credentials private.

## Project status

This project is under active development.

## License

MIT License
