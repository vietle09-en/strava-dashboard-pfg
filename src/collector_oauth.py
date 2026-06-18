import json
import sqlite3
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

# =========================
# CONFIG
# =========================
APP_TOKEN_FILE = r"F:\strava\token.json"
ATHLETE_TOKENS_FILE = r"F:\strava\athlete_tokens.json"
DB_FILE = r"F:\strava\activities.db"

CHALLENGE_START = "2026-05-30 00:00:00"
CHALLENGE_END = "2026-07-20 23:59:59"
TIMEZONE = "Asia/Ho_Chi_Minh"

SPORTS_ALLOWED = {"Run", "Ride"}
PER_PAGE = 100
MAX_PAGES = 20


def to_epoch_vietnam(dt_text: str) -> int:
    dt = datetime.strptime(dt_text, "%Y-%m-%d %H:%M:%S")
    dt = dt.replace(tzinfo=ZoneInfo(TIMEZONE))
    return int(dt.timestamp())


def now_vietnam() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")


def load_app_config():
    with open(APP_TOKEN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_athlete_tokens():
    with open(ATHLETE_TOKENS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_athlete_tokens(tokens):
    with open(ATHLETE_TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2, ensure_ascii=False)


def refresh_athlete_token(app_config, athlete_item):
    response = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": app_config["client_id"],
            "client_secret": app_config["client_secret"],
            "refresh_token": athlete_item["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=30,
    )

    response.raise_for_status()
    data = response.json()

    athlete_item["access_token"] = data["access_token"]
    athlete_item["refresh_token"] = data["refresh_token"]
    athlete_item["expires_at"] = data["expires_at"]

    return data["access_token"]


def connect_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS activities (
        activity_id TEXT PRIMARY KEY,
        strava_activity_id TEXT,
        athlete_id TEXT,
        athlete TEXT,
        type TEXT,
        sport_type TEXT,
        distance REAL,
        moving_time INTEGER,
        elapsed_time INTEGER,
        pace_min_per_km REAL,
        speed_kmh REAL,
        status TEXT,
        note TEXT,
        activity_name TEXT,
        start_date TEXT,
        start_date_local TEXT,
        activity_date TEXT,
        activity_time TEXT,
        vietnam_time TEXT,
        first_seen_at TEXT,
        last_seen_at TEXT,
        source TEXT
    )
    """)

    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(activities)")}

    extra_columns = {
        "strava_activity_id": "TEXT",
        "athlete_id": "TEXT",
        "sport_type": "TEXT",
        "elapsed_time": "INTEGER",
        "start_date_local": "TEXT",
        "activity_date": "TEXT",
        "activity_time": "TEXT",
        "first_seen_at": "TEXT",
        "last_seen_at": "TEXT",
        "source": "TEXT",
    }

    for col, col_type in extra_columns.items():
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE activities ADD COLUMN {col} {col_type}")

    conn.commit()
    return conn


def validate_activity(activity_type, distance_km, moving_time):
    pace_min_per_km = None
    speed_kmh = None
    status = "VALID"
    note = "OK"

    if activity_type == "Run":
        if distance_km > 0:
            pace_min_per_km = round((moving_time / 60) / distance_km, 2)

        if distance_km < 1:
            status, note = "INVALID", "Run dưới 1km"
        elif pace_min_per_km is not None and pace_min_per_km < 4:
            status, note = "INVALID", "Pace quá nhanh"
        elif pace_min_per_km is not None and pace_min_per_km > 13:
            status, note = "INVALID", "Pace quá chậm"

    elif activity_type == "Ride":
        if moving_time > 0:
            speed_kmh = round(distance_km / (moving_time / 3600), 2)

        if distance_km < 3:
            status, note = "INVALID", "Ride dưới 3km"
        elif speed_kmh is not None and speed_kmh < 10:
            status, note = "INVALID", "Speed quá thấp"
        elif speed_kmh is not None and speed_kmh > 27:
            status, note = "INVALID", "Speed quá cao"

    return pace_min_per_km, speed_kmh, status, note


def parse_start_date_local(value):
    if not value:
        return "", "", ""

    # Strava thường trả dạng: 2026-05-30T05:12:34Z
    cleaned = value.replace("T", " ").replace("Z", "")
    activity_date = cleaned[:10]
    activity_time = cleaned[11:19] if len(cleaned) >= 19 else ""

    return cleaned, activity_date, activity_time


def fetch_athlete_activities(access_token, after_epoch, before_epoch):
    headers = {"Authorization": f"Bearer {access_token}"}

    for page in range(1, MAX_PAGES + 1):
        response = requests.get(
            "https://www.strava.com/api/v3/athlete/activities",
            headers=headers,
            params={
                "after": after_epoch,
                "before": before_epoch,
                "page": page,
                "per_page": PER_PAGE,
            },
            timeout=30,
        )

        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list):
            raise RuntimeError(f"API trả về không phải list: {data}")

        if not data:
            break

        print(f"  Page {page}: {len(data)} activities")
        yield from data

        if len(data) < PER_PAGE:
            break


def main():
    scan_time = now_vietnam()
    after_epoch = to_epoch_vietnam(CHALLENGE_START)
    before_epoch = to_epoch_vietnam(CHALLENGE_END)

    app_config = load_app_config()
    athlete_tokens = load_athlete_tokens()

    if not athlete_tokens:
        raise SystemExit("Chưa có VĐV nào trong athlete_tokens.json")

    conn = connect_db()
    cursor = conn.cursor()

    total_inserted = 0
    total_updated = 0
    total_ignored_sport = 0
    total_ignored_date = 0

    for index, athlete_item in enumerate(athlete_tokens, start=1):
        athlete_id = str(athlete_item.get("athlete_id"))
        athlete_name = athlete_item.get("athlete_name", "")

        print("\n====================================")
        print(f"[{index}/{len(athlete_tokens)}] Đồng bộ: {athlete_name} ({athlete_id})")

        access_token = refresh_athlete_token(app_config, athlete_item)

        inserted = 0
        updated = 0
        ignored_sport = 0
        ignored_date = 0

        for act in fetch_athlete_activities(access_token, after_epoch, before_epoch):
            activity_type = act.get("type")
            sport_type = act.get("sport_type", activity_type)

            if activity_type not in SPORTS_ALLOWED:
                ignored_sport += 1
                continue

            strava_activity_id = str(act.get("id", ""))
            if not strava_activity_id:
                continue

            start_date = act.get("start_date", "")
            start_date_local_raw = act.get("start_date_local", "")
            start_date_local, activity_date, activity_time = parse_start_date_local(start_date_local_raw)

            # Chốt cứng: nếu vì lý do nào đó API trả ngoài khoảng ngày giải thì bỏ.
            if start_date_local < CHALLENGE_START or start_date_local > CHALLENGE_END:
                ignored_date += 1
                continue

            activity_name = act.get("name", "")
            distance_km = round(float(act.get("distance", 0) or 0) / 1000, 2)
            moving_time = int(act.get("moving_time", 0) or 0)
            elapsed_time = int(act.get("elapsed_time", 0) or 0)

            pace, speed, status, note = validate_activity(activity_type, distance_km, moving_time)

            activity_id = strava_activity_id

            cursor.execute(
                "SELECT 1 FROM activities WHERE activity_id = ?",
                (activity_id,)
            )
            exists = cursor.fetchone() is not None

            cursor.execute("""
            INSERT INTO activities (
                activity_id,
                strava_activity_id,
                athlete_id,
                athlete,
                type,
                sport_type,
                distance,
                moving_time,
                elapsed_time,
                pace_min_per_km,
                speed_kmh,
                status,
                note,
                activity_name,
                start_date,
                start_date_local,
                activity_date,
                activity_time,
                vietnam_time,
                first_seen_at,
                last_seen_at,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(activity_id) DO UPDATE SET
                strava_activity_id = excluded.strava_activity_id,
                athlete_id = excluded.athlete_id,
                athlete = excluded.athlete,
                type = excluded.type,
                sport_type = excluded.sport_type,
                distance = excluded.distance,
                moving_time = excluded.moving_time,
                elapsed_time = excluded.elapsed_time,
                pace_min_per_km = excluded.pace_min_per_km,
                speed_kmh = excluded.speed_kmh,
                status = excluded.status,
                note = excluded.note,
                activity_name = excluded.activity_name,
                start_date = excluded.start_date,
                start_date_local = excluded.start_date_local,
                activity_date = excluded.activity_date,
                activity_time = excluded.activity_time,
                vietnam_time = excluded.vietnam_time,
                last_seen_at = excluded.last_seen_at,
                source = excluded.source
            """, (
                activity_id,
                strava_activity_id,
                athlete_id,
                athlete_name,
                activity_type,
                sport_type,
                distance_km,
                moving_time,
                elapsed_time,
                pace,
                speed,
                status,
                note,
                activity_name,
                start_date,
                start_date_local,
                activity_date,
                activity_time,
                scan_time,
                scan_time,
                scan_time,
                "athlete_oauth",
            ))

            if exists:
                updated += 1
            else:
                inserted += 1

        conn.commit()

        total_inserted += inserted
        total_updated += updated
        total_ignored_sport += ignored_sport
        total_ignored_date += ignored_date

        print(f"  Lưu mới: {inserted}")
        print(f"  Cập nhật: {updated}")
        print(f"  Bỏ qua môn khác: {ignored_sport}")
        print(f"  Bỏ qua ngoài ngày giải: {ignored_date}")

        # Tránh gọi API quá dồn dập
        time.sleep(1)

    save_athlete_tokens(athlete_tokens)

    conn.close()

    print("\n====================================")
    print("HOÀN TẤT ĐỒNG BỘ OAUTH")
    print(f"Tổng lưu mới: {total_inserted}")
    print(f"Tổng cập nhật: {total_updated}")
    print(f"Tổng bỏ qua môn khác: {total_ignored_sport}")
    print(f"Tổng bỏ qua ngoài ngày giải: {total_ignored_date}")
    print(f"Thời điểm quét: {scan_time}")


if __name__ == "__main__":
    main()