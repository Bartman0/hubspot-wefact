import pytest
from fastapi import HTTPException

import auth
from auth import verify_api_key


@pytest.fixture(autouse=True)
def set_known_key(monkeypatch):
    monkeypatch.setattr(auth, "VALID_API_KEY", "secret-key")


def test_valid_bearer_token_returns_token():
    assert verify_api_key("Bearer secret-key") == "secret-key"


def test_scheme_is_case_insensitive():
    assert verify_api_key("bearer secret-key") == "secret-key"


def test_missing_header_raises_401():
    with pytest.raises(HTTPException) as exc:
        verify_api_key(None)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Missing authorization header"


def test_wrong_scheme_raises_403():
    with pytest.raises(HTTPException) as exc:
        verify_api_key("Basic secret-key")
    assert exc.value.status_code == 403
    assert exc.value.detail == "Invalid API key"


def test_wrong_token_raises_403():
    with pytest.raises(HTTPException) as exc:
        verify_api_key("Bearer wrong-key")
    assert exc.value.status_code == 403


def test_token_only_no_scheme_raises_400():
    with pytest.raises(HTTPException) as exc:
        verify_api_key("secret-key")
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid authorization header format"


def test_too_many_parts_raises_400():
    with pytest.raises(HTTPException) as exc:
        verify_api_key("Bearer secret key")
    assert exc.value.status_code == 400


def test_empty_string_raises_400():
    # "".split() -> [] -> cannot unpack -> ValueError -> 400
    with pytest.raises(HTTPException) as exc:
        verify_api_key("")
    assert exc.value.status_code == 400
