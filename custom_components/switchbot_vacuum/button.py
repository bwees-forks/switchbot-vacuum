"""Button entities for SwitchBot Vacuum base station tasks."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
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
    SELF_CLEAN_DUST_COLLECT,
    SELF_CLEAN_MOP_WASH,
    STATION_BUSY_STATUSES,
)
from .coordinator import SwitchBotS10Coordinator


@dataclass(frozen=True, kw_only=True)
class SelfCleanButtonDescription(ButtonEntityDescription):
    """Describes a button that triggers one base station task."""

    action: int


# There is no stop for either of these, which is why they are buttons rather than
# switches; only drying can be cancelled.
BUTTONS: tuple[SelfCleanButtonDescription, ...] = (
    SelfCleanButtonDescription(
        key="collect_dust",
        name="Collect Dust",
        translation_key="collect_dust",
        icon="mdi:delete-empty",
        action=SELF_CLEAN_DUST_COLLECT,
    ),
    SelfCleanButtonDescription(
        key="wash_mop",
        name="Wash Mop",
        translation_key="wash_mop",
        icon="mdi:washing-machine",
        action=SELF_CLEAN_MOP_WASH,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up base station button entities."""
    if entry.data.get("device_type") in K10_FAMILY_DEVICE_TYPES:
        return

    coordinator: SwitchBotS10Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SwitchBotSelfCleanButton(coordinator, description) for description in BUTTONS
    )


class SwitchBotSelfCleanButton(
    CoordinatorEntity[SwitchBotS10Coordinator], ButtonEntity
):
    """Triggers a one-shot base station task."""

    entity_description: SelfCleanButtonDescription

    def __init__(
        self,
        coordinator: SwitchBotS10Coordinator,
        description: SelfCleanButtonDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_mac}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_mac)},
        )

    async def async_press(self) -> None:
        """Run the task, refusing while the station is mid-cycle."""
        if self.coordinator.data.get("work_status") in STATION_BUSY_STATUSES:
            raise HomeAssistantError(
                "The base station is busy; wait for the current task to finish"
            )
        await self.coordinator.async_send_command(
            CMD_SELF_CLEANING, {"0": self.entity_description.action}
        )
        await self.coordinator.async_request_refresh()
