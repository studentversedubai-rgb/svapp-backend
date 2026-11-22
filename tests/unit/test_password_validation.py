import pytest
from pydantic import ValidationError

from app.modules.auth.schemas import RegisterRequest, ResetPasswordRequest


def registration(password: str) -> RegisterRequest:
    return RegisterRequest(
        email="student@example.edu",
        name="Test Student",
        first_name="Test",
        last_name="Student",
        password=password,
    )


def test_underscore_matches_frontend_special_character_rule():
    assert registration("Testingaccount123_").password == "Testingaccount123_"


def test_password_without_non_alphanumeric_character_is_rejected():
    with pytest.raises(ValidationError, match="special character"):
        registration("Testingaccount123")


def test_password_rule_is_shared_by_password_reset():
    request = ResetPasswordRequest(
        email="student@example.edu",
        reset_token="reset-token",
        new_password="Testingaccount123_",
    )
    assert request.new_password == "Testingaccount123_"
