"""Tests for the SwitchBot Vacuum map image entity."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.switchbot_vacuum.image import SwitchBotVacuumMap
from custom_components.switchbot_vacuum.map import SwitchBotMap


@pytest.fixture
def sample_map():
    """Return a decoded map."""
    return SwitchBotMap(
        image=b"first",
        width=400,
        height=300,
        resolution=0.05,
        origin=(-10.0, -5.0),
        rotation=0,
        rooms={"ROOM_001": "Kitchen"},
    )


@pytest.fixture
def mock_coordinator(sample_map):
    """Create a mock coordinator holding a map."""
    coord = MagicMock()
    coord.data = {}
    coord.device_mac = "AABBCCDDEEFF"
    coord.map = sample_map
    return coord


@pytest.fixture
def entity(mock_coordinator):
    """Create the map image entity."""
    with patch("homeassistant.components.image.get_async_client"):
        return SwitchBotVacuumMap(MagicMock(), mock_coordinator)


class TestMapImage:
    """Test the map image entity."""

    def test_unique_id(self, entity):
        """Test unique_id includes the device mac."""
        assert entity.unique_id == "AABBCCDDEEFF_map"

    def test_content_type_is_png(self, entity):
        """Test the entity advertises PNG."""
        assert entity.content_type == "image/png"

    @pytest.mark.asyncio
    async def test_image_empty_before_first_update(self, entity):
        """Test no bytes are served until the coordinator has run."""
        assert await entity.async_image() is None

    @pytest.mark.asyncio
    async def test_image_served_after_update(self, entity):
        """Test the coordinator's map bytes are served."""
        with patch.object(entity, "async_write_ha_state"):
            entity._handle_coordinator_update()
        assert await entity.async_image() == b"first"

    def test_timestamp_bumps_only_on_change(self, entity, mock_coordinator, sample_map):
        """Test image_last_updated tracks changes rather than every refresh."""
        with patch.object(entity, "async_write_ha_state"):
            entity._handle_coordinator_update()
            first = entity.image_last_updated
            entity._handle_coordinator_update()
            assert entity.image_last_updated == first

            mock_coordinator.map = SwitchBotMap(
                image=b"second",
                width=sample_map.width,
                height=sample_map.height,
                resolution=sample_map.resolution,
                origin=sample_map.origin,
                rotation=sample_map.rotation,
            )
            entity._handle_coordinator_update()
        assert entity.image_last_updated != first

    def test_attributes_expose_calibration(self, entity):
        """Test the Xiaomi vacuum map card gets what it needs."""
        attrs = entity.extra_state_attributes
        assert len(attrs["calibration_points"]) == 3
        assert attrs["calibration_points"][0]["vacuum"] == {"x": 0.0, "y": 0.0}
        assert attrs["calibration_points"][0]["map"] == {"x": 200.0, "y": 199.0}
        assert attrs["rooms"] == {"ROOM_001": "Kitchen"}

    def test_attributes_empty_without_map(self, entity, mock_coordinator):
        """Test no attributes are published before a map exists."""
        mock_coordinator.map = None
        assert entity.extra_state_attributes == {}
