"""Map image entity for SwitchBot Vacuum."""
from __future__ import annotations

from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, K10_FAMILY_DEVICE_TYPES
from .coordinator import SwitchBotS10Coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the map image entity — only the S10 family has a map."""
    coordinator: SwitchBotS10Coordinator = hass.data[DOMAIN][entry.entry_id]
    if entry.data.get("device_type") in K10_FAMILY_DEVICE_TYPES:
        return
    async_add_entities([SwitchBotVacuumMap(hass, coordinator)])


class SwitchBotVacuumMap(CoordinatorEntity[SwitchBotS10Coordinator], ImageEntity):
    """The vacuum's current map, as rendered by the robot itself."""

    _attr_content_type = "image/png"
    _attr_name = "Map"
    _entity_component_unrecorded_attributes = frozenset({"calibration_points", "rooms"})

    def __init__(self, hass: HomeAssistant, coordinator: SwitchBotS10Coordinator) -> None:
        """Initialize."""
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{coordinator.device_mac}_map"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_mac)},
        )
        self._image: bytes | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Bump the image timestamp only when the map bytes actually changed."""
        current = self.coordinator.map
        if current is not None and current.image != self._image:
            self._image = current.image
            self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        """Return the current map PNG."""
        return self._image

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the world-to-pixel calibration and the room list."""
        current = self.coordinator.map
        if current is None:
            return {}
        return {
            "calibration_points": current.calibration_points,
            "rooms": current.rooms,
            "resolution": current.resolution,
            "rotation": current.rotation,
        }
