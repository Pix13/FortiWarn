from typing import Optional
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class FortiWarnSettings(BaseSettings):
    # Fortinet Credentials
    fortinet_host: str = Field(..., validation_alias='FORTINET_HOST')
    fortinet_username: str = Field(..., validation_alias='FORTINET_USERNAME')
    fortinet_password: SecretStr = Field(..., validation_alias='FORTINET_PASSWORD')
    fortinet_api_key: Optional[SecretStr] = Field(None, validation_alias='FORTINET_API_KEY')

    # SDWAN Interface Names
    main_interface: str = Field(..., validation_alias='MAIN_INTERFACE')
    backup_interface: str = Field(..., validation_alias='BACKUP_INTERFACE')

    # Email Settings
    smtp_server: str = Field(..., validation_alias='SMTP_SERVER')
    smtp_port: int = Field(..., validation_alias='SMTP_PORT')
    smtp_user: str = Field(..., validation_alias='SMTP_USER')
    smtp_password: SecretStr = Field(..., validation_alias='SMTP_PASSWORD')
    email_from: str = Field(..., validation_alias='EMAIL_FROM')
    email_to: str = Field(..., validation_alias='EMAIL_TO')

    # Daemon Settings
    check_interval_seconds: int = Field(60, validation_alias='CHECK_INTERVAL_SECONDS')

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

def get_settings() -> FortiWarnSettings:
    return FortiWarnSettings()
