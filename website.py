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
# HIGH-SPEED JSON SEARCH WEBSITE
# ============================================================

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INDEX_DIR = BASE_DIR / "index"
DB_PATH = INDEX_DIR / "search.db"

MAX_NUMBERS = 100

INDEX_DIR.mkdir(parents=True, exist_ok=True)

_index_lock = threading.Lock()


# ============================================================
# DATABASE
# ============================================================

def get_db():
    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=60,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    # Faster reads
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


# ============================================================
# NUMBER NORMALIZATION
# ============================================================

def normalize_number(value):
    if value is None:
        return ""

    return re.sub(r"\D", "", str(value))


def extract_numbers(value):
    """
    Supports:

    9377711765

    9377711765,9812345674

    9377711765
    9812345674

    9377711765 9812345674

    9377711765;9812345674
    """

    if isinstance(value, list):
        parts = value
    else:
        parts = re.split(r"[\s,;]+", str(value or ""))

    numbers = []

    for part in parts:
        number = normalize_number(part)

        if number and number not in numbers:
            numbers.append(number)

    return numbers


# ============================================================
# JSON FILE SIGNATURE
# ============================================================

def get_data_signature():
    """
    Creates a signature from JSON filenames + modification times +
    file sizes.

    If data changes, the index will be rebuilt.
    """

    if not DATA_DIR.exists():
        return "NO_DATA_DIRECTORY"

    files = sorted(DATA_DIR.glob("*.json"))

    if not files:
        return "NO_JSON_FILES"

    parts = []

    for file_path in files:
        try:
            stat = file_path.stat()

            parts.append(
                f"{file_path.name}|"
                f"{stat.st_size}|"
                f"{stat.st_mtime_ns}"
            )

        except OSError:
            continue

    raw = "\n".join(parts)

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# JSON LOADER
# ============================================================

def load_json_file(file_path):
    """
    Supports the exact format:

    [
        {
            "id": "RECORD-000001",
            "mobile": "9377711765",
            "name": "ARIFBHAI KASMANI",
            "pincode": "361001",
            "city": "Jamnagar",
            "address": "11"
        }
    ]

    Also supports:

    {
        "data": [
            {...}
        ]
    }
    """

    with file_path.open(
        "r",
        encoding="utf-8-sig"
    ) as file:

        content = json.load(file)

    if isinstance(content, list):
        records = content

    elif isinstance(content, dict):
        records = content.get("data", [])

    else:
        return []

    if not isinstance(records, list):
        return []

    return [
        record
        for record in records
        if isinstance(record, dict)
    ]


# ============================================================
# INDEX BUILD
# ============================================================

def get_metadata(key):
    conn = get_db()

    try:
        row = conn.execute(
            "SELECT value FROM metadata WHERE key = ?",
            (key,)
        ).fetchone()

        return row["value"] if row else None

    finally:
        conn.close()


def set_metadata(key, value):
    conn = get_db()

    try:
        conn.execute("""
            INSERT INTO metadata(key, value)
            VALUES (?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value
        """, (key, value))

        conn.commit()

    finally:
        conn.close()


def index_is_current():
    current_signature = get_data_signature()

    stored_signature = get_metadata("data_signature")

    record_count = get_metadata("record_count")

    return (
        current_signature == stored_signature
        and record_count is not None
    )


def build_index():
    """
    Build SQLite index from all JSON files.

    This happens only when:
    - database doesn't exist
    - JSON files changed
    - index is missing
    """

    with _index_lock:

        create_database()

        current_signature = get_data_signature()

        if index_is_current():
            app.logger.info(
                "INDEX OK - using existing SQLite index"
            )
            return True

        app.logger.info("=" * 60)
        app.logger.info(
            "BUILDING HIGH-SPEED SEARCH INDEX"
        )
        app.logger.info(
            "DATA DIRECTORY: %s",
            DATA_DIR
        )
        app.logger.info("=" * 60)

        if not DATA_DIR.exists():
            app.logger.error(
                "DATA DIRECTORY NOT FOUND"
            )
            return False

        json_files = sorted(
            DATA_DIR.glob("*.json")
        )

        app.logger.info(
            "JSON FILES FOUND: %d",
            len(json_files)
        )

        conn = get_db()

        try:
            # Temporary transaction
            conn.execute("BEGIN")

            conn.execute(
                "DELETE FROM records"
            )

            total_records = 0
            indexed_records = 0
            failed_files = 0

            for file_path in json_files:

                app.logger.info(
                    "[INDEXING] %s",
                    file_path.name
                )

                try:
                    records = load_json_file(
                        file_path
                    )

                    total_records += len(records)

                    batch = []

                    for record in records:

                        mobile = normalize_number(
                            record.get("mobile", "")
                        )

                        if not mobile:
                            continue

                        record_json = json.dumps(
                            record,
                            ensure_ascii=False,
                            separators=(",", ":")
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

                        indexed_records += len(batch)

                except Exception as exc:

                    failed_files += 1

                    app.logger.exception(
                        "[JSON ERROR] %s: %s",
                        file_path.name,
                        exc
                    )

            conn.execute(
                """
                INSERT INTO metadata(key, value)
                VALUES (?, ?)
                ON CONFLICT(key)
                DO UPDATE SET value=excluded.value
                """,
                (
                    "data_signature",
                    current_signature
                )
            )

            conn.execute(
                """
                INSERT INTO metadata(key, value)
                VALUES (?, ?)
                ON CONFLICT(key)
                DO UPDATE SET value=excluded.value
                """,
                (
                    "record_count",
                    str(indexed_records)
                )
            )

            conn.execute(
                """
                INSERT INTO metadata(key, value)
                VALUES (?, ?)
                ON CONFLICT(key)
                DO UPDATE SET value=excluded.value
                """,
                (
                    "total_records",
                    str(total_records)
                )
            )

            conn.execute(
                """
                INSERT INTO metadata(key, value)
                VALUES (?, ?)
                ON CONFLICT(key)
                DO UPDATE SET value=excluded.value
                """,
                (
                    "failed_files",
                    str(failed_files)
                )
            )

            conn.commit()

            app.logger.info("=" * 60)
            app.logger.info(
                "INDEX READY"
            )
            app.logger.info(
                "FILES: %d",
                len(json_files)
            )
            app.logger.info(
                "TOTAL RECORDS: %d",
                total_records
            )
            app.logger.info(
                "INDEXED RECORDS: %d",
                indexed_records
            )
            app.logger.info(
                "FAILED FILES: %d",
                failed_files
            )
            app.logger.info("=" * 60)

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
# SEARCH
# ============================================================

def search_database(numbers):
    """
    Extremely fast indexed SQLite lookup.

    No JSON files are read during normal searches.
    """

    if not numbers:
        return []

    conn = get_db()

    try:
        placeholders = ",".join(
            "?" for _ in numbers
        )

        query = f"""
            SELECT mobile, record_json
            FROM records
            WHERE mobile IN ({placeholders})
        """

        rows = conn.execute(
            query,
            numbers
        ).fetchall()

        results = []

        for row in rows:

            try:
                record = json.loads(
                    row["record_json"]
                )

                results.append(record)

            except Exception:
                continue

        return results

    finally:
        conn.close()


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def home():
    return render_template(
        "index.html"
    )


@app.route("/health")
def health():

    json_files = 0

    if DATA_DIR.exists():
        json_files = len(
            list(DATA_DIR.glob("*.json"))
        )

    index_ready = index_is_current()

    record_count = get_metadata(
        "record_count"
    )

    return jsonify({
        "ok": True,
        "status": "online",
        "json_files": json_files,
        "index_ready": index_ready,
        "indexed_records": int(
            record_count or 0
        )
    })


@app.route("/search", methods=["POST"])
def search():

    try:

        data = request.get_json(
            silent=True
        )

        if not isinstance(data, dict):

            return jsonify({
                "ok": False,
                "error": "Invalid JSON request"
            }), 400

        numbers = extract_numbers(
            data.get("numbers")
        )

        if not numbers:

            return jsonify({
                "ok": False,
                "error": "Please enter at least one valid number"
            }), 400

        if len(numbers) > MAX_NUMBERS:

            return jsonify({
                "ok": False,
                "error": (
                    f"Maximum "
                    f"{MAX_NUMBERS} numbers allowed"
                )
            }), 400

        # Build only if necessary.
        if not index_is_current():

            success = build_index()

            if not success:

                return jsonify({
                    "ok": False,
                    "error": "Search index could not be built"
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
            "error": "Search failed",
            "details": str(exc)
        }), 500


# ============================================================
# DEBUG / STATUS
# ============================================================

@app.route("/status")
def status():

    return jsonify({
        "ok": True,
        "data_directory": str(
            DATA_DIR
        ),
        "database": str(
            DB_PATH
        ),
        "json_files": (
            len(list(DATA_DIR.glob("*.json")))
            if DATA_DIR.exists()
            else 0
        ),
        "index_ready": index_is_current(),
        "indexed_records": int(
            get_metadata("record_count")
            or 0
        )
    })


# ============================================================
# BLOCK DIRECT DATA ACCESS
# ============================================================

@app.route("/data")
@app.route("/data/")
@app.route(
    "/data/<path:filename>"
)
def block_data(filename=None):

    return jsonify({
        "ok": False,
        "error": "Access denied"
    }), 403


# ============================================================
# LOCAL START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    print("=" * 60)
    print(
        "KRUTIK CYBER EXPERT"
    )
    print(
        "HIGH-SPEED JSON SEARCH"
    )
    print("=" * 60)

    print(
        "DATA:",
        DATA_DIR
    )

    print(
        "DATABASE:",
        DB_PATH
    )

    if DATA_DIR.exists():

        files = list(
            DATA_DIR.glob("*.json")
        )

        print(
            "JSON FILES:",
            len(files)
        )

    else:

        print(
            "JSON DIRECTORY NOT FOUND"
        )

    print("=" * 60)

    # Build index before serving locally.
    build_index()

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
