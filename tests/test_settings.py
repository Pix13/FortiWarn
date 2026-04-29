"""Tests for FortiWarnSettings validators (auth-mode requirement, host normalisation)."""
import pytest
from pydantic import ValidationError

from fortivarn.config.settings import FortiWarnSettings


_BASE_ENV = {
    "FORTINET_HOST": "fw.example.com",
    "MAIN_INTERFACE": "wan1",
    "BACKUP_INTERFACE": "wan2",
    "SMTP_SERVER": "smtp.example.com",
    "SMTP_PORT": "25",
    "EMAIL_FROM": "fw@example.com",
    "EMAIL_TO": "ops@example.com",
}


def _settings(monkeypatch, overrides):
    """Build settings from a clean env populated with the supplied keys only."""
    # Wipe any inherited FORTINET_/SMTP_/EMAIL_/MAIN_/BACKUP_ env vars.
    for k in list(_BASE_ENV.keys()) + [
        "FORTINET_USERNAME", "FORTINET_PASSWORD", "FORTINET_API_KEY", "FORTINET_VDOM",
        "SMTP_USER", "SMTP_PASSWORD",
    ]:
        monkeypatch.delenv(k, raising=False)
    env = {**_BASE_ENV, **overrides}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # Disable .env file loading so the actual repo .env can't influence the test.
    return FortiWarnSettings(_env_file=None)


def test_api_key_alone_is_sufficient(monkeypatch):
    s = _settings(monkeypatch, {"FORTINET_API_KEY": "abc"})
    assert s.fortinet_api_key.get_secret_value() == "abc"
    assert s.fortinet_username is None


def test_username_password_alone_is_sufficient(monkeypatch):
    s = _settings(monkeypatch, {
        "FORTINET_USERNAME": "admin",
        "FORTINET_PASSWORD": "pw",
    })
    assert s.fortinet_username == "admin"


def test_no_auth_at_all_raises(monkeypatch):
    with pytest.raises(ValidationError) as exc:
        _settings(monkeypatch, {})
    assert "authentication is missing" in str(exc.value).lower()


def test_username_without_password_raises(monkeypatch):
    with pytest.raises(ValidationError):
        _settings(monkeypatch, {"FORTINET_USERNAME": "admin"})


def test_smtp_creds_are_optional(monkeypatch):
    s = _settings(monkeypatch, {"FORTINET_API_KEY": "abc"})
    assert s.smtp_user is None
    assert s.smtp_password is None


@pytest.mark.parametrize("raw,expected", [
    ("fw.example.com", "fw.example.com"),
    ("fw.example.com:8443", "fw.example.com:8443"),
    ("https://fw.example.com:8443/", "fw.example.com:8443"),
    ("http://fw.example.com/", "fw.example.com"),
    ("HTTPS://Fw.Example.Com:8443", "Fw.Example.Com:8443"),
    ("  https://fw.example.com/  ", "fw.example.com"),
])
def test_host_strips_scheme_and_slash(monkeypatch, raw, expected):
    s = _settings(monkeypatch, {"FORTINET_HOST": raw, "FORTINET_API_KEY": "abc"})
    assert s.fortinet_host == expected
