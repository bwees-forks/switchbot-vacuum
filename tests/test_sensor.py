"""Tests for the SwitchBot Vacuum room sensor entities."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.switchbot_vacuum.binary_sensor import (
    SwitchBotMopDrying,
    SwitchBotMopWashing,
)
from custom_components.switchbot_vacuum.const import (
    WORK_STATUS_DRYING_MOP,
    WORK_STATUS_SWEEPING,
    WORK_STATUS_WASHING_MOP,
)
from custom_components.switchbot_vacuum.sensor import (
    SwitchBotRoomSensor,
    SwitchBotVacuumStatus,
)


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator with rooms."""
    coord = MagicMock()
    coord.data = {
        "rooms": {"ROOM_001": "Table", "ROOM_013": "Kitchen"},
        "work_status": WORK_STATUS_SWEEPING,
        "error_code": 0,
    }
    coord.device_mac = "AABBCCDDEEFF"
    coord.device_name = "S10"
    return coord


class TestRoomSensor:
    """Test room sensor entity."""

    def test_sensor_name(self, mock_coordinator):
        """Test sensor name is room name."""
        sensor = SwitchBotRoomSensor(mock_coordinator, "ROOM_013", "Kitchen")
        assert sensor.name == "Kitchen"

    def test_sensor_unique_id(self, mock_coordinator):
        """Test unique_id includes device mac and room id."""
        sensor = SwitchBotRoomSensor(mock_coordinator, "ROOM_013", "Kitchen")
        assert sensor.unique_id == "AABBCCDDEEFF_room_ROOM_013"

    def test_native_value_is_room_name(self, mock_coordinator):
        """Test native value returns current room name."""
        sensor = SwitchBotRoomSensor(mock_coordinator, "ROOM_013", "Kitchen")
        assert sensor.native_value == "Kitchen"

    def test_native_value_updates_on_rename(self, mock_coordinator):
        """Test native value reflects renamed room."""
        sensor = SwitchBotRoomSensor(mock_coordinator, "ROOM_013", "Kitchen")
        mock_coordinator.data["rooms"]["ROOM_013"] = "Kuchnia"
        assert sensor.native_value == "Kuchnia"

    def test_extra_attributes_has_room_id(self, mock_coordinator):
        """Test extra attributes contain room_id."""
        sensor = SwitchBotRoomSensor(mock_coordinator, "ROOM_001", "Table")
        assert sensor.extra_state_attributes["room_id"] == "ROOM_001"

    def test_icon(self, mock_coordinator):
        """Test sensor icon."""
        sensor = SwitchBotRoomSensor(mock_coordinator, "ROOM_001", "Table")
        assert sensor.icon == "mdi:floor-plan"


class TestStatusSensor:
    """Test the work status sensor."""

    def test_known_status_name(self, mock_coordinator):
        """Test a known work status resolves to its name."""
        sensor = SwitchBotVacuumStatus(mock_coordinator)
        assert sensor.native_value == "sweeping"

    def test_station_activity_is_distinguishable(self, mock_coordinator):
        """Test base station activities are distinct, unlike the vacuum's DOCKED state."""
        sensor = SwitchBotVacuumStatus(mock_coordinator)
        mock_coordinator.data["work_status"] = WORK_STATUS_DRYING_MOP
        assert sensor.native_value == "drying_mop"
        mock_coordinator.data["work_status"] = WORK_STATUS_WASHING_MOP
        assert sensor.native_value == "deeply_washing_mop"

    def test_unknown_status(self, mock_coordinator):
        """Test an unmapped status does not raise."""
        sensor = SwitchBotVacuumStatus(mock_coordinator)
        mock_coordinator.data["work_status"] = 999
        assert sensor.native_value == "unknown"

    def test_every_value_is_a_declared_option(self, mock_coordinator):
        """Test the enum options cover every name the sensor can report."""
        sensor = SwitchBotVacuumStatus(mock_coordinator)
        for status in list(range(40)) + [999]:
            mock_coordinator.data["work_status"] = status
            assert sensor.native_value in sensor.options


class TestMopSensors:
    """Test the mop drying and washing binary sensors."""

    def test_drying_on_from_work_status(self, mock_coordinator):
        """Test drying is detected from work_status 20."""
        mock_coordinator.data["work_status"] = WORK_STATUS_DRYING_MOP
        assert SwitchBotMopDrying(mock_coordinator).is_on is True

    def test_error_code_does_not_imply_drying(self, mock_coordinator):
        """Test drying is not inferred from an error code.

        Code 11 was previously treated as "drying mop", but that was read from property
        1019 (upgradeStatus) rather than the real error code, and 11 does not exist in
        the S10 error enum at all.
        """
        mock_coordinator.data["error_code"] = 11
        assert SwitchBotMopDrying(mock_coordinator).is_on is False

    def test_drying_off_while_sweeping(self, mock_coordinator):
        """Test drying is off during normal cleaning."""
        assert SwitchBotMopDrying(mock_coordinator).is_on is False

    def test_washing(self, mock_coordinator):
        """Test washing tracks work_status 16."""
        assert SwitchBotMopWashing(mock_coordinator).is_on is False
        mock_coordinator.data["work_status"] = WORK_STATUS_WASHING_MOP
        assert SwitchBotMopWashing(mock_coordinator).is_on is True
