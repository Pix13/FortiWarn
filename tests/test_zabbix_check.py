import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fortivarn.controllers import zabbix_check
from fortivarn.models.schemas import HealthCheckResult


def _settings_stub():
    s = MagicMock()
    s.main_interface = "wan1"
    s.backup_interface = "wan2"
    return s


def _patched_probe(checks):
    """Patch FortinetClient + FortiWarnSettings so _probe can run without env/network."""
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get_health_checks = AsyncMock(return_value=checks)

    return (
        patch.object(zabbix_check, "FortiWarnSettings", return_value=_settings_stub()),
        patch.object(zabbix_check, "FortinetClient", return_value=fake_client),
    )


@pytest.mark.asyncio
async def test_probe_returns_main_when_main_up():
    s_patch, c_patch = _patched_probe([
        HealthCheckResult(name="wan1", status="up"),
        HealthCheckResult(name="wan2", status="up"),
    ])
    with s_patch, c_patch:
        assert await zabbix_check._probe() == zabbix_check.STATUS_MAIN


@pytest.mark.asyncio
async def test_probe_returns_backup_when_main_down_backup_up():
    s_patch, c_patch = _patched_probe([
        HealthCheckResult(name="wan1", status="down"),
        HealthCheckResult(name="wan2", status="up"),
    ])
    with s_patch, c_patch:
        assert await zabbix_check._probe() == zabbix_check.STATUS_BACKUP


@pytest.mark.asyncio
async def test_probe_returns_unknown_when_both_down():
    s_patch, c_patch = _patched_probe([
        HealthCheckResult(name="wan1", status="down"),
        HealthCheckResult(name="wan2", status="down"),
    ])
    with s_patch, c_patch:
        assert await zabbix_check._probe() == zabbix_check.STATUS_UNKNOWN


def test_main_prints_unknown_and_exits_zero_on_error(capsys):
    """If anything raises (e.g. missing .env), main() must still print 2 and exit 0."""
    with patch.object(zabbix_check, "_probe", side_effect=RuntimeError("boom")):
        with pytest.raises(SystemExit) as exc:
            zabbix_check.main()
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == "2"
