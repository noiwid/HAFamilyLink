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
- ``bedtime``, ``daily_limit``, ``school_time``: the policy cannot be changed
  from the Family Link side. The reference is the state observed when strict
  mode was switched on, changed only from Home Assistant; whatever differs on
  Google's side is put back, on or off.
- ``values``: the weekly bedtime hours and the weekday quotas (7 days each)
  cannot be changed from the Family Link side either. Same reference logic;
  hours are rewritten in the weekly schedule. For the quotas, Google only
  honours today's override, so the rule enforces the minutes applied today
  against the reference of the weekday (the weekly value when strict mode
  started, or what HA set since).

Home Assistant stays in charge, not the rules: a change made from Home
Assistant (a switch, a button, an action) is the parent's decision and becomes
the setting to enforce for the rest of the day. Only what differs from that
setting on Google's side is reverted. Nothing is forced on: a policy that was
off when strict mode was switched on stays off. The coordinator passes those decisions
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
STRICT_RULE_VALUES = "values"

STRICT_RULES: tuple[str, ...] = (
	STRICT_RULE_BONUS,
	STRICT_RULE_LOCK,
	STRICT_RULE_BEDTIME,
	STRICT_RULE_DAILY_LIMIT,
	STRICT_RULE_SCHOOL_TIME,
	STRICT_RULE_VALUES,
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
ACTION_DISABLE_BEDTIME = "disable_bedtime"
ACTION_DISABLE_DAILY_LIMIT = "disable_daily_limit"
ACTION_DISABLE_SCHOOL_TIME = "disable_school_time"
ACTION_SET_BEDTIME = "set_bedtime"
ACTION_SET_DAILY_LIMIT = "set_daily_limit"

POLICY_RULES: tuple[str, ...] = (STRICT_RULE_BEDTIME, STRICT_RULE_DAILY_LIMIT, STRICT_RULE_SCHOOL_TIME)
_POLICY_ACTIONS = {
	STRICT_RULE_BEDTIME: (ACTION_ENABLE_BEDTIME, ACTION_DISABLE_BEDTIME, "bedtime"),
	STRICT_RULE_DAILY_LIMIT: (ACTION_ENABLE_DAILY_LIMIT, ACTION_DISABLE_DAILY_LIMIT, "daily limit"),
	STRICT_RULE_SCHOOL_TIME: (ACTION_ENABLE_SCHOOL_TIME, ACTION_DISABLE_SCHOOL_TIME, "school time"),
}


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
	today: int | None = None,
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

	for policy in POLICY_RULES:
		if policy not in rules:
			continue
		reference = wanted.get(policy)
		observed_states = observed_policy_states(child_data, policy)
		# No reference yet (snapshot pending) or state unknown: nothing to compare.
		# Both today's effective state and the weekly switch must match: a
		# "today only" change and a weekly change are both reverted.
		if reference is None or not observed_states or all(o == bool(reference) for o in observed_states):
			continue
		enable_action, disable_action, label = _POLICY_ACTIONS[policy]
		actions.append({
			"action": enable_action if reference else disable_action,
			"child_id": child_id,
			"reason": f"{label} switched {'off' if reference else 'on'} on Google's side",
		})

	if STRICT_RULE_VALUES in rules:
		actions.extend(_plan_values(child_data, intents.get("values") or {}, today))

	return actions


def observed_policy_states(child_data: dict[str, Any], policy: str) -> list[bool]:
	"""Today-effective and weekly states of a policy as Google reports them (known ones only)."""
	if policy == STRICT_RULE_BEDTIME:
		candidates = (child_data.get("bedtime_enabled_today"), child_data.get("bedtime_enabled"))
	elif policy == STRICT_RULE_SCHOOL_TIME:
		candidates = (child_data.get("school_time_enabled_today"), child_data.get("school_time_enabled"))
	elif policy == STRICT_RULE_DAILY_LIMIT:
		candidates = (observed_policy_state(child_data, policy),)
	else:
		candidates = ()
	return [bool(c) for c in candidates if c is not None]


def observed_policy_state(child_data: dict[str, Any], policy: str) -> bool | None:
	"""Today-effective state of a policy as Google reports it, None when unknown."""
	if policy == STRICT_RULE_BEDTIME:
		today = child_data.get("bedtime_enabled_today")
		return today if today is not None else child_data.get("bedtime_enabled")
	if policy == STRICT_RULE_SCHOOL_TIME:
		today = child_data.get("school_time_enabled_today")
		return today if today is not None else child_data.get("school_time_enabled")
	if policy == STRICT_RULE_DAILY_LIMIT:
		# Aggregated over the devices: meaningless for a child without any.
		if not child_data.get("devices"):
			return None
		return child_data.get("daily_limit_enabled")
	return None


def snapshot_policies(
	child_data: dict[str, Any],
	rules: set[str] | frozenset[str],
	intents: dict[str, Any] | None,
) -> dict[str, bool]:
	"""Policies whose reference is missing: the state observed now becomes it.

	Called by the coordinator before planning, when strict mode is on: the
	state in force when strict mode starts (or at the first poll of the day)
	is what Family Link may no longer change. Returns the entries to add.
	"""
	known = (intents or {}).get("policies") or {}
	added: dict[str, bool] = {}
	for policy in POLICY_RULES:
		if policy not in rules or policy in known:
			continue
		observed = observed_policy_state(child_data, policy)
		if observed is not None:
			added[policy] = bool(observed)
	return added

def _time_pair(value: Any) -> list[int] | None:
	"""[h, m] as a list of two ints, or None."""
	if (
		isinstance(value, (list, tuple)) and len(value) == 2
		and all(type(v) is int for v in value)
		and 0 <= value[0] <= 23 and 0 <= value[1] <= 59
	):
		return [int(value[0]), int(value[1])]
	return None


def observed_bedtime_hours(child_data: dict[str, Any]) -> dict[str, list[list[int]]]:
	"""Enabled weekly bedtime slots as {"1": [[h, m], [h, m]], ...} (ISO weekday keys)."""
	hours: dict[str, list[list[int]]] = {}
	for slot in child_data.get("bedtime_schedule") or []:
		if not isinstance(slot, dict) or not slot.get("enabled"):
			continue
		start, end = _time_pair(slot.get("start")), _time_pair(slot.get("end"))
		day = slot.get("day")
		if start and end and isinstance(day, int) and 1 <= day <= 7:
			hours[str(day)] = [start, end]
	return hours


def observed_daily_limits(child_data: dict[str, Any]) -> dict[str, int]:
	"""The seven weekday quotas of the weekly schedule (the app's values), {"1": minutes, ...}."""
	limits: dict[str, int] = {}
	for entry in child_data.get("daily_limit_week") or []:
		if not isinstance(entry, dict):
			continue
		day, minutes = entry.get("day"), entry.get("weekly_minutes")
		if type(day) is int and 1 <= day <= 7 and type(minutes) is int and minutes >= 0:
			limits[str(day)] = minutes
	return limits


def snapshot_values(
	child_data: dict[str, Any],
	rules: set[str] | frozenset[str],
	intents: dict[str, Any] | None,
) -> dict[str, Any]:
	"""Values whose reference is missing: the weekly bedtime hours and the
	daily limit minutes observed now become it. Returns the entries to add."""
	if STRICT_RULE_VALUES not in rules:
		return {}
	known = (intents or {}).get("values") or {}
	added: dict[str, Any] = {}
	if "bedtime" not in known:
		hours = observed_bedtime_hours(child_data)
		if hours:
			added["bedtime"] = hours
	if "weekly_limits" not in known:
		limits = observed_daily_limits(child_data)
		if limits:
			added["weekly_limits"] = limits
	return added


def _plan_values(child_data: dict[str, Any], values: dict[str, Any], today: int | None = None) -> list[dict[str, Any]]:
	"""Rule ``values``: put the weekly bedtime hours and the daily limits back."""
	child_id = child_data.get("child_id")
	actions: list[dict[str, Any]] = []

	reference_hours = values.get("bedtime") or {}
	if reference_hours:
		observed = observed_bedtime_hours(child_data)
		for day, (start, end) in sorted(reference_hours.items()):
			if observed.get(day) == [start, end]:
				continue
			actions.append({
				"action": ACTION_SET_BEDTIME,
				"child_id": child_id,
				"day": int(day),
				"start": start,
				"end": end,
				"reason": (
					f"bedtime hours for day {day} changed on Google's side "
					f"({observed.get(day) or 'slot missing'} instead of {[start, end]})"
				),
			})

	reference_limits = values.get("weekly_limits") or {}
	reference_today = reference_limits.get(str(today)) if today is not None else None
	if reference_today is not None:
		# The only write Google honours is today's override, so the rule
		# enforces today's quota: the minutes applied on each device must be
		# the reference of the weekday. Other weekdays are kept in the
		# reference for when they come (and for the weekly write, once its
		# form is captured). Limit off: the daily_limit policy rule owns it.
		devices_time_data = child_data.get("devices_time_data") or {}
		for device_id, time_data in devices_time_data.items():
			if not isinstance(time_data, dict) or not time_data.get("daily_limit_enabled"):
				continue
			applied = time_data.get("daily_limit_minutes")
			if type(applied) is not int or applied == reference_today:
				continue
			actions.append({
				"action": ACTION_SET_DAILY_LIMIT,
				"child_id": child_id,
				"device_id": device_id,
				"day": int(today),
				"minutes": int(reference_today),
				"reason": f"today's daily limit changed on Google's side ({applied} min instead of {reference_today})",
			})

	return actions
