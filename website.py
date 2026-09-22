from flask import Flask, render_template, request, jsonify
from pathlib import Path
import json
import re
import traceback

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

MAX_NUMBERS = 100
MAX_RESULTS = 500


def normalize_number(value):
    return re.sub(r"\D", "", str(value or ""))


def load_all_json_files():
    records = []
    loaded_files = 0

    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return records

    for file_path in sorted(DATA_DIR.glob("*.json")):

        try:
            with file_path.open(
                "r",
                encoding="utf-8"
            ) as f:
                data = json.load(f)

            if isinstance(data, list):
                items = data

            elif isinstance(data, dict):
                items = data.get("data", [])

            else:
                print(
                    f"[SKIP] {file_path.name}: "
                    "JSON must be list or {data: [...]}"
                )
                continue

            if not isinstance(items, list):
                print(
                    f"[SKIP] {file_path.name}: "
                    "data is not a list"
                )
                continue

            loaded_files += 1

            for item in items:

                if isinstance(item, dict):
                    records.append(item)

            print(
                f"[LOADED] {file_path.name} -> "
                f"{len(items)} records"
            )

        except json.JSONDecodeError as e:

            print(
                f"[JSON ERROR] {file_path.name}: {e}"
            )

        except Exception as e:

            print(
                f"[ERROR] {file_path.name}: {e}"
            )

    print(
        f"[TOTAL] Files: {loaded_files} | "
        f"Records: {len(records)}"
    )

    return records


def search_numbers(numbers):

    wanted = {
        normalize_number(x)
        for x in numbers
    }

    wanted.discard("")

    if not wanted:
        return []

    all_records = load_all_json_files()

    results = []

    for record in all_records:

        mobile = normalize_number(
            record.get("mobile", "")
        )

        if mobile and mobile in wanted:

            results.append(record)

            if len(results) >= MAX_RESULTS:
                break

    return results


@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search():

    try:

        data = request.get_json(
            silent=True
        )

        if not isinstance(data, dict):

            return jsonify({
                "ok": False,
                "message": "Invalid JSON request."
            }), 400

        raw_numbers = str(
            data.get("numbers", "")
        ).strip()

        if not raw_numbers:

            return jsonify({
                "ok": False,
                "message": "Please enter number."
            }), 400

        parts = re.split(
            r"[\s,;]+",
            raw_numbers
        )

        parts = [
            x.strip()
            for x in parts
            if x.strip()
        ]

        if len(parts) > MAX_NUMBERS:

            return jsonify({
                "ok": False,
                "message": (
                    f"Maximum {MAX_NUMBERS} "
                    "numbers allowed."
                )
            }), 400

        valid_numbers = []

        for number in parts:

            normalized = normalize_number(
                number
            )

            if len(normalized) >= 7:
                valid_numbers.append(
                    normalized
                )

        if not valid_numbers:

            return jsonify({
                "ok": False,
                "message": "No valid numbers."
            }), 400

        results = search_numbers(
            valid_numbers
        )

        return jsonify({
            "ok": True,
            "searched": len(valid_numbers),
            "found": len(results),
            "results": results
        }), 200

    except Exception as e:

        print(
            "[SEARCH ERROR]"
        )

        traceback.print_exc()

        return jsonify({
            "ok": False,
            "message": "Internal server error."
        }), 500


@app.route("/health", methods=["GET"])
def health():

    try:

        files = list(
            DATA_DIR.glob("*.json")
        ) if DATA_DIR.exists() else []

        return jsonify({
            "ok": True,
            "status": "online",
            "json_files": len(files)
        }), 200

    except Exception as e:

        return jsonify({
            "ok": False,
            "message": str(e)
        }), 500


@app.errorhandler(404)
def handle_404(error):

    return jsonify({
        "ok": False,
        "message": "Not found."
    }), 404


@app.errorhandler(405)
def handle_405(error):

    return jsonify({
        "ok": False,
        "message": "Method not allowed."
    }), 405


@app.errorhandler(500)
def handle_500(error):

    return jsonify({
        "ok": False,
        "message": "Internal server error."
    }), 500


if __name__ == "__main__":

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    print()
    print("==============================")
    print("KRUTIK CYBER EXPERT API")
    print("==============================")
    print(
        "DATA DIR:",
        DATA_DIR
    )
    print()
    print("Server: http://127.0.0.1:5000")
    print()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
