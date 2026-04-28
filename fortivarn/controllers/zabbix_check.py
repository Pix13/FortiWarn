"""Zabbix-friendly one-shot status probe.

Invoked by a Zabbix agent ``UserParameter`` to report which SDWAN link is
currently carrying traffic on the FortiGate. Performs a single health-check
API call and prints one integer to stdout:

    0  main interface is up (normal state)
    1  backup interface is active (main is down, backup is up)
    2  unknown / error / both interfaces down

Exit code is always 0 so Zabbix records the value rather than treating the
poll as a failed item.
"""
import asyncio
import logging
import sys

from fortivarn.config.settings import FortiWarnSettings
from fortivarn.models.fortinet_client import FortinetClient
from fortivarn.services.sdwan_service import SDWANMonitorService, _is_up

STATUS_MAIN = 0
STATUS_BACKUP = 1
STATUS_UNKNOWN = 2


async def _probe() -> int:
    settings = FortiWarnSettings()
    client = FortinetClient(settings)
    service = SDWANMonitorService(
        client=client,
        main_iface=settings.main_interface,
        backup_iface=settings.backup_interface,
    )
    async with client:
        checks = await client.get_health_checks()
        main_up = _is_up(checks, service.main_iface)
        backup_up = _is_up(checks, service.backup_iface)

    if main_up:
        return STATUS_MAIN
    if backup_up:
        return STATUS_BACKUP
    return STATUS_UNKNOWN


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
