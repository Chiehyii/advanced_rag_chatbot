from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import admin_api
import config


def _request(method: str, *, headers: dict | None = None, cookies: dict | None = None):
    return SimpleNamespace(
        method=method,
        headers=headers or {},
        cookies=cookies or {},
        client=SimpleNamespace(host="203.0.113.10"),
    )


def _access_token():
    return admin_api.create_access_token(
        {"sub": config.ADMIN_USERNAME},
        expires_delta=timedelta(minutes=5),
        token_type="access",
    )


def test_admin_get_request_allows_valid_access_token_without_csrf():
    request = _request("GET")

    assert admin_api.verify_admin(request, token=_access_token()) == config.ADMIN_USERNAME


def test_admin_unsafe_request_requires_ajax_header():
    request = _request("POST")

    with pytest.raises(HTTPException) as exc_info:
        admin_api.verify_admin(request, token=_access_token())

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Missing CSRF protection header"


def test_admin_unsafe_request_requires_matching_csrf_header_and_cookie():
    csrf_token = admin_api.create_csrf_token(config.ADMIN_USERNAME)
    request = _request(
        "POST",
        headers={"X-Requested-With": "XMLHttpRequest", "X-CSRF-Token": csrf_token},
        cookies={admin_api.ADMIN_CSRF_COOKIE_NAME: csrf_token},
    )

    assert admin_api.verify_admin(request, token=_access_token()) == config.ADMIN_USERNAME


def test_admin_unsafe_request_rejects_missing_csrf_cookie():
    csrf_token = admin_api.create_csrf_token(config.ADMIN_USERNAME)
    request = _request(
        "POST",
        headers={"X-Requested-With": "XMLHttpRequest", "X-CSRF-Token": csrf_token},
    )

    with pytest.raises(HTTPException) as exc_info:
        admin_api.verify_admin(request, token=_access_token())

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Invalid CSRF token"


def test_active_subject_from_refresh_token_rejects_revoked_or_missing_db_record(monkeypatch):
    refresh_token = admin_api.create_access_token(
        {"sub": config.ADMIN_USERNAME, "jti": "refresh-jti"},
        expires_delta=timedelta(days=1),
        token_type="refresh",
    )

    class Cursor:
        def execute(self, query, params=None):
            self.params = params

        def fetchone(self):
            return None

    class CursorContext:
        def __enter__(self):
            return object(), Cursor()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(admin_api, "_ensure_auth_tables", lambda: None)
    monkeypatch.setattr(admin_api, "get_db_cursor", lambda commit=False: CursorContext())

    assert admin_api._active_subject_from_refresh_token(refresh_token) is None


def test_active_subject_from_refresh_token_accepts_active_db_record(monkeypatch):
    refresh_token = admin_api.create_access_token(
        {"sub": config.ADMIN_USERNAME, "jti": "refresh-jti"},
        expires_delta=timedelta(days=1),
        token_type="refresh",
    )

    class Cursor:
        def execute(self, query, params=None):
            self.params = params

        def fetchone(self):
            return (1,)

    class CursorContext:
        def __enter__(self):
            return object(), Cursor()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(admin_api, "_ensure_auth_tables", lambda: None)
    monkeypatch.setattr(admin_api, "get_db_cursor", lambda commit=False: CursorContext())

    assert admin_api._active_subject_from_refresh_token(refresh_token) == config.ADMIN_USERNAME
