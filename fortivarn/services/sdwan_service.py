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
        Logic: If main interface is down OR SDWAN status indicates backup is active.
        """
        # 1. Check physical/logical status of interfaces
        interfaces = await self.client.get_interface_status(self.main_iface)
        # The API might return multiple if name match isn't exact, but we expect the specific one
        main_is_up = any(i.name == self.main_iface and i.status == "up" for i in interfaces)

        # 2. Check SDWAN status (as a secondary verification)
        sdwan_statuses = await self.client.get_sdwan_status()
        # Depending on FortiOS version, we check if the active interface is NOT the main one
        backup_active = any(s.interface == self.backup_iface for s in sdwan_statuses)

        return not main_is_up or backup_active
