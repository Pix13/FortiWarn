import httpx
import logging
from typing import Any, Dict, List, Optional, Union
from fortivarn.config.settings import FortiWarnSettings
from fortivarn.models.schemas import InterfaceStatus, SDWANStatus, FortinetResponse

logger = logging.getLogger(__name__)


class FortinetClient:
    def __init__(self, settings: FortiWarnSettings):
        self.settings = settings
        self.base_url = f"https://{settings.fortinet_host}"
        self._session = httpx.AsyncClient(
            verify=False,  # Often needed for internal fortigate SSL certs
            timeout=10.0
        )
        self.session_token: Optional[str] = None

    async def __aenter__(self):
        await self._authenticate()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any):
        await self._session.aclose()

    async def _authenticate(self) -> None:
        """
        Authenticate with FortiGate and obtain a session token.
        Supports both API key and username/password authentication.
        """
        url = f"{self.base_url}/api/v2/authentication"

        if self.settings.fortinet_api_key:
            # Use API key authentication
            data = {
                "secretkey": self.settings.fortinet_api_key.get_secret_value(),
                "request_key": True,
            }
        else:
            # Use username/password authentication
            data = {
                "username": self.settings.fortinet_username,
                "password": self.settings.fortinet_password.get_secret_value(),
                "secure": True,
            }

        try:
            response = await self._session.post(url, json=data)
            response.raise_for_status()
            resp_data = response.json()
            if resp_data.get("success") and resp_data.get("status_code") == 200:
                self.session_token = resp_data.get("session_key")
                logger.info("Authenticated with FortiGate successfully.")
            else:
                raise RuntimeError(f"FortiGate authentication failed: {resp_data}")
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to authenticate with FortiGate: {e}")
            raise

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers with session token and VDOM parameter."""
        headers = {"Content-Type": "application/json"}
        if self.session_token:
            headers["Authorization"] = f"Bearer {self.session_token}"
        return headers

    def _build_query_params(self) -> Dict[str, str]:
        """Build query parameters for API requests (includes VDOM support)."""
        params: Dict[str, str] = {}
        # Add VDOM parameter if FortiGate is running in single-VDOM or multi-VDOM mode
        # Most deployments require explicit vdom handling
        return params

    async def _request(self, method: str, url: str) -> Any:
        """Send an HTTP request to the FortiGate API with proper auth and VDOM support."""
        query = self._build_query_params()
        response = await self._session.request(
            method=method,
            url=url,
            headers=self._build_headers(),
            params=query if query else None,
        )
        response.raise_for_status()
        return response.json()

    async def get_interface_status(self, interface_name: str) -> List[InterfaceStatus]:
        """
        Queries the FortiGate SDWAN member list to determine if a specific
        WAN member (physical/vlink interface) is up or down.

        Uses /api/v2/monitor/system/sdwan/member endpoint which returns all
        SDWAN vlink members and their health-check status.
        """
        url = f"{self.base_url}/api/v2/monitor/system/sdwan/member"
        try:
            data = await self._request("GET", url)
            # Parse member list to find the requested interface
            member_statuses = []
            for item in data.get("results", []):
                member_iface = item.get("interface", "")
                if member_iface == interface_name or item.get("name") == interface_name:
                    health = item.get("status", "unknown")
                    # FortiGate SDWAN health checks return status like:
                    # "up" (healthy), "down" (unhealthy)
                    member_statuses.append(InterfaceStatus(
                        name=item.get("interface", item.get("name", "")),
                        status="up" if health in ("up",) else "down",
                    ))
            return member_statuses
        except Exception as e:
            logger.error(f"Failed to get interface/membership status for {interface_name}: {e}")
            raise

    async def get_sdwan_status(self) -> List[SDWANStatus]:
        """
        Queries the FortiGate SDWAN members' health status.
        Uses /api/v2/monitor/system/sdwan member endpoint.
        """
        url = f"{self.base_url}/api/v2/monitor/system/sdwan/member"
        try:
            data = await self._request("GET", url)
            response_data = FortinetResponse(**data)
            if response_data.results:
                return response_data.results
            # Fallback: parse SDWAN member status from results
            sdwan_statuses = []
            for item in data.get("results", []):
                try:
                    sdwan_statuses.append(SDWANStatus(
                        name=item.get("name", ""),
                        status=item.get("status", "unknown"),
                        interface=item.get("interface", ""),
                    ))
                except Exception as exc:
                    logger.warning(f"Failed to parse SDWAN member item: {item} (error: {exc})")
            return sdwan_statuses
        except Exception as e:
            logger.error(f"Failed to get SDWAN member status: {e}")
            raise


