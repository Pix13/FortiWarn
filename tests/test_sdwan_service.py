import pytest
from unittest.mock import AsyncMock, MagicMock

from fortivarn.services.sdwan_service import SDWANMonitorService
from fortivarn.models.schemas import HealthCheckResult


@pytest.mark.asyncio
async def test_check_connection_switch_detects_main_down_backup_up():
    """Switch is confirmed when main is down AND backup explicitly shows up."""
    mock_client = MagicMock()
    mock_client.get_health_checks = AsyncMock(return_value=[
        HealthCheckResult(name="wan1", status="down"),
        HealthCheckResult(name="wan2", status="up"),
    ])

    service = SDWANMonitorService(client=mock_client, main_iface="wan1", backup_iface="wan2")

    assert await service.check_connection_switch() is True


@pytest.mark.asyncio
async def test_check_connection_switch_stable_on_main():
    """No switch when both interfaces report up (normal load-balanced state)."""
    mock_client = MagicMock()
    mock_client.get_health_checks = AsyncMock(return_value=[
        HealthCheckResult(name="wan1", status="up"),
        HealthCheckResult(name="wan2", status="up"),
    ])

    service = SDWANMonitorService(client=mock_client, main_iface="wan1", backup_iface="wan2")

    assert await service.check_connection_switch() is False


@pytest.mark.asyncio
async def test_check_connection_switch_no_false_positive_both_down():
    """When both are down (transient failure), do NOT treat it as a switch."""
    mock_client = MagicMock()
    mock_client.get_health_checks = AsyncMock(return_value=[
        HealthCheckResult(name="wan1", status="down"),
        HealthCheckResult(name="wan2", status="down"),
    ])

    service = SDWANMonitorService(client=mock_client, main_iface="wan1", backup_iface="wan2")

    assert await service.check_connection_switch() is False


@pytest.mark.asyncio
async def test_check_connection_switch_empty_results():
    """No switch reported when the API returns no health-check entries."""
    mock_client = MagicMock()
    mock_client.get_health_checks = AsyncMock(return_value=[])

    service = SDWANMonitorService(client=mock_client, main_iface="wan1", backup_iface="wan2")

    assert await service.check_connection_switch() is False


@pytest.mark.asyncio
async def test_check_interface_status_filters_single():
    """get_interface_status returns only the requested interface."""
    mock_client = MagicMock()
    mock_client.get_health_checks = AsyncMock(return_value=[
        HealthCheckResult(name="wan1", status="up"),
        HealthCheckResult(name="wan2", status="down"),
    ])

    from fortivarn.models.fortinet_client import FortinetClient
    # We only need the filtering behaviour which lives in SDWANMonitorService;
    # this test verifies that _is_up helper correctly identifies a single interface.
    from fortivarn.services.sdwan_service import _is_up

    checks = await mock_client.get_health_checks()  # type: ignore[misc]
    assert _is_up(checks, "wan1") is True
    assert _is_up(checks, "wan2") is False


@pytest.mark.asyncio
async def test_check_connection_switch_main_missing_backup_present():
    """Main interface not in results at all + backup up = switch detected."""
    mock_client = MagicMock()
    mock_client.get_health_checks = AsyncMock(return_value=[
        HealthCheckResult(name="wan2", status="up"),
    ])

    service = SDWANMonitorService(client=mock_client, main_iface="wan1", backup_iface="wan2")

    assert await service.check_connection_switch() is True


@pytest.mark.asyncio
async def test_check_connection_switch_backup_missing_main_up():
    """Backup not in results + main up = stable (no switch)."""
    mock_client = MagicMock()
    mock_client.get_health_checks = AsyncMock(return_value=[
        HealthCheckResult(name="wan1", status="up"),
    ])

    service = SDWANMonitorService(client=mock_client, main_iface="wan1", backup_iface="wan2")

    assert await service.check_connection_switch() is False
