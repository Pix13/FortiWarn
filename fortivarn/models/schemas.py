from pydantic import BaseModel, Field
from typing import List, Optional

class InterfaceStatus(BaseModel):
    name: str
    status: str  # e.g., "up", "down"
    ip: Optional[str] = None
    mac: Optional[str] = None

class FortinetResponse(BaseModel):
    """Wrapper for typical FortiOS API responses."""
    results: List[InterfaceStatus] = Field(default_factory=list)

class SDWANStatus(BaseModel):
    name: str
    status: str  # e.g., "up", "down", "pending" — FortiGate SDWAN member health status
    interface: str  # The physical/vlink interface used by this member

class InterfaceSDWANMember(BaseModel):
    """Represents an SDWAN vlink member from the API."""
    name: str
    seq_num: int
    interface: str
    zone: Optional[str] = None
