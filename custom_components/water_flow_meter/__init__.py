"""The Water Flow Meter integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, entity_platform

from .const import (
    DOMAIN,
    SERVICE_RESET_TOTAL_VOLUME,
    SERVICE_SET_TOTAL_VOLUME,
    SERVICE_RESET_DAILY_STATISTICS,
    ATTR_VOLUME,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Water Flow Meter from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    # Initialize entry data (will be populated by sensor platform)
    if entry.entry_id not in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.entry_id] = {}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    await async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Water Flow Meter."""

    async def async_reset_total_volume(call: ServiceCall) -> None:
        """Handle reset total volume service call."""
        entity_ids = call.data.get("entity_id")
        if not entity_ids:
            return

        # Ensure it's a list
        if not isinstance(entity_ids, list):
            entity_ids = [entity_ids]

        for entity_id in entity_ids:
            # Find the entity
            for entry_id, entry_data in hass.data[DOMAIN].items():
                if "entities" not in entry_data:
                    continue

                for entity in entry_data["entities"]:
                    if entity.entity_id == entity_id:
                        # Check if entity has the method
                        if hasattr(entity, "async_reset_total_volume"):
                            await entity.async_reset_total_volume()
                            _LOGGER.info("Reset total volume for %s", entity_id)
                        break

    async def async_set_total_volume(call: ServiceCall) -> None:
        """Handle set total volume service call."""
        entity_ids = call.data.get("entity_id")
        volume = call.data.get(ATTR_VOLUME)

        if not entity_ids or volume is None:
            return

        # Ensure it's a list
        if not isinstance(entity_ids, list):
            entity_ids = [entity_ids]

        for entity_id in entity_ids:
            # Find the entity
            for entry_id, entry_data in hass.data[DOMAIN].items():
                if "entities" not in entry_data:
                    continue

                for entity in entry_data["entities"]:
                    if entity.entity_id == entity_id:
                        # Check if entity has the method
                        if hasattr(entity, "async_set_total_volume"):
                            await entity.async_set_total_volume(volume)
                            _LOGGER.info("Set total volume to %s L for %s", volume, entity_id)
                        break

    async def async_reset_daily_statistics(call: ServiceCall) -> None:
        """Handle reset daily statistics service call."""
        entity_ids = call.data.get("entity_id")
        if not entity_ids:
            return

        # Ensure it's a list
        if not isinstance(entity_ids, list):
            entity_ids = [entity_ids]

        for entity_id in entity_ids:
            # Find the entity
            for entry_id, entry_data in hass.data[DOMAIN].items():
                if "entities" not in entry_data:
                    continue

                for entity in entry_data["entities"]:
                    if entity.entity_id == entity_id:
                        # Check if entity has the method
                        if hasattr(entity, "async_reset_daily_statistics"):
                            await entity.async_reset_daily_statistics()
                            _LOGGER.info("Reset daily statistics for %s", entity_id)
                        break

    # Register services only if not already registered
    if not hass.services.has_service(DOMAIN, SERVICE_RESET_TOTAL_VOLUME):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESET_TOTAL_VOLUME,
            async_reset_total_volume,
            schema=cv.make_entity_service_schema({}),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_TOTAL_VOLUME):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_TOTAL_VOLUME,
            async_set_total_volume,
            schema=cv.make_entity_service_schema(
                {vol.Required(ATTR_VOLUME): cv.positive_float}
            ),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_RESET_DAILY_STATISTICS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESET_DAILY_STATISTICS,
            async_reset_daily_statistics,
            schema=cv.make_entity_service_schema({}),
        )

    _LOGGER.info("Water Flow Meter services registered")
