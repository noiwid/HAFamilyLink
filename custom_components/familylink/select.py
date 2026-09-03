"""Select platform for Google Family Link integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER_NAME
from .coordinator import FamilyLinkDataUpdateCoordinator
from .devices import ensure_child_device

_LOGGER = logging.getLogger(LOGGER_NAME)

# Restriction levels of the trustedcontacts endpoint. 0 is what an account
# returns before the setting has ever been touched (captured live 2026-08-26)
# and behaves like 1, so both map to "Anyone".
OPTION_ANYONE = "Anyone"
OPTION_CONTACTS_ONLY = "Only contacts I add"
OPTION_CONTACTS_AND_GROUPS = "Contacts I add & limited groups"

OPTION_TO_LEVEL = {
    OPTION_ANYONE: 1,
    OPTION_CONTACTS_ONLY: 3,
    OPTION_CONTACTS_AND_GROUPS: 4,
}
LEVEL_TO_OPTION = {0: OPTION_ANYONE, **{level: option for option, level in OPTION_TO_LEVEL.items()}}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Family Link select platform."""
    coordinator: FamilyLinkDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    if not coordinator.data or "children_data" not in coordinator.data:
        _LOGGER.error("No children data in coordinator after first refresh")
        return

    for child_data in coordinator.data.get("children_data", []):
        ensure_child_device(hass, coordinator, entry.entry_id, child_data["child_id"], child_data["child_name"])

    entities = [
        FamilyLinkContactRestrictionSelect(
            coordinator, child_data["child_id"], child_data["child_name"]
        )
        for child_data in coordinator.data.get("children_data", [])
    ]
    async_add_entities(entities)


class FamilyLinkContactRestrictionSelect(CoordinatorEntity, SelectEntity):
    """Who can call and text the child (Family Link "Allowed calls and texts").

    The level is fetched by the coordinator with the other per-child data, so
    this entity only reads coordinator.data like the rest of the platform and
    benefits from its cache fallback and session-expiry handling.
    """

    _attr_options = list(OPTION_TO_LEVEL)
    _attr_icon = "mdi:phone-lock"

    def __init__(
        self,
        coordinator: FamilyLinkDataUpdateCoordinator,
        child_id: str,
        child_name: str,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._child_id = child_id
        self._child_name = child_name
        self._attr_name = f"{child_name} Allowed Calls & Texts"
        self._attr_unique_id = f"{DOMAIN}_{child_id}_allowed_calls_texts"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this child."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._child_id)},
            name=f"{self._child_name} (Family Link)",
            manufacturer="Google",
            model="Family Link Account",
        )

    def _get_child_data(self) -> dict[str, Any] | None:
        """Get coordinator data for this child."""
        if not self.coordinator.data or "children_data" not in self.coordinator.data:
            return None
        for child_data in self.coordinator.data["children_data"]:
            if child_data["child_id"] == self._child_id:
                return child_data
        return None

    @property
    def current_option(self) -> str | None:
        """Return the option matching the level last read by the coordinator."""
        child_data = self._get_child_data()
        if not child_data:
            return None
        level = child_data.get("contact_restriction")
        if level is None:
            return None
        option = LEVEL_TO_OPTION.get(level)
        if option is None:
            _LOGGER.debug(
                f"Unknown contact restriction level {level} for {self._child_name}"
            )
        return option

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the child ids so services can target this child."""
        attributes: dict[str, Any] = {
            "child_id": self._child_id,
            "child_name": self._child_name,
        }
        child_data = self._get_child_data()
        if child_data:
            attributes["restriction_level"] = child_data.get("contact_restriction")
        return attributes

    async def async_select_option(self, option: str) -> None:
        """Change who can call and text the child."""
        level = OPTION_TO_LEVEL[option]
        success = await self.coordinator.client.async_set_contact_restriction(
            level, account_id=self._child_id
        )
        if not success:
            _LOGGER.error(
                f"Failed to set allowed calls and texts to '{option}' for {self._child_name}"
            )
            return
        _LOGGER.info(f"Set allowed calls and texts to '{option}' for {self._child_name}")
        await self.coordinator.async_request_refresh()
