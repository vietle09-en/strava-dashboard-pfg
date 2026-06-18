import sqlite3
import pandas as pd
import gspread

from google.oauth2.service_account import Credentials

# =========================
# GOOGLE AUTH
# =========================

SERVICE_ACCOUNT_FILE = "credentials.json"

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=scope
)

client = gspread.authorize(creds)

# =========================
# OPEN SHEET
# =========================

sheet = client.open(
    "Strava Club Dashboard"
)

# =========================
# SQLITE
# =========================

conn = sqlite3.connect(
    "activities.db"
)

# =========================
# DAILY RUN
# =========================

run_query = """

SELECT

    substr(vietnam_time, 1, 10) as date,

    athlete,

    ROUND(SUM(distance), 2) as total_run_km

FROM activities

WHERE type = 'Run'

AND status = 'VALID'

AND vietnam_time >= '2026-05-30 00:00:00'

AND vietnam_time <= '2026-07-20 23:59:59'

GROUP BY date, athlete

ORDER BY date ASC, total_run_km DESC

"""

run_df = pd.read_sql_query(
    run_query,
    conn
)

# =========================
# DAILY RIDE
# =========================

ride_query = """

SELECT

    substr(vietnam_time, 1, 10) as date,

    athlete,

    ROUND(SUM(distance), 2) as total_ride_km

FROM activities

WHERE type = 'Ride'

AND status = 'VALID'

AND vietnam_time >= '2026-05-30 00:00:00'

AND vietnam_time <= '2026-07-20 23:59:59'

GROUP BY date, athlete

ORDER BY date ASC, total_ride_km DESC

"""

ride_df = pd.read_sql_query(
    ride_query,
    conn
)

conn.close()

# =========================
# UPDATE DAILY RUN
# =========================

run_ws = sheet.worksheet(
    "Daily_Run"
)

run_ws.clear()

run_ws.update(
    [run_df.columns.values.tolist()] +
    run_df.values.tolist()
)

# =========================
# UPDATE DAILY RIDE
# =========================

ride_ws = sheet.worksheet(
    "Daily_Ride"
)

ride_ws.clear()

ride_ws.update(
    [ride_df.columns.values.tolist()] +
    ride_df.values.tolist()
)

print("Daily leaderboard updated")