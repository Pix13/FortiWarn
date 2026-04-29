from enum import Enum
from typing import List, Protocol

from fortivarn.models.schemas import HealthCheckResult


class FortinetClientProtocol(Protocol):
    async def get_health_checks(self) -> List[HealthCheckResult]: ...


class LinkState(str, Enum):
    """Operational state of the SDWAN main/backup pair."""

    HEALTHY = "healthy"               # main up, backup up — full redundancy
    DEGRADED_BACKUP_DOWN = "degraded" # main up, backup DOWN — no failover capacity
    ON_BACKUP = "on_backup"           # main DOWN, backup up — failover in progress
    BOTH_DOWN = "both_down"           # both DOWN — total outage / transient flap


def _is_up(checks: List[HealthCheckResult], iface_name: str) -> bool:
    """Return True if *iface_name* has at least one health-check entry with status ``up``."""
    for c in checks:
        if c.name == iface_name and c.status == "up":
            return True
    return False


class SDWANMonitorService:
    def __init__(self, client: FortinetClientProtocol, main_iface: str, backup_iface: str):
        self.client = client
        self.main_iface = main_iface
        self.backup_iface = backup_iface

    async def get_link_state(self) -> LinkState:
        """Classify the current SDWAN pair into one of four ``LinkState`` values.

        A single API call fetches health checks for *all* interfaces; we then
        categorise the (main, backup) pair locally.
        """
        checks = await self.client.get_health_checks()
        main_up = _is_up(checks, self.main_iface)
        backup_up = _is_up(checks, self.backup_iface)

        if main_up and backup_up:
            return LinkState.HEALTHY
        if main_up and not backup_up:
            return LinkState.DEGRADED_BACKUP_DOWN
        if not main_up and backup_up:
            return LinkState.ON_BACKUP
        return LinkState.BOTH_DOWN

    async def check_connection_switch(self) -> bool:
        """Return True when the SD-WAN connection has switched to the backup.

        Kept for backward compatibility — equivalent to ``get_link_state() == ON_BACKUP``.
        """
        return await self.get_link_state() == LinkState.ON_BACKUP
