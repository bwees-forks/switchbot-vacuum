"""Tests for the SwitchBot Vacuum clean mode select entities."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.switchbot_vacuum.select import SELECTS, SwitchBotCleanModeSelect

SELECT_BY_KEY = {description.key: description for description in SELECTS}


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator exposing a clean mode."""
    coord = MagicMock()
    coord.device_mac = "AABBCCDDEEFF"
    coord.data = {
        "clean_mode": {
            "type": "sweep_mop",
            "fan_level": 2,
            "water_level": 1,
            "times": 1,
        }
    }
    coord.current_clean_mode = MagicMock(
        side_effect=lambda: dict(coord.data["clean_mode"])
    )
    coord.async_change_clean_mode = AsyncMock()
    return coord


def _make(coordinator, key: str) -> SwitchBotCleanModeSelect:
    """Build one select entity by key."""
    return SwitchBotCleanModeSelect(coordinator, SELECT_BY_KEY[key])


class TestCleanTypeSelect:
    """Test the clean type select."""

    def test_options_include_sweep_then_mop(self, mock_coordinator):
        """Test all four modes decoded from the app are offered."""
        assert _make(mock_coordinator, "clean_type").options == [
            "sweep",
            "mop",
            "sweep_mop",
            "first_sweep_then_mop",
        ]

    def test_current_option(self, mock_coordinator):
        """Test current option reflects the device's clean mode."""
        assert _make(mock_coordinator, "clean_type").current_option == "sweep_mop"

    @pytest.mark.asyncio
    async def test_select_sends_only_that_field(self, mock_coordinator):
        """Test selecting a mode does not clobber the other clean mode fields."""
        await _make(mock_coordinator, "clean_type").async_select_option(
            "first_sweep_then_mop"
        )
        assert mock_coordinator.async_change_clean_mode.call_args.kwargs == {
            "type": "first_sweep_then_mop"
        }


class TestWaterLevelSelect:
    """Test the water level select."""

    def test_current_option_maps_int_to_name(self, mock_coordinator):
        """Test the numeric water level is shown as a name."""
        sel = _make(mock_coordinator, "water_level")
        assert sel.current_option == "low"
        mock_coordinator.data["clean_mode"]["water_level"] = 3
        assert sel.current_option == "high"

    @pytest.mark.asyncio
    async def test_select_maps_name_to_int(self, mock_coordinator):
        """Test the chosen name is sent as the numeric level."""
        await _make(mock_coordinator, "water_level").async_select_option("medium")
        assert mock_coordinator.async_change_clean_mode.call_args.kwargs == {
            "water_level": 2
        }


class TestPassesSelect:
    """Test the passes select."""

    @pytest.mark.asyncio
    async def test_select_sends_int(self, mock_coordinator):
        """Test passes are sent as an int, not the option string."""
        await _make(mock_coordinator, "passes").async_select_option("2")
        assert mock_coordinator.async_change_clean_mode.call_args.kwargs == {"times": 2}


class TestUnknownValues:
    """Test resilience to values the device reports but we do not model."""

    def test_unmodelled_value_reads_as_none(self, mock_coordinator):
        """Test an unexpected value does not raise or invent an option."""
        mock_coordinator.data["clean_mode"]["type"] = "some_future_mode"
        assert _make(mock_coordinator, "clean_type").current_option is None
        mock_coordinator.data["clean_mode"]["water_level"] = 9
        assert _make(mock_coordinator, "water_level").current_option == "low"

    def test_every_select_has_unique_id(self, mock_coordinator):
        """Test each select gets a distinct unique_id."""
        ids = {_make(mock_coordinator, d.key).unique_id for d in SELECTS}
        assert len(ids) == len(SELECTS)
