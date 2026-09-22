import os
import json
import re
import sqlite3
import hashlib
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request


# ============================================================
# KRUTIK CYBER EXPERT
# HIGH SPEED JSON SEARCH
# ============================================================

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INDEX_DIR = BASE_DIR / "index"
DB_PATH = INDEX_DIR / "search.db"

MAX_NUMBERS = 100

INDEX_DIR.mkdir(parents=True, exist_ok=True)

index_lock = threading.Lock()


# ============================================================
# DATABASE
# ============================================================

def get_db():
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=120,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-50000")

    return conn


def create_database():
    conn = get_db()

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mobile TEXT NOT NULL,
                record_json TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_records_mobile
            ON records(mobile)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        conn.commit()

    finally:
        conn.close()


def get_meta(key):
    create_database()

    conn = get_db()

    try:
        row = conn.execute(
            "SELECT value FROM metadata WHERE key = ?",
            (key,)
        ).fetchone()

        return row["value"] if row else None

    finally:
        conn.close()


def set_meta(key, value):
    create_database()

    conn = get_db()

    try:
        conn.execute("""
            INSERT INTO metadata(key, value)
            VALUES (?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
        """, (key, str(value)))

        conn.commit()

    finally:
        conn.close()


# ============================================================
# NUMBER
# ============================================================

def normalize_number(value):
    if value is None:
        return ""

    return re.sub(r"\D", "", str(value))


def extract_numbers(value):
    if isinstance(value, list):
        parts = value
    else:
        parts = re.split(
            r"[\s,;]+",
            str(value or "")
        )

    result = []

    for part in parts:
        number = normalize_number(part)

        if number and number not in result:
            result.append(number)

    return result


# ============================================================
# JSON FILE DISCOVERY
# ============================================================

def get_json_files():
    """
    Recursive search.

    So this also works:

    data/a.json
    data/folder1/b.json
    data/folder2/c.json
    """

    if not DATA_DIR.exists():
        return []

    return sorted(
        DATA_DIR.rglob("*.json")
    )


# ============================================================
# DATA SIGNATURE
# ============================================================

def get_data_signature():
    files = get_json_files()

    if not files:
        return "NO_JSON_FILES"

    parts = []

    for path in files:

        try:
            stat = path.stat()

            relative = path.relative_to(
                DATA_DIR
            )

            parts.append(
                f"{relative}|"
                f"{stat.st_size}|"
                f"{stat.st_mtime_ns}"
            )

        except Exception:
            continue

    raw = "\n".join(parts)

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# ROBUST JSON PARSER
# ============================================================

def parse_json_content(content):
    """
    Supports:

    1. Direct list

       [
         {...},
         {...}
       ]

    2. data wrapper

       {
         "data": [...]
       }

    3. records wrapper

       {
         "records": [...]
       }

    4. results wrapper

       {
         "results": [...]
       }

    5. JSON string containing JSON

    """

    if isinstance(content, str):

        stripped = content.strip()

        if stripped:

            try:
                decoded = json.loads(
                    stripped
                )

                return parse_json_content(
                    decoded
                )

            except Exception:
                pass

        return []

    if isinstance(content, list):

        return [
            x for x in content
            if isinstance(x, dict)
        ]

    if isinstance(content, dict):

        # Most common wrappers
        for key in (
            "data",
            "records",
            "results",
            "items"
        ):

            value = content.get(key)

            if isinstance(value, list):

                return [
                    x for x in value
                    if isinstance(x, dict)
                ]

        # If dictionary itself looks like
        # one record
        if "mobile" in content:

            return [content]

        return []

    return []


def load_json_file(path):
    """
    Read one JSON file safely.
    """

    with path.open(
        "r",
        encoding="utf-8-sig"
    ) as f:

        raw = f.read()

    if not raw.strip():
        return []

    try:

        content = json.loads(raw)

    except json.JSONDecodeError:

        # Sometimes data can contain a JSON
        # document inside a quoted string.
        content = raw

    return parse_json_content(
        content
    )


# ============================================================
# INDEX CURRENT?
# ============================================================

def index_is_current():
    create_database()

    current = get_data_signature()
    stored = get_meta("data_signature")
    count = get_meta("record_count")

    return (
        stored is not None
        and count is not None
        and current == stored
    )


# ============================================================
# BUILD INDEX
# ============================================================

def build_index(force=False):

    with index_lock:

        create_database()

        files = get_json_files()

        current_signature = (
            get_data_signature()
        )

        if not force and index_is_current():

            app.logger.info(
                "INDEX ALREADY CURRENT"
            )

            return True

        app.logger.info("=" * 70)
        app.logger.info(
            "KRUTIK CYBER EXPERT - INDEX BUILD"
        )
        app.logger.info("=" * 70)

        app.logger.info(
            "BASE DIR: %s",
            BASE_DIR
        )

        app.logger.info(
            "DATA DIR: %s",
            DATA_DIR
        )

        app.logger.info(
            "JSON FILES FOUND: %d",
            len(files)
        )

        conn = get_db()

        total_records = 0
        indexed_records = 0
        failed_files = 0
        files_with_records = 0
        files_without_records = 0

        file_report = []

        try:

            conn.execute("BEGIN")

            conn.execute(
                "DELETE FROM records"
            )

            for path in files:

                try:

                    relative_name = str(
                        path.relative_to(
                            DATA_DIR
                        )
                    )

                    app.logger.info(
                        "[READING] %s",
                        relative_name
                    )

                    records = load_json_file(
                        path
                    )

                    record_count = len(
                        records
                    )

                    total_records += (
                        record_count
                    )

                    if record_count > 0:

                        files_with_records += 1

                    else:

                        files_without_records += 1

                    valid_mobile = 0

                    batch = []

                    for record in records:

                        mobile = normalize_number(
                            record.get(
                                "mobile"
                            )
                        )

                        if not mobile:
                            continue

                        valid_mobile += 1

                        record_json = json.dumps(
                            record,
                            ensure_ascii=False,
                            separators=(
                                ",",
                                ":"
                            )
                        )

                        batch.append(
                            (
                                mobile,
                                record_json
                            )
                        )

                    if batch:

                        conn.executemany(
                            """
                            INSERT INTO records(
                                mobile,
                                record_json
                            )
                            VALUES (?, ?)
                            """,
                            batch
                        )

                        indexed_records += len(
                            batch
                        )

                    file_report.append({
                        "file": relative_name,
                        "records": record_count,
                        "mobile_records": valid_mobile
                    })

                    app.logger.info(
                        "[OK] %s | records=%d | mobile=%d",
                        relative_name,
                        record_count,
                        valid_mobile
                    )

                except Exception as exc:

                    failed_files += 1

                    file_report.append({
                        "file": str(
                            path.relative_to(
                                DATA_DIR
                            )
                        ),
                        "records": 0,
                        "mobile_records": 0,
                        "error": str(exc)
                    })

                    app.logger.exception(
                        "[FILE ERROR] %s",
                        path.name
                    )

            # ------------------------------------------------
            # Metadata
            # ------------------------------------------------

            metadata = {
                "data_signature":
                    current_signature,

                "record_count":
                    indexed_records,

                "total_records":
                    total_records,

                "failed_files":
                    failed_files,

                "files_with_records":
                    files_with_records,

                "files_without_records":
                    files_without_records
            }

            for key, value in metadata.items():

                conn.execute("""
                    INSERT INTO metadata(
                        key,
                        value
                    )
                    VALUES (?, ?)

                    ON CONFLICT(key)
                    DO UPDATE SET
                        value = excluded.value
                """, (
                    key,
                    str(value)
                ))

            conn.commit()

            app.logger.info("=" * 70)
            app.logger.info(
                "INDEX BUILD COMPLETE"
            )
            app.logger.info(
                "FILES: %d",
                len(files)
            )
            app.logger.info(
                "TOTAL RECORDS: %d",
                total_records
            )
            app.logger.info(
                "MOBILE RECORDS: %d",
                indexed_records
            )
            app.logger.info(
                "FAILED FILES: %d",
                failed_files
            )
            app.logger.info("=" * 70)

            return True

        except Exception:

            conn.rollback()

            app.logger.exception(
                "INDEX BUILD FAILED"
            )

            return False

        finally:

            conn.close()


# ============================================================
# FAST SEARCH
# ============================================================

def search_database(numbers):

    if not numbers:
        return []

    conn = get_db()

    try:

        placeholders = ",".join(
            "?" for _ in numbers
        )

        sql = f"""
            SELECT mobile, record_json
            FROM records
            WHERE mobile IN ({placeholders})
        """

        rows = conn.execute(
            sql,
            numbers
        ).fetchall()

        results = []

        for row in rows:

            try:

                record = json.loads(
                    row["record_json"]
                )

                results.append(
                    record
                )

            except Exception:
                continue

        return results

    finally:

        conn.close()


# ============================================================
# INITIALIZATION
# ============================================================

def initialize():

    try:

        create_database()

        app.logger.info(
            "DATABASE READY"
        )

    except Exception:

        app.logger.exception(
            "DATABASE INITIALIZATION ERROR"
        )


initialize()


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    try:

        create_database()

        files = get_json_files()

        record_count = int(
            get_meta(
                "record_count"
            ) or 0
        )

        return jsonify({
            "ok": True,
            "status": "online",
            "json_files": len(files),
            "index_ready":
                index_is_current(),
            "indexed_records":
                record_count
        })

    except Exception as exc:

        app.logger.exception(
            "HEALTH ERROR"
        )

        return jsonify({
            "ok": False,
            "status": "error",
            "error": str(exc)
        }), 500


# ============================================================
# STATUS / DIAGNOSTICS
# ============================================================

@app.route("/status")
def status():

    try:

        create_database()

        files = get_json_files()

        report = []

        for path in files:

            item = {
                "file": str(
                    path.relative_to(
                        DATA_DIR
                    )
                )
            }

            try:

                records = load_json_file(
                    path
                )

                mobile_count = 0

                for record in records:

                    if normalize_number(
                        record.get(
                            "mobile"
                        )
                    ):
                        mobile_count += 1

                item["records"] = len(
                    records
                )

                item["mobile_records"] = (
                    mobile_count
                )

                item["status"] = "ok"

            except Exception as exc:

                item["records"] = 0
                item["mobile_records"] = 0
                item["status"] = "error"
                item["error"] = str(exc)

            report.append(item)

        return jsonify({
            "ok": True,

            "json_files": len(files),

            "index_ready":
                index_is_current(),

            "indexed_records": int(
                get_meta(
                    "record_count"
                ) or 0
            ),

            "total_records": int(
                get_meta(
                    "total_records"
                ) or 0
            ),

            "failed_files": int(
                get_meta(
                    "failed_files"
                ) or 0
            ),

            "files": report
        })

    except Exception as exc:

        app.logger.exception(
            "STATUS ERROR"
        )

        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 500


# ============================================================
# FORCE REBUILD
# ============================================================

@app.route(
    "/rebuild",
    methods=["POST"]
)
def rebuild():

    try:

        success = build_index(
            force=True
        )

        if not success:

            return jsonify({
                "ok": False,
                "error":
                    "Index rebuild failed"
            }), 500

        return jsonify({
            "ok": True,
            "message":
                "Index rebuilt successfully",
            "indexed_records": int(
                get_meta(
                    "record_count"
                ) or 0
            )
        })

    except Exception as exc:

        app.logger.exception(
            "REBUILD ERROR"
        )

        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 500


# ============================================================
# SEARCH
# ============================================================

@app.route(
    "/search",
    methods=["POST"]
)
def search():

    try:

        body = request.get_json(
            silent=True
        )

        if not isinstance(
            body,
            dict
        ):

            return jsonify({
                "ok": False,
                "error":
                    "Invalid JSON request"
            }), 400

        numbers = extract_numbers(
            body.get(
                "numbers"
            )
        )

        if not numbers:

            return jsonify({
                "ok": False,
                "error":
                    "Enter at least one number"
            }), 400

        if len(numbers) > MAX_NUMBERS:

            return jsonify({
                "ok": False,
                "error":
                    f"Maximum {MAX_NUMBERS} numbers allowed"
            }), 400

        # Build index only when required.
        if not index_is_current():

            app.logger.info(
                "INDEX NOT READY"
            )

            app.logger.info(
                "BUILDING INDEX..."
            )

            if not build_index():

                return jsonify({
                    "ok": False,
                    "error":
                        "Could not build search index"
                }), 500

        results = search_database(
            numbers
        )

        return jsonify({
            "ok": True,
            "searched": len(numbers),
            "found": len(results),
            "results": results
        })

    except Exception as exc:

        app.logger.exception(
            "SEARCH ERROR"
        )

        return jsonify({
            "ok": False,
            "error":
                "Internal Server Error",
            "details": str(exc)
        }), 500


# ============================================================
# BLOCK DATA DOWNLOAD
# ============================================================

@app.route("/data")
@app.route("/data/")
@app.route("/data/<path:filename>")
def block_data(filename=None):

    return jsonify({
        "ok": False,
        "error": "Access denied"
    }), 403


# ============================================================
# BLOCK INDEX DOWNLOAD
# ============================================================

@app.route("/index")
@app.route("/index/")
@app.route("/index/<path:filename>")
def block_index(filename=None):

    return jsonify({
        "ok": False,
        "error": "Access denied"
    }), 403


# ============================================================
# LOCAL
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    print("=" * 70)
    print(
        "KRUTIK CYBER EXPERT"
    )
    print(
        "HIGH SPEED JSON SEARCH"
    )
    print("=" * 70)

    print(
        "BASE:",
        BASE_DIR
    )

    print(
        "DATA:",
        DATA_DIR
    )

    print(
        "DATABASE:",
        DB_PATH
    )

    print(
        "JSON FILES:",
        len(get_json_files())
    )

    print("=" * 70)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
