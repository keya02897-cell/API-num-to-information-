from flask import Flask, render_template, request, jsonify
from pathlib import Path
import json
import re
from functools import lru_cache

app = Flask(__name__)

# IMPORTANT:
# data/ is server-side only.
# Do NOT put it inside static/.
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

MAX_NUMBERS_PER_SEARCH = 100
MAX_RESULTS = 100


def normalize_number(value):
    """
    Converts:
        +91 98765 43210
        9876543210
        98765-43210
    into digits only.
    """
    return re.sub(r"\D", "", str(value or ""))


@lru_cache(maxsize=1)
def load_data():
    """
    Loads all JSON datasets from server-side data/ directory.

    Supported formats:

    [
        {...},
        {...}
    ]

    OR

    {
        "data": [
            {...},
            {...}
        ]
    }
    """

    records = []

    if not DATA_DIR.exists():
        print("WARNING: data directory does not exist:", DATA_DIR)
        return records

    for json_file in sorted(DATA_DIR.glob("*.json")):

        try:
            with json_file.open("r", encoding="utf-8") as file:
                content = json.load(file)

            if isinstance(content, list):
                items = content

            elif isinstance(content, dict):
                items = content.get("data", [])

            else:
                print(
                    f"SKIPPED {json_file.name}: "
                    "invalid JSON structure"
                )
                continue

            if not isinstance(items, list):
                print(
                    f"SKIPPED {json_file.name}: "
                    "'data' must be a list"
                )
                continue

            for item in items:

                if not isinstance(item, dict):
                    continue

                record = dict(item)

                # Internal field.
                # It is removed before sending response.
                record["_dataset"] = json_file.name

                records.append(record)

            print(
                f"LOADED {json_file.name}: "
                f"{len(items)} records"
            )

        except json.JSONDecodeError as exc:

            print(
                f"JSON ERROR [{json_file.name}]: {exc}"
            )

        except Exception as exc:

            print(
                f"LOAD ERROR [{json_file.name}]: {exc}"
            )

    print(
        f"TOTAL RECORDS LOADED: {len(records)}"
    )

    return records


def find_records(numbers):
    """
    Exact mobile-number matching.

    Only the server reads the dataset.
    """

    wanted = {
        normalize_number(number)
        for number in numbers
    }

    wanted.discard("")

    if not wanted:
        return []

    found = []

    for record in load_data():

        mobile = normalize_number(
            record.get("mobile", "")
        )

        if mobile in wanted:

            # Never expose internal dataset name.
            safe_record = {
                key: value
                for key, value in record.items()
                if key != "_dataset"
            }

            found.append(safe_record)

            if len(found) >= MAX_RESULTS:
                break

    return found


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/search")
def search():

    payload = request.get_json(
        silent=True
    )

    if not isinstance(payload, dict):
        return jsonify({
            "ok": False,
            "message": "Invalid request."
        }), 400

    raw_numbers = str(
        payload.get("numbers", "")
    ).strip()

    if not raw_numbers:

        return jsonify({
            "ok": False,
            "message": "Please enter at least one number."
        }), 400

    # New line / comma / semicolon / whitespace
    parts = re.split(
        r"[\s,;]+",
        raw_numbers
    )

    parts = [
        part.strip()
        for part in parts
        if part.strip()
    ]

    if len(parts) > MAX_NUMBERS_PER_SEARCH:

        return jsonify({
            "ok": False,
            "message": (
                f"Maximum "
                f"{MAX_NUMBERS_PER_SEARCH} "
                "numbers per search."
            )
        }), 400

    valid_numbers = []
    invalid_numbers = []

    for number in parts:

        normalized = normalize_number(number)

        if len(normalized) < 7:
            invalid_numbers.append(number)
            continue

        valid_numbers.append(normalized)

    if not valid_numbers:

        return jsonify({
            "ok": False,
            "message": "No valid numbers found."
        }), 400

    results = find_records(
        valid_numbers
    )

    return jsonify({
        "ok": True,
        "searched": len(valid_numbers),
        "found": len(results),
        "invalid": invalid_numbers,
        "results": results
    })


@app.get("/health")
def health():

    return jsonify({
        "status": "ok",
        "datasets": (
            len(
                list(DATA_DIR.glob("*.json"))
            )
            if DATA_DIR.exists()
            else 0
        )
    })


@app.errorhandler(404)
def not_found(error):

    return jsonify({
        "ok": False,
        "message": "Not found."
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):

    return jsonify({
        "ok": False,
        "message": "Method not allowed."
    }), 405


@app.errorhandler(500)
def server_error(error):

    return jsonify({
        "ok": False,
        "message": "Internal server error."
    }), 500


if __name__ == "__main__":

    # Local testing only.
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
