"""Select entities for SwitchBot Vacuum cleaning options."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CLEAN_PASS_LIST,
    CLEAN_PASSES,
    CLEAN_TYPES,
    DOMAIN,
    K10_FAMILY_DEVICE_TYPES,
    WATER_LEVEL_LIST,
    WATER_LEVEL_TO_NAME,
    WATER_LEVELS,
)
from .coordinator import SwitchBotS10Coordinator


@dataclass(frozen=True, kw_only=True)
class CleanModeSelectDescription(SelectEntityDescription):
    """Describes a select backed by one field of the clean mode property."""

    mode_field: str
    to_option: Callable[[Any], str]
    to_value: Callable[[str], Any]


SELECTS: tuple[CleanModeSelectDescription, ...] = (
    CleanModeSelectDescription(
        key="clean_type",
        name="Clean Type",
        translation_key="clean_type",
        icon="mdi:broom",
        options=CLEAN_TYPES,
        mode_field="type",
        to_option=str,
        to_value=str,
    ),
    CleanModeSelectDescription(
        key="water_level",
        name="Water Level",
        translation_key="water_level",
        icon="mdi:water",
        options=WATER_LEVEL_LIST,
        mode_field="water_level",
        to_option=lambda v: WATER_LEVEL_TO_NAME.get(v, "low"),
        to_value=lambda o: WATER_LEVELS[o],
    ),
    CleanModeSelectDescription(
        key="passes",
        name="Passes",
        translation_key="passes",
        icon="mdi:repeat",
        options=CLEAN_PASS_LIST,
        mode_field="times",
        to_option=str,
        to_value=lambda o: CLEAN_PASSES[o],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up clean mode select entities."""
    if entry.data.get("device_type") in K10_FAMILY_DEVICE_TYPES:
        return

    coordinator: SwitchBotS10Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SwitchBotCleanModeSelect(coordinator, description) for description in SELECTS
    )


class SwitchBotCleanModeSelect(
    CoordinatorEntity[SwitchBotS10Coordinator], SelectEntity
):
    """Select for one field of the vacuum's clean mode."""

    entity_description: CleanModeSelectDescription

    def __init__(
        self,
        coordinator: SwitchBotS10Coordinator,
        description: CleanModeSelectDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_mac}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_mac)},
        )

    @property
    def current_option(self) -> str | None:
        """Return the active option for this clean mode field."""
        mode = self.coordinator.current_clean_mode()
        option = self.entity_description.to_option(
            mode.get(self.entity_description.mode_field)
        )
        return option if option in self.options else None

    async def async_select_option(self, option: str) -> None:
        """Change this field, leaving the rest of the clean mode untouched."""
        await self.coordinator.async_change_clean_mode(
            **{
                self.entity_description.mode_field: self.entity_description.to_value(
                    option
                )
            }
        )
