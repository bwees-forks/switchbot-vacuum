"""Switch entities for SwitchBot Vacuum base station tasks."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CMD_SELF_CLEANING,
    DOMAIN,
    K10_FAMILY_DEVICE_TYPES,
    SELF_CLEAN_START_DRYING,
    SELF_CLEAN_STOP_DRYING,
    STATION_BUSY_STATUSES,
    WORK_STATUS_DRYING_MOP,
)
from .coordinator import SwitchBotS10Coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up base station switch entities."""
    if entry.data.get("device_type") in K10_FAMILY_DEVICE_TYPES:
        return

    coordinator: SwitchBotS10Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SwitchBotMopDryingSwitch(coordinator)])


class SwitchBotMopDryingSwitch(
    CoordinatorEntity[SwitchBotS10Coordinator], SwitchEntity
):
    """Starts and stops mop drying at the base station."""

    _attr_name = "Mop Drying"
    _attr_icon = "mdi:hair-dryer"

    def __init__(self, coordinator: SwitchBotS10Coordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_mac}_mop_drying_switch"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_mac)},
        )

    @property
    def is_on(self) -> bool:
        """Return True while the mop is being dried."""
        return self.coordinator.data.get("work_status") == WORK_STATUS_DRYING_MOP

    async def _async_self_clean(self, action: int, optimistic: int | None) -> None:
        """Send a self-clean action, refusing while the station is mid-cycle."""
        status = self.coordinator.data.get("work_status")
        if status in STATION_BUSY_STATUSES:
            raise HomeAssistantError(
                "The base station is busy; wait for the current task to finish"
            )
        await self.coordinator.async_send_command(CMD_SELF_CLEANING, {"0": action})
        if optimistic is not None:
            self.coordinator.async_set_updated_data(
                self.coordinator.data | {"work_status": optimistic}
            )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start drying the mop."""
        await self._async_self_clean(SELF_CLEAN_START_DRYING, WORK_STATUS_DRYING_MOP)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop drying the mop."""
        await self._async_self_clean(SELF_CLEAN_STOP_DRYING, None)
