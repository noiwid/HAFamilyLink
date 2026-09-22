"""Authorization of the familylink.* services.

Home Assistant evaluates a user's entity permissions only on service calls
that go through the entity platform machinery (toggling a switch, pressing a
button). The services registered by this integration take a raw ``child_id``
or ``device_id``, or no target at all (meaning every supervised child), so
without a check of our own any authenticated user, administrator or not,
could grant a bonus, lift a bedtime or unlock a device through the API. That
is the wrong default for a household where the supervised child may well have
a Home Assistant account (issue #169).

The rule mirrors what Home Assistant already does for the entities:

- a call without a user (automation, script started by the system) is trusted;
- an administrator can do anything;
- a call that names an ``entity_id`` and nothing else is allowed when the user
  may control that entity, exactly as if they had toggled it from a dashboard,
  so an entity permission policy applies to the services too;
- a call that relies on raw identifiers, or that has no target at all, needs an
  administrator, because there is no entity to evaluate a policy against.

A non-administrator may not combine an ``entity_id`` with a raw identifier:
the handlers let the raw value win over the one read from the entity, which
would otherwise turn a permitted entity into a key for any other device.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
import logging

import voluptuous as vol

from homeassistant.auth.permissions.const import POLICY_CONTROL
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import Unauthorized, UnknownUser

_LOGGER = logging.getLogger(__name__)

# Fields whose presence turns a call into a raw-identifier call.
RAW_TARGET_FIELDS = ("child_id", "device_id")


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

	entity_id = call.data.get("entity_id")
	raw_fields = [field for field in RAW_TARGET_FIELDS if call.data.get(field)]

	if entity_id and not raw_fields:
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


def async_register_guarded_service(
	hass: HomeAssistant,
	domain: str,
	service: str,
	handler: Callable[[ServiceCall], Awaitable[None]],
	schema: vol.Schema,
) -> None:
	"""Register a service whose handler only runs for an authorized caller."""

	@wraps(handler)
	async def guarded(call: ServiceCall) -> None:
		await async_verify_service_call(hass, call)
		await handler(call)

	hass.services.async_register(domain, service, guarded, schema=schema)
