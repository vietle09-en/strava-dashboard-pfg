from flask import Flask, request, redirect, render_template_string, jsonify
import requests
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


# =========================
# CẤU HÌNH THƯ MỤC
# =========================
BASE_DIR = Path(r"F:\strava")
DB_FILE = BASE_DIR / "activities.db"
TOKEN_FILE = BASE_DIR / "athlete_tokens.json"


# =========================
# CẤU HÌNH STRAVA APP
# =========================
STRAVA_CLIENT_ID = "HÃY ĐIỀN THÔNG TIN"
STRAVA_CLIENT_SECRET = "HÃY ĐIỀN THÔNG TIN"

# Mỗi lần đổi link cloudflared thì sửa dòng này
PUBLIC_BASE_URL = "HÃY CHÈN LINK"

CALLBACK_URL = PUBLIC_BASE_URL + "/strava/callback"

STRAVA_AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"

# Scope cần để đọc hoạt động của VĐV
STRAVA_SCOPE = "read,activity:read_all"

# Verify token tự đặt, dùng khi đăng ký webhook với Strava
STRAVA_WEBHOOK_VERIFY_TOKEN = "HÃY ĐIỀN THÔNG TIN"

TIMEZONE = "Asia/Ho_Chi_Minh"

app = Flask(__name__)


# =========================
# HÀM PHỤ TRỢ THỜI GIAN
# =========================
def now_text():
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")


def unix_to_vn_time(timestamp_value):
    """
    Strava webhook event_time là Unix timestamp.
    Chuyển sang giờ Việt Nam.
    """
    if not timestamp_value:
        return ""

    try:
        return datetime.fromtimestamp(
            int(timestamp_value),
            tz=timezone.utc
        ).astimezone(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


# =========================
# HÀM PHỤ TRỢ TOKEN
# =========================
def load_tokens():
    if not TOKEN_FILE.exists():
        return []

    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return data

        # Nếu file cũ là dict thì chuyển sang list
        if isinstance(data, dict):
            output = []
            for key, value in data.items():
                if isinstance(value, dict):
                    value["athlete_id"] = value.get("athlete_id") or key
                    output.append(value)
            return output

        return []

    except Exception as e:
        print("Lỗi đọc athlete_tokens.json:", e)
        return []


def save_tokens(tokens):
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)


def upsert_token(new_item):
    tokens = load_tokens()

    new_athlete_id = str(new_item.get("athlete_id", "")).strip()

    updated = False

    for i, item in enumerate(tokens):
        old_athlete_id = str(item.get("athlete_id", "")).strip()

        if old_athlete_id == new_athlete_id:
            tokens[i] = new_item
            updated = True
            break

    if not updated:
        tokens.append(new_item)

    save_tokens(tokens)


def get_athlete_name(athlete):
    firstname = str(athlete.get("firstname") or "").strip()
    lastname = str(athlete.get("lastname") or "").strip()
    username = str(athlete.get("username") or "").strip()

    full_name = (firstname + " " + lastname).strip()

    if full_name:
        return full_name

    if username:
        return username

    return "Strava Athlete"


# =========================
# HÀM PHỤ TRỢ DATABASE WEBHOOK
# =========================
def init_webhook_table():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS webhook_events (
            object_id TEXT PRIMARY KEY,
            owner_id TEXT,
            aspect_type TEXT,
            object_type TEXT,
            event_time TEXT,
            received_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_webhook_event(data):
    """
    Lưu webhook event vào activities.db.
    object_id = activity_id nếu object_type là activity.
    owner_id = athlete_id.
    event_time = thời điểm Strava báo event.
    received_at = thời điểm server mình nhận event.
    """
    object_id = str(data.get("object_id", "")).strip()
    owner_id = str(data.get("owner_id", "")).strip()
    aspect_type = str(data.get("aspect_type", "")).strip()
    object_type = str(data.get("object_type", "")).strip()
    event_time_raw = data.get("event_time")

    event_time = unix_to_vn_time(event_time_raw)
    received_at = now_text()

    if not object_id:
        print("Webhook thiếu object_id, bỏ qua.")
        return False

    if object_type != "activity":
        print("Webhook không phải activity, bỏ qua:", object_type)
        return False

    init_webhook_table()

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        INSERT OR REPLACE INTO webhook_events (
            object_id,
            owner_id,
            aspect_type,
            object_type,
            event_time,
            received_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        object_id,
        owner_id,
        aspect_type,
        object_type,
        event_time,
        received_at,
    ))

    conn.commit()
    conn.close()

    print("Đã lưu webhook event:")
    print("  object_id:", object_id)
    print("  owner_id:", owner_id)
    print("  aspect_type:", aspect_type)
    print("  object_type:", object_type)
    print("  event_time:", event_time)
    print("  received_at:", received_at)

    return True


# =========================
# GIAO DIỆN TRANG CHỦ
# =========================
HOME_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Strava Authorization</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      max-width: 900px;
      margin: 30px auto;
      padding: 0 20px;
      color: #111;
    }

    h1 {
      font-size: 28px;
      margin-bottom: 24px;
    }

    .box {
      background: #f7f7f7;
      border: 1px solid #ddd;
      padding: 14px;
      margin-bottom: 22px;
      font-family: Consolas, monospace;
      font-size: 13px;
      white-space: pre-wrap;
    }

    .btn {
      display: inline-block;
      background: #fc4c02;
      color: white;
      padding: 14px 22px;
      text-decoration: none;
      border-radius: 6px;
      font-weight: bold;
      margin: 10px 0 24px 0;
    }

    table {
      border-collapse: collapse;
      width: 100%;
      margin-top: 15px;
    }

    th, td {
      border: 1px solid #ddd;
      padding: 10px;
      text-align: left;
    }

    th {
      background: #f2f2f2;
    }

    .note {
      color: #444;
      margin-bottom: 10px;
    }
  </style>
</head>
<body>

  <h1>Kết nối Strava cho giải vận động</h1>

  <div class="box">PUBLIC_BASE_URL hiện tại:
{{ public_base_url }}

Callback URL:
{{ callback_url }}

Webhook URL:
{{ webhook_url }}</div>

  <p class="note">VĐV bấm nút bên dưới, đăng nhập đúng tài khoản Strava đang ghi hoạt động và cấp quyền.</p>

  <a class="btn" href="/authorize">Kết nối Strava</a>

  <h2>Đã cấp quyền: {{ count }} VĐV</h2>

  <table>
    <thead>
      <tr>
        <th>STT</th>
        <th>Athlete ID</th>
        <th>Tên Strava</th>
        <th>Thời điểm cấp quyền</th>
      </tr>
    </thead>
    <tbody>
      {% for item in tokens %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>{{ item.get("athlete_id", "") }}</td>
        <td>{{ item.get("athlete_name", "") }}</td>
        <td>{{ item.get("authorized_at", "") }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

</body>
</html>
"""


SUCCESS_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Kết nối thành công</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      max-width: 700px;
      margin: 50px auto;
      padding: 0 20px;
    }

    .success {
      color: #138a36;
      font-size: 24px;
      font-weight: bold;
    }

    .box {
      background: #f7f7f7;
      border: 1px solid #ddd;
      padding: 14px;
      margin-top: 20px;
    }

    a {
      color: #fc4c02;
      font-weight: bold;
    }
  </style>
</head>
<body>

  <div class="success">Kết nối Strava thành công!</div>

  <div class="box">
    <p><b>Athlete ID:</b> {{ athlete_id }}</p>
    <p><b>Tên Strava:</b> {{ athlete_name }}</p>
    <p><b>Thời điểm cấp quyền:</b> {{ authorized_at }}</p>
  </div>

  <p>Cụ có thể đóng trang này.</p>

  <p><a href="/">Quay lại danh sách đã cấp quyền</a></p>

</body>
</html>
"""


ERROR_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Lỗi kết nối Strava</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      max-width: 700px;
      margin: 50px auto;
      padding: 0 20px;
    }

    .error {
      color: #b00020;
      font-size: 24px;
      font-weight: bold;
    }

    .box {
      background: #fff3f3;
      border: 1px solid #ffcccc;
      padding: 14px;
      margin-top: 20px;
      white-space: pre-wrap;
      font-family: Consolas, monospace;
    }
  </style>
</head>
<body>

  <div class="error">Lỗi kết nối Strava</div>

  <div class="box">{{ message }}</div>

  <p><a href="/">Quay lại trang kết nối</a></p>

</body>
</html>
"""


# =========================
# ROUTES OAUTH
# =========================
@app.route("/")
def index():
    tokens = load_tokens()

    return render_template_string(
        HOME_HTML,
        public_base_url=PUBLIC_BASE_URL,
        callback_url=CALLBACK_URL,
        webhook_url=PUBLIC_BASE_URL + "/strava/webhook",
        tokens=tokens,
        count=len(tokens),
    )


@app.route("/authorize")
def authorize():
    if STRAVA_CLIENT_ID == "DÁN_CLIENT_ID_VÀO_ĐÂY":
        return render_template_string(
            ERROR_HTML,
            message="Chưa cấu hình STRAVA_CLIENT_ID trong auth_server.py",
        )

    params = {
        "client_id": STRAVA_CLIENT_ID,
        "redirect_uri": CALLBACK_URL,
        "response_type": "code",
        "approval_prompt": "force",
        "scope": STRAVA_SCOPE,
    }

    query = "&".join(
        [f"{k}={requests.utils.quote(str(v))}" for k, v in params.items()]
    )

    return redirect(f"{STRAVA_AUTHORIZE_URL}?{query}")


@app.route("/strava/callback")
def strava_callback():
    error = request.args.get("error")
    code = request.args.get("code")

    if error:
        return render_template_string(
            ERROR_HTML,
            message=f"Strava trả về lỗi: {error}",
        )

    if not code:
        return render_template_string(
            ERROR_HTML,
            message="Không nhận được code từ Strava callback.",
        )

    payload = {
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
    }

    try:
        res = requests.post(STRAVA_TOKEN_URL, data=payload, timeout=30)
    except Exception as e:
        return render_template_string(
            ERROR_HTML,
            message=f"Lỗi gọi Strava token API:\n{str(e)}",
        )

    if res.status_code != 200:
        return render_template_string(
            ERROR_HTML,
            message=(
                f"Strava token API lỗi.\n"
                f"Status: {res.status_code}\n"
                f"Response:\n{res.text}"
            ),
        )

    token_data = res.json()

    athlete = token_data.get("athlete", {})
    athlete_id = str(athlete.get("id") or "").strip()
    athlete_name = get_athlete_name(athlete)

    if not athlete_id:
        return render_template_string(
            ERROR_HTML,
            message="Không lấy được athlete_id từ Strava.",
        )

    item = {
        "athlete_id": athlete_id,
        "athlete_name": athlete_name,
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": token_data.get("expires_at"),
        "scope": token_data.get("scope") or STRAVA_SCOPE,
        "authorized_at": now_text(),
    }

    upsert_token(item)

    return render_template_string(
        SUCCESS_HTML,
        athlete_id=athlete_id,
        athlete_name=athlete_name,
        authorized_at=item["authorized_at"],
    )


# =========================
# ROUTES WEBHOOK
# =========================
@app.route("/strava/webhook", methods=["GET"])
def strava_webhook_verify():
    """
    Strava gọi GET endpoint này khi tạo webhook subscription.
    Nếu verify_token đúng, mình trả lại hub.challenge.
    """
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    print("========================================")
    print("STRAVA WEBHOOK VERIFY")
    print("hub.mode:", mode)
    print("hub.verify_token:", token)
    print("hub.challenge:", challenge)
    print("========================================")

    if mode == "subscribe" and token == STRAVA_WEBHOOK_VERIFY_TOKEN:
        return jsonify({"hub.challenge": challenge})

    return "Verification failed", 403


@app.route("/strava/webhook", methods=["POST"])
def strava_webhook_event():
    """
    Strava gửi POST vào đây khi có activity created/updated/deleted.
    Lưu vào bảng webhook_events.
    """
    data = request.get_json(force=True, silent=True) or {}

    print("========================================")
    print("STRAVA WEBHOOK EVENT")
    print(data)
    print("========================================")

    saved = save_webhook_event(data)

    return jsonify(
        {
            "status": "ok",
            "saved": saved,
            "received_at": now_text(),
        }
    )


# =========================
# HEALTH / DEBUG
# =========================
@app.route("/health")
def health():
    init_webhook_table()

    return {
        "status": "ok",
        "public_base_url": PUBLIC_BASE_URL,
        "callback_url": CALLBACK_URL,
        "webhook_url": PUBLIC_BASE_URL + "/strava/webhook",
        "verify_token": STRAVA_WEBHOOK_VERIFY_TOKEN,
        "tokens": len(load_tokens()),
        "db_file": str(DB_FILE),
        "time": now_text(),
    }


@app.route("/webhook-events")
def webhook_events():
    init_webhook_table()

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        SELECT
            object_id,
            owner_id,
            aspect_type,
            object_type,
            event_time,
            received_at
        FROM webhook_events
        ORDER BY received_at DESC
        LIMIT 50
    """)

    rows = cur.fetchall()
    conn.close()

    html_rows = ""

    for row in rows:
        html_rows += "<tr>"
        for cell in row:
            html_rows += f"<td>{cell}</td>"
        html_rows += "</tr>"

    html = f"""
    <!DOCTYPE html>
    <html lang="vi">
    <head>
      <meta charset="UTF-8">
      <title>Webhook Events</title>
      <style>
        body {{
          font-family: Arial, sans-serif;
          max-width: 1000px;
          margin: 30px auto;
        }}
        table {{
          border-collapse: collapse;
          width: 100%;
        }}
        th, td {{
          border: 1px solid #ddd;
          padding: 8px;
          font-size: 13px;
        }}
        th {{
          background: #f2f2f2;
        }}
      </style>
    </head>
    <body>
      <h1>50 Webhook Events mới nhất</h1>
      <p><a href="/">Quay lại trang chủ</a></p>
      <table>
        <thead>
          <tr>
            <th>object_id</th>
            <th>owner_id</th>
            <th>aspect_type</th>
            <th>object_type</th>
            <th>event_time</th>
            <th>received_at</th>
          </tr>
        </thead>
        <tbody>
          {html_rows}
        </tbody>
      </table>
    </body>
    </html>
    """

    return html


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    init_webhook_table()

    print("========================================")
    print("STRAVA AUTH SERVER + WEBHOOK SERVER")
    print("========================================")
    print("PUBLIC_BASE_URL:", PUBLIC_BASE_URL)
    print("CALLBACK_URL:", CALLBACK_URL)
    print("WEBHOOK_URL:", PUBLIC_BASE_URL + "/strava/webhook")
    print("VERIFY_TOKEN:", STRAVA_WEBHOOK_VERIFY_TOKEN)
    print("TOKEN_FILE:", TOKEN_FILE)
    print("DB_FILE:", DB_FILE)
    print("========================================")
    print("Chạy tại: http://localhost:5000")
    print("Public link:", PUBLIC_BASE_URL)
    print("Health:", PUBLIC_BASE_URL + "/health")
    print("Webhook events:", PUBLIC_BASE_URL + "/webhook-events")
    print("========================================")

    app.run(host="0.0.0.0", port=5000, debug=False)