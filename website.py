import os
import json
import re
import sqlite3
import hashlib
from pathlib import Path
from flask import Flask, request, jsonify, render_template, abort

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INDEX_DIR = BASE_DIR / "index"
DB_PATH = INDEX_DIR / "search.db"

APP_NAME = "KRUTIK CYBER EXPERT API"

app = Flask(__name__, template_folder="templates", static_folder="static")


# ============================================================
# DATABASE
# ============================================================

def get_db():
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(
        str(DB_PATH),
        timeout=60,
        check_same_thread=False
    )

    db.row_factory = sqlite3.Row

    db.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mobile TEXT NOT NULL,
            record_json TEXT NOT NULL
        )
    """)

    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_mobile
        ON records(mobile)
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    db.commit()
    return db


# ============================================================
# NUMBER NORMALIZATION
# ============================================================

def normalize_number(value):
    if value is None:
        return ""

    value = str(value).strip()

    # Keep digits only
    value = re.sub(r"\D", "", value)

    # Indian +91 numbers
    if len(value) == 12 and value.startswith("91"):
        value = value[2:]

    if len(value) == 11 and value.startswith("0"):
        value = value[1:]

    return value


def extract_numbers(text):
    if not text:
        return []

    # newline / comma / semicolon / space separated
    parts = re.split(r"[\s,;]+", text.strip())

    numbers = []

    for part in parts:
        number = normalize_number(part)

        if number and number not in numbers:
            numbers.append(number)

    return numbers


# ============================================================
# JSON PARSER
# ============================================================

def parse_json_file(path):
    try:
        raw = path.read_text(
            encoding="utf-8-sig",
            errors="ignore"
        ).strip()

        if not raw:
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:

            # JSON Lines fallback
            records = []

            for line in raw.splitlines():
                line = line.strip()

                if not line:
                    continue

                try:
                    obj = json.loads(line)

                    if isinstance(obj, dict):
                        records.append(obj)

                except Exception:
                    continue

            return records

        # Direct list
        if isinstance(data, list):
            return [
                x for x in data
                if isinstance(x, dict)
            ]

        # Common wrappers
        if isinstance(data, dict):

            for key in (
                "data",
                "records",
                "results",
                "items"
            ):
                value = data.get(key)

                if isinstance(value, list):
                    return [
                        x for x in value
                        if isinstance(x, dict)
                    ]

            # Single record
            if isinstance(data, dict):
                return [data]

        return []

    except Exception as e:
        print(f"[FILE ERROR] {path}: {e}")
        return []


# ============================================================
# DATA SIGNATURE
# ============================================================

def get_data_signature():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(DATA_DIR.rglob("*.json"))

    parts = []

    for path in files:
        try:
            stat = path.stat()

            relative = str(
                path.relative_to(DATA_DIR)
            )

            parts.append(
                f"{relative}|{stat.st_size}|{stat.st_mtime_ns}"
            )

        except Exception:
            pass

    raw = "\n".join(parts)

    return hashlib.sha256(
        raw.encode()
    ).hexdigest()


# ============================================================
# INDEX
# ============================================================

def rebuild_index():

    print("=" * 60)
    print("BUILDING SEARCH INDEX")
    print("=" * 60)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    db = get_db()

    try:
        db.execute("DELETE FROM records")
        db.execute("DELETE FROM meta")
        db.commit()

        files = sorted(DATA_DIR.rglob("*.json"))

        total_records = 0
        mobile_records = 0
        failed_files = 0

        for path in files:

            print(f"[READING] {path}")

            records = parse_json_file(path)

            if not records:
                print(
                    f"[EMPTY] {path.name} -> 0 records"
                )

            file_count = 0
            file_mobile_count = 0

            rows = []

            for record in records:

                total_records += 1
                file_count += 1

                mobile = normalize_number(
                    record.get("mobile", "")
                )

                if not mobile:
                    continue

                # Store only server-side.
                # Browser never receives database directly.
                record_copy = dict(record)

                record_copy["_dataset"] = path.name

                rows.append(
                    (
                        mobile,
                        json.dumps(
                            record_copy,
                            ensure_ascii=False,
                            separators=(",", ":")
                        )
                    )
                )

                mobile_records += 1
                file_mobile_count += 1

            if rows:

                db.executemany(
                    """
                    INSERT INTO records
                    (mobile, record_json)
                    VALUES (?, ?)
                    """,
                    rows
                )

            print(
                f"[OK] {path.name} | "
                f"records={file_count} | "
                f"mobile={file_mobile_count}"
            )

        signature = get_data_signature()

        db.execute(
            """
            INSERT INTO meta(key, value)
            VALUES (?, ?)
            """,
            ("signature", signature)
        )

        db.execute(
            """
            INSERT INTO meta(key, value)
            VALUES (?, ?)
            """,
            ("indexed_records", str(total_records))
        )

        db.execute(
            """
            INSERT INTO meta(key, value)
            VALUES (?, ?)
            """,
            ("mobile_records", str(mobile_records))
        )

        db.execute(
            """
            INSERT INTO meta(key, value)
            VALUES (?, ?)
            """,
            ("json_files", str(len(files)))
        )

        db.execute(
            """
            INSERT INTO meta(key, value)
            VALUES (?, ?)
            """,
            ("failed_files", str(failed_files))
        )

        db.commit()

        print("=" * 60)
        print("INDEX READY")
        print(f"JSON files     : {len(files)}")
        print(f"Records        : {total_records}")
        print(f"Mobile records : {mobile_records}")
        print("=" * 60)

        return {
            "json_files": len(files),
            "total_records": total_records,
            "mobile_records": mobile_records,
            "failed_files": failed_files
        }

    finally:
        db.close()


def index_is_ready():

    if not DB_PATH.exists():
        return False

    try:
        db = get_db()

        row = db.execute(
            """
            SELECT value
            FROM meta
            WHERE key='signature'
            """
        ).fetchone()

        if not row:
            db.close()
            return False

        current = get_data_signature()

        ready = row["value"] == current

        db.close()

        return ready

    except Exception:
        return False


def ensure_index():

    if not index_is_ready():
        rebuild_index()


# ============================================================
# SEARCH
# ============================================================

def search_numbers(numbers):

    if not numbers:
        return []

    ensure_index()

    db = get_db()

    try:
        placeholders = ",".join(
            ["?"] * len(numbers)
        )

        query = f"""
            SELECT mobile, record_json
            FROM records
            WHERE mobile IN ({placeholders})
        """

        rows = db.execute(
            query,
            numbers
        ).fetchall()

        found = {}

        for row in rows:

            mobile = row["mobile"]

            try:
                record = json.loads(
                    row["record_json"]
                )

            except Exception:
                continue

            found.setdefault(
                mobile,
                []
            ).append(record)

        results = []

        for number in numbers:

            matches = found.get(
                number,
                []
            )

            if matches:
                results.append({
                    "number": number,
                    "found": True,
                    "results": matches
                })
            else:
                results.append({
                    "number": number,
                    "found": False,
                    "results": []
                })

        return results

    finally:
        db.close()


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def home():
    return render_template(
        "index.html",
        app_name=APP_NAME
    )


@app.route("/health", methods=["GET", "HEAD"])
def health():

    try:
        db = get_db()

        files = list(
            DATA_DIR.rglob("*.json")
        ) if DATA_DIR.exists() else []

        row = db.execute(
            """
            SELECT value
            FROM meta
            WHERE key='mobile_records'
            """
        ).fetchone()

        mobile_records = (
            int(row["value"])
            if row else 0
        )

        db.close()

        return jsonify({
            "ok": True,
            "status": "online",
            "json_files": len(files),
            "index_ready": index_is_ready(),
            "indexed_mobile_records": mobile_records
        })

    except Exception as e:

        return jsonify({
            "ok": False,
            "status": "error",
            "error": str(e)
        }), 500


@app.route("/status")
def status():

    try:

        files = sorted(
            DATA_DIR.rglob("*.json")
        ) if DATA_DIR.exists() else []

        db = get_db()

        row = db.execute(
            """
            SELECT value
            FROM meta
            WHERE key='indexed_records'
            """
        ).fetchone()

        indexed_records = (
            int(row["value"])
            if row else 0
        )

        row = db.execute(
            """
            SELECT value
            FROM meta
            WHERE key='mobile_records'
            """
        ).fetchone()

        mobile_records = (
            int(row["value"])
            if row else 0
        )

        db.close()

        return jsonify({
            "ok": True,
            "json_files": len(files),
            "index_ready": index_is_ready(),
            "indexed_records": indexed_records,
            "indexed_mobile_records": mobile_records
        })

    except Exception as e:

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@app.route("/rebuild", methods=["POST"])
def rebuild():

    try:

        result = rebuild_index()

        return jsonify({
            "ok": True,
            "message": "Index rebuilt successfully",
            **result
        })

    except Exception as e:

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@app.route("/search", methods=["POST"])
def search():

    try:

        # JSON request
        if request.is_json:

            body = request.get_json(
                silent=True
            ) or {}

            raw_numbers = body.get(
                "numbers",
                body.get("number", "")
            )

        else:

            raw_numbers = request.form.get(
                "numbers",
                request.form.get("number", "")
            )

        if isinstance(raw_numbers, list):

            text = " ".join(
                str(x)
                for x in raw_numbers
            )

        else:
            text = str(raw_numbers)

        numbers = extract_numbers(text)

        if not numbers:

            return jsonify({
                "ok": False,
                "error": "Please enter at least one number."
            }), 400

        if len(numbers) > 100:

            return jsonify({
                "ok": False,
                "error": "Maximum 100 numbers per request."
            }), 400

        results = search_numbers(numbers)

        found_count = sum(
            1
            for item in results
            if item["found"]
        )

        return jsonify({
            "ok": True,
            "searched": len(numbers),
            "found": found_count,
            "results": results
        })

    except Exception as e:

        print(
            f"[SEARCH ERROR] {e}"
        )

        return jsonify({
            "ok": False,
            "error": "Search failed."
        }), 500


# ============================================================
# BLOCK DIRECT DATA ACCESS
# ============================================================

@app.route("/data/<path:filename>")
def block_data(filename):
    abort(404)


@app.route("/index/<path:filename>")
def block_index(filename):
    abort(404)


# ============================================================
# STARTUP
# ============================================================

get_db().close()


if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
