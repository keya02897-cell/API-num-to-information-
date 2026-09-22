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
# HIGH SPEED JSON SEARCH API
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
    """
    Open SQLite database.
    """

    INDEX_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=60,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    # SQLite performance settings
    conn.execute(
        "PRAGMA journal_mode=WAL"
    )

    conn.execute(
        "PRAGMA synchronous=NORMAL"
    )

    conn.execute(
        "PRAGMA temp_store=MEMORY"
    )

    conn.execute(
        "PRAGMA cache_size=-50000"
    )

    return conn


def create_database():
    """
    Always make sure database and tables exist.
    """

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
# METADATA
# ============================================================

def get_metadata(key):
    """
    Get metadata value safely.
    """

    create_database()

    conn = get_db()

    try:

        row = conn.execute(
            """
            SELECT value
            FROM metadata
            WHERE key = ?
            """,
            (key,)
        ).fetchone()

        if row is None:
            return None

        return row["value"]

    finally:

        conn.close()


def set_metadata(key, value):
    """
    Store metadata.
    """

    create_database()

    conn = get_db()

    try:

        conn.execute(
            """
            INSERT INTO metadata(key, value)
            VALUES (?, ?)

            ON CONFLICT(key)
            DO UPDATE SET
                value = excluded.value
            """,
            (key, str(value))
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# NUMBER NORMALIZATION
# ============================================================

def normalize_number(value):
    """
    Keep only numbers.

    Example:

    +91 93777-11765
    ->
    919377711765

    9377711765
    ->
    9377711765
    """

    if value is None:
        return ""

    return re.sub(
        r"\D",
        "",
        str(value)
    )


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

        parts = re.split(
            r"[\s,;]+",
            str(value or "")
        )

    numbers = []

    for part in parts:

        number = normalize_number(
            part
        )

        if number and number not in numbers:

            numbers.append(number)

    return numbers


# ============================================================
# DATA SIGNATURE
# ============================================================

def get_data_signature():
    """
    Generate signature from all JSON files.

    If files are changed, the index is rebuilt.
    """

    if not DATA_DIR.exists():

        return "NO_DATA_DIRECTORY"

    json_files = sorted(
        DATA_DIR.glob("*.json")
    )

    if not json_files:

        return "NO_JSON_FILES"

    parts = []

    for file_path in json_files:

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
    Supports:

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

        records = content.get(
            "data",
            []
        )

    else:

        return []

    if not isinstance(
        records,
        list
    ):

        return []

    return [
        record
        for record in records
        if isinstance(
            record,
            dict
        )
    ]


# ============================================================
# INDEX STATUS
# ============================================================

def index_is_current():
    """
    Check whether SQLite index matches
    current JSON files.
    """

    # IMPORTANT:
    # Make database before reading metadata.
    create_database()

    current_signature = (
        get_data_signature()
    )

    stored_signature = get_metadata(
        "data_signature"
    )

    record_count = get_metadata(
        "record_count"
    )

    if not stored_signature:
        return False

    if record_count is None:
        return False

    return (
        current_signature
        == stored_signature
    )


# ============================================================
# BUILD INDEX
# ============================================================

def build_index():
    """
    Convert JSON data into SQLite indexed database.

    This does NOT happen for every search.
    """

    with _index_lock:

        create_database()

        current_signature = (
            get_data_signature()
        )

        # Someone may have already built it.
        if index_is_current():

            app.logger.info(
                "INDEX ALREADY CURRENT"
            )

            return True

        app.logger.info(
            "=" * 60
        )

        app.logger.info(
            "BUILDING SEARCH INDEX"
        )

        app.logger.info(
            "DATA DIRECTORY: %s",
            DATA_DIR
        )

        app.logger.info(
            "=" * 60
        )

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

            conn.execute(
                "BEGIN"
            )

            # Remove old index
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

                    total_records += (
                        len(records)
                    )

                    batch = []

                    for record in records:

                        mobile = normalize_number(
                            record.get(
                                "mobile",
                                ""
                            )
                        )

                        if not mobile:

                            continue

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

                        indexed_records += (
                            len(batch)
                        )

                except Exception as exc:

                    failed_files += 1

                    app.logger.exception(
                        "[JSON ERROR] %s",
                        file_path.name
                    )

            # Save index metadata
            conn.execute(
                """
                INSERT INTO metadata(
                    key,
                    value
                )
                VALUES (?, ?)

                ON CONFLICT(key)
                DO UPDATE SET
                    value = excluded.value
                """,
                (
                    "data_signature",
                    current_signature
                )
            )

            conn.execute(
                """
                INSERT INTO metadata(
                    key,
                    value
                )
                VALUES (?, ?)

                ON CONFLICT(key)
                DO UPDATE SET
                    value = excluded.value
                """,
                (
                    "record_count",
                    indexed_records
                )
            )

            conn.execute(
                """
                INSERT INTO metadata(
                    key,
                    value
                )
                VALUES (?, ?)

                ON CONFLICT(key)
                DO UPDATE SET
                    value = excluded.value
                """,
                (
                    "total_records",
                    total_records
                )
            )

            conn.execute(
                """
                INSERT INTO metadata(
                    key,
                    value
                )
                VALUES (?, ?)

                ON CONFLICT(key)
                DO UPDATE SET
                    value = excluded.value
                """,
                (
                    "failed_files",
                    failed_files
                )
            )

            conn.commit()

            app.logger.info(
                "=" * 60
            )

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

            app.logger.info(
                "=" * 60
            )

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
    """
    Search only SQLite.

    JSON files are NOT opened here.
    """

    if not numbers:

        return []

    conn = get_db()

    try:

        placeholders = ",".join(
            ["?"] * len(numbers)
        )

        query = f"""
            SELECT
                mobile,
                record_json
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

                results.append(
                    record
                )

            except Exception:

                continue

        return results

    finally:

        conn.close()


# ============================================================
# APPLICATION STARTUP
# ============================================================

def initialize_app():
    """
    Safe initialization for Gunicorn/Render.

    Gunicorn imports:
        website:app

    So this function is called during import.
    """

    try:

        create_database()

        app.logger.info(
            "DATABASE INITIALIZED"
        )

        # IMPORTANT:
        # Do NOT build a huge index here automatically.
        #
        # First /search request will build it if required.
        # This keeps Render health check responsive.

    except Exception:

        app.logger.exception(
            "APPLICATION INITIALIZATION FAILED"
        )


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

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    try:

        create_database()

        json_files = 0

        if DATA_DIR.exists():

            json_files = len(
                list(
                    DATA_DIR.glob(
                        "*.json"
                    )
                )
            )

        index_ready = (
            index_is_current()
        )

        record_count = (
            get_metadata(
                "record_count"
            )
            or 0
        )

        return jsonify({
            "ok": True,
            "status": "online",
            "json_files": json_files,
            "index_ready": index_ready,
            "indexed_records": int(
                record_count
            )
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
# SEARCH
# ============================================================

@app.route(
    "/search",
    methods=["POST"]
)
def search():

    try:

        data = request.get_json(
            silent=True
        )

        if not isinstance(
            data,
            dict
        ):

            return jsonify({
                "ok": False,
                "error": "Invalid JSON request"
            }), 400

        numbers = extract_numbers(
            data.get(
                "numbers"
            )
        )

        if not numbers:

            return jsonify({
                "ok": False,
                "error": (
                    "Please enter at least "
                    "one valid number"
                )
            }), 400

        if len(numbers) > MAX_NUMBERS:

            return jsonify({
                "ok": False,
                "error": (
                    f"Maximum "
                    f"{MAX_NUMBERS} numbers "
                    f"allowed"
                )
            }), 400

        # Build index only if needed.
        if not index_is_current():

            app.logger.info(
                "INDEX NOT READY - "
                "BUILDING NOW"
            )

            success = build_index()

            if not success:

                return jsonify({
                    "ok": False,
                    "error": (
                        "Search index "
                        "could not be built"
                    )
                }), 500

        # FAST DATABASE SEARCH
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
            "error": "Internal server error",
            "details": str(exc)
        }), 500


# ============================================================
# STATUS
# ============================================================

@app.route(
    "/status",
    methods=["GET"]
)
def status():

    try:

        create_database()

        json_files = 0

        if DATA_DIR.exists():

            json_files = len(
                list(
                    DATA_DIR.glob(
                        "*.json"
                    )
                )
            )

        record_count = (
            get_metadata(
                "record_count"
            )
            or 0
        )

        total_records = (
            get_metadata(
                "total_records"
            )
            or 0
        )

        failed_files = (
            get_metadata(
                "failed_files"
            )
            or 0
        )

        return jsonify({
            "ok": True,
            "json_files": json_files,
            "index_ready": (
                index_is_current()
            ),
            "indexed_records": int(
                record_count
            ),
            "total_records": int(
                total_records
            ),
            "failed_files": int(
                failed_files
            )
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
# BLOCK DIRECT DATA ACCESS
# ============================================================

@app.route(
    "/data"
)
@app.route(
    "/data/"
)
@app.route(
    "/data/<path:filename>"
)
def block_data_access(
    filename=None
):

    return jsonify({
        "ok": False,
        "error": "Access denied"
    }), 403


# ============================================================
# BLOCK DATABASE ACCESS
# ============================================================

@app.route(
    "/index/<path:filename>"
)
def block_index_access(
    filename=None
):

    return jsonify({
        "ok": False,
        "error": "Access denied"
    }), 403


# ============================================================
# INITIALIZE WHEN GUNICORN IMPORTS APP
# ============================================================

initialize_app()


# ============================================================
# LOCAL RUN
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    print(
        "=" * 60
    )

    print(
        "KRUTIK CYBER EXPERT"
    )

    print(
        "HIGH SPEED JSON SEARCH"
    )

    print(
        "=" * 60
    )

    print(
        "BASE DIR:",
        BASE_DIR
    )

    print(
        "DATA DIR:",
        DATA_DIR
    )

    print(
        "DATABASE:",
        DB_PATH
    )

    if DATA_DIR.exists():

        print(
            "JSON FILES:",
            len(
                list(
                    DATA_DIR.glob(
                        "*.json"
                    )
                )
            )
        )

    else:

        print(
            "DATA DIRECTORY NOT FOUND"
        )

    print(
        "=" * 60
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
