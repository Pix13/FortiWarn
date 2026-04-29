"""Zabbix-friendly one-shot status probe.

Invoked by a Zabbix agent ``UserParameter`` to report which SDWAN link is
currently carrying traffic on the FortiGate. Performs a single health-check
API call and prints one integer to stdout:

    0  HEALTHY              — main up, backup up (full redundancy)
    1  ON_BACKUP            — main down, backup up (failover active)
    2  UNKNOWN              — probe failed / both interfaces down
    3  DEGRADED_BACKUP_DOWN — main up, backup down (no failover capacity)

Exit code is always 0 so Zabbix records the value rather than treating the
poll as a failed item.
"""
import asyncio
import logging
import sys

from fortivarn.config.settings import FortiWarnSettings
from fortivarn.models.fortinet_client import FortinetClient
from fortivarn.services.sdwan_service import LinkState, SDWANMonitorService

STATUS_MAIN = 0
STATUS_BACKUP = 1
STATUS_UNKNOWN = 2
STATUS_DEGRADED = 3

_STATE_TO_STATUS = {
    LinkState.HEALTHY: STATUS_MAIN,
    LinkState.ON_BACKUP: STATUS_BACKUP,
    LinkState.BOTH_DOWN: STATUS_UNKNOWN,
    LinkState.DEGRADED_BACKUP_DOWN: STATUS_DEGRADED,
}


async def _probe() -> int:
    settings = FortiWarnSettings()
    client = FortinetClient(settings)
    service = SDWANMonitorService(
        client=client,
        main_iface=settings.main_interface,
        backup_iface=settings.backup_interface,
    )
    async with client:
        state = await service.get_link_state()
    return _STATE_TO_STATUS.get(state, STATUS_UNKNOWN)


def main() -> None:
    # Silence library noise so stdout stays a single integer for Zabbix.
    logging.basicConfig(level=logging.CRITICAL)
    try:
        status = asyncio.run(_probe())
    except Exception:
        status = STATUS_UNKNOWN
    print(status)
    sys.exit(0)


if __name__ == "__main__":
    main()
