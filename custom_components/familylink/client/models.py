"""Data models for Google Family Link integration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class DeviceStatus(Enum):
	"""Device status enumeration."""
	LOCKED = "locked"
	UNLOCKED = "unlocked"
	OFFLINE = "offline"
	UNKNOWN = "unknown"


@dataclass
class Device:
	"""Representation of a Family Link device."""
	
	id: str
	name: str
	status: DeviceStatus
	device_type: str | None = None
	last_seen: datetime | None = None
	battery_level: int | None = None
	location: dict[str, Any] | None = None
	
	@classmethod
	def from_dict(cls, data: dict[str, Any]) -> Device:
		"""Create Device from dictionary data."""
		status = DeviceStatus.UNKNOWN
		if "locked" in data:
			status = DeviceStatus.LOCKED if data["locked"] else DeviceStatus.UNLOCKED
		elif "status" in data:
			try:
				status = DeviceStatus(data["status"])
			except ValueError:
				status = DeviceStatus.UNKNOWN
		
		return cls(
			id=data["id"],
			name=data.get("name", f"Device {data['id']}"),
			status=status,
			device_type=data.get("type"),
			last_seen=data.get("last_seen"),
			battery_level=data.get("battery_level"),
			location=data.get("location"),
		)
	
	def to_dict(self) -> dict[str, Any]:
		"""Convert Device to dictionary."""
		return {
			"id": self.id,
			"name": self.name,
			"status": self.status.value,
			"locked": self.status == DeviceStatus.LOCKED,
			"device_type": self.device_type,
			"last_seen": self.last_seen.isoformat() if self.last_seen else None,
			"battery_level": self.battery_level,
			"location": self.location,
		} 