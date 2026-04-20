from typing import Protocol, List
from fortivarn.models.fortinet_client import FortinetClient
from fortivarn.models.schemas import InterfaceStatus, SDWANStatus

class FortinetClientProtocol(Protocol):
    async def get_interface_status(self, interface_name: str) -> List[InterfaceStatus]: ...
    async def get_sdwan_status(self) -> List[SDWANStatus]: ...

class SDWANMonitorService:
    def __init__(self, client: FortinetClientProtocol, main_iface: str, backup_iface: str):
        self.client = client
        self.main_iface = main_iface
        self.backup_iface = backup_iface

    async def check_connection_switch(self) -> bool:
        """
        Returns True if the connection has switched to the backup interface.
        Logic: If main SDWAN member is down (no health-check success) OR
              SDWAN reports a different member is active as the preferred path.

        For FortiGate vlink-based SDWAN topologies, we check:
        1. Interface status of each SDWAN member via health checks
        2. SDWAN member list to see which members report "up"
           If backup is reported as up while main isn't clearly down,
           that indicates a routing/policy shift — treat it as a switch.
        """
        # 1. Check if the main interface (SDWAN member) is up
        interfaces = await self.client.get_interface_status(self.main_iface)
        main_is_up = any(i.name == self.main_iface and i.status == "up" for i in interfaces)

        # 2. Check SDWAN member status
        sdwan_statuses = await self.client.get_sdwan_status()

        # A switch has occurred if:
        # - Main member is down (interface health check failed), OR
        # - Backup member reports up (indicating it's the active path)
        backup_is_up = any(
            s.interface == self.backup_iface and s.status == "up" for s in sdwan_statuses
        )

        return not main_is_up or backup_is_up
