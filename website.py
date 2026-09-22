from flask import Flask, render_template, request, jsonify
from pathlib import Path
import json
import re
import traceback
import threading

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

MAX_NUMBERS = 100
MAX_RESULTS = 500

# Mobile -> records
NUMBER_INDEX = {}

# Prevent multiple workers from building index simultaneously
INDEX_LOCK = threading.Lock()

INDEX_READY = False


def normalize_number(value):
    return re.sub(r"\D", "", str(value or ""))


def build_index():
    """
    Load all JSON files once and create:

        mobile_number -> matching records

    JSON files remain server-side.
    """

    global NUMBER_INDEX
    global INDEX_READY

    with INDEX_LOCK:

        if INDEX_READY:
            return

        print("=" * 50)
        print("KRUTIK CYBER EXPERT API")
        print("Building data index...")
        print("DATA DIR:", DATA_DIR)
        print("=" * 50)

        temp_index = {}

        if not DATA_DIR.exists():

            DATA_DIR.mkdir(
                parents=True,
                exist_ok=True
            )

            print("Data directory created.")

            NUMBER_INDEX = {}
            INDEX_READY = True

            return


        json_files = sorted(
            DATA_DIR.glob("*.json")
        )

        print(
            "JSON files found:",
            len(json_files)
        )


        total_records = 0
        successful_files = 0


        for file_path in json_files:

            try:

                print(
                    "[LOADING]",
                    file_path.name
                )

                with file_path.open(
                    "r",
                    encoding="utf-8"
                ) as file:

                    data = json.load(file)


                if isinstance(data, list):

                    records = data

                elif isinstance(data, dict):

                    records = data.get(
                        "data",
                        []
                    )

                else:

                    print(
                        "[SKIP]",
                        file_path.name,
                        "- invalid format"
                    )

                    continue


                if not isinstance(
                    records,
                    list
                ):

                    print(
                        "[SKIP]",
                        file_path.name,
                        "- data is not list"
                    )

                    continue


                file_count = 0


                for record in records:

                    if not isinstance(
                        record,
                        dict
                    ):

                        continue


                    mobile = normalize_number(
                        record.get(
                            "mobile",
                            ""
                        )
                    )


                    if not mobile:
                        continue


                    if mobile not in temp_index:

                        temp_index[mobile] = []


                    temp_index[
                        mobile
                    ].append(record)


                    file_count += 1
                    total_records += 1


                successful_files += 1


                print(
                    "[LOADED]",
                    file_path.name,
                    "->",
                    file_count,
                    "records"
                )


            except json.JSONDecodeError as error:

                print(
                    "[JSON ERROR]",
                    file_path.name
                )

                print(error)


            except MemoryError:

                print(
                    "[MEMORY ERROR]",
                    file_path.name
                )

                raise


            except Exception as error:

                print(
                    "[FILE ERROR]",
                    file_path.name,
                    error
                )


        NUMBER_INDEX = temp_index
        INDEX_READY = True


        print("=" * 50)

        print(
            "INDEX READY"
        )

        print(
            "Files:",
            successful_files
        )

        print(
            "Records:",
            total_records
        )

        print(
            "Unique numbers:",
            len(NUMBER_INDEX)
        )

        print("=" * 50)


def search_numbers(numbers):

    if not INDEX_READY:

        build_index()


    results = []


    for number in numbers:

        normalized = normalize_number(
            number
        )


        matches = NUMBER_INDEX.get(
            normalized,
            []
        )


        for record in matches:

            # Make a copy so original
            # server-side data is untouched.
            safe_record = dict(record)

            results.append(
                safe_record
            )


            if len(results) >= MAX_RESULTS:

                return results


    return results


@app.route("/", methods=["GET"])
def home():

    return render_template(
        "index.html"
    )


@app.route("/health", methods=["GET"])
def health():

    try:

        json_files = (
            list(DATA_DIR.glob("*.json"))
            if DATA_DIR.exists()
            else []
        )


        return jsonify({
            "ok": True,
            "status": "online",
            "json_files": len(json_files),
            "index_ready": INDEX_READY
        }), 200


    except Exception as error:

        return jsonify({
            "ok": False,
            "message": str(error)
        }), 500


@app.route("/search", methods=["POST"])
def search():

    try:

        # Make sure index is ready.
        if not INDEX_READY:

            build_index()


        payload = request.get_json(
            silent=True
        )


        if not isinstance(
            payload,
            dict
        ):

            return jsonify({
                "ok": False,
                "message": "Invalid JSON request."
            }), 400


        raw_numbers = str(
            payload.get(
                "numbers",
                ""
            )
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
            item.strip()
            for item in parts
            if item.strip()
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
            "searched": len(
                valid_numbers
            ),
            "found": len(results),
            "results": results
        }), 200


    except MemoryError:

        print(
            "[MEMORY ERROR] Search"
        )

        return jsonify({
            "ok": False,
            "message": (
                "Server memory limit reached."
            )
        }), 503


    except Exception as error:

        print(
            "[SEARCH ERROR]"
        )

        traceback.print_exc()


        return jsonify({
            "ok": False,
            "message": (
                "Search failed: "
                + str(error)
            )
        }), 500


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
def internal_error(error):

    return jsonify({
        "ok": False,
        "message": "Internal server error."
    }), 500


if __name__ == "__main__":

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    print(
        "Starting local server..."
    )

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
