import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fortivarn.services.sdwan_service import LinkState


def _build_controller():
    from fortivarn.controllers import daemon_controller as dc

    settings = MagicMock()
    settings.main_interface = "wan1"
    settings.backup_interface = "wan2"
    settings.check_interval_seconds = 60

    with patch.object(dc, "FortiWarnSettings", return_value=settings), \
         patch.object(dc, "FortinetClient"), \
         patch.object(dc, "SDWANMonitorService"), \
         patch.object(dc, "EmailService") as email_cls:
        email = MagicMock()
        email.send_switch_alert = AsyncMock()
        email.send_backup_down_alert = AsyncMock()
        email_cls.return_value = email

        ctrl = dc.DaemonController()
        ctrl.email_service = email
        return ctrl, email


@pytest.mark.asyncio
async def test_failover_edge_sends_one_email():
    ctrl, email = _build_controller()

    await ctrl._handle_state(LinkState.ON_BACKUP)
    await ctrl._handle_state(LinkState.ON_BACKUP)  # still on backup — no second mail
    assert email.send_switch_alert.await_count == 1
    assert ctrl.is_on_backup is True


@pytest.mark.asyncio
async def test_recovery_resets_state():
    ctrl, email = _build_controller()
    await ctrl._handle_state(LinkState.ON_BACKUP)
    await ctrl._handle_state(LinkState.HEALTHY)
    assert ctrl.is_on_backup is False


@pytest.mark.asyncio
async def test_backup_down_edge_sends_one_email():
    ctrl, email = _build_controller()

    await ctrl._handle_state(LinkState.DEGRADED_BACKUP_DOWN)
    await ctrl._handle_state(LinkState.DEGRADED_BACKUP_DOWN)
    assert email.send_backup_down_alert.await_count == 1
    assert ctrl.is_backup_degraded is True


@pytest.mark.asyncio
async def test_backup_recovery_resets_degraded_flag():
    ctrl, email = _build_controller()
    await ctrl._handle_state(LinkState.DEGRADED_BACKUP_DOWN)
    await ctrl._handle_state(LinkState.HEALTHY)
    assert ctrl.is_backup_degraded is False


@pytest.mark.asyncio
async def test_healthy_state_sends_nothing():
    ctrl, email = _build_controller()
    await ctrl._handle_state(LinkState.HEALTHY)
    email.send_switch_alert.assert_not_awaited()
    email.send_backup_down_alert.assert_not_awaited()


@pytest.mark.asyncio
async def test_both_down_sends_nothing_but_does_not_crash():
    """BOTH_DOWN is logged as error but emits no email (avoids alert during transient flap)."""
    ctrl, email = _build_controller()
    await ctrl._handle_state(LinkState.BOTH_DOWN)
    email.send_switch_alert.assert_not_awaited()
    email.send_backup_down_alert.assert_not_awaited()


@pytest.mark.asyncio
async def test_failover_then_backup_recovers_to_main_clears_both_flags():
    """Worst-case path: backup goes down (degraded), then main also goes down (both_down),
    then backup recovers (on_backup), then main recovers (healthy)."""
    ctrl, email = _build_controller()

    await ctrl._handle_state(LinkState.DEGRADED_BACKUP_DOWN)
    assert ctrl.is_backup_degraded is True
    assert email.send_backup_down_alert.await_count == 1

    await ctrl._handle_state(LinkState.BOTH_DOWN)
    # leaving DEGRADED clears the flag
    assert ctrl.is_backup_degraded is False

    await ctrl._handle_state(LinkState.ON_BACKUP)
    assert ctrl.is_on_backup is True
    assert email.send_switch_alert.await_count == 1

    await ctrl._handle_state(LinkState.HEALTHY)
    assert ctrl.is_on_backup is False
    assert ctrl.is_backup_degraded is False
