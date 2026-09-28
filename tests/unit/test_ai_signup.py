from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.modules.auth.service import AuthService


def document(filename, mime_type):
    return {"filename": filename, "mime_type": mime_type, "bytes": b"document"}


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.post = AsyncMock(side_effect=error, return_value=response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


@pytest.mark.asyncio
async def test_automated_signup_sends_exact_orbit_contract_and_accepts_matching_identity():
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "approved": True,
        "errors": [],
        "extracted": {
            "name_from_id": "Test Student",
            "university": "Test University Dubai",
        },
    }
    client = FakeClient(response=response)
    with patch("app.modules.auth.service.httpx.AsyncClient", return_value=client):
        result = await AuthService()._verify_automated_signup(
            enrollment_payload=document("letter.pdf", "application/pdf"),
            student_id_payload=document("student.jpg", "image/jpeg"),
            first_name="Test",
            last_name="Student",
            university="Test University Dubai",
        )
    assert result["approved"] is True
    _, kwargs = client.post.call_args
    assert client.post.call_args.args[0].endswith("/verify")
    assert set(kwargs["files"]) == {"student_id", "university_letter"}
    assert kwargs["files"]["student_id"][0] == "student.jpg"
    assert kwargs["files"]["university_letter"][0] == "letter.pdf"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"approved": False, "errors": ["Student ID mismatch"], "extracted": {}},
        {
            "approved": True,
            "errors": [],
            "extracted": {"name_from_id": "Another Person", "university": "Test University Dubai"},
        },
        {
            "approved": True,
            "errors": [],
            "extracted": {"name_from_id": "Test Student", "university": "Another University"},
        },
    ],
)
async def test_automated_signup_rejects_failed_or_mismatched_documents(payload):
    response = MagicMock(status_code=200)
    response.json.return_value = payload
    with patch("app.modules.auth.service.httpx.AsyncClient", return_value=FakeClient(response=response)):
        with pytest.raises(HTTPException) as exc:
            await AuthService()._verify_automated_signup(
                enrollment_payload=document("letter.pdf", "application/pdf"),
                student_id_payload=document("student.jpg", "image/jpeg"),
                first_name="Test",
                last_name="Student",
                university="Test University Dubai",
            )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "AI_VERIFICATION_FAILED"


@pytest.mark.asyncio
async def test_automated_signup_maps_orbit_outage_to_retryable_service_error():
    request = httpx.Request("POST", "https://example.com/verify")
    error = httpx.ConnectError("offline", request=request)
    with patch("app.modules.auth.service.httpx.AsyncClient", return_value=FakeClient(error=error)):
        with pytest.raises(HTTPException) as exc:
            await AuthService()._verify_automated_signup(
                enrollment_payload=document("letter.pdf", "application/pdf"),
                student_id_payload=document("student.jpg", "image/jpeg"),
                first_name="Test",
                last_name="Student",
                university="Test University Dubai",
            )
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "AI_VERIFICATION_UNAVAILABLE"
