"""Config flow for Water Flow Meter integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_SOURCE_SENSOR,
    CONF_PULSES_PER_LITER,
    CONF_FLOW_RATE_WINDOW,
    DEFAULT_PULSES_PER_LITER,
    DEFAULT_FLOW_RATE_WINDOW,
)

_LOGGER = logging.getLogger(__name__)


class WaterFlowMeterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Water Flow Meter."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate the source sensor exists
            source_sensor = user_input[CONF_SOURCE_SENSOR]

            # Create a unique ID based on the source sensor
            await self.async_set_unique_id(f"{DOMAIN}_{source_sensor}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Water Flow Meter ({source_sensor})",
                data=user_input,
            )

        # Schema for configuration
        data_schema = vol.Schema(
            {
                vol.Required(CONF_SOURCE_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor"),
                ),
                vol.Required(
                    CONF_PULSES_PER_LITER,
                    default=DEFAULT_PULSES_PER_LITER
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.01,
                        max=1000,
                        step=0.01,
                        mode=selector.NumberSelectorMode.BOX,
                    ),
                ),
                vol.Required(
                    CONF_FLOW_RATE_WINDOW,
                    default=DEFAULT_FLOW_RATE_WINDOW
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=600,
                        step=10,
                        unit_of_measurement="seconds",
                        mode=selector.NumberSelectorMode.BOX,
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> WaterFlowMeterOptionsFlow:
        """Get the options flow for this handler."""
        return WaterFlowMeterOptionsFlow(config_entry)


class WaterFlowMeterOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Water Flow Meter."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_PULSES_PER_LITER,
                    default=self.config_entry.options.get(
                        CONF_PULSES_PER_LITER,
                        self.config_entry.data.get(
                            CONF_PULSES_PER_LITER, DEFAULT_PULSES_PER_LITER
                        ),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.01,
                        max=1000,
                        step=0.01,
                        mode=selector.NumberSelectorMode.BOX,
                    ),
                ),
                vol.Required(
                    CONF_FLOW_RATE_WINDOW,
                    default=self.config_entry.options.get(
                        CONF_FLOW_RATE_WINDOW,
                        self.config_entry.data.get(
                            CONF_FLOW_RATE_WINDOW, DEFAULT_FLOW_RATE_WINDOW
                        ),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=600,
                        step=10,
                        unit_of_measurement="seconds",
                        mode=selector.NumberSelectorMode.BOX,
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )
