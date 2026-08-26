"""Tests for the base station switch and button entities."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.switchbot_vacuum.button import BUTTONS, SwitchBotSelfCleanButton
from custom_components.switchbot_vacuum.const import (
    CMD_SELF_CLEANING,
    WORK_STATUS_DRYING_MOP,
    WORK_STATUS_SWEEPING,
    WORK_STATUS_WASHING_MOP,
)
from custom_components.switchbot_vacuum.switch import SwitchBotMopDryingSwitch

BUTTON_BY_KEY = {description.key: description for description in BUTTONS}


@pytest.fixture(autouse=True)
def no_ha_state_writes():
    """Let entities be exercised without being registered with Home Assistant."""
    with patch.object(SwitchBotMopDryingSwitch, "async_write_ha_state"):
        yield


def _switch(coordinator) -> SwitchBotMopDryingSwitch:
    """Build the drying switch."""
    return SwitchBotMopDryingSwitch(coordinator)


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator parked on the dock."""
    coord = MagicMock()
    coord.device_mac = "AABBCCDDEEFF"
    coord.data = {"work_status": WORK_STATUS_SWEEPING}
    coord.async_send_command = AsyncMock(return_value={"resultCode": 100})
    coord.async_request_refresh = AsyncMock()
    coord.async_set_updated_data = MagicMock()
    return coord


class TestMopDryingSwitch:
    """Test the mop drying switch."""

    def test_is_on_tracks_work_status(self, mock_coordinator):
        """Test the switch reflects the drying work status."""
        switch = _switch(mock_coordinator)
        assert switch.is_on is False
        mock_coordinator.data["work_status"] = WORK_STATUS_DRYING_MOP
        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on_starts_drying(self, mock_coordinator):
        """Test turning on sends self-clean action 2."""
        await _switch(mock_coordinator).async_turn_on()
        assert mock_coordinator.async_send_command.call_args[0] == (
            CMD_SELF_CLEANING,
            {"0": 2},
        )

    @pytest.mark.asyncio
    async def test_turn_off_stops_drying(self, mock_coordinator):
        """Test turning off sends self-clean action 3."""
        await _switch(mock_coordinator).async_turn_off()
        assert mock_coordinator.async_send_command.call_args[0] == (
            CMD_SELF_CLEANING,
            {"0": 3},
        )

    @pytest.mark.asyncio
    async def test_refuses_while_station_busy(self, mock_coordinator):
        """Test the command is not sent while the station is mid-cycle."""
        mock_coordinator.data["work_status"] = WORK_STATUS_WASHING_MOP
        with pytest.raises(HomeAssistantError):
            await _switch(mock_coordinator).async_turn_on()
        mock_coordinator.async_send_command.assert_not_called()


class TestSelfCleanButtons:
    """Test the one-shot base station buttons."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("key", "action"), [("collect_dust", 4), ("wash_mop", 1)]
    )
    async def test_press_sends_action(self, mock_coordinator, key, action):
        """Test each button sends its self-clean action."""
        button = SwitchBotSelfCleanButton(mock_coordinator, BUTTON_BY_KEY[key])
        await button.async_press()
        assert mock_coordinator.async_send_command.call_args[0] == (
            CMD_SELF_CLEANING,
            {"0": action},
        )

    @pytest.mark.asyncio
    async def test_refuses_while_station_busy(self, mock_coordinator):
        """Test the command is not sent while the station is mid-cycle."""
        mock_coordinator.data["work_status"] = WORK_STATUS_WASHING_MOP
        button = SwitchBotSelfCleanButton(
            mock_coordinator, BUTTON_BY_KEY["collect_dust"]
        )
        with pytest.raises(HomeAssistantError):
            await button.async_press()
        mock_coordinator.async_send_command.assert_not_called()

    def test_unique_ids_are_distinct(self, mock_coordinator):
        """Test each button gets its own unique_id."""
        ids = {
            SwitchBotSelfCleanButton(mock_coordinator, d).unique_id for d in BUTTONS
        }
        assert len(ids) == len(BUTTONS)


class TestDryingOptimisticState:
    """Test that the switch does not snap back before the station catches up."""

    @pytest.mark.asyncio
    async def test_stays_on_until_device_agrees(self, mock_coordinator):
        """Regression: the switch flipped straight back off after being turned on.

        The station needs several seconds to report work_status 20, so a poll landing
        in between must not be read as "the command did nothing".
        """
        switch = _switch(mock_coordinator)
        await switch.async_turn_on()
        assert switch.is_on is True

        # A poll arrives while the station is still spinning up.
        mock_coordinator.data["work_status"] = WORK_STATUS_SWEEPING
        assert switch.is_on is True

        mock_coordinator.data["work_status"] = WORK_STATUS_DRYING_MOP
        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_stays_off_until_device_agrees(self, mock_coordinator):
        """Test the same hold applies when stopping."""
        mock_coordinator.data["work_status"] = WORK_STATUS_DRYING_MOP
        switch = _switch(mock_coordinator)
        await switch.async_turn_off()
        assert switch.is_on is False

        mock_coordinator.data["work_status"] = WORK_STATUS_SWEEPING
        assert switch.is_on is False

    @pytest.mark.asyncio
    async def test_reverts_when_command_had_no_effect(self, mock_coordinator):
        """Test the optimistic value expires rather than sticking forever."""
        switch = _switch(mock_coordinator)
        await switch.async_turn_on()
        assert switch.is_on is True

        switch._pending_expiry = time.monotonic() - 1
        assert switch.is_on is False

    @pytest.mark.asyncio
    async def test_device_confirmation_clears_pending(self, mock_coordinator):
        """Test the hold is released once the device agrees, not left latched."""
        switch = _switch(mock_coordinator)
        await switch.async_turn_on()
        mock_coordinator.data["work_status"] = WORK_STATUS_DRYING_MOP
        assert switch.is_on is True
        assert switch._pending is None

        mock_coordinator.data["work_status"] = WORK_STATUS_SWEEPING
        assert switch.is_on is False
