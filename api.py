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
    version="2.0.0",
    description="Authorized synthetic-data API",
)


# =========================================================
# DATA
# =========================================================

def load_records():
    records = []

    if not DATA_DIR.exists():
        return records

    for file_path in sorted(DATA_DIR.glob("*.json")):
        try:
            with open(
                file_path,
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        records.append(item)

            elif isinstance(data, dict):
                data_list = data.get("data")

                if isinstance(data_list, list):
                    for item in data_list:
                        if isinstance(item, dict):
                            records.append(item)

        except Exception as exc:
            print(
                f"JSON LOAD ERROR: {file_path}: {exc}"
            )

    return records


def search_records(search_value, limit):
    search_value = (
        search_value.strip().lower()
    )

    if not search_value:
        return []

    records = load_records()

    results = []

    fields = [
        "id",
        "mobile",
        "name",
        "pincode",
        "city",
        "address",
    ]

    for record in records:
        for field in fields:
            value = record.get(field)

            if value is None:
                continue

            if search_value in str(value).lower():
                results.append(record)
                break

        if len(results) >= limit:
            break

    return results


# =========================================================
# BASIC ROUTES
# =========================================================

@app.get("/")
async def root():
    return {
        "service": APP_NAME,
        "status": "online",
        "version": "2.0.0",
        "docs": "/docs",
        "search": "/api/search",
        "status_endpoint": "/api/status",
    }


@app.get("/health")
async def health():
    database.init_db()

    return {
        "status": "ok",
        "service": APP_NAME,
        "database": "sqlite",
        "data_directory": str(DATA_DIR),
        "time": datetime.now(
            timezone.utc
        ).isoformat(),
    }


# =========================================================
# SEARCH API
# =========================================================

@app.get("/api/search")
async def search_api(
    api_key: str = Query(...),
    query: str = Query(
        ...,
        min_length=1,
        max_length=100,
    ),
    limit: int = Query(
        20,
        ge=1,
        le=50,
    ),
):
    key = database.get_api_key(api_key)

    if not key:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "invalid_api_key",
            },
        )

    allowed, reason, updated_key = (
        database.consume_api_request(api_key)
    )

    if not allowed:

        if reason == "blocked":
            database.log_request(
                key["id"],
                query,
                False,
                403,
            )

            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "user_blocked",
                },
            )

        if reason == "api_disabled":
            database.log_request(
                key["id"],
                query,
                False,
                403,
            )

            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "api_access_disabled",
                },
            )

        if reason == "daily_limit":
            database.log_request(
                key["id"],
                query,
                False,
                429,
            )

            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": "daily_limit_reached",
                    "daily_limit": key[
                        "daily_limit"
                    ],
                },
            )

        if reason == "expired":
            database.log_request(
                key["id"],
                query,
                False,
                403,
            )

            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "api_key_expired",
                },
            )

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "invalid_api_key",
            },
        )

    results = search_records(
        query,
        limit,
    )

    database.log_request(
        updated_key["id"],
        query,
        True,
        200,
    )

    return {
        "success": True,
        "query": query,
        "count": len(results),
        "usage": {
            "today": updated_key[
                "today_requests"
            ],
            "daily_limit": updated_key[
                "daily_limit"
            ],
            "total": updated_key[
                "total_requests"
            ],
        },
        "results": results,
    }


# =========================================================
# API STATUS
# =========================================================

@app.get("/api/status")
async def api_status(
    api_key: str = Query(...),
):
    key = database.get_api_key(api_key)

    if not key:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "invalid_api_key",
            },
        )

    user = database.get_user(
        key["chat_id"]
    )

    if user and user.get("blocked"):
        return {
            "success": True,
            "plan": key["plan"],
            "status": key["status"],
            "api_enabled": False,
            "blocked": True,
            "today_requests": key[
                "today_requests"
            ],
            "daily_limit": key[
                "daily_limit"
            ],
            "total_requests": key[
                "total_requests"
            ],
            "expires_at": key[
                "expires_at"
            ],
        }

    return {
        "success": True,
        "plan": key["plan"],
        "status": key["status"],
        "api_enabled": (
            True
            if not user
            else bool(
                user.get(
                    "api_enabled",
                    1,
                )
            )
        ),
        "blocked": False,
        "today_requests": key[
            "today_requests"
        ],
        "daily_limit": key[
            "daily_limit"
        ],
        "total_requests": key[
            "total_requests"
        ],
        "expires_at": key[
            "expires_at"
        ],
    }


# =========================================================
# PUBLIC STATS
# =========================================================

@app.get("/api/stats")
async def public_stats():
    return {
        "service": APP_NAME,
        "status": "online",
    }


if __name__ == "__main__":
    import uvicorn

    database.init_db()

    port = int(
        os.getenv("PORT", "10000")
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
    )
