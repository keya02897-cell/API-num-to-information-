import os
import secrets
import sqlite3
import hashlib
import json
from urllib.request import Request, urlopen
from datetime import datetime, timezone, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

# ============================================================
# KRUTIK CYBER EXPERT - API WEBSITE
# Production-oriented Flask website for the existing API system.
# ============================================================

APP_NAME = "KRUTIK CYBER EXPERT API"
BRAND = "KRUTIK CYBER EXPERT"
DB_PATH = os.getenv("DB_PATH", "bot.db")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEB_SECRET = os.getenv("WEB_SECRET", "").strip()
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "10000"))
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))

if not WEB_SECRET:
    # Safe for local development; production should always set WEB_SECRET.
    WEB_SECRET = secrets.token_urlsafe(48)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=WEB_SECRET,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)


# --------------------------- DB -----------------------------

def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def init_web_schema():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS web_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL DEFAULT '',
        chat_id INTEGER UNIQUE,
        blocked INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        last_login_at TEXT
    );

    CREATE TABLE IF NOT EXISTS web_audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        web_user_id INTEGER,
        action TEXT NOT NULL,
        target TEXT DEFAULT '',
        ip TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_web_users_chat_id ON web_users(chat_id);
    CREATE INDEX IF NOT EXISTS idx_web_audit_created ON web_audit_logs(created_at);
    CREATE INDEX IF NOT EXISTS idx_access_requests_status ON access_requests(status);
    CREATE INDEX IF NOT EXISTS idx_api_keys_chat_id ON api_keys(chat_id);
    CREATE INDEX IF NOT EXISTS idx_logs_key_id ON request_logs(api_key_id);
    """)
    conn.commit()
    conn.close()


def ensure_existing_schema():
    """Import-compatible schema matching the existing database.py project."""
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        username TEXT DEFAULT '',
        first_name TEXT DEFAULT '',
        blocked INTEGER DEFAULT 0,
        api_enabled INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS access_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        username TEXT DEFAULT '',
        plan TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL,
        processed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        key_hash TEXT UNIQUE NOT NULL,
        key_name TEXT DEFAULT 'API KEY',
        plan TEXT DEFAULT 'custom',
        daily_limit INTEGER NOT NULL DEFAULT 1000,
        today_requests INTEGER NOT NULL DEFAULT 0,
        total_limit INTEGER,
        total_requests INTEGER NOT NULL DEFAULT 0,
        last_request_date TEXT,
        start_at TEXT,
        expires_at TEXT,
        rate_limit INTEGER,
        rate_window_start TEXT,
        rate_window_count INTEGER DEFAULT 0,
        last_used_at TEXT,
        status TEXT DEFAULT 'active',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS request_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key_id INTEGER,
        chat_id INTEGER,
        query TEXT,
        success INTEGER NOT NULL,
        status_code INTEGER NOT NULL,
        error TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)
    defaults = {
        "global_api_enabled": "1",
        "basic_daily": "1000", "basic_days": "30",
        "pro_daily": "10000", "pro_days": "30",
        "custom_daily": "50000", "custom_days": "30",
        "api_url": "https://krutik-cyber-expert-api.onrender.com",
        "welcome_text": "🔥 KRUTIK CYBER EXPERT API\n\nWelcome!",
        "support_text": "🆘 Contact the owner for support.",
        "howto_text": "Use GET /api/search with your API key and query.",
        "docs_text": "GET /api/search\nGET /api/status\nGET /api/stats",
    }
    for k, v in defaults.items():
        conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)", (k, v))
    conn.commit()
    conn.close()


ensure_existing_schema()
init_web_schema()


# ------------------------- Helpers ---------------------------

def setting(key, default=""):
    conn = db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = db()
    conn.execute("""INSERT INTO settings(key,value) VALUES (?,?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (key, str(value)))
    conn.commit()
    conn.close()


def owner_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not is_owner_session():
            abort(403)
        return fn(*args, **kwargs)
    return wrapped


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        uid = session.get("web_user_id")
        if not uid:
            return redirect(url_for("login", next=request.path))
        conn = db()
        user = conn.execute("SELECT * FROM web_users WHERE id=?", (uid,)).fetchone()
        conn.close()
        if not user or user["blocked"]:
            session.clear()
            flash("Your account is blocked or no longer available.", "error")
            return redirect(url_for("login"))
        return fn(user, *args, **kwargs)
    return wrapped


def is_owner_session():
    return bool(session.get("owner_authenticated"))


def audit(action, target="", user_id=None):
    conn = db()
    conn.execute("""INSERT INTO web_audit_logs(web_user_id,action,target,ip,created_at)
                    VALUES (?,?,?,?,?)""", (user_id, action, str(target), request.headers.get("X-Forwarded-For", request.remote_addr or ""), now_iso()))
    conn.commit()
    conn.close()


def get_chat_id(web_user_id):
    conn = db()
    row = conn.execute("SELECT chat_id FROM web_users WHERE id=?", (web_user_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return row["chat_id"]


def ensure_chat_user(web_user_id):
    """Give a web account a stable internal chat_id if it isn't linked to Telegram."""
    conn = db()
    row = conn.execute("SELECT chat_id,username,display_name FROM web_users WHERE id=?", (web_user_id,)).fetchone()
    if not row:
        conn.close()
        return None
    if row["chat_id"] is None:
        # Negative namespace avoids collision with real Telegram IDs.
        chat_id = -(10_000_000_000 + int(web_user_id))
        conn.execute("UPDATE web_users SET chat_id=? WHERE id=?", (chat_id, web_user_id))
        conn.execute("""INSERT OR IGNORE INTO users(chat_id,username,first_name,created_at)
                        VALUES (?,?,?,?)""", (chat_id, row["username"], row["display_name"], now_iso()))
        conn.commit()
    else:
        chat_id = row["chat_id"]
        conn.execute("""INSERT OR IGNORE INTO users(chat_id,username,first_name,created_at)
                        VALUES (?,?,?,?)""", (chat_id, row["username"], row["display_name"], now_iso()))
        conn.commit()
    conn.close()
    return chat_id


def telegram_notify(text, chat_id=None):
    """Optional Telegram notification; silently skips when BOT_TOKEN is unset."""
    token = BOT_TOKEN
    target = str(chat_id or OWNER_CHAT_ID).strip()
    if not token or not target:
        return False
    try:
        payload = json.dumps({"chat_id": int(target), "text": text}).encode()
        req = Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=8) as response:
            return response.status == 200
    except Exception:
        return False


def plan_config(plan):
    plan = plan.lower()
    return {
        "basic": (int(setting("basic_daily", "1000")), int(setting("basic_days", "30"))),
        "pro": (int(setting("pro_daily", "10000")), int(setting("pro_days", "30"))),
        "custom": (int(setting("custom_daily", "50000")), int(setting("custom_days", "30"))),
    }.get(plan, (0, 0))


def create_raw_api_key(chat_id, plan):
    daily, days = plan_config(plan)
    if daily <= 0 or days <= 0:
        raise ValueError("Invalid plan configuration")
    raw = "KCE_" + secrets.token_urlsafe(32).replace("-", "").replace("_", "")[:40]
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    created = datetime.now(timezone.utc)
    expires = created + timedelta(days=days)
    conn = db()
    conn.execute("""INSERT INTO api_keys(
        chat_id,key_hash,key_name,plan,daily_limit,today_requests,total_limit,total_requests,
        last_request_date,start_at,expires_at,rate_limit,rate_window_start,rate_window_count,
        last_used_at,status,created_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
        chat_id, key_hash, f"{plan.upper()} API KEY", plan, daily, 0, None, 0,
        created.date().isoformat(), created.isoformat(), expires.isoformat(), None, None, 0,
        None, "active", created.isoformat()
    ))
    conn.commit()
    conn.close()
    return raw


def refresh_key_statuses(conn=None):
    own = conn is None
    conn = conn or db()
    now = now_iso()
    conn.execute("UPDATE api_keys SET status='expired' WHERE status='active' AND expires_at IS NOT NULL AND expires_at <= ?", (now,))
    if own:
        conn.commit(); conn.close()


def key_rows_for_user(chat_id):
    conn = db(); refresh_key_statuses(conn)
    rows = conn.execute("SELECT * FROM api_keys WHERE chat_id=? ORDER BY id DESC", (chat_id,)).fetchall()
    conn.commit(); conn.close()
    return rows


def stats():
    conn = db(); refresh_key_statuses(conn)
    q = lambda sql: conn.execute(sql).fetchone()["c"]
    data = {
        "users": q("SELECT COUNT(*) c FROM users"),
        "blocked": q("SELECT COUNT(*) c FROM users WHERE blocked=1"),
        "keys": q("SELECT COUNT(*) c FROM api_keys"),
        "active_keys": q("SELECT COUNT(*) c FROM api_keys WHERE status='active'"),
        "revoked_keys": q("SELECT COUNT(*) c FROM api_keys WHERE status='revoked'"),
        "expired_keys": q("SELECT COUNT(*) c FROM api_keys WHERE status='expired'"),
        "requests": q("SELECT COUNT(*) c FROM request_logs"),
        "successful": q("SELECT COUNT(*) c FROM request_logs WHERE success=1"),
        "failed": q("SELECT COUNT(*) c FROM request_logs WHERE success=0"),
        "pending": q("SELECT COUNT(*) c FROM access_requests WHERE status='pending'"),
        "total_usage": conn.execute("SELECT COALESCE(SUM(total_requests),0) c FROM api_keys").fetchone()["c"],
    }
    conn.commit(); conn.close()
    data["global_api_enabled"] = setting("global_api_enabled", "1") == "1"
    return data



# ----------------------- Local Data Search --------------------

def load_json_records():
    """Load authorized JSON records from DATA_DIR/*.json.

    Supported formats:
      1) [ {"id": "...", "mobile": "...", ...}, ... ]
      2) {"data": [ ... ]}
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    for file_path in sorted(DATA_DIR.glob("*.json")):
        try:
            with file_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, list):
                source = payload
            elif isinstance(payload, dict):
                source = payload.get("data", [])
            else:
                source = []
            if isinstance(source, list):
                for item in source:
                    if isinstance(item, dict):
                        row = dict(item)
                        row["_dataset"] = file_path.name
                        records.append(row)
        except Exception as exc:
            app.logger.warning("JSON LOAD ERROR %s: %s", file_path, exc)
    return records


def searchable_text(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def search_local_data(query, limit=20):
    q = str(query or "").strip().casefold()
    if not q:
        return []
    limit = max(1, min(int(limit or 20), 100))
    results = []
    for row in load_json_records():
        if any(q in searchable_text(value).casefold() for value in row.values()):
            # Hide the internal dataset marker from the browser result.
            result = {k: v for k, v in row.items() if k != "_dataset"}
            results.append(result)
            if len(results) >= limit:
                break
    return results


def get_active_web_key(chat_id):
    conn = db()
    refresh_key_statuses(conn)
    row = conn.execute(
        "SELECT * FROM api_keys WHERE chat_id=? AND status='active' "
        "ORDER BY id DESC LIMIT 1",
        (chat_id,),
    ).fetchone()
    conn.commit()
    conn.close()
    return row


def consume_web_search(chat_id):
    """Consume one request from the user's active website API key.
    This mirrors the website-side limits without depending on the FastAPI process.
    """
    if setting("global_api_enabled", "1") != "1":
        return False, "api_access_disabled", None

    conn = db()
    refresh_key_statuses(conn)
    user = conn.execute(
        "SELECT * FROM users WHERE chat_id=?", (chat_id,)
    ).fetchone()
    key = conn.execute(
        "SELECT * FROM api_keys WHERE chat_id=? AND status='active' "
        "ORDER BY id DESC LIMIT 1", (chat_id,)
    ).fetchone()

    if not user:
        conn.close()
        return False, "user_not_found", None
    if user["blocked"]:
        conn.close()
        return False, "user_blocked", None
    if not user["api_enabled"]:
        conn.close()
        return False, "api_access_disabled", None
    if not key:
        conn.close()
        return False, "no_active_key", None

    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    today_requests = key["today_requests"]
    if key["last_request_date"] != today:
        today_requests = 0

    if key["daily_limit"] is not None and today_requests >= key["daily_limit"]:
        conn.close()
        return False, "daily_limit", key
    if key["total_limit"] is not None and key["total_requests"] >= key["total_limit"]:
        conn.close()
        return False, "total_limit", key

    new_today = today_requests + 1
    new_total = key["total_requests"] + 1
    conn.execute(
        """UPDATE api_keys
           SET today_requests=?, total_requests=?, last_request_date=?, last_used_at=?
           WHERE id=?""",
        (new_today, new_total, today, now.isoformat(), key["id"]),
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM api_keys WHERE id=?", (key["id"],)).fetchone()
    conn.close()
    return True, "ok", updated


@app.route("/search", methods=["GET", "POST"])
@login_required
def search_page(user):
    query = request.values.get("query", "").strip()
    limit = request.values.get("limit", "20").strip() or "20"
    try:
        limit = max(1, min(int(limit), 100))
    except ValueError:
        limit = 20

    results = []
    error = ""
    searched = False
    chat_id = ensure_chat_user(user["id"])

    if query:
        searched = True
        allowed, reason, _key = consume_web_search(chat_id)
        if not allowed:
            messages = {
                "api_access_disabled": "API access is currently disabled.",
                "user_blocked": "Your account is blocked.",
                "no_active_key": "You need an active API key before searching.",
                "daily_limit": "Your daily search limit has been reached.",
                "total_limit": "Your total search limit has been reached.",
                "user_not_found": "User account was not found.",
            }
            error = messages.get(reason, "Search is not available right now.")
        else:
            results = search_local_data(query, limit)
            audit("website_search", query, user["id"])

    return render_template(
        "search.html",
        user=user,
        query=query,
        limit=limit,
        results=results,
        error=error,
        searched=searched,
        data_dir=str(DATA_DIR),
        json_file_count=len(list(DATA_DIR.glob("*.json"))) if DATA_DIR.exists() else 0,
    )


@app.route("/api/site/search")
@login_required
def site_search_api(user):
    query = request.args.get("query", "").strip()
    if not query:
        return jsonify({"success": False, "error": "query_required"}), 400

    try:
        limit = max(1, min(int(request.args.get("limit", "20")), 100))
    except ValueError:
        limit = 20

    chat_id = ensure_chat_user(user["id"])
    allowed, reason, key = consume_web_search(chat_id)
    if not allowed:
        return jsonify({"success": False, "error": reason}), 403

    results = search_local_data(query, limit)
    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "usage": {
            "today": key["today_requests"],
            "daily_limit": key["daily_limit"],
            "total": key["total_requests"],
            "total_limit": key["total_limit"],
        },
    })


# -------------------------- Public ---------------------------

@app.context_processor
def inject_globals():
    return {
        "brand": BRAND,
        "app_name": APP_NAME,
        "owner": is_owner_session(),
        "logged_in": bool(session.get("web_user_id")),
        "setting": setting,
    }


@app.route("/")
def index():
    return render_template("index.html", plans=[
        ("basic", "Basic", int(setting("basic_daily", "1000")), int(setting("basic_days", "30"))),
        ("pro", "Pro", int(setting("pro_daily", "10000")), int(setting("pro_days", "30"))),
        ("custom", "Custom", int(setting("custom_daily", "50000")), int(setting("custom_days", "30"))),
    ])


@app.route("/health")
def health():
    try:
        conn = db(); conn.execute("SELECT 1").fetchone(); conn.close()
        return jsonify({"status": "ok", "service": APP_NAME})
    except Exception:
        return jsonify({"status": "error"}), 503


# --------------------------- Auth ----------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        display_name = request.form.get("display_name", "").strip() or username
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if len(username) < 3 or len(username) > 32 or not username.replace("_", "").isalnum():
            flash("Username must be 3-32 characters and use letters, numbers or underscore.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            conn = db()
            try:
                cur = conn.execute("""INSERT INTO web_users(username,password_hash,display_name,created_at)
                                     VALUES (?,?,?,?)""", (username, generate_password_hash(password), display_name, now_iso()))
                uid = cur.lastrowid
                conn.commit()
                session.clear(); session["web_user_id"] = uid
                audit("register", username, uid)
                flash("Account created successfully.", "success")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                flash("Username already exists.", "error")
            finally:
                conn.close()
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = db(); user = conn.execute("SELECT * FROM web_users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
        if user and not user["blocked"] and check_password_hash(user["password_hash"], password):
            conn.execute("UPDATE web_users SET last_login_at=? WHERE id=?", (now_iso(), user["id"]))
            conn.commit(); conn.close()
            session.clear(); session["web_user_id"] = user["id"]
            audit("login", username, user["id"])
            return redirect(request.args.get("next") or url_for("dashboard"))
        conn.close()
        flash("Invalid username/password or blocked account.", "error")
    return render_template("auth.html", mode="login")


@app.route("/logout")
def logout():
    uid = session.get("web_user_id")
    if uid: audit("logout", "", uid)
    session.clear(); return redirect(url_for("index"))


# -------------------------- User -----------------------------

@app.route("/dashboard")
@login_required
def dashboard(user):
    chat_id = ensure_chat_user(user["id"])
    keys = key_rows_for_user(chat_id)
    conn = db()
    requests = conn.execute("SELECT * FROM access_requests WHERE chat_id=? ORDER BY id DESC LIMIT 10", (chat_id,)).fetchall()
    logs = conn.execute("SELECT * FROM request_logs WHERE chat_id=? ORDER BY id DESC LIMIT 10", (chat_id,)).fetchall()
    conn.close()
    return render_template("dashboard.html", user=user, keys=keys, requests=requests, logs=logs)


@app.route("/plans")
@login_required
def plans(user):
    plans = [(p, p.title(), *plan_config(p)) for p in ("basic", "pro", "custom")]
    return render_template("plans.html", plans=plans)


@app.route("/request-access/<plan>", methods=["POST"])
@login_required
def request_access(user, plan):
    if plan not in {"basic", "pro", "custom"}:
        abort(404)
    chat_id = ensure_chat_user(user["id"])
    conn = db()
    pending = conn.execute("SELECT id FROM access_requests WHERE chat_id=? AND status='pending'", (chat_id,)).fetchone()
    if pending:
        conn.close(); flash("You already have a pending request.", "error"); return redirect(url_for("plans"))
    conn.execute("""INSERT INTO access_requests(chat_id,username,plan,status,created_at)
                    VALUES (?,?,?,'pending',?)""", (chat_id, user["username"], plan, now_iso()))
    conn.commit(); conn.close()
    audit("request_access", plan, user["id"])
    telegram_notify(
        "🔔 NEW API ACCESS REQUEST\n\n"
        f"User: @{user['username']}\n"
        f"Web account: {user['id']}\n"
        f"Plan: {plan.upper()}\n\n"
        "Open the website Owner Panel to approve/reject."
    )
    flash("Access request submitted. Please wait for owner approval.", "success")
    return redirect(url_for("dashboard"))


@app.route("/keys")
@login_required
def keys_page(user):
    return redirect(url_for("dashboard"))


@app.route("/docs")
def docs():
    return render_template("docs.html", api_url=setting("api_url", ""))


# -------------------------- Owner ----------------------------

@app.route("/owner/login", methods=["GET", "POST"])
def owner_login():
    if request.method == "POST":
        owner_id = request.form.get("owner_id", "").strip()
        secret = request.form.get("secret", "")
        expected = os.getenv("OWNER_WEB_SECRET", "").strip()
        if OWNER_CHAT_ID and owner_id == OWNER_CHAT_ID and expected and secrets.compare_digest(secret, expected):
            session.clear(); session["owner_authenticated"] = True
            audit("owner_login", owner_id)
            return redirect(url_for("admin_dashboard"))
        flash("Invalid owner credentials.", "error")
    return render_template("owner_login.html")


@app.route("/owner/logout")
def owner_logout():
    session.clear(); return redirect(url_for("index"))


@app.route("/admin")
@owner_required
def admin_dashboard():
    s = stats()
    conn = db()
    pending = conn.execute("""SELECT ar.*, u.first_name FROM access_requests ar
                              LEFT JOIN users u ON u.chat_id=ar.chat_id
                              WHERE ar.status='pending' ORDER BY ar.id DESC LIMIT 50""").fetchall()
    users = conn.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT 50").fetchall()
    keys = conn.execute("SELECT * FROM api_keys ORDER BY id DESC LIMIT 50").fetchall()
    logs = conn.execute("SELECT * FROM request_logs ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    return render_template("admin.html", stats=s, pending=pending, users=users, keys=keys, logs=logs,
                           api_enabled=setting("global_api_enabled", "1") == "1")


@app.route("/admin/request/<int:request_id>/<decision>", methods=["POST"])
@owner_required
def decide_request(request_id, decision):
    if decision not in {"approve", "reject"}: abort(404)
    conn = db()
    row = conn.execute("SELECT * FROM access_requests WHERE id=?", (request_id,)).fetchone()
    if not row or row["status"] != "pending":
        conn.close(); flash("Request not found or already processed.", "error"); return redirect(url_for("admin_dashboard"))
    if decision == "approve":
        raw = create_raw_api_key(row["chat_id"], row["plan"])
        status = "approved"
        telegram_notify(
            "🎉 API ACCESS APPROVED\n\n"
            f"Plan: {row['plan'].upper()}\n\n"
            "🔑 Your API key:\n" + raw + "\n\n"
            "Keep this key private." ,
            row["chat_id"] if row["chat_id"] > 0 else None,
        )
        flash(f"Request #{request_id} approved. New API key: {raw}", "success")
        audit("approve_request", request_id)
    else:
        raw = None; status = "rejected"
        telegram_notify(
            "❌ API ACCESS REQUEST REJECTED\n\n"
            f"Plan: {row['plan'].upper()}\n"
            "You can submit a new request later.",
            row["chat_id"] if row["chat_id"] > 0 else None,
        )
        flash(f"Request #{request_id} rejected.", "success")
        audit("reject_request", request_id)
    conn.execute("UPDATE access_requests SET status=?, processed_at=? WHERE id=?", (status, now_iso(), request_id))
    conn.commit(); conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/key/<int:key_id>/<action>", methods=["POST"])
@owner_required
def key_action(key_id, action):
    if action not in {"revoke", "activate"}: abort(404)
    conn = db()
    status = "revoked" if action == "revoke" else "active"
    conn.execute("UPDATE api_keys SET status=? WHERE id=?", (status, key_id))
    conn.commit(); conn.close()
    audit(action + "_key", key_id)
    flash(f"Key #{key_id} set to {status}.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/user/<int:chat_id>/<action>", methods=["POST"])
@owner_required
def user_action(chat_id, action):
    if action not in {"block", "unblock", "disable_api", "enable_api"}: abort(404)
    conn = db()
    if action == "block":
        conn.execute("UPDATE users SET blocked=1 WHERE chat_id=?", (chat_id,))
    elif action == "unblock":
        conn.execute("UPDATE users SET blocked=0 WHERE chat_id=?", (chat_id,))
    elif action == "disable_api":
        conn.execute("UPDATE users SET api_enabled=0 WHERE chat_id=?", (chat_id,))
    else:
        conn.execute("UPDATE users SET api_enabled=1 WHERE chat_id=?", (chat_id,))
    conn.commit(); conn.close()
    audit(action, chat_id)
    flash("User updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/api-toggle", methods=["POST"])
@owner_required
def api_toggle():
    enabled = request.form.get("enabled") == "1"
    set_setting("global_api_enabled", "1" if enabled else "0")
    audit("global_api_toggle", enabled)
    flash("Global API status updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/settings", methods=["GET", "POST"])
@owner_required
def admin_settings():
    if request.method == "POST":
        allowed = ["basic_daily", "basic_days", "pro_daily", "pro_days", "custom_daily", "custom_days", "api_url", "welcome_text", "support_text", "howto_text", "docs_text"]
        conn = db()
        for key in allowed:
            if key in request.form:
                value = request.form.get(key, "").strip()
                if key.endswith("_daily") or key.endswith("_days"):
                    if not value.isdigit() or int(value) <= 0:
                        continue
                conn.execute("""INSERT INTO settings(key,value) VALUES (?,?)
                                ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (key, value))
        conn.commit(); conn.close()
        audit("update_settings")
        flash("Settings saved.", "success")
    return render_template("settings.html", settings={
        k: setting(k, "") for k in ["basic_daily","basic_days","pro_daily","pro_days","custom_daily","custom_days","api_url","welcome_text","support_text","howto_text","docs_text"]
    })


# ---------------------- API-compatible helpers ---------------
# These endpoints are for the website's frontend and do not replace the existing FastAPI API.

@app.route("/api/site/stats")
def site_stats():
    return jsonify(stats())


@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", code=403, message="Access denied."), 403


@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="Page not found."), 404


@app.errorhandler(500)
def server_error(_):
    return render_template("error.html", code=500, message="Internal server error."), 500


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False)
