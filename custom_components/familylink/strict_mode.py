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
- ``lock``: the device lock follows Home Assistant. Locked from HA today and
  unlocked on Google's side -> locked again; unlocked from HA today and
  locked on Google's side -> unlocked again; no HA decision and a Google
  unlock override (code 4) bypassing an active bedtime, school time or
  reached daily limit -> locked again, and unlocked by strict mode itself
  once the restriction is over, as Google would have done
- ``bedtime``: bedtime is off for today -> switch it back on
- ``daily_limit``: the daily limit is off -> switch it back on
- ``school_time``: school time is off for today -> switch it back on (opt-in,
  many parents run school hours from Home Assistant and keep Google's off)

Home Assistant stays in charge, not the rules: a change made from Home
Assistant (a switch, a button, an action) is the parent's decision and becomes
the setting to enforce for the rest of the day. Only what differs from that
setting on Google's side is reverted. The coordinator passes those decisions
as ``intents``: the policies switched on or off from HA today, the devices
locked or unlocked from HA today, and the devices whose HA-granted bonus is
still running.
"""
from __future__ import annotations

from typing import Any

STRICT_RULE_BONUS = "bonus"
STRICT_RULE_LOCK = "lock"
STRICT_RULE_BEDTIME = "bedtime"
STRICT_RULE_DAILY_LIMIT = "daily_limit"
STRICT_RULE_SCHOOL_TIME = "school_time"

STRICT_RULES: tuple[str, ...] = (
	STRICT_RULE_BONUS,
	STRICT_RULE_LOCK,
	STRICT_RULE_BEDTIME,
	STRICT_RULE_DAILY_LIMIT,
	STRICT_RULE_SCHOOL_TIME,
)

ACTION_CANCEL_BONUS = "cancel_bonus"
ACTION_LOCK_DEVICE = "lock_device"
ACTION_UNLOCK_DEVICE = "unlock_device"

# Device decision recorded by strict mode itself when it counters a bypass:
# it must lift that lock when the restriction ends.
DEVICE_INTENT_AUTO_LOCK = "auto_lock"
LOCK_OVERRIDE_LOCKED = 1
LOCK_OVERRIDE_UNLOCKED = 4
ACTION_ENABLE_BEDTIME = "enable_bedtime"
ACTION_ENABLE_DAILY_LIMIT = "enable_daily_limit"
ACTION_ENABLE_SCHOOL_TIME = "enable_school_time"


def device_is_usable(device: dict[str, Any], time_data: dict[str, Any] | None) -> bool:
	"""Same reading as the device switch: usable unless locked or restricted.

	A running bonus makes the device usable whatever the other restrictions;
	a manual lock always wins.
	"""
	if device.get("locked", False):
		return False
	if not time_data:
		return True
	if (time_data.get("bonus_minutes") or 0) > 0:
		return True
	if time_data.get("bedtime_active", False):
		return False
	daily_limit_remaining = time_data.get("daily_limit_remaining")
	if daily_limit_remaining is not None and daily_limit_remaining <= 0:
		return False
	return True


def restriction_active(time_data: dict[str, Any]) -> str | None:
	"""Name of the restriction Google should be enforcing on the device right now, or None."""
	if time_data.get("bedtime_active"):
		return "bedtime"
	if time_data.get("schooltime_active"):
		return "school time"
	remaining = time_data.get("daily_limit_remaining")
	if time_data.get("daily_limit_enabled") and remaining is not None and remaining <= 0:
		return "daily limit reached"
	return None


def _plan_device_lock(
	child_id: str | None,
	device: dict[str, Any],
	time_data: dict[str, Any],
	intent: str | None,
) -> list[dict[str, Any]]:
	"""The device lock follows Home Assistant (rule ``lock``).

	``intent`` is today's HA decision for the device: "lock", "unlock",
	"auto_lock" (a lock strict mode placed itself to counter a bypass) or
	None. Google's manual override on the device is ``lock_override``:
	1 locked, 4 unlocked (a bypass of the active restriction), None.
	"""
	device_id = device.get("id")
	locked = bool(device.get("locked", False))
	override = time_data.get("lock_override")
	active = restriction_active(time_data)

	def _action(name: str, reason: str, **extra: Any) -> dict[str, Any]:
		return {"action": name, "child_id": child_id, "device_id": device_id, "reason": reason, **extra}

	if intent == "lock":
		if not locked:
			return [_action(ACTION_LOCK_DEVICE, "unlocked on Google's side while locked from Home Assistant")]
		return []

	if intent == "unlock":
		if locked:
			return [_action(ACTION_UNLOCK_DEVICE, "locked on Google's side while unlocked from Home Assistant")]
		return []

	if intent == DEVICE_INTENT_AUTO_LOCK:
		if active is None:
			# The restriction strict mode was protecting is over: lift the
			# lock it placed, as Google's schedule would have done.
			return [_action(ACTION_UNLOCK_DEVICE, "restriction over, lifting the strict mode lock", clear_intent=True)]
		if not locked:
			return [_action(ACTION_LOCK_DEVICE, f"bypass of {active} ({'unlock override' if override == LOCK_OVERRIDE_UNLOCKED else 'lock lifted'})", record=DEVICE_INTENT_AUTO_LOCK)]
		return []

	# No HA decision: only a Google-side unlock override that bypasses an
	# active restriction is countered. A running bonus is a legitimate
	# bypass (a Google-side one is handled by the bonus rule first).
	if (
		active is not None
		and override == LOCK_OVERRIDE_UNLOCKED
		and not locked
		and (time_data.get("bonus_minutes") or 0) <= 0
	):
		return [_action(ACTION_LOCK_DEVICE, f"unlock override bypassing {active}", record=DEVICE_INTENT_AUTO_LOCK)]
	return []


def plan_strict_actions(
	child_data: dict[str, Any],
	rules: set[str] | frozenset[str],
	ha_bonus_devices: set[str] | frozenset[str] = frozenset(),
	intents: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
	"""Return the actions strict mode must take for one child, in order.

	``ha_bonus_devices`` lists the devices whose running bonus was granted from
	Home Assistant (button or action) and must be left alone. ``intents`` holds
	today's decisions made from Home Assistant: ``{"policies": {"bedtime":
	bool, "daily_limit": bool, "school_time": bool}, "devices": {device_id:
	"lock" | "unlock" | "auto_lock"}}``. A policy switched off from HA is not
	switched back on; the device lock follows the HA decision of the day.

	Each action is ``{"action": ..., "child_id": ..., "device_id"?: ...,
	"override_id"?: ..., "reason": ...}``. Device actions come first (a bonus
	is cancelled before the device is locked, as the device switch does),
	then the child-level policies.
	"""
	child_id = child_data.get("child_id")
	actions: list[dict[str, Any]] = []
	devices_time_data = child_data.get("devices_time_data") or {}
	intents = intents or {}
	wanted: dict[str, Any] = intents.get("policies") or {}
	device_intents: dict[str, str] = intents.get("devices") or {}

	for device in child_data.get("devices", []) or []:
		device_id = device.get("id")
		if not device_id:
			continue
		time_data = devices_time_data.get(device_id) or {}

		if STRICT_RULE_BONUS in rules and device_id not in ha_bonus_devices:
			override_id = time_data.get("bonus_override_id")
			if override_id:
				actions.append({
					"action": ACTION_CANCEL_BONUS,
					"child_id": child_id,
					"device_id": device_id,
					"override_id": override_id,
					"reason": f"bonus of {time_data.get('bonus_minutes', 0)} min active",
				})

		if STRICT_RULE_LOCK in rules and time_data:
			actions.extend(_plan_device_lock(child_id, device, time_data, device_intents.get(device_id)))

	if STRICT_RULE_BEDTIME in rules and wanted.get(STRICT_RULE_BEDTIME, True):
		today = child_data.get("bedtime_enabled_today")
		weekly = child_data.get("bedtime_enabled")
		effective = today if today is not None else weekly
		if effective is False:
			actions.append({
				"action": ACTION_ENABLE_BEDTIME,
				"child_id": child_id,
				"reason": "bedtime switched off",
			})

	if STRICT_RULE_DAILY_LIMIT in rules and wanted.get(STRICT_RULE_DAILY_LIMIT, True):
		# daily_limit_enabled is aggregated over the devices, so it is False
		# for a child without any device: nothing to enforce there.
		if child_data.get("daily_limit_enabled") is False and child_data.get("devices"):
			actions.append({
				"action": ACTION_ENABLE_DAILY_LIMIT,
				"child_id": child_id,
				"reason": "daily limit switched off",
			})

	if STRICT_RULE_SCHOOL_TIME in rules and wanted.get(STRICT_RULE_SCHOOL_TIME, True):
		today = child_data.get("school_time_enabled_today")
		weekly = child_data.get("school_time_enabled")
		effective = today if today is not None else weekly
		if effective is False:
			actions.append({
				"action": ACTION_ENABLE_SCHOOL_TIME,
				"child_id": child_id,
				"reason": "school time switched off",
			})

	return actions
