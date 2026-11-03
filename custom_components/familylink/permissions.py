"""Authorization of the familylink.* services.

Home Assistant evaluates a user's entity permissions only on service calls
that go through the entity platform machinery (toggling a switch, pressing a
button). The services registered by this integration take a raw ``child_id``
or ``device_id``, or no target at all (``all_children: true`` on the app
services, the first child or every child on others, see SERVICES.md), so
without a check of our own any authenticated user, administrator or not,
could grant a bonus, lift a bedtime or unlock a device through the API. That
is the wrong default for a household where the supervised child may well have
a Home Assistant account (issue #169).

The rule mirrors what Home Assistant already does for the entities:

- a call without a user (automation, script started by the system) is trusted;
- an administrator can do anything;
- a call that names an ``entity_id`` and nothing else is allowed when that entity
  is a Family Link entity and the user may control it, exactly as if they had
  toggled it from a dashboard, so an entity permission policy applies to the
  services too;
- a call that relies on raw identifiers, or that has no target at all, needs an
  administrator, because there is no entity to evaluate a policy against.

A non-administrator may not combine an ``entity_id`` with a raw identifier:
the handlers let the raw value win over the one read from the entity, which
would otherwise turn a permitted entity into a key for any other device.

On top of that, the "Users allowed to control Family Link" option (issue
#224) closes the entities themselves: Home Assistant lets every user press
any button or flip any switch unless an entity permission policy says
otherwise, and core has no UI for such policies. When the option lists users,
a person who is neither an administrator nor in the list is refused on every
Family Link entity action (button, switch, number, time, select) and every
``familylink.*`` service. An empty list keeps the previous behaviour. Calls
without a user (automations, scripts run by the system) stay allowed.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
import logging
from typing import Any

import voluptuous as vol

from homeassistant.auth.permissions.const import POLICY_CONTROL
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import Unauthorized, UnknownUser
from homeassistant.helpers import entity_registry as er

from .const import CONF_ALLOWED_USERS, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Fields whose presence turns a call into a raw-identifier call.
RAW_TARGET_FIELDS = ("child_id", "device_id")


def allowed_user_ids(hass: HomeAssistant) -> set[str] | None:
	"""The users the option allows, across the Family Link entries; None when no entry restricts."""
	allowed: set[str] = set()
	restricted = False
	for entry in hass.config_entries.async_entries(DOMAIN):
		users = entry.options.get(CONF_ALLOWED_USERS) or []
		if users:
			restricted = True
			allowed.update(users)
	return allowed if restricted else None


def _refuse_unlisted(hass: HomeAssistant, user: Any, context: Any, action: str) -> None:
	"""Raise Unauthorized when the option lists users and this non-administrator is not one of them."""
	allowed = allowed_user_ids(hass)
	if allowed is None or user.id in allowed:
		return
	_LOGGER.warning(
		"%s refused: user %s is not in the users allowed to control Family Link",
		action, user.name,
	)
	raise Unauthorized(context=context, permission=POLICY_CONTROL)


async def async_check_entity_action(entity: Any) -> None:
	"""Raise Unauthorized unless the user behind this entity action may control Family Link.

	Home Assistant sets the context of the service call on the entity right
	before it calls the action method, so ``entity._context`` names the user
	who pressed the button or flipped the switch.
	"""
	context = getattr(entity, "_context", None)
	user_id = context.user_id if context else None
	if not user_id:
		# No user: an automation, a script run by the system
		return
	if allowed_user_ids(entity.hass) is None:
		return
	user = await entity.hass.auth.async_get_user(user_id)
	if user is None:
		raise UnknownUser(context=context, permission=POLICY_CONTROL)
	if user.is_admin:
		return
	_refuse_unlisted(entity.hass, user, context, f"Action on {entity.entity_id}")


async def async_verify_service_call(hass: HomeAssistant, call: ServiceCall) -> None:
	"""Raise Unauthorized unless the caller may run this service call."""
	user_id = call.context.user_id
	if not user_id:
		# No user: an automation, a script run by the system, a startup task.
		return

	user = await hass.auth.async_get_user(user_id)
	if user is None:
		raise UnknownUser(context=call.context, permission=POLICY_CONTROL)
	if user.is_admin:
		return
	_refuse_unlisted(hass, user, call.context, f"Service {call.domain}.{call.service}")

	entity_id = call.data.get("entity_id")
	raw_fields = [field for field in RAW_TARGET_FIELDS if call.data.get(field)]

	if entity_id and not raw_fields:
		# The entity must be one of ours: a light the user controls resolves no
		# child, and the handlers then fall back to the first child, which would
		# turn any controllable entity into a key for that child's settings
		entry = er.async_get(hass).async_get(entity_id)
		if entry is None or entry.platform != DOMAIN:
			_LOGGER.warning(
				"Service %s.%s refused: %s is not a Family Link entity",
				call.domain, call.service, entity_id,
			)
			raise Unauthorized(
				context=call.context, entity_id=entity_id, permission=POLICY_CONTROL
			)
		if user.permissions.check_entity(entity_id, POLICY_CONTROL):
			return
		_LOGGER.warning(
			"Service %s.%s refused: user %s may not control %s",
			call.domain, call.service, user.name, entity_id,
		)
		raise Unauthorized(
			context=call.context, entity_id=entity_id, permission=POLICY_CONTROL
		)

	if raw_fields:
		reason = f"uses raw identifiers ({', '.join(raw_fields)})"
	else:
		reason = "has no entity target"
	_LOGGER.warning(
		"Service %s.%s refused: user %s is not an administrator and the call %s",
		call.domain, call.service, user.name, reason,
	)
	raise Unauthorized(context=call.context, permission=POLICY_CONTROL)


async def async_require_admin(hass: HomeAssistant, call: ServiceCall) -> None:
	"""Raise Unauthorized unless the caller is an administrator.

	For a service that no entity permission can make safe for a non-administrator,
	one that fetches a URL from inside Home Assistant for instance. As above, a
	call without a user is trusted.
	"""
	user_id = call.context.user_id
	if not user_id:
		return
	user = await hass.auth.async_get_user(user_id)
	if user is None:
		raise UnknownUser(context=call.context, permission=POLICY_CONTROL)
	if user.is_admin:
		return
	_LOGGER.warning(
		"Service %s.%s refused: user %s is not an administrator",
		call.domain, call.service, user.name,
	)
	raise Unauthorized(context=call.context, permission=POLICY_CONTROL)


def async_register_guarded_service(
	hass: HomeAssistant,
	domain: str,
	service: str,
	handler: Callable[[ServiceCall], Awaitable[Any]],
	schema: vol.Schema,
	supports_response: SupportsResponse = SupportsResponse.NONE,
) -> None:
	"""Register a service whose handler only runs for an authorized caller."""

	@wraps(handler)
	async def guarded(call: ServiceCall) -> Any:
		await async_verify_service_call(hass, call)
		return await handler(call)

	hass.services.async_register(domain, service, guarded, schema=schema, supports_response=supports_response)
