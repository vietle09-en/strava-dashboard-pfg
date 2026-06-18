import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd


# =========================
# CONFIG
# =========================
BASE_DIR = Path(r"F:\strava")

DB_FILE = BASE_DIR / "activities.db"
MEMBERS_FILE = BASE_DIR / "members.xlsx"

CHALLENGE_START = "2026-05-30 00:00:00"
CHALLENGE_END = "2026-07-20 23:59:59"


# =========================
# NORMALIZE HELPERS
# =========================
def remove_vietnamese_accents(text):
    """
    Bỏ dấu tiếng Việt, xử lý cả chữ đ/Đ.
    """
    if text is None:
        return ""

    text = str(text).strip()
    text = text.replace("Đ", "D").replace("đ", "d")

    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")

    text = " ".join(text.split())
    return text


def normalize_name(value):
    """
    Chuẩn hóa tên để match mềm:
    - bỏ dấu
    - lower case
    - bỏ khoảng trắng thừa
    """
    if pd.isna(value):
        return ""

    text = remove_vietnamese_accents(value)
    return text.lower().strip()


def normalize_sport(value):
    """
    Chuẩn hóa môn đăng ký trong members.xlsx.

    Excel có thể ghi:
    - Chạy bộ / Chạy / Run -> Run
    - Đạp xe / Đạp / Ride -> Ride

    Strava activity type đang dùng:
    - Run
    - Ride
    """
    if pd.isna(value):
        return ""

    raw = str(value).strip()
    s = normalize_name(raw)

    run_values = {
        "run",
        "running",
        "chay",
        "chay bo",
        "di bo",
        "jogging",
    }

    ride_values = {
        "ride",
        "cycling",
        "bike",
        "bicycle",
        "dap",
        "dap xe",
        "xe dap",
    }

    if s in run_values:
        return "Run"

    if s in ride_values:
        return "Ride"

    return raw


# =========================
# LOAD DATA
# =========================
def load_activities():
    if not DB_FILE.exists():
        raise FileNotFoundError(f"Không tìm thấy DB: {DB_FILE}")

    conn = sqlite3.connect(DB_FILE)

    table_info = pd.read_sql_query("PRAGMA table_info(activities)", conn)
    existing_cols = set(table_info["name"].tolist())

    wanted_cols = [
        "activity_id",
        "athlete",
        "type",
        "distance",
        "moving_time",
        "pace_min_per_km",
        "speed_kmh",
        "status",
        "note",
        "activity_name",
        "start_date_local",
        "first_seen_at",
        "last_seen_at",
        "source",
    ]

    select_cols = [col for col in wanted_cols if col in existing_cols]

    if not select_cols:
        conn.close()
        raise RuntimeError("Bảng activities không có cột phù hợp để đọc.")

    sql = f"""
        SELECT
            {", ".join(select_cols)}
        FROM activities
    """

    df = pd.read_sql_query(sql, conn)
    conn.close()

    # Bổ sung cột thiếu nếu DB cũ chưa có
    for col in wanted_cols:
        if col not in df.columns:
            df[col] = ""

    # Chuẩn hóa dữ liệu số
    df["distance"] = pd.to_numeric(df["distance"], errors="coerce").fillna(0)
    df["moving_time"] = pd.to_numeric(df["moving_time"], errors="coerce").fillna(0).astype(int)
    df["pace_min_per_km"] = pd.to_numeric(df["pace_min_per_km"], errors="coerce")
    df["speed_kmh"] = pd.to_numeric(df["speed_kmh"], errors="coerce")

    # Chuẩn hóa text
    df["activity_id"] = df["activity_id"].astype(str).str.strip()
    df["athlete"] = df["athlete"].astype(str).str.strip()
    df["type"] = df["type"].astype(str).str.strip()
    df["status"] = df["status"].astype(str).str.strip()
    df["note"] = df["note"].astype(str).str.strip()
    df["activity_name"] = df["activity_name"].astype(str).str.strip()
    df["source"] = df["source"].astype(str).str.strip()

    # Thời gian hoạt động thật
    df["start_dt"] = pd.to_datetime(df["start_date_local"], errors="coerce")

    start = pd.to_datetime(CHALLENGE_START)
    end = pd.to_datetime(CHALLENGE_END)

    df = df[
        (df["start_dt"] >= start)
        & (df["start_dt"] <= end)
    ].copy()

    df["activity_date"] = df["start_dt"].dt.strftime("%Y-%m-%d")
    df["activity_time"] = df["start_dt"].dt.strftime("%H:%M:%S")

    df["athlete_key"] = df["athlete"].apply(normalize_name)

    # Key match chính: tên Strava + môn activity
    df["match_key"] = df["athlete_key"] + "||" + df["type"]

    return df


def load_members():
    if not MEMBERS_FILE.exists():
        raise FileNotFoundError(f"Không tìm thấy file members.xlsx: {MEMBERS_FILE}")

    excel = pd.ExcelFile(MEMBERS_FILE)

    if "members_clean" in excel.sheet_names:
        members = pd.read_excel(MEMBERS_FILE, sheet_name="members_clean")
    else:
        members = pd.read_excel(MEMBERS_FILE, sheet_name=0)

    members.columns = [str(c).strip() for c in members.columns]

    required_cols = [
        "full_name",
        "sport",
        "gender",
        "strava_name",
    ]

    for col in required_cols:
        if col not in members.columns:
            members[col] = ""

    members["full_name"] = members["full_name"].astype(str).str.strip()
    members["sport"] = members["sport"].astype(str).str.strip()
    members["gender"] = members["gender"].astype(str).str.strip()
    members["strava_name"] = members["strava_name"].astype(str).str.strip()

    # Loại dòng rỗng
    members = members[
        members["full_name"].ne("")
        & members["strava_name"].ne("")
        & members["strava_name"].str.lower().ne("nan")
    ].copy()

    members["sport_normalized"] = members["sport"].apply(normalize_sport)
    members["strava_key"] = members["strava_name"].apply(normalize_name)

    # Key match chính: tên Strava + môn đăng ký đã chuẩn hóa
    members["match_key"] = members["strava_key"] + "||" + members["sport_normalized"]

    # Tránh lỗi nhân đôi nếu cùng 1 người bị nhập trùng cùng 1 môn
    members = members.drop_duplicates(
        subset=["strava_key", "sport_normalized"],
        keep="first",
    ).copy()

    return members


# =========================
# BUILD DATA
# =========================
def build_member_lookup(members):
    """
    Tạo bảng lookup theo strava_key để phục vụ:
    - xác định tên có tồn tại trong members.xlsx hay không
    - liệt kê các môn VĐV đã đăng ký
    """
    if members.empty:
        return pd.DataFrame(
            columns=[
                "strava_key",
                "registered_full_name",
                "registered_gender",
                "registered_strava_name",
                "registered_sports",
                "registered_sports_normalized",
            ]
        )

    lookup = (
        members.groupby("strava_key", dropna=False)
        .agg(
            registered_full_name=("full_name", "first"),
            registered_gender=("gender", "first"),
            registered_strava_name=("strava_name", "first"),
            registered_sports=(
                "sport",
                lambda x: ", ".join(
                    sorted(
                        set(
                            str(v).strip()
                            for v in x
                            if str(v).strip() and str(v).strip().lower() != "nan"
                        )
                    )
                ),
            ),
            registered_sports_normalized=(
                "sport_normalized",
                lambda x: ", ".join(
                    sorted(
                        set(
                            str(v).strip()
                            for v in x
                            if str(v).strip() and str(v).strip().lower() != "nan"
                        )
                    )
                ),
            ),
        )
        .reset_index()
    )

    return lookup


def build_matched(activities, members):
    """
    Logic mới theo yêu cầu:

    1. VĐV có thể đăng ký 1 môn hoặc 2 môn.
       Nếu đăng ký 2 môn thì members.xlsx có 2 dòng cùng strava_name:
       - Chạy bộ
       - Đạp xe

    2. Activity chỉ được tính nếu match đúng:
       strava_name + sport

    3. Nếu tên VĐV có trong members.xlsx nhưng activity là môn chưa đăng ký:
       -> is_wrong_sport = True
       -> đưa vào sheet Wrong_Sport

    4. Nếu tên VĐV không có trong members.xlsx:
       -> đưa vào sheet Unmatched_Activities

    5. Không nhân đôi activity khi VĐV đăng ký 2 môn.
    """

    activities = activities.copy()
    members = members.copy()

    member_cols = [
        "full_name",
        "sport",
        "sport_normalized",
        "gender",
        "strava_name",
        "strava_key",
        "match_key",
    ]

    for col in member_cols:
        if col not in members.columns:
            members[col] = ""

    # Merge chính xác theo tên + môn
    matched = activities.merge(
        members[member_cols],
        on="match_key",
        how="left",
        indicator=True,
    )

    matched["is_matched_name"] = matched["_merge"].eq("both")

    # Lookup theo tên Strava để biết tên này có đăng ký trong members.xlsx không
    member_lookup = build_member_lookup(members)

    matched = matched.merge(
        member_lookup,
        left_on="athlete_key",
        right_on="strava_key",
        how="left",
        suffixes=("", "_registered"),
    )

    matched["is_registered_name"] = matched["registered_full_name"].notna()

    # Sai môn = tên có trong members.xlsx nhưng môn activity không nằm trong môn đã đăng ký
    matched["is_wrong_sport"] = (
        matched["is_registered_name"]
        & ~matched["is_matched_name"]
    )

    # Với Wrong_Sport, bổ sung thông tin đăng ký để dễ kiểm tra
    wrong_mask = matched["is_wrong_sport"].eq(True)

    matched.loc[wrong_mask, "full_name"] = matched.loc[wrong_mask, "registered_full_name"]
    matched.loc[wrong_mask, "gender"] = matched.loc[wrong_mask, "registered_gender"]
    matched.loc[wrong_mask, "strava_name"] = matched.loc[wrong_mask, "registered_strava_name"]
    matched.loc[wrong_mask, "sport"] = matched.loc[wrong_mask, "registered_sports"]
    matched.loc[wrong_mask, "sport_normalized"] = matched.loc[
        wrong_mask,
        "registered_sports_normalized",
    ]

    return matched


def build_unmatched_activities(matched):
    """
    Chỉ đưa vào Unmatched khi tên Strava không có trong members.xlsx.
    Không đưa Wrong_Sport vào Unmatched.
    """
    df = matched[~matched["is_registered_name"]].copy()

    columns = [
        "athlete",
        "type",
        "distance",
        "activity_name",
        "start_date_local",
        "activity_date",
        "activity_time",
        "status",
        "note",
    ]

    for col in columns:
        if col not in df.columns:
            df[col] = ""

    return df[columns].sort_values(
        by=["athlete", "start_date_local"],
        ascending=[True, True],
    )


def build_wrong_sport(matched):
    """
    Activity sai môn:
    - Tên VĐV có trong members.xlsx
    - Nhưng activity type không nằm trong môn đã đăng ký
    """
    df = matched[matched["is_wrong_sport"]].copy()

    columns = [
        "full_name",
        "gender",
        "sport",
        "sport_normalized",
        "strava_name",
        "athlete",
        "type",
        "distance",
        "activity_name",
        "start_date_local",
        "activity_date",
        "activity_time",
        "status",
        "note",
    ]

    for col in columns:
        if col not in df.columns:
            df[col] = ""

    return df[columns].sort_values(
        by=["full_name", "start_date_local"],
        ascending=[True, True],
    )


def build_invalid_activities(matched):
    df = matched[matched["status"].ne("VALID")].copy()

    columns = [
        "athlete",
        "type",
        "distance",
        "moving_time",
        "pace_min_per_km",
        "speed_kmh",
        "activity_name",
        "start_date_local",
        "activity_date",
        "activity_time",
        "status",
        "note",
    ]

    for col in columns:
        if col not in df.columns:
            df[col] = ""

    return df[columns].sort_values(
        by=["athlete", "start_date_local"],
        ascending=[True, True],
    )


def build_leaderboard(matched, sport_type):
    df = matched[
        matched["is_matched_name"]
        & ~matched["is_wrong_sport"]
        & matched["status"].eq("VALID")
        & matched["type"].eq(sport_type)
    ].copy()

    if df.empty:
        return pd.DataFrame(
            columns=[
                "Rank",
                "Full_name",
                "Gender",
                "Strava_name",
                "Total_km",
                "Activity_count",
                "First_activity",
                "Last_activity",
            ]
        )

    result = (
        df.groupby(["full_name", "gender", "strava_name"], dropna=False)
        .agg(
            Total_km=("distance", "sum"),
            Activity_count=("activity_id", "count"),
            First_activity=("start_dt", "min"),
            Last_activity=("start_dt", "max"),
        )
        .reset_index()
    )

    result["Total_km"] = result["Total_km"].round(2)
    result["First_activity"] = result["First_activity"].dt.strftime("%Y-%m-%d %H:%M:%S")
    result["Last_activity"] = result["Last_activity"].dt.strftime("%Y-%m-%d %H:%M:%S")

    result = result.sort_values(
        by=["Total_km", "Activity_count"],
        ascending=[False, False],
    ).reset_index(drop=True)

    result.insert(0, "Rank", result.index + 1)

    result = result.rename(
        columns={
            "full_name": "Full_name",
            "gender": "Gender",
            "strava_name": "Strava_name",
        }
    )

    return result[
        [
            "Rank",
            "Full_name",
            "Gender",
            "Strava_name",
            "Total_km",
            "Activity_count",
            "First_activity",
            "Last_activity",
        ]
    ]


def build_daily_summary(matched, sport_type):
    df = matched[
        matched["is_matched_name"]
        & ~matched["is_wrong_sport"]
        & matched["status"].eq("VALID")
        & matched["type"].eq(sport_type)
    ].copy()

    if df.empty:
        return pd.DataFrame(
            columns=[
                "activity_date",
                "full_name",
                "gender",
                "strava_name",
                "total_km",
                "activity_count",
            ]
        )

    result = (
        df.groupby(["activity_date", "full_name", "gender", "strava_name"], dropna=False)
        .agg(
            total_km=("distance", "sum"),
            activity_count=("activity_id", "count"),
        )
        .reset_index()
    )

    result["total_km"] = result["total_km"].round(2)

    result = result.sort_values(
        by=["activity_date", "total_km"],
        ascending=[True, False],
    )

    return result


def build_overview(activities, matched):
    total_activities = len(activities)
    valid_activities = len(activities[activities["status"].eq("VALID")])
    invalid_activities = len(activities[activities["status"].ne("VALID")])

    matched_activities = len(
        matched[
            matched["is_matched_name"]
            & ~matched["is_wrong_sport"]
            & matched["status"].eq("VALID")
        ]
    )

    unmatched_activities = len(matched[~matched["is_registered_name"]])
    wrong_sport_activities = len(matched[matched["is_wrong_sport"]])

    run_athletes = matched[
        matched["is_matched_name"]
        & ~matched["is_wrong_sport"]
        & matched["status"].eq("VALID")
        & matched["type"].eq("Run")
    ]["full_name"].nunique()

    ride_athletes = matched[
        matched["is_matched_name"]
        & ~matched["is_wrong_sport"]
        & matched["status"].eq("VALID")
        & matched["type"].eq("Ride")
    ]["full_name"].nunique()

    return pd.DataFrame(
        [
            ["challenge_start", CHALLENGE_START],
            ["challenge_end", CHALLENGE_END],
            ["total_activities_in_period", total_activities],
            ["valid_activities", valid_activities],
            ["invalid_activities", invalid_activities],
            ["matched_activities", matched_activities],
            ["unmatched_activities", unmatched_activities],
            ["wrong_sport_activities", wrong_sport_activities],
            ["run_athletes", run_athletes],
            ["ride_athletes", ride_athletes],
            ["last_calculated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ],
        columns=["metric", "value"],
    )


# =========================
# SAVE TO SQLITE
# =========================
def save_table(conn, table_name, df):
    df = df.copy()

    # Bỏ cột kỹ thuật không cần lưu
    drop_cols = [
        "_merge",
        "athlete_key",
        "strava_key",
        "strava_key_registered",
        "match_key",
        "start_dt",
    ]

    for col in drop_cols:
        if col in df.columns:
            df = df.drop(columns=[col])

    df.to_sql(table_name, conn, if_exists="replace", index=False)


# =========================
# MAIN
# =========================
def main():
    print("Đang cập nhật leaderboard theo start_date_local...")

    activities = load_activities()
    members = load_members()
    matched = build_matched(activities, members)

    unmatched_df = build_unmatched_activities(matched)
    wrong_sport_df = build_wrong_sport(matched)
    invalid_df = build_invalid_activities(matched)
    run_leaderboard_df = build_leaderboard(matched, "Run")
    ride_leaderboard_df = build_leaderboard(matched, "Ride")
    daily_run_df = build_daily_summary(matched, "Run")
    daily_ride_df = build_daily_summary(matched, "Ride")
    overview_df = build_overview(activities, matched)

    conn = sqlite3.connect(DB_FILE)

    save_table(conn, "matched_activities_report", matched)
    save_table(conn, "unmatched_activities_report", unmatched_df)
    save_table(conn, "wrong_sport_report", wrong_sport_df)
    save_table(conn, "invalid_activities_report", invalid_df)
    save_table(conn, "run_leaderboard_report", run_leaderboard_df)
    save_table(conn, "ride_leaderboard_report", ride_leaderboard_df)
    save_table(conn, "daily_run_report", daily_run_df)
    save_table(conn, "daily_ride_report", daily_ride_df)
    save_table(conn, "overview_report", overview_df)

    conn.close()

    run_athletes = len(run_leaderboard_df)
    ride_athletes = len(ride_leaderboard_df)

    overview = dict(overview_df.values)

    print("✅ Leaderboard updated theo start_date_local")
    print(f"Run athletes: {run_athletes}")
    print(f"Ride athletes: {ride_athletes}")
    print(f"Matched activities: {overview.get('matched_activities', 0)}")
    print(f"Unmatched activities: {overview.get('unmatched_activities', 0)}")
    print(f"Wrong sport activities: {overview.get('wrong_sport_activities', 0)}")
    print(f"Invalid activities: {overview.get('invalid_activities', 0)}")


if __name__ == "__main__":
    main()