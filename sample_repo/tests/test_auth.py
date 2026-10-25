"""Tests for the authentication module."""
import pytest

from app import auth
from app.models import USERS, User


def setup_function():
    USERS.clear()
    USERS["ana"] = User("ana", auth.hash_password("s3cret-pass"))


def test_login_returns_token_for_valid_credentials():
    token = auth.login("ana", "s3cret-pass")
    assert auth.verify_token(token) == "ana"


def test_login_rejects_wrong_password():
    with pytest.raises(PermissionError):
        auth.login("ana", "wrong")
