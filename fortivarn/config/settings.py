from typing import Optional
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class FortiWarnSettings(BaseSettings):
    # Fortinet Credentials
    fortinet_host: str = Field(..., validation_alias='FORTINET_HOST')
    # Username / password are only required if no API key is provided.
    fortinet_username: Optional[str] = Field(None, validation_alias='FORTINET_USERNAME')
    fortinet_password: Optional[SecretStr] = Field(None, validation_alias='FORTINET_PASSWORD')
    fortinet_api_key: Optional[SecretStr] = Field(None, validation_alias='FORTINET_API_KEY')
    fortinet_vdom: Optional[str] = Field(None, validation_alias='FORTINET_VDOM')

    # SDWAN Interface Names
    main_interface: str = Field(..., validation_alias='MAIN_INTERFACE')
    backup_interface: str = Field(..., validation_alias='BACKUP_INTERFACE')

    # Email Settings — SMTP creds are optional (unauthenticated internal relays).
    smtp_server: str = Field(..., validation_alias='SMTP_SERVER')
    smtp_port: int = Field(..., validation_alias='SMTP_PORT')
    smtp_user: Optional[str] = Field(None, validation_alias='SMTP_USER')
    smtp_password: Optional[SecretStr] = Field(None, validation_alias='SMTP_PASSWORD')
    email_from: str = Field(..., validation_alias='EMAIL_FROM')
    email_to: str = Field(..., validation_alias='EMAIL_TO')

    # Daemon Settings
    check_interval_seconds: int = Field(60, validation_alias='CHECK_INTERVAL_SECONDS')

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("fortinet_host", mode="before")
    @classmethod
    def _strip_host_url(cls, v: str) -> str:
        """Accept either ``host[:port]`` or a full ``https://host[:port]/`` URL.

        The HTTP client builds ``f"https://{host}"`` so any scheme/trailing slash here
        produces a malformed URL like ``https://https://host/``. Normalise both forms.
        """
        if not isinstance(v, str):
            return v
        host = v.strip()
        for scheme in ("https://", "http://"):
            if host.lower().startswith(scheme):
                host = host[len(scheme):]
                break
        return host.rstrip("/")

    @model_validator(mode="after")
    def _require_some_auth(self) -> "FortiWarnSettings":
        """Require either an API key OR a username+password pair."""
        if self.fortinet_api_key:
            return self
        if self.fortinet_username and self.fortinet_password:
            return self
        raise ValueError(
            "FortiGate authentication is missing: set FORTINET_API_KEY, "
            "or both FORTINET_USERNAME and FORTINET_PASSWORD."
        )


def get_settings() -> FortiWarnSettings:
    return FortiWarnSettings()
