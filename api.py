import os
import json
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

import database


APP_NAME = "KRUTIK CYBER EXPERT API"

DATA_DIR = Path(
    os.getenv("DATA_DIR", "data")
)

app = FastAPI(
    title=APP_NAME,
    version="1.0.0"
)


def load_json_files():
    """
    Loads only JSON files from DATA_DIR.

    Expected synthetic format:

    [
        {
            "id": "FAKE-000001",
            "mobile": "9000000001",
            "name": "Demo User",
            "pincode": "380001",
            "city": "Ahmedabad",
            "address": "Demo Address"
        }
    ]
    """

    records = []

    if not DATA_DIR.exists():
        return records

    for file_path in DATA_DIR.glob("*.json"):
        try:
            with open(
                file_path,
                "r",
                encoding="utf-8"
            ) as f:
                data = json.load(f)

            if isinstance(data, list):
                records.extend(data)

            elif isinstance(data, dict):
                if isinstance(data.get("data"), list):
                    records.extend(data["data"])

        except Exception as e:
            print(
                f"JSON LOAD ERROR {file_path}: {e}"
            )

    return records


def search_records(query, limit=20):
    records = load_json_files()

    query = query.strip().lower()

    if not query:
        return []

    results = []

    searchable_fields = [
        "id",
        "mobile",
        "name",
        "pincode",
        "city",
        "address"
    ]

    for record in records:
        if not isinstance(record, dict):
            continue

        found = False

        for field in searchable_fields:
            value = record.get(field)

            if value is None:
                continue

            if query in str(value).lower():
                found = True
                break

        if found:
            results.append(record)

        if len(results) >= limit:
            break

    return results


@app.get("/")
async def root():
    return {
        "name": APP_NAME,
        "status": "online",
        "message": "API server is running."
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": APP_NAME,
        "time": datetime.now(
            timezone.utc
        ).isoformat()
    }


@app.get("/api/search")
async def api_search(
    api_key: str = Query(...),
    query: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(
        20,
        ge=1,
        le=50
    )
):
    key = database.get_api_key(api_key)

    if not key:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "invalid_api_key"
            }
        )

    # Expiration check
    expires_at = key["expires_at"]

    if expires_at:
        try:
            expires = datetime.fromisoformat(
                expires_at
            )

            if expires < datetime.now(timezone.utc):
                database.log_request(
                    key["id"],
                    query,
                    False,
                    403
                )

                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "error": "api_key_expired"
                    }
                )

        except ValueError:
            pass

    allowed, reason, updated_key = database.consume_request(
        api_key
    )

    if not allowed:

        if reason == "daily_limit":
            database.log_request(
                key["id"],
                query,
                False,
                429
            )

            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": "daily_limit_reached",
                    "daily_limit": key["daily_limit"]
                }
            )

        database.log_request(
            key["id"],
            query,
            False,
            401
        )

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "invalid_api_key"
            }
        )

    results = search_records(
        query,
        limit
    )

    database.log_request(
        key["id"],
        query,
        True,
        200
    )

    return {
        "success": True,
        "query": query,
        "count": len(results),
        "usage": {
            "today": updated_key["today_requests"],
            "daily_limit": updated_key["daily_limit"],
            "total": updated_key["total_requests"]
        },
        "results": results
    }


@app.get("/api/status")
async def api_status(
    api_key: str = Query(...)
):
    key = database.get_api_key(api_key)

    if not key:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "invalid_api_key"
            }
        )

    return {
        "success": True,
        "plan": key["plan"],
        "status": key["status"],
        "today_requests": key["today_requests"],
        "daily_limit": key["daily_limit"],
        "total_requests": key["total_requests"],
        "expires_at": key["expires_at"]
    }


if __name__ == "__main__":
    import uvicorn

    port = int(
        os.getenv("PORT", "8000")
    )

    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=port
    )
