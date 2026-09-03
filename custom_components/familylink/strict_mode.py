"""Strict mode: decide which Family Link changes must be reverted.

Family Link lets a supervised child, through the Google UI, cancel a
restriction the parent has set: post a time bonus, lift the lock of a device
that has no time left, or switch bedtime and the daily limit off. Strict mode
makes Home Assistant the authority: after every refresh the coordinator
compares what Google reports with what the parent wants and reverts the
difference. This module only contains the pure decision; the coordinator
performs the actions.

The four rules mirror the automations parents were writing by hand:

- ``bonus``: a bonus is active on a device -> cancel it
- ``unlock``: a device is usable although no screen time is left -> lock it
- ``bedtime``: bedtime is off for today -> switch it back on
- ``daily_limit``: the daily limit is off -> switch it back on
"""
from __future__ import annotations

from typing import Any

STRICT_RULE_BONUS = "bonus"
STRICT_RULE_UNLOCK = "unlock"
STRICT_RULE_BEDTIME = "bedtime"
STRICT_RULE_DAILY_LIMIT = "daily_limit"

STRICT_RULES: tuple[str, ...] = (
	STRICT_RULE_BONUS,
	STRICT_RULE_UNLOCK,
	STRICT_RULE_BEDTIME,
	STRICT_RULE_DAILY_LIMIT,
)

ACTION_CANCEL_BONUS = "cancel_bonus"
ACTION_LOCK_DEVICE = "lock_device"
ACTION_ENABLE_BEDTIME = "enable_bedtime"
ACTION_ENABLE_DAILY_LIMIT = "enable_daily_limit"


def device_is_usable(device: dict[str, Any], time_data: dict[str, Any] | None) -> bool:
	"""Same reading as the device switch: usable unless locked or restricted.

	A running bonus makes the device usable whatever the other restrictions;
	a manual lock always wins.
	"""
	if device.get("locked", False):
		return False
	if not time_data:
		return True
	if time_data.get("bonus_minutes", 0) > 0:
		return True
	if time_data.get("bedtime_active", False):
		return False
	if time_data.get("daily_limit_remaining", 1) <= 0:
		return False
	return True


def plan_strict_actions(child_data: dict[str, Any], rules: set[str] | frozenset[str]) -> list[dict[str, Any]]:
	"""Return the actions strict mode must take for one child, in order.

	Each action is ``{"action": ..., "child_id": ..., "device_id"?: ...,
	"override_id"?: ..., "reason": ...}``. Device actions come first (a bonus
	is cancelled before the device is locked, as the device switch does),
	then the child-level policies.
	"""
	child_id = child_data.get("child_id")
	actions: list[dict[str, Any]] = []
	devices_time_data = child_data.get("devices_time_data") or {}

	for device in child_data.get("devices", []) or []:
		device_id = device.get("id")
		if not device_id:
			continue
		time_data = devices_time_data.get(device_id) or {}

		if STRICT_RULE_BONUS in rules:
			override_id = time_data.get("bonus_override_id")
			if override_id:
				actions.append({
					"action": ACTION_CANCEL_BONUS,
					"child_id": child_id,
					"device_id": device_id,
					"override_id": override_id,
					"reason": f"bonus of {time_data.get('bonus_minutes', 0)} min active",
				})

		if STRICT_RULE_UNLOCK in rules:
			# The device is usable while the remaining time (bonus included,
			# 0 when the daily limit is off) is exhausted: somebody lifted
			# the lock or removed the limit from the Google side.
			remaining = time_data.get("remaining_minutes", 0) or 0
			if time_data and device_is_usable(device, time_data) and remaining <= 0:
				actions.append({
					"action": ACTION_LOCK_DEVICE,
					"child_id": child_id,
					"device_id": device_id,
					"reason": "device usable with no screen time left",
				})

	if STRICT_RULE_BEDTIME in rules:
		today = child_data.get("bedtime_enabled_today")
		weekly = child_data.get("bedtime_enabled")
		effective = today if today is not None else weekly
		if effective is False:
			actions.append({
				"action": ACTION_ENABLE_BEDTIME,
				"child_id": child_id,
				"reason": "bedtime switched off",
			})

	if STRICT_RULE_DAILY_LIMIT in rules:
		# daily_limit_enabled is aggregated over the devices, so it is False
		# for a child without any device: nothing to enforce there.
		if child_data.get("daily_limit_enabled") is False and child_data.get("devices"):
			actions.append({
				"action": ACTION_ENABLE_DAILY_LIMIT,
				"child_id": child_id,
				"reason": "daily limit switched off",
			})

	return actions
