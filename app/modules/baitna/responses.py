"""
Response envelopes.

Routes return these instead of raising HTTPException: the app-wide handler rewrites
every 404 message to "Resource not found." and drops anything beyond ok/error,
which would lose our messages and the fallback endpoint's Dubizzle/Bayut URLs.
"""

from typing import Any, Optional

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def baitna_ok(data: Any, status_code: int = 200) -> JSONResponse:
    """{"ok": true, "data": {...}}"""
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder({"ok": True, "data": data}),
    )


def baitna_error(
    status_code: int,
    error: str,
    code: Optional[str] = None,
    data: Optional[Any] = None,
) -> JSONResponse:
    """
    {"ok": false, "error": "...", "code": "...", "data": {...}}

    `code` is what lets the client tell the five 409s apart.
    """
    body: dict = {"ok": False, "error": error}
    if code is not None:
        body["code"] = code
    if data is not None:
        body["data"] = data
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body))
