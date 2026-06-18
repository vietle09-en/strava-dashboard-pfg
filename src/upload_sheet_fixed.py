import math
import sqlite3
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials


# =========================
# CONFIG
# =========================
BASE_DIR = Path(r"F:\strava")
DB_FILE = BASE_DIR / "activities.db"
MEMBERS_FILE = BASE_DIR / "members.xlsx"

SPREADSHEET_NAME = "Strava Club Dashboard"

SERVICE_ACCOUNT_CANDIDATES = [
    BASE_DIR / "service_account.json",
    BASE_DIR / "credentials.json",
    BASE_DIR / "google_credentials.json",
    BASE_DIR / "strava-dashboard-pfg.json",
]


# =========================
# NORMALIZE HELPERS
# =========================
def remove_vietnamese_accents(text):
    if text is None:
        return ""
    text = str(text).strip()
    text = text.replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = " ".join(text.split())
    return text


def normalize_name(value):
    if pd.isna(value):
        return ""
    return remove_vietnamese_accents(value).lower().strip()


def normalize_sport(value):
    if pd.isna(value):
        return ""
    raw = str(value).strip()
    s = normalize_name(raw)
    run_values = {"run", "running", "chay", "chay bo", "di bo", "jogging"}
    ride_values = {"ride", "cycling", "bike", "bicycle", "dap", "dap xe", "xe dap"}
    if s in run_values:
        return "Run"
    if s in ride_values:
        return "Ride"
    return raw


def clean_athlete_id(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    if text.lower() in ["nan", "none", "nat", "<na>"]:
        return ""
    if text.endswith(".0"):
        text = text[:-2]
    return text


# =========================
# SAFE VALUE HELPERS
# =========================
def is_bad_value(value):
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return True
    if isinstance(value, np.floating) and (np.isnan(value) or np.isinf(value)):
        return True
    text = str(value).strip()
    if text in ["nan", "NaN", "NaT", "None", "<NA>", "inf", "-inf"]:
        return True
    return False


def safe_cell(value):
    if is_bad_value(value):
        return ""
    text = str(value).strip()
    if text in ["nan", "NaN", "NaT", "None", "<NA>", "inf", "-inf"]:
        return ""
    return text


def clean_dataframe_for_sheet(df):
    if df is None:
        return pd.DataFrame()
    df = df.copy()
    if df.empty:
        return df
    df = df.replace([np.inf, -np.inf], "")
    df = df.where(pd.notnull(df), "")
    for col in df.columns:
        df[col] = df[col].apply(safe_cell)
    return df


def dataframe_to_safe_values(df):
    df = clean_dataframe_for_sheet(df)
    headers = [safe_cell(col) for col in df.columns.tolist()]
    if df.empty:
        return [headers]
    values = [headers]
    for row in df.values.tolist():
        values.append([safe_cell(cell) for cell in row])
    return values


# =========================
# GOOGLE SHEET HELPERS
# =========================
def find_service_account_file():
    for file in SERVICE_ACCOUNT_CANDIDATES:
        if file.exists():
            return file
    raise FileNotFoundError(
        "Không tìm thấy file service account JSON trong F:\\strava. "
        "Cần có một trong các file: service_account.json, credentials.json, "
        "google_credentials.json, strava-dashboard-pfg.json"
    )


def connect_google_sheet():
    service_account_file = find_service_account_file()
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_file(service_account_file, scopes=scopes)
    client = gspread.authorize(credentials)
    spreadsheet = client.open(SPREADSHEET_NAME)
    return spreadsheet


def get_or_create_worksheet(spreadsheet, sheet_name, rows=1000, cols=30):
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=sheet_name, rows=rows, cols=cols)


def upload_dataframe(spreadsheet, sheet_name, df):
    df = clean_dataframe_for_sheet(df)
    worksheet = get_or_create_worksheet(
        spreadsheet,
        sheet_name,
        rows=max(len(df) + 10, 1000),
        cols=max(len(df.columns) + 5, 20),
    )
    worksheet.clear()
    values = dataframe_to_safe_values(df)
    worksheet.update(values)
    print(f"Đã upload {sheet_name}: {len(df)} dòng")


# =========================
# SQLITE HELPERS
# =========================
def table_exists(conn, table_name):
    cur = conn.cursor()
    cur.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name=?
        """, (table_name,))
    return cur.fetchone() is not None


def get_table_columns(conn, table_name):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cur.fetchall()]


def read_table_if_exists(conn, table_name):
    if not table_exists(conn, table_name):
        print(f"⚠️ Không tìm thấy bảng {table_name}, bỏ qua.")
        return pd.DataFrame()
    df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    return clean_dataframe_for_sheet(df)


# =========================
# MEMBERS
# =========================
def load_members():
    columns = [
        "athlete_id", "full_name", "gender", "sport", "sport_normalized",
        "strava_name", "strava_key", "id_match_key", "name_match_key",
        "id_only_key", "name_only_key",
    ]
    if not MEMBERS_FILE.exists():
        print(f"⚠️ Không tìm thấy members.xlsx: {MEMBERS_FILE}")
        return pd.DataFrame(columns=columns)
    excel = pd.ExcelFile(MEMBERS_FILE)
    if "members_clean" in excel.sheet_names:
        df = pd.read_excel(MEMBERS_FILE, sheet_name="members_clean", dtype=str).fillna("")
    else:
        df = pd.read_excel(MEMBERS_FILE, sheet_name=0, dtype=str).fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    for col in ["athlete_id", "full_name", "gender", "sport", "strava_name"]:
        if col not in df.columns:
            df[col] = ""
    df["athlete_id"] = df["athlete_id"].apply(clean_athlete_id)
    df["full_name"] = df["full_name"].astype(str).str.strip()
    df["gender"] = df["gender"].astype(str).str.strip()
    df["sport"] = df["sport"].astype(str).str.strip()
    df["strava_name"] = df["strava_name"].astype(str).str.strip()
    df["sport_normalized"] = df["sport"].apply(normalize_sport)
    df["strava_key"] = df["strava_name"].apply(normalize_name)
    df["id_match_key"] = df["athlete_id"] + "||" + df["sport_normalized"]
    df["name_match_key"] = df["strava_key"] + "||" + df["sport_normalized"]
    df["id_only_key"] = df["athlete_id"]
    df["name_only_key"] = df["strava_key"]
    df = df[df["full_name"].ne("") & (df["athlete_id"].ne("") | df["strava_name"].ne(""))].copy()
    return df[columns]


# =========================
# RAW DATA
# =========================
def read_raw_data(conn):
    """
    Đọc bảng activities và LEFT JOIN với webhook_events.
    Kết quả Raw_Data có thêm strava_event_time và webhook_received_at.
    """
    if not table_exists(conn, "activities"):
        raise RuntimeError("Không tìm thấy bảng activities trong activities.db")
    existing_cols = set(get_table_columns(conn, "activities"))
    activity_cols = [
        "first_seen_at", "last_seen_at", "athlete_id", "athlete", "type", "distance",
        "moving_time", "pace_min_per_km", "speed_kmh", "status", "note", "activity_name",
        "start_date_local", "activity_date", "activity_time", "activity_id", "source",
    ]
    raw_output_cols = [
        "first_seen_at", "last_seen_at", "strava_event_time", "webhook_received_at",
        "athlete_id", "athlete", "type", "distance", "moving_time", "pace_min_per_km",
        "speed_kmh", "status", "note", "activity_name", "start_date_local", "activity_date",
        "activity_time", "activity_id", "source",
    ]
    select_cols = [col for col in activity_cols if col in existing_cols]
    if not select_cols:
        raise RuntimeError("Bảng activities không có cột phù hợp để upload Raw_Data.")
    order_col = "start_date_local" if "start_date_local" in existing_cols else "activity_id"
    activity_select_sql = ", ".join([f"a.{col}" for col in select_cols])
    if table_exists(conn, "webhook_events"):
        sql = f"""
            SELECT
                {activity_select_sql},
                w.event_time AS strava_event_time,
                w.received_at AS webhook_received_at
            FROM activities a
            LEFT JOIN (
                SELECT
                    CAST(object_id AS TEXT) AS object_id,
                    MAX(event_time) AS event_time,
                    MAX(received_at) AS received_at
                FROM webhook_events
                WHERE object_type = 'activity'
                GROUP BY CAST(object_id AS TEXT)
            ) w
                ON CAST(a.activity_id AS TEXT) = CAST(w.object_id AS TEXT)
            ORDER BY a.{order_col} ASC
        """
    else:
        sql = f"""
            SELECT
                {activity_select_sql},
                '' AS strava_event_time,
                '' AS webhook_received_at
            FROM activities a
            ORDER BY a.{order_col} ASC
        """
    df = pd.read_sql_query(sql, conn)
    for col in raw_output_cols:
        if col not in df.columns:
            df[col] = ""
    df["athlete_id"] = df["athlete_id"].apply(clean_athlete_id)
    if "start_date_local" in df.columns:
        start_dt = pd.to_datetime(df["start_date_local"], errors="coerce")
        if df["activity_date"].astype(str).str.strip().eq("").all():
            df["activity_date"] = start_dt.dt.strftime("%Y-%m-%d").fillna("")
        if df["activity_time"].astype(str).str.strip().eq("").all():
            df["activity_time"] = start_dt.dt.strftime("%H:%M:%S").fillna("")
    df = df[raw_output_cols]
    return df


# =========================
# RAW DATA ENRICH
# =========================
def enrich_raw_data_with_members(raw_df, members_df):
    """
    Bổ sung thông tin VĐV cho Raw_Data.

    Ưu tiên match:
    1. athlete_id + type
    2. athlete_id
    3. athlete name + type
    4. athlete name

    Sửa lỗi KeyError sport_exact_id:
    - Không dùng suffix mơ hồ của pandas merge.
    - Đổi tên cột member trước khi merge.
    """
    raw_df = raw_df.copy()
    for col in ["athlete_id", "athlete", "type"]:
        if col not in raw_df.columns:
            raw_df[col] = ""
    for col in ["full_name", "gender", "registered_sport", "registered_strava_name"]:
        if col not in raw_df.columns:
            raw_df[col] = ""
    raw_df["athlete_id"] = raw_df["athlete_id"].apply(clean_athlete_id)
    raw_df["athlete_key"] = raw_df["athlete"].apply(normalize_name)
    raw_df["type"] = raw_df["type"].astype(str).str.strip()
    raw_df["id_match_key"] = raw_df["athlete_id"] + "||" + raw_df["type"]
    raw_df["name_match_key"] = raw_df["athlete_key"] + "||" + raw_df["type"]
    raw_df["id_only_key"] = raw_df["athlete_id"]
    raw_df["name_only_key"] = raw_df["athlete_key"]
    raw_df["full_name"] = raw_df["full_name"].astype(str).str.strip()
    raw_df["gender"] = raw_df["gender"].astype(str).str.strip()
    raw_df["registered_sport"] = raw_df["registered_sport"].astype(str).str.strip()
    raw_df["registered_strava_name"] = raw_df["registered_strava_name"].astype(str).str.strip()
    if members_df.empty:
        return raw_df.drop(columns=["athlete_key", "id_match_key", "name_match_key", "id_only_key", "name_only_key"], errors="ignore")
    exact_id = members_df[members_df["athlete_id"].ne("")].drop_duplicates(subset=["id_match_key"], keep="first")
    id_only = members_df[members_df["athlete_id"].ne("")].drop_duplicates(subset=["id_only_key"], keep="first")
    exact_name = members_df[members_df["strava_key"].ne("")].drop_duplicates(subset=["name_match_key"], keep="first")
    name_only = members_df[members_df["strava_key"].ne("")].drop_duplicates(subset=["name_only_key"], keep="first")

    def apply_match(base_df, lookup_df, key_col, suffix):
        if base_df.empty or lookup_df.empty:
            return base_df
        member_athlete_id_col = f"member_athlete_id_{suffix}"
        member_full_name_col = f"member_full_name_{suffix}"
        member_gender_col = f"member_gender_{suffix}"
        member_sport_col = f"member_sport_{suffix}"
        member_strava_name_col = f"member_strava_name_{suffix}"
        lookup = lookup_df[[key_col, "athlete_id", "full_name", "gender", "sport", "strava_name"]].copy()
        lookup = lookup.rename(columns={
            "athlete_id": member_athlete_id_col,
            "full_name": member_full_name_col,
            "gender": member_gender_col,
            "sport": member_sport_col,
            "strava_name": member_strava_name_col,
        })
        merged = base_df.merge(lookup, on=key_col, how="left")
        mask = (
            merged["full_name"].astype(str).str.strip().eq("")
            & merged[member_full_name_col].notna()
            & merged[member_full_name_col].astype(str).str.strip().ne("")
        )
        merged.loc[mask, "full_name"] = merged.loc[mask, member_full_name_col].astype(str).str.strip()
        merged.loc[mask, "gender"] = merged.loc[mask, member_gender_col].astype(str).str.strip()
        merged.loc[mask, "registered_sport"] = merged.loc[mask, member_sport_col].astype(str).str.strip()
        merged.loc[mask, "registered_strava_name"] = merged.loc[mask, member_strava_name_col].astype(str).str.strip()
        merged["athlete_id"] = merged["athlete_id"].apply(clean_athlete_id)
        merged[member_athlete_id_col] = merged[member_athlete_id_col].apply(clean_athlete_id)
        id_mask = merged["athlete_id"].eq("") & merged[member_athlete_id_col].ne("")
        merged.loc[id_mask, "athlete_id"] = merged.loc[id_mask, member_athlete_id_col]
        merged = merged.drop(columns=[member_athlete_id_col, member_full_name_col, member_gender_col, member_sport_col, member_strava_name_col], errors="ignore")
        return merged

    raw_df = apply_match(raw_df, exact_id, "id_match_key", "exact_id")
    raw_df = apply_match(raw_df, id_only, "id_only_key", "id_only")
    raw_df = apply_match(raw_df, exact_name, "name_match_key", "exact_name")
    raw_df = apply_match(raw_df, name_only, "name_only_key", "name_only")
    raw_df["athlete_id"] = raw_df["athlete_id"].apply(clean_athlete_id)
    raw_df["full_name"] = raw_df["full_name"].astype(str).str.strip()
    raw_df["gender"] = raw_df["gender"].astype(str).str.strip()
    raw_df["registered_sport"] = raw_df["registered_sport"].astype(str).str.strip()
    raw_df["registered_strava_name"] = raw_df["registered_strava_name"].astype(str).str.strip()
    raw_df = raw_df.drop(columns=["athlete_key", "id_match_key", "name_match_key", "id_only_key", "name_only_key"], errors="ignore")
    return raw_df


# =========================
# TIME HELPERS
# =========================
def seconds_to_hhmmss(seconds):
    try:
        seconds = int(float(seconds))
    except Exception:
        seconds = 0
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def get_valid_correct_sport_df(raw_df):
    """
    Data chuẩn để tổng hợp:
    - status = VALID
    - Có full_name
    - Đúng môn đăng ký nếu registered_sport có dữ liệu
    """
    df = raw_df.copy()
    for col in ["athlete_id", "full_name", "gender", "registered_sport", "type", "distance", "moving_time", "status", "start_date_local", "activity_id", "last_seen_at"]:
        if col not in df.columns:
            df[col] = ""
    df = df[df["status"].astype(str).str.upper().eq("VALID")].copy()
    if df.empty:
        return df
    df["athlete_id"] = df["athlete_id"].apply(clean_athlete_id)
    df["full_name"] = df["full_name"].astype(str).str.strip()
    df["gender"] = df["gender"].astype(str).str.strip()
    df["type"] = df["type"].astype(str).str.strip()
    df["registered_sport"] = df["registered_sport"].astype(str).str.strip()
    df["registered_sport_normalized"] = df["registered_sport"].apply(normalize_sport)
    df["distance"] = pd.to_numeric(df["distance"], errors="coerce").fillna(0)
    df["moving_time"] = pd.to_numeric(df["moving_time"], errors="coerce").fillna(0)
    df["start_dt"] = pd.to_datetime(df["start_date_local"], errors="coerce")
    df = df[df["full_name"].ne("")].copy()
    df = df[df["registered_sport_normalized"].eq("") | df["registered_sport_normalized"].eq(df["type"])].copy()
    return df


# =========================
# BUILD SUMMARY SHEETS FROM RAW
# =========================
def build_athlete_summary_from_raw(raw_df):
    columns = ["Number", "athlete_id", "full_name", "gender", "type", "total_km", "total_moving_time"]
    df = get_valid_correct_sport_df(raw_df)
    if df.empty:
        return pd.DataFrame(columns=columns)
    result = df.groupby(["athlete_id", "full_name", "gender", "type"], dropna=False).agg(
        total_km=("distance", "sum"),
        total_seconds=("moving_time", "sum"),
    ).reset_index()
    result["total_km"] = result["total_km"].round(2)
    result["total_moving_time"] = result["total_seconds"].apply(seconds_to_hhmmss)
    result = result.sort_values(by=["type", "total_km"], ascending=[True, False]).reset_index(drop=True)
    result.insert(0, "Number", result.index + 1)
    result = result[["Number", "athlete_id", "full_name", "gender", "type", "total_km", "total_moving_time"]]
    return clean_dataframe_for_sheet(result)


def build_gender_leaderboard_from_raw(raw_df, sport_type, gender_value):
    columns = ["Rank", "athlete_id", "full_name", "gender", "type", "total_km", "total_moving_time", "activity_count", "first_activity", "last_activity", "last_updated"]
    df = get_valid_correct_sport_df(raw_df)
    if df.empty:
        return pd.DataFrame(columns=columns)
    df = df[df["type"].eq(sport_type) & df["gender"].eq(gender_value)].copy()
    if df.empty:
        return pd.DataFrame(columns=columns)
    result = df.groupby(["athlete_id", "full_name", "gender", "type"], dropna=False).agg(
        total_km=("distance", "sum"),
        total_seconds=("moving_time", "sum"),
        activity_count=("activity_id", "count"),
        first_activity=("start_dt", "min"),
        last_activity=("start_dt", "max"),
    ).reset_index()
    result["total_km"] = result["total_km"].round(2)
    result["total_moving_time"] = result["total_seconds"].apply(seconds_to_hhmmss)
    result["first_activity"] = result["first_activity"].dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")
    result["last_activity"] = result["last_activity"].dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")
    result["last_updated"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    result = result.sort_values(by=["total_km", "activity_count"], ascending=[False, False]).reset_index(drop=True)
    result.insert(0, "Rank", result.index + 1)
    result = result[columns]
    return clean_dataframe_for_sheet(result)


def build_summary_table_from_raw(raw_df):
    columns = ["Thứ tự", "Chỉ số", "Giá trị"]
    df = get_valid_correct_sport_df(raw_df)
    if df.empty:
        return pd.DataFrame([
            [1, "Số VĐV tham gia", 0],
            [2, "Tổng km đạp xe", 0],
            [3, "Tổng giờ đạp xe", 0],
            [4, "Tổng hoạt động đạp xe", 0],
            [5, "Tổng km chạy bộ", 0],
            [6, "Tổng giờ chạy bộ", 0],
            [7, "Tổng hoạt động chạy bộ", 0],
            [8, "Lần cập nhật cuối", ""],
        ], columns=columns)
    ride_df = df[df["type"].eq("Ride")].copy()
    run_df = df[df["type"].eq("Run")].copy()
    df["participant_key"] = df["athlete_id"]
    df.loc[df["participant_key"].eq(""), "participant_key"] = df["full_name"]
    total_athletes = df[df["participant_key"].ne("")]["participant_key"].nunique()
    total_ride_km = round(float(ride_df["distance"].sum()), 2)
    total_ride_hours = round(float(ride_df["moving_time"].sum()) / 3600, 2)
    total_ride_activities = int(len(ride_df))
    total_run_km = round(float(run_df["distance"].sum()), 2)
    total_run_hours = round(float(run_df["moving_time"].sum()) / 3600, 2)
    total_run_activities = int(len(run_df))
    last_seen = ""
    if "last_seen_at" in df.columns:
        last_seen_series = pd.to_datetime(df["last_seen_at"], errors="coerce")
        if not last_seen_series.dropna().empty:
            last_seen = last_seen_series.max().strftime("%d/%m/%Y %H:%M:%S")
    result = pd.DataFrame([
        [1, "Số VĐV tham gia", total_athletes],
        [2, "Tổng km đạp xe", total_ride_km],
        [3, "Tổng giờ đạp xe", total_ride_hours],
        [4, "Tổng hoạt động đạp xe", total_ride_activities],
        [5, "Tổng km chạy bộ", total_run_km],
        [6, "Tổng giờ chạy bộ", total_run_hours],
        [7, "Tổng hoạt động chạy bộ", total_run_activities],
        [8, "Lần cập nhật cuối", last_seen],
    ], columns=columns)
    return clean_dataframe_for_sheet(result)


# =========================
# REPORT TABLES FROM SQLITE
# =========================
def read_reports(conn):
    reports = {
        "Daily_Run": "daily_run_report",
        "Daily_Ride": "daily_ride_report",
        "Run_Leaderboard": "run_leaderboard_report",
        "Ride_Leaderboard": "ride_leaderboard_report",
        "Unmatched_Activities": "unmatched_activities_report",
        "Wrong_Sport": "wrong_sport_report",
        "Invalid_Activities": "invalid_activities_report",
        "Overview": "overview_report",
    }
    result = {}
    for sheet_name, table_name in reports.items():
        result[sheet_name] = read_table_if_exists(conn, table_name)
    return result


def build_duplicate_members_report():
    columns = ["athlete_id", "strava_name", "full_name", "sport", "gender", "duplicate_type", "note"]
    members_df = load_members()
    if members_df.empty:
        return pd.DataFrame(columns=columns)
    duplicate_by_id_sport = members_df[members_df.duplicated(subset=["athlete_id", "sport_normalized"], keep=False) & members_df["athlete_id"].ne("")].copy()
    duplicate_by_name_sport = members_df[members_df.duplicated(subset=["strava_key", "sport_normalized"], keep=False) & members_df["strava_key"].ne("")].copy()
    duplicate_by_id_sport["duplicate_type"] = "Trùng athlete_id + sport"
    duplicate_by_name_sport["duplicate_type"] = "Trùng strava_name + sport"
    duplicate_df = pd.concat([duplicate_by_id_sport, duplicate_by_name_sport], ignore_index=True)
    if duplicate_df.empty:
        return pd.DataFrame(columns=columns)
    duplicate_df = duplicate_df.drop_duplicates()
    duplicate_df["note"] = "Kiểm tra lại vì có thể nhập trùng VĐV cùng môn"
    for col in columns:
        if col not in duplicate_df.columns:
            duplicate_df[col] = ""
    duplicate_df = duplicate_df[columns]
    return clean_dataframe_for_sheet(duplicate_df)


# =========================
# MAIN
# =========================
def main():
    if not DB_FILE.exists():
        raise FileNotFoundError(f"Không tìm thấy DB: {DB_FILE}")
    print("Đang đọc activities.db...")
    conn = sqlite3.connect(DB_FILE)
    raw_df = read_raw_data(conn)
    reports = read_reports(conn)
    conn.close()
    print("Đang đọc members.xlsx...")
    members_df = load_members()
    print("Đang bổ sung full_name / athlete_id cho Raw_Data...")
    raw_df = enrich_raw_data_with_members(raw_df, members_df)
    print("Đang tạo Athlete_Summary chuẩn...")
    athlete_summary_df = build_athlete_summary_from_raw(raw_df)
    print("Đang tạo Summary_Table từ Raw_Data...")
    summary_table_df = build_summary_table_from_raw(raw_df)
    print("Đang tạo leaderboard Nam/Nữ từ Raw_Data...")
    run_male_df = build_gender_leaderboard_from_raw(raw_df, "Run", "Nam")
    run_female_df = build_gender_leaderboard_from_raw(raw_df, "Run", "Nữ")
    ride_male_df = build_gender_leaderboard_from_raw(raw_df, "Ride", "Nam")
    ride_female_df = build_gender_leaderboard_from_raw(raw_df, "Ride", "Nữ")
    raw_columns = [
        "first_seen_at", "last_seen_at", "strava_event_time", "webhook_received_at",
        "athlete_id", "full_name", "gender", "registered_sport", "registered_strava_name",
        "athlete", "type", "distance", "moving_time", "pace_min_per_km", "speed_kmh",
        "status", "note", "activity_name", "start_date_local", "activity_date", "activity_time",
        "activity_id", "source",
    ]
    for col in raw_columns:
        if col not in raw_df.columns:
            raw_df[col] = ""
    raw_df = raw_df[raw_columns]
    raw_df = clean_dataframe_for_sheet(raw_df)
    duplicate_members_df = build_duplicate_members_report()
    print(f"Tổng activity trong thời gian giải: {len(raw_df)}")
    print("Đang kết nối Google Sheet...")
    spreadsheet = connect_google_sheet()
    print("Đang upload Raw_Data...")
    upload_dataframe(spreadsheet, "Raw_Data", raw_df)
    print("Đang upload Athlete_Summary...")
    upload_dataframe(spreadsheet, "Athlete_Summary", athlete_summary_df)
    print("Đang upload Summary_Table...")
    upload_dataframe(spreadsheet, "Summary_Table", summary_table_df)
    print("Đang upload Run_Male_Leaderboard...")
    upload_dataframe(spreadsheet, "Run_Male_Leaderboard", run_male_df)
    print("Đang upload Run_Female_Leaderboard...")
    upload_dataframe(spreadsheet, "Run_Female_Leaderboard", run_female_df)
    print("Đang upload Ride_Male_Leaderboard...")
    upload_dataframe(spreadsheet, "Ride_Male_Leaderboard", ride_male_df)
    print("Đang upload Ride_Female_Leaderboard...")
    upload_dataframe(spreadsheet, "Ride_Female_Leaderboard", ride_female_df)
    for sheet_name, df in reports.items():
        print(f"Đang upload {sheet_name}...")
        upload_dataframe(spreadsheet, sheet_name, df)
    print("Đang upload Duplicate_Members...")
    upload_dataframe(spreadsheet, "Duplicate_Members", duplicate_members_df)
    print(f"Upload Google Sheets thành công. Số dòng Raw_Data: {len(raw_df)}")
    print("HOAN TAT")


if __name__ == "__main__":
    main()
