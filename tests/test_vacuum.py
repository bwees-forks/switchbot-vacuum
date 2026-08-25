"""Tests for the SwitchBot S10 vacuum entity."""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from homeassistant.components.vacuum import VacuumEntityFeature

from custom_components.switchbot_vacuum import vacuum as vacuum_module
from custom_components.switchbot_vacuum.const import (
    DEVICE_TYPE_K10,
    DEVICE_TYPE_S10,
    DEVICE_TYPE_S20,
    DEVICE_TYPE_S20PRO,
    WORK_STATUS_CHARGE_DONE,
    WORK_STATUS_CHARGING,
    WORK_STATUS_CLEANING,
    WORK_STATUS_DRYING_MOP,
    WORK_STATUS_GO_CHARGE,
    WORK_STATUS_PAUSED,
    WORK_STATUS_STANDBY,
)
from custom_components.switchbot_vacuum.vacuum import SwitchBotS10Vacuum


@dataclass
class _StandInSegment:
    """Stands in for homeassistant.components.vacuum.Segment on HA < 2026.8."""

    id: str
    name: str
    group: str | None = None


SEGMENT_CLS = vacuum_module.Segment or _StandInSegment
CLEAN_AREA = VacuumEntityFeature(16384)


@pytest.fixture
def clean_area_supported():
    """Make the entity behave as it does on an HA core that has area cleaning."""
    with patch.object(vacuum_module, "Segment", SEGMENT_CLS), patch.object(
        vacuum_module, "CLEAN_AREA_FEATURE", CLEAN_AREA
    ):
        yield


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator with data."""
    coord = MagicMock()
    coord.entry.data = {"device_type": DEVICE_TYPE_S10}
    coord.data = {
        "online": True,
        "battery": 85,
        "work_status": WORK_STATUS_CHARGE_DONE,
        "error_code": 0,
        "clean_mode": {"fan_level": 2, "times": 1, "type": "sweep_mop", "water_level": 1},
        "clean_summary": {"clean_area": 45, "clean_time": 30, "duration": 1800},
        "firmware": "1.1.061",
        "rooms": {"ROOM_001": "Table", "ROOM_013": "Kitchen"},
    }
    coord.device_mac = "AABBCCDDEEFF"
    coord.device_name = "S10 B6"
    coord.async_send_command = AsyncMock(return_value={"resultCode": 100})
    coord.async_request_refresh = AsyncMock()
    coord.async_refresh = AsyncMock()
    coord.async_refresh_rooms = AsyncMock()
    coord.async_change_clean_mode = AsyncMock(return_value={"resultCode": 100})
    coord.current_clean_mode = MagicMock(
        side_effect=lambda: dict(coord.data["clean_mode"])
    )
    return coord


class TestVacuumState:
    """Test vacuum state mapping."""

    def test_activity_docked_when_charging(self, mock_coordinator):
        """Test charging maps to DOCKED."""
        mock_coordinator.data["work_status"] = WORK_STATUS_CHARGING
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.activity.value == "docked"

    def test_activity_docked_when_charge_done(self, mock_coordinator):
        """Test charge done maps to DOCKED."""
        mock_coordinator.data["work_status"] = WORK_STATUS_CHARGE_DONE
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.activity.value == "docked"

    def test_activity_cleaning(self, mock_coordinator):
        """Test cleaning status maps to CLEANING."""
        mock_coordinator.data["work_status"] = WORK_STATUS_CLEANING
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.activity.value == "cleaning"

    def test_activity_paused(self, mock_coordinator):
        """Test paused status maps to PAUSED."""
        mock_coordinator.data["work_status"] = WORK_STATUS_PAUSED
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.activity.value == "paused"

    def test_activity_returning(self, mock_coordinator):
        """Test go charge maps to RETURNING."""
        mock_coordinator.data["work_status"] = WORK_STATUS_GO_CHARGE
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.activity.value == "returning"

    def test_activity_idle_when_standby(self, mock_coordinator):
        """Test standby maps to IDLE."""
        mock_coordinator.data["work_status"] = WORK_STATUS_STANDBY
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.activity.value == "idle"

    def test_battery_level(self, mock_coordinator):
        """Test battery level is read from data."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.battery_level == 85

    def test_fan_speed(self, mock_coordinator):
        """Test fan speed maps from fan_level."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.fan_speed == "Standard"

    def test_extra_state_attributes(self, mock_coordinator):
        """Test extra attributes include rooms and clean info."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        attrs = vac.extra_state_attributes
        assert attrs["water_level"] == 1
        assert attrs["clean_type"] == "sweep_mop"
        assert "rooms" in attrs
        assert attrs["rooms"]["ROOM_013"] == "Kitchen"


class TestVacuumCommands:
    """Test vacuum command methods."""

    @pytest.mark.asyncio
    async def test_start(self, mock_coordinator):
        """Test start sends clean_all."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_start()
        mock_coordinator.async_send_command.assert_called_once()
        args = mock_coordinator.async_send_command.call_args
        assert args[0][0] == 1001  # CMD_CLEAN
        assert args[0][1]["0"] == "clean_all"

    @pytest.mark.asyncio
    async def test_stop(self, mock_coordinator):
        """Test stop sends stop command."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_stop()
        args = mock_coordinator.async_send_command.call_args
        assert args[0][0] == 1009  # CMD_CONTROL
        assert args[0][1]["0"] == "stop"

    @pytest.mark.asyncio
    async def test_pause(self, mock_coordinator):
        """Test pause sends pause command."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_pause()
        args = mock_coordinator.async_send_command.call_args
        assert args[0][1]["0"] == "pause"

    @pytest.mark.asyncio
    async def test_return_to_base(self, mock_coordinator):
        """Test return to base sends go charge."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_return_to_base()
        args = mock_coordinator.async_send_command.call_args
        assert args[0][0] == 1022  # CMD_GO_CHARGE

    @pytest.mark.asyncio
    async def test_set_fan_speed(self, mock_coordinator):
        """Test set fan speed sends change mode."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_set_fan_speed("Strong")
        assert mock_coordinator.async_change_clean_mode.call_args.kwargs == {
            "fan_level": 3
        }

    @pytest.mark.asyncio
    async def test_clean_rooms_with_ids(self, mock_coordinator):
        """Test clean_rooms with room IDs."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_clean_rooms(
            rooms=["ROOM_013", "ROOM_008"],
            mode="mop",
            fan_level=1,
            water_level=2,
            times=1,
            force_order=True,
        )
        args = mock_coordinator.async_send_command.call_args
        assert args[0][0] == 1001
        params = args[0][1]
        assert params["0"] == "clean_rooms"
        assert len(params["1"]["rooms"]) == 2
        assert params["1"]["rooms"][0]["room_id"] == "ROOM_013"
        assert params["1"]["rooms"][0]["mode"]["type"] == "mop"


class TestFanSpeedLabels:
    """Test the capitalized fan speed labels and their lowercase aliases."""

    def test_list_is_capitalized(self, mock_coordinator):
        """Test the UI is offered capitalized labels."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.fan_speed_list == ["Quiet", "Standard", "Strong", "Max"]

    def test_reported_speed_is_capitalized(self, mock_coordinator):
        """Test the current speed reads back capitalized."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.fan_speed == "Standard"

    @pytest.mark.asyncio
    async def test_legacy_lowercase_still_works(self, mock_coordinator):
        """Test automations written against the old lowercase names do not silently break."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        for name in ("quiet", "standard", "strong", "max"):
            await vac.async_set_fan_speed(name)
        levels = [
            call.kwargs["fan_level"]
            for call in mock_coordinator.async_change_clean_mode.call_args_list
        ]
        assert levels == [1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_k10_legacy_lowercase_still_works(self, mock_coordinator):
        """Test the K10 suction path also accepts the old lowercase names."""
        mock_coordinator.entry.data = {"device_type": DEVICE_TYPE_K10}
        mock_coordinator.async_send_info = AsyncMock()
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_set_fan_speed("max")
        assert mock_coordinator.async_send_info.call_args[0][0] == {
            "SuctionPowLevel": 3
        }


class TestRoomNameResolution:
    """Test that clean_rooms accepts room names, not just IDs."""

    @pytest.mark.asyncio
    async def test_resolve_room_names(self, mock_coordinator):
        """Test room names are resolved to IDs."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_clean_rooms(
            rooms=["Kitchen", "Table"],
            mode="mop",
            fan_level=1,
            water_level=2,
            times=1,
            force_order=True,
        )
        args = mock_coordinator.async_send_command.call_args
        rooms_sent = args[0][1]["1"]["rooms"]
        room_ids = [r["room_id"] for r in rooms_sent]
        assert "ROOM_013" in room_ids
        assert "ROOM_001" in room_ids

    @pytest.mark.asyncio
    async def test_mixed_names_and_ids(self, mock_coordinator):
        """Test mix of names and IDs."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_clean_rooms(
            rooms=["Kitchen", "ROOM_001"],
            mode="sweep_mop",
            fan_level=2,
            water_level=1,
            times=1,
            force_order=False,
        )
        args = mock_coordinator.async_send_command.call_args
        rooms_sent = args[0][1]["1"]["rooms"]
        room_ids = [r["room_id"] for r in rooms_sent]
        assert "ROOM_013" in room_ids
        assert "ROOM_001" in room_ids


class TestS20:
    """Test that the S20 family is driven by the S10 protocol path."""

    @pytest.mark.parametrize("device_type", [DEVICE_TYPE_S20, DEVICE_TYPE_S20PRO])
    def test_uses_s10_status_map(self, mock_coordinator, device_type):
        """Test S20 work statuses resolve via the S10 table, not the K10 one."""
        mock_coordinator.entry.data = {"device_type": device_type}
        mock_coordinator.data["work_status"] = WORK_STATUS_DRYING_MOP
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.activity.value == "docked"

    @pytest.mark.parametrize("device_type", [DEVICE_TYPE_S20, DEVICE_TYPE_S20PRO])
    def test_uses_s10_fan_speeds(self, mock_coordinator, device_type):
        """Test S20 exposes the 4-level S10 fan speed list."""
        mock_coordinator.entry.data = {"device_type": device_type}
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.fan_speed_list == ["Quiet", "Standard", "Strong", "Max"]
        assert vac.fan_speed == "Standard"

    @pytest.mark.parametrize("device_type", [DEVICE_TYPE_S20, DEVICE_TYPE_S20PRO])
    def test_model_name(self, mock_coordinator, device_type):
        """Test S20 reports a friendly model rather than the raw product code."""
        mock_coordinator.entry.data = {"device_type": device_type}
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert "S20" in vac.device_info["model"]
        assert device_type not in vac.device_info["model"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("device_type", [DEVICE_TYPE_S20, DEVICE_TYPE_S20PRO])
    async def test_clean_rooms_uses_invoke_func(self, mock_coordinator, device_type):
        """Test S20 room cleaning uses the S10 clean_rooms command, not StartDefaultClean."""
        mock_coordinator.entry.data = {"device_type": device_type}
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_clean_rooms(rooms=["ROOM_013"], mode="first_sweep_then_mop")
        args = mock_coordinator.async_send_command.call_args
        assert args[0][0] == 1001
        assert args[0][1]["0"] == "clean_rooms"
        assert args[0][1]["1"]["rooms"][0]["mode"]["type"] == "first_sweep_then_mop"
        mock_coordinator.async_send_action.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("device_type", [DEVICE_TYPE_S20, DEVICE_TYPE_S20PRO])
    async def test_return_to_base(self, mock_coordinator, device_type):
        """Test S20 return to base uses the S10 go-charge command."""
        mock_coordinator.entry.data = {"device_type": device_type}
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_return_to_base()
        assert mock_coordinator.async_send_command.call_args[0][0] == 1022


class TestSetCleanMode:
    """Test the set_clean_mode service."""

    @pytest.mark.asyncio
    async def test_overrides_only_given_fields(self, mock_coordinator):
        """Test omitted fields keep their current value."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_set_clean_mode(mode="mop", water_level=3)
        assert mock_coordinator.async_change_clean_mode.call_args.kwargs == {
            "type": "mop",
            "water_level": 3,
            "fan_level": None,
            "times": None,
        }

    @pytest.mark.asyncio
    async def test_rejected_on_k10(self, mock_coordinator):
        """Test K10 has no clean mode property to set."""
        mock_coordinator.entry.data = {"device_type": DEVICE_TYPE_K10}
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_set_clean_mode(mode="mop")
        mock_coordinator.async_change_clean_mode.assert_not_called()


class TestCleanAreaFeature:
    """Test how the CLEAN_AREA feature flag is advertised."""

    def test_advertised_for_s10_family(self, mock_coordinator, clean_area_supported):
        """Test the S10 family advertises area cleaning."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert CLEAN_AREA in vac.supported_features

    def test_not_advertised_for_k10_family(self, mock_coordinator, clean_area_supported):
        """Test K10 devices never advertise area cleaning."""
        mock_coordinator.entry.data = {"device_type": DEVICE_TYPE_K10}
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert CLEAN_AREA not in vac.supported_features

    def test_not_advertised_on_older_core(self, mock_coordinator):
        """Test the flag is skipped when the running HA does not have it."""
        with patch.object(vacuum_module, "CLEAN_AREA_FEATURE", None):
            vac = SwitchBotS10Vacuum(mock_coordinator)
        assert CLEAN_AREA not in vac.supported_features


class TestSegments:
    """Test segment discovery and segment cleaning."""

    @pytest.mark.asyncio
    async def test_segments_from_rooms(self, mock_coordinator, clean_area_supported):
        """Test every map room becomes a segment with its id and name."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        segments = await vac.async_get_segments()
        assert [(s.id, s.name) for s in segments] == [
            ("ROOM_001", "Table"),
            ("ROOM_013", "Kitchen"),
        ]

    @pytest.mark.asyncio
    async def test_segments_refresh_rooms_first(
        self, mock_coordinator, clean_area_supported
    ):
        """Test rooms are re-read so the mapping dialog shows current data."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_get_segments()
        mock_coordinator.async_refresh_rooms.assert_called_once()

    @pytest.mark.asyncio
    async def test_segments_empty_when_no_rooms(
        self, mock_coordinator, clean_area_supported
    ):
        """Test a vacuum with no mapped rooms reports no segments."""
        mock_coordinator.data["rooms"] = {}
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert await vac.async_get_segments() == []

    @pytest.mark.asyncio
    async def test_clean_segments_sends_clean_rooms(
        self, mock_coordinator, clean_area_supported
    ):
        """Test segment cleaning uses the room clean command with the current mode."""
        mock_coordinator.data["clean_mode"] = {
            "fan_level": 3,
            "times": 2,
            "type": "mop",
            "water_level": 3,
        }
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_clean_segments(["ROOM_013", "ROOM_001"])

        args = mock_coordinator.async_send_command.call_args
        assert args[0][0] == 1001
        params = args[0][1]
        assert params["0"] == "clean_rooms"
        assert [r["room_id"] for r in params["1"]["rooms"]] == ["ROOM_013", "ROOM_001"]
        assert params["1"]["mode"] == {
            "fan_level": 3,
            "times": 2,
            "type": "mop",
            "water_level": 3,
        }

    @pytest.mark.asyncio
    async def test_clean_segments_with_no_segments(
        self, mock_coordinator, clean_area_supported
    ):
        """Test an empty segment list still sends a well-formed command."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_clean_segments([])
        params = mock_coordinator.async_send_command.call_args[0][1]
        assert params["1"]["rooms"] == []


class TestSegmentsChangedIssue:
    """Test the repair raised when the map's rooms stop matching the mapped areas."""

    @staticmethod
    def _vacuum(coordinator, last_seen):
        """Build an entity registered with the given previously mapped segments."""
        vac = SwitchBotS10Vacuum(coordinator)
        vac.registry_entry = MagicMock()
        return vac, patch.object(
            SwitchBotS10Vacuum,
            "last_seen_segments",
            new_callable=PropertyMock,
            return_value=last_seen,
            create=True,
        )

    def test_issue_created_when_rooms_changed(
        self, mock_coordinator, clean_area_supported
    ):
        """Test a renamed room prompts the user to re-map."""
        vac, last_seen = self._vacuum(
            mock_coordinator,
            [SEGMENT_CLS(id="ROOM_001", name="Table"),
             SEGMENT_CLS(id="ROOM_013", name="Pantry")],
        )
        with last_seen, patch.object(
            SwitchBotS10Vacuum, "async_create_segments_issue", create=True
        ) as create_issue:
            vac._async_check_segments_changed()
        create_issue.assert_called_once()

    def test_no_issue_when_rooms_unchanged(
        self, mock_coordinator, clean_area_supported
    ):
        """Test an unchanged map raises nothing."""
        vac, last_seen = self._vacuum(
            mock_coordinator,
            [SEGMENT_CLS(id="ROOM_001", name="Table"),
             SEGMENT_CLS(id="ROOM_013", name="Kitchen")],
        )
        with last_seen, patch.object(
            SwitchBotS10Vacuum, "async_create_segments_issue", create=True
        ) as create_issue:
            vac._async_check_segments_changed()
        create_issue.assert_not_called()

    def test_no_issue_when_never_mapped(self, mock_coordinator, clean_area_supported):
        """Test nothing is raised before the user has mapped any area."""
        vac, last_seen = self._vacuum(mock_coordinator, None)
        with last_seen, patch.object(
            SwitchBotS10Vacuum, "async_create_segments_issue", create=True
        ) as create_issue:
            vac._async_check_segments_changed()
        create_issue.assert_not_called()

    def test_no_issue_when_rooms_empty(self, mock_coordinator, clean_area_supported):
        """Test a failed room refresh does not look like a changed map."""
        mock_coordinator.data["rooms"] = {}
        vac, last_seen = self._vacuum(
            mock_coordinator, [SEGMENT_CLS(id="ROOM_013", name="Kitchen")]
        )
        with last_seen, patch.object(
            SwitchBotS10Vacuum, "async_create_segments_issue", create=True
        ) as create_issue:
            vac._async_check_segments_changed()
        create_issue.assert_not_called()

    def test_no_issue_without_registry_entry(
        self, mock_coordinator, clean_area_supported
    ):
        """Test an entity that is not registered yet is left alone."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        with patch.object(
            SwitchBotS10Vacuum, "async_create_segments_issue", create=True
        ) as create_issue:
            vac._async_check_segments_changed()
        create_issue.assert_not_called()

    def test_no_issue_on_older_core(self, mock_coordinator):
        """Test cores without Segment support never touch the repair API."""
        vac, last_seen = self._vacuum(
            mock_coordinator, [SEGMENT_CLS(id="ROOM_013", name="Pantry")]
        )
        with patch.object(vacuum_module, "Segment", None), last_seen, patch.object(
            SwitchBotS10Vacuum, "async_create_segments_issue", create=True
        ) as create_issue:
            vac._async_check_segments_changed()
        create_issue.assert_not_called()


class TestForceRefresh:
    """Test force_refresh service."""

    @pytest.mark.asyncio
    async def test_force_refresh(self, mock_coordinator):
        """Test force_refresh calls coordinator refresh methods."""
        mock_coordinator.async_refresh = AsyncMock()
        mock_coordinator.async_refresh_rooms = AsyncMock()
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_force_refresh()
        mock_coordinator.async_refresh_rooms.assert_called_once()
        mock_coordinator.async_refresh.assert_called_once()
