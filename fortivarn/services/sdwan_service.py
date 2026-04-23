from typing import List, Protocol

from fortivarn.models.schemas import HealthCheckResult


class FortinetClientProtocol(Protocol):
    async def get_health_checks(self) -> List[HealthCheckResult]: ...


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

    async def check_connection_switch(self) -> bool:
        """Return True when the SD-WAN connection has switched to (or is using) the backup.

        A single API call fetches health checks for *all* interfaces at once, then we filter
        locally — no redundant round-trips to the FortiGate.

        Detection logic: a switch is confirmed only when **both** of these conditions hold:

            1. The main interface reports ``down`` (health-check failed).
            2. The backup interface explicitly exists in the results and reports ``up``.

        This avoids false positives during transient states where both links may briefly show
        "down" or where only one probe is temporarily flapping while the other remains healthy.
        """
        checks = await self.client.get_health_checks()

        main_up = _is_up(checks, self.main_iface)
        backup_up = _is_up(checks, self.backup_iface)

        return not main_up and backup_up
