from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class HealthCheckResult(BaseModel):
    """Represents health-check data for a single SD-WAN interface.

    Matches the response from: GET /api/v2/monitor/virtual-wan/health-check
    Example API response (per-interface object inside results.<probe_type>):
      {"status": "up", "latency": 0.134, "jitter": 0.023, "packet_loss": 0}
    """

    name: str = Field(description="Interface or SD-WAN member name")
    status: str = Field(
        description='Health check state: "up" (alive) or "down" (dead)'
    )
    latency: Optional[float] = None
    jitter: Optional[float] = None
    packet_loss: Optional[float] = None


class HealthCheckResponse(BaseModel):
    """Top-level FortiOS monitor API response wrapper.

    The /api/v2/monitor/virtual-wan/health-check endpoint returns:
      {"http_method": "GET", "results": {"<probe_type>": {...}}, ...}
    We only need the results dict keyed by probe type (e.g. ping, tcp).
    """

    results: Dict[str, Dict[str, HealthCheckResult]] = Field(default_factory=dict)


class SDWANMember(BaseModel):
    """Represents an individual SD-WAN member interface and its health state."""

    name: str = Field(description="SD-WAN zone or vlink name")
    status: str = Field(
        description='Interface health status from the FortiGate (e.g. "up", "down")'
    )
    interface: str = Field(description="Physical/vlink member interface, e.g. x1, wan1")
