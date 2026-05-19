import pytest

import config


def _set_valid_runtime_config(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", None)
    monkeypatch.setattr(config, "ADMIN_PASSWORD_HASH", "$2b$12$hash")
    monkeypatch.setattr(config, "JWT_SECRET_KEY", "x" * 64)
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "DB_POOL_MINCONN", 1)
    monkeypatch.setattr(config, "DB_POOL_MAXCONN", 5)
    monkeypatch.setattr(config, "RATE_LIMIT_STORAGE_URI", "redis://localhost:6379/0")
    monkeypatch.setattr(config, "ALLOWED_ORIGINS_LIST", ["https://example.com"])


def test_runtime_config_rejects_wildcard_cors_with_credentials(monkeypatch):
    _set_valid_runtime_config(monkeypatch)
    monkeypatch.setattr(config, "ALLOWED_ORIGINS_LIST", ["*"])

    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        config._validate_runtime_config()


def test_runtime_config_rejects_plain_admin_password_in_production(monkeypatch):
    _set_valid_runtime_config(monkeypatch)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "plain-password")
    monkeypatch.setattr(config, "ADMIN_PASSWORD_HASH", "")

    with pytest.raises(ValueError, match="ADMIN_PASSWORD_HASH"):
        config._validate_runtime_config()


def test_runtime_config_rejects_non_redis_rate_limit_uri(monkeypatch):
    _set_valid_runtime_config(monkeypatch)
    monkeypatch.setattr(config, "RATE_LIMIT_STORAGE_URI", "postgresql://localhost/db")

    with pytest.raises(ValueError, match="RATE_LIMIT_STORAGE_URI"):
        config._validate_runtime_config()


def test_parse_bool_env_rejects_ambiguous_values(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "maybe")

    with pytest.raises(ValueError, match="TRUST_PROXY_HEADERS"):
        config._parse_bool_env("TRUST_PROXY_HEADERS", False)
