import os
import json
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

import database


APP_NAME = "KRUTIK CYBER EXPERT API"

VERSION = "2.0.0"

DATA_DIR = Path(
    os.getenv("DATA_DIR", "data")
)


app = FastAPI(
    title=APP_NAME,
    version=VERSION,
    description=(
        "KRUTIK CYBER EXPERT API - "
        "Authorized synthetic-data API"
    ),
)


# =========================================================
# RESPONSE HELPERS
# =========================================================

def success_response(**data):
    return {
        "service": APP_NAME,
        "success": True,
        **data,
    }


def error_response(
    status_code,
    error,
    message,
    **extra,
):
    content = {
        "service": APP_NAME,
        "success": False,
        "error": error,
        "message": message,
        **extra,
    }

    return JSONResponse(
        status_code=status_code,
        content=content,
    )


# =========================================================
# DATA
# =========================================================

def load_records():
    records = []

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for file_path in sorted(
        DATA_DIR.glob("*.json")
    ):
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
                "JSON LOAD ERROR:",
                file_path,
                exc,
            )

    return records


def search_records(
    search_value,
    limit,
):
    search_value = (
        str(search_value)
        .strip()
        .lower()
    )

    if not search_value:
        return []

    records = load_records()

    fields = [
        "id",
        "mobile",
        "name",
        "pincode",
        "city",
        "address",
    ]

    results = []

    for record in records:
        for field in fields:
            value = record.get(field)

            if value is None:
                continue

            if search_value in str(
                value
            ).lower():
                results.append(record)
                break

        if len(results) >= limit:
            break

    return results


# =========================================================
# ROOT
# =========================================================

@app.get("/")
async def root():
    return success_response(
        status="online",
        version=VERSION,
        docs="/docs",
        health="/health",
        search_endpoint="/api/search",
        status_endpoint="/api/status",
        stats_endpoint="/api/stats",
    )


@app.get("/health")
async def health():
    return success_response(
        status="ok",
        version=VERSION,
        database="sqlite",
        data_directory=str(DATA_DIR),
        time=datetime.now(
            timezone.utc
        ).isoformat(),
    )


# =========================================================
# SEARCH
# =========================================================

@app.get("/api/search")
async def api_search(
    api_key: str = Query(
        ...,
        min_length=1,
    ),
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
    key = database.get_api_key(
        api_key
    )

    if not key:
        return error_response(
            401,
            "invalid_api_key",
            "The API key is invalid.",
        )

    allowed, reason, updated_key = (
        database.consume_api_request(
            api_key
        )
    )

    if not allowed:

        errors = {
            "user_blocked": (
                403,
                "user_blocked",
                "This user is blocked.",
            ),
            "api_access_disabled": (
                403,
                "api_access_disabled",
                "API access is disabled for this user.",
            ),
            "maintenance_mode": (
                503,
                "maintenance_mode",
                "API is temporarily disabled.",
            ),
            "not_started": (
                403,
                "api_not_started",
                "This API key is not active yet.",
            ),
            "expired": (
                403,
                "api_key_expired",
                "This API key has expired.",
            ),
            "daily_limit": (
                429,
                "daily_limit_reached",
                "Daily request limit reached.",
            ),
            "total_limit": (
                429,
                "total_limit_reached",
                "Total request limit reached.",
            ),
            "rate_limit": (
                429,
                "rate_limit_reached",
                "Requests per minute limit reached.",
            ),
        }

        status, error, message = errors.get(
            reason,
            (
                401,
                "invalid_api_key",
                "The API key is invalid.",
            ),
        )

        database.log_request(
            key["id"],
            key["chat_id"],
            query,
            False,
            status,
            error,
        )

        return error_response(
            status,
            error,
            message,
        )

    results = search_records(
        query,
        limit,
    )

    database.log_request(
        updated_key["id"],
        updated_key["chat_id"],
        query,
        True,
        200,
    )

    remaining_daily = max(
        0,
        updated_key["daily_limit"]
        - updated_key["today_requests"],
    )

    if updated_key.get("total_limit") is None:
        remaining_total = None
    else:
        remaining_total = max(
            0,
            updated_key["total_limit"]
            - updated_key["total_requests"],
        )

    return success_response(
        status="success",
        query=query,
        count=len(results),
        key={
            "id": updated_key["id"],
            "name": updated_key["key_name"],
            "plan": updated_key["plan"],
        },
        usage={
            "today": updated_key[
                "today_requests"
            ],
            "daily_limit": updated_key[
                "daily_limit"
            ],
            "daily_remaining": remaining_daily,
            "total": updated_key[
                "total_requests"
            ],
            "total_limit": updated_key[
                "total_limit"
            ],
            "total_remaining": remaining_total,
        },
        results=results,
    )


# =========================================================
# STATUS
# =========================================================

@app.get("/api/status")
async def api_status(
    api_key: str = Query(
        ...,
        min_length=1,
    ),
):
    key = database.get_api_key(
        api_key
    )

    if not key:
        return error_response(
            401,
            "invalid_api_key",
            "The API key is invalid.",
        )

    return success_response(
        status=key["status"],
        key={
            "id": key["id"],
            "name": key["key_name"],
            "plan": key["plan"],
        },
        limits={
            "daily": key["daily_limit"],
            "total": key["total_limit"],
            "rate_per_minute": key[
                "rate_limit"
            ],
        },
        usage={
            "today": key[
                "today_requests"
            ],
            "total": key[
                "total_requests"
            ],
        },
        start_at=key["start_at"],
        expires_at=key["expires_at"],
        last_used_at=key[
            "last_used_at"
        ],
    )


# =========================================================
# STATS
# =========================================================

@app.get("/api/stats")
async def api_stats():
    return success_response(
        status="online",
        version=VERSION,
        global_api_enabled=(
            database.is_global_api_enabled()
        ),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                "10000",
            )
        ),
    )
