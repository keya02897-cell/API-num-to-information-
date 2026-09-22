import os
import json
import re
from pathlib import Path
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# ============================================================
# KRUTIK CYBER EXPERT API
# Server-side JSON search website
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

MAX_NUMBERS_PER_REQUEST = 100

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def normalize_number(value):
    """
    Keep only digits.
    Example:
        '+91 93777-11765' -> '919377711765'
        '9377711765'      -> '9377711765'
    """
    if value is None:
        return ""

    return re.sub(r"\D", "", str(value))


def extract_numbers(value):
    """
    Accept:
      9377711765
      9377711765,9812345674
      9377711765
      9812345674
      9377711765 9812345674
      9377711765;9812345674
    """
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[\s,;]+", str(value or ""))

    numbers = []

    for item in raw_items:
        number = normalize_number(item)

        if number and number not in numbers:
            numbers.append(number)

    return numbers


def load_json_file(file_path):
    """
    Supports the user's exact format:

    [
        {
            "id": "...",
            "mobile": "...",
            "name": "...",
            "pincode": "...",
            "city": "...",
            "address": "..."
        }
    ]

    Also supports:

    {
        "data": [
            {...}
        ]
    }
    """

    with file_path.open("r", encoding="utf-8-sig") as f:
        content = json.load(f)

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


# ------------------------------------------------------------
# Search JSON files
# ------------------------------------------------------------

def search_json_files(numbers):
    """
    Searches all JSON files inside /data.

    IMPORTANT:
    Data never goes directly to browser.
    Only matching records are returned.
    """

    wanted = set(numbers)

    results = []
    searched_files = 0
    loaded_records = 0
    errors = []

    if not DATA_DIR.exists():
        return {
            "results": [],
            "searched_files": 0,
            "loaded_records": 0,
            "errors": ["data directory not found"]
        }

    json_files = sorted(DATA_DIR.glob("*.json"))

    for file_path in json_files:
        searched_files += 1

        try:
            records = load_json_file(file_path)
            loaded_records += len(records)

            for record in records:
                mobile = normalize_number(record.get("mobile", ""))

                if mobile in wanted:
                    result = dict(record)

                    # Do not expose internal filename/path.
                    results.append(result)

        except Exception as exc:
            errors.append(
                f"{file_path.name}: {type(exc).__name__}: {exc}"
            )

    return {
        "results": results,
        "searched_files": searched_files,
        "loaded_records": loaded_records,
        "errors": errors
    }


# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health():
    """
    Health check.

    Does NOT expose data.
    """

    json_files = 0

    if DATA_DIR.exists():
        json_files = len(list(DATA_DIR.glob("*.json")))

    return jsonify({
        "ok": True,
        "status": "online",
        "json_files": json_files
    })


@app.route("/search", methods=["POST"])
def search():
    """
    POST /search

    JSON:
    {
        "numbers": "9377711765,9812345674"
    }

    or:

    {
        "numbers": [
            "9377711765",
            "9812345674"
        ]
    }
    """

    try:
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify({
                "ok": False,
                "error": "Invalid JSON request"
            }), 400

        numbers = extract_numbers(data.get("numbers"))

        if not numbers:
            return jsonify({
                "ok": False,
                "error": "Please enter at least one valid number"
            }), 400

        if len(numbers) > MAX_NUMBERS_PER_REQUEST:
            return jsonify({
                "ok": False,
                "error": f"Maximum {MAX_NUMBERS_PER_REQUEST} numbers allowed per request"
            }), 400

        search_result = search_json_files(numbers)

        return jsonify({
            "ok": True,
            "searched": len(numbers),
            "found": len(search_result["results"]),
            "results": search_result["results"]
        })

    except Exception as exc:
        app.logger.exception("SEARCH ERROR")

        return jsonify({
            "ok": False,
            "error": "Server search error",
            "details": str(exc)
        }), 500


# ------------------------------------------------------------
# Prevent accidental exposure of data directory
# ------------------------------------------------------------

@app.route("/data")
@app.route("/data/")
@app.route("/data/<path:filename>")
def block_data_access(filename=None):
    return jsonify({
        "ok": False,
        "error": "Access denied"
    }), 403


# ------------------------------------------------------------
# Run locally
# ------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    print("=" * 60)
    print("KRUTIK CYBER EXPERT API")
    print("=" * 60)
    print(f"BASE DIR : {BASE_DIR}")
    print(f"DATA DIR : {DATA_DIR}")

    if DATA_DIR.exists():
        files = list(DATA_DIR.glob("*.json"))
        print(f"JSON FILES: {len(files)}")
    else:
        print("DATA DIR NOT FOUND")

    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
