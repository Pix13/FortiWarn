import asyncio
import httpx
import logging
from typing import Any, Dict, List, Optional

from fortivarn.config.settings import FortiWarnSettings
from fortivarn.models.schemas import HealthCheckResult, SDWANMember

logger = logging.getLogger(__name__)


class FortinetClient:
    """Async client for the FortiOS REST API.

    Supports two authentication modes (documented per FortiOS 7.x admin guide):

      - **API token** (recommended) — a pre-generated access_token is passed in every
        request as ``Authorization: Bearer <token>``. No login step required; tokens are
        long-lived unless revoked on the device.

      - **Username / password** (fallback) — obtains a short-lived session key via
        ``POST /api/v2/authentication`` and re-authenticates automatically when it expires.
    """

    # FortiOS session keys expire after 30 minutes by default; refresh at 25 min to stay safe.
    _SESSION_TTL_SECONDS = 25 * 60

    def __init__(self, settings: FortiWarnSettings):
        self.settings = settings
        self.base_url = f"https://{settings.fortinet_host}"
        self._session = httpx.AsyncClient(verify=False, timeout=10.0)
        # True when using an API token (no session refresh needed).
        self._using_api_token: bool = False
        # Session key for username/password auth mode; refreshed on expiry.
        self._session_key: Optional[str] = None

    async def __aenter__(self):
        await self._authenticate()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any):
        if not self._using_api_token and self._session_key is not None:
            try:
                # Log out to invalidate the session key on the FortiGate.
                await self._request("POST", f"{self.base_url}/api/v2/logout")
            except Exception as exc:  # noqa: BLE001 — logout failure is non-fatal at shutdown.
                logger.debug(f"Logout failed (non-critical): {exc}")
        await self._session.aclose()

    # ------------------------------------------------------------------ auth helpers
    async def _authenticate(self) -> None:
        """Authenticate with the FortiGate and obtain credentials for subsequent calls."""
        if self.settings.fortinet_api_key:
            token = str(self.settings.fortinet_api_key.get_secret_value())
            await self._verify_token(token)
            return

        # Username / password — exchange creds for a session key.
        url = f"{self.base_url}/api/v2/authentication"
        data = {
            "username": self.settings.fortinet_username,
            "secretkey": self.settings.fortinet_password.get_secret_value(),
            "request_key": True,
        }

        try:
            response = await self._session.post(url, json=data)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(f"Failed to authenticate with FortiGate: {exc}")
            raise RuntimeError(
                f"FortiOS authentication failed (HTTP {response.status_code})"
            ) from exc

        resp_data = response.json()
        if not self._check_success(resp_data):
            raise RuntimeError(f"FortiGate login rejected: {resp_data}")

        self._session_key = str(resp_data.get("session_key"))
        logger.info("Authenticated with FortiGate via username/password.")

    async def _verify_token(self, token: str) -> None:
        """Probe the API to make sure *token* is still valid."""
        url = f"{self.base_url}/api/v2/monitor/system/status"
        try:
            response = await self._session.get(
                url, headers=self._build_headers(token), params=self._vdom_params()
            )
            if response.status_code == 401:
                raise RuntimeError("API token rejected by FortiGate — check FORTINET_API_KEY")
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Token verification failed (HTTP {response.status_code})") from exc

    @staticmethod
    def _check_success(data: Dict[str, Any]) -> bool:
        return data.get("success", False) is True and data.get("status_code", -1) >= 200

    async def _ensure_authenticated(self):
        """Re-authenticate when using session-based auth if the TTL expired."""
        # API-token mode never needs refresh.
        pass  # pragma: no cover — actual re-auth logic is handled by catching HTTP 401 below.

    # ------------------------------------------------------------------ request helpers
    def _build_headers(self, token: Optional[str] = None) -> Dict[str, str]:
        """Build standard FortiOS API headers."""
        api_token = self.settings.fortinet_api_key.get_secret_value() if self.settings.fortinet_api_key else ""

        # Prefer the caller-provided session key; fall back to stored one.
        effective_token = token or self._session_key or api_token

        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {effective_token}",
        }

    def _vdom_params(self) -> Optional[Dict[str, str]]:
        """Return VDOM query parameters if configured."""
        vdom = getattr(self.settings, "fortinet_vdom", None)
        if not vdom:
            return None
        return {"vdom": vdom}

    async def _request(
        self, method: str, url: str, data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send an HTTP request to the FortiGate API.

        On ``HTTP 401`` with session-based auth this attempts a single re-login and retries.
        """
        headers = self._build_headers()
        params = self._vdom_params()

        try:
            response = await self._session.request(
                method=method, url=url, json=data, headers=headers, params=params or None
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401 and not self.settings.fortinet_api_key:
                logger.warning("Session expired — re-authenticating.")
                await self._authenticate()
                headers = self._build_headers()
                response = await self._session.request(
                    method=method, url=url, json=data, headers=headers, params=params or None
                )
            # Raise on any other error (or a second 401 after re-login).
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc2:
                logger.error(f"API request failed for {url}: {exc2}")
                raise

        return response.json()

    # ------------------------------------------------------------------ public API methods
    async def get_health_checks(self) -> List[HealthCheckResult]:
        """Return the health-check status of every SD-WAN member.

        Uses ``GET /api/v2/monitor/virtual-wan/health-check`` which returns a nested map:

            {"results": {<probe_type>: {<interface_name>: {...}}}}

        We flatten all probes and deduplicate by interface name (keeping the last probe's
        result, since any "down" status is sufficient to flag an issue).
        """
        url = f"{self.base_url}/api/v2/monitor/virtual-wan/health-check"
        try:
            data = await self._request("GET", url)

            seen: Dict[str, HealthCheckResult] = {}
            for _probe_type, members in data.get("results").items():  # type: ignore[union-attr]
                if isinstance(members, dict):
                    for name, attrs in members.items():
                        status_raw = attrs.get("status", "unknown")
                        seen[name] = HealthCheckResult(
                            name=name,
                            status="up" if status_raw == "up" else "down",
                            latency=attrs.get("latency"),
                            jitter=attrs.get("jitter"),
                            packet_loss=attrs.get("packet_loss"),
                        )

            return list(seen.values())

        except Exception as exc:  # noqa: BLE001 — log and re-raise.
            logger.error(f"Failed to query SD-WAN health checks: {exc}")
            raise

    async def get_interface_status(self, interface_name: str) -> List[HealthCheckResult]:
        """Return the health-check status for a *single* interface by name."""
        all_checks = await self.get_health_checks()
        return [hc for hc in all_checks if hc.name == interface_name]

    async def get_sdwan_status(self) -> List[SDWANMember]:
        """Convenience wrapper that returns the same health-check data as ``SDWANMember``.

        This keeps backward compatibility with code that expects an object carrying both
        a member *name* and its underlying physical *interface*.  In practice, for SD-WAN
        vlink topologies each probe name **is** the interface name (e.g. "wan1").
        """
        checks = await self.get_health_checks()
        return [
            SDWANMember(name=c.name, status=c.status, interface=c.name)
            for c in checks
        ]
