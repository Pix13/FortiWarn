import pytest
from unittest.mock import AsyncMock, MagicMock
from fortivarn.services.sdwan_service import SDWANMonitorService
from fortivarn.models.schemas import InterfaceStatus, SDWANStatus

@pytest.mark.asyncio
async def test_check_connection_switch_detects_main_down():
    # Arrange
    mock_client = MagicMock()
    # Mock get_interface_status to return main interface as 'down'
    mock_client.get_interface_status = AsyncMock(return_value=[
        InterfaceStatus(name="wan1", status="down")
    ])
    # Mock get_sdwan_status to return empty list (no backup active)
    mock_client.get_sdwan_status = AsyncMock(return_value=[])
    
    service = SDWANMonitorService(client=mock_client, main_iface="wan1", backup_iface="wan2")

    # Act
    result = await service.check_connection_switch()

    # Assert
    assert result is True  # Should detect switch because main is down

@pytest.mark.asyncio
async def test_check_connection_switch_detects_backup_active():
    # Arrange
    mock_client = MagicMock()
    # Main interface is up
    mock_client.get_interface_status = AsyncMock(return_value=[
        InterfaceStatus(name="wan1", status="up")
    ])
    # SDWAN reports backup (wan2) member is healthy/up
    mock_client.get_sdwan_status = AsyncMock(return_value=[
        SDWANStatus(name="sdwan1", status="up", interface="wan2")
    ])
    
    service = SDWANMonitorService(client=mock_client, main_iface="wan1", backup_iface="wan2")

    # Act
    result = await service.check_connection_switch()

    # Assert
    assert result is True  # Should detect switch because backup interface reports up

@pytest.mark.asyncio
async def test_check_connection_switch_stable_on_main():
    # Arrange
    mock_client = MagicMock()
    mock_client.get_interface_status = AsyncMock(return_value=[
        InterfaceStatus(name="wan1", status="up")
    ])
    mock_client.get_sdwan_status = AsyncMock(return_value=[])
    
    service = SDWANMonitorService(client=mock_client, main_iface="wan1", backup_iface="wan2")

    # Act
    result = await service.check_connection_switch()

    # Assert
    assert result is False  # Should be stable (main up, no backup reported)
