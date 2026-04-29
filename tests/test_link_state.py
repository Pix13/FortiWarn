import pytest
from unittest.mock import AsyncMock, MagicMock

from fortivarn.services.sdwan_service import SDWANMonitorService, LinkState
from fortivarn.models.schemas import HealthCheckResult


def _service(checks):
    client = MagicMock()
    client.get_health_checks = AsyncMock(return_value=checks)
    return SDWANMonitorService(client=client, main_iface="wan1", backup_iface="wan2")


@pytest.mark.asyncio
async def test_state_healthy():
    s = _service([
        HealthCheckResult(name="wan1", status="up"),
        HealthCheckResult(name="wan2", status="up"),
    ])
    assert await s.get_link_state() == LinkState.HEALTHY


@pytest.mark.asyncio
async def test_state_degraded_backup_down():
    s = _service([
        HealthCheckResult(name="wan1", status="up"),
        HealthCheckResult(name="wan2", status="down"),
    ])
    assert await s.get_link_state() == LinkState.DEGRADED_BACKUP_DOWN


@pytest.mark.asyncio
async def test_state_degraded_backup_missing():
    """Backup not reported at all should also count as DEGRADED while main is up."""
    s = _service([HealthCheckResult(name="wan1", status="up")])
    assert await s.get_link_state() == LinkState.DEGRADED_BACKUP_DOWN


@pytest.mark.asyncio
async def test_state_on_backup():
    s = _service([
        HealthCheckResult(name="wan1", status="down"),
        HealthCheckResult(name="wan2", status="up"),
    ])
    assert await s.get_link_state() == LinkState.ON_BACKUP


@pytest.mark.asyncio
async def test_state_both_down():
    s = _service([
        HealthCheckResult(name="wan1", status="down"),
        HealthCheckResult(name="wan2", status="down"),
    ])
    assert await s.get_link_state() == LinkState.BOTH_DOWN


@pytest.mark.asyncio
async def test_check_connection_switch_backcompat():
    """Old API still works — only ON_BACKUP returns True."""
    s = _service([
        HealthCheckResult(name="wan1", status="down"),
        HealthCheckResult(name="wan2", status="up"),
    ])
    assert await s.check_connection_switch() is True

    s2 = _service([
        HealthCheckResult(name="wan1", status="up"),
        HealthCheckResult(name="wan2", status="down"),
    ])
    assert await s2.check_connection_switch() is False
