"""Tests for the SwitchBot map package decoder.

The map package is synthetic: no real S10 map was available, so the fixture is
built from the format documented in docs/map-format.md. Run tools/dump_map.py
against a real account to check the decoder against genuine data.
"""
from __future__ import annotations

import json
import math
import struct
import zlib

import pytest

from custom_components.switchbot_vacuum.map import (
    MAP_IMAGE_FILE,
    MAP_INFO_FILE,
    MAP_LABELS_FILE,
    MAP_METADATA_FILE,
    ROOM_COLORS,
    Marker,
    Room,
    SwitchBotMap,
    parse_map,
    parse_path,
    parse_room_shapes,
    parse_rooms,
    png_dimensions,
    render_svg,
)


def _png(width: int, height: int) -> bytes:
    """Build a minimal valid greyscale PNG of the given size."""
    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes([200] * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


@pytest.fixture
def map_files():
    """Return a synthetic map package as raw S3 objects."""
    return {
        MAP_IMAGE_FILE: _png(400, 300),
        MAP_METADATA_FILE: json.dumps(
            {"resolution": 0.05, "origin": [-10.0, -5.0, 0.0]}
        ).encode(),
        MAP_INFO_FILE: json.dumps({"rotation": math.pi / 2}).encode(),
        MAP_LABELS_FILE: json.dumps(
            {
                "data": [
                    {"id": "ROOM_001", "name": "Kitchen", "geometry": [0, 0, 1, 0, 1, 1]},
                    {"id": "ROOM_002", "geometry": []},
                    {"id": "CARPET_001", "name": "Rug", "geometry": []},
                ]
            }
        ).encode(),
    }


class TestPngDimensions:
    """Test PNG header parsing."""

    def test_reads_ihdr(self):
        """Test width and height come from the IHDR chunk."""
        assert png_dimensions(_png(400, 300)) == (400, 300)

    def test_rejects_non_png(self):
        """Test a non-PNG payload is refused rather than misread."""
        with pytest.raises(ValueError):
            png_dimensions(b"GIF89a not a png")


class TestParseRooms:
    """Test labels.json room extraction."""

    def test_only_room_entries(self, map_files):
        """Test carpet labels are ignored and missing names fall back to the ID."""
        assert parse_rooms(map_files[MAP_LABELS_FILE]) == {
            "ROOM_001": "Kitchen",
            "ROOM_002": "ROOM_002",
        }

    def test_missing_labels(self):
        """Test an absent labels.json yields no rooms."""
        assert parse_rooms(None) == {}


class TestParseMap:
    """Test assembling a map from the raw S3 objects."""

    def test_fields(self, map_files):
        """Test every field is read from the right file."""
        result = parse_map(map_files)
        assert result.width == 400
        assert result.height == 300
        assert result.resolution == 0.05
        assert result.origin == (-10.0, -5.0)
        assert result.rotation == 90
        assert result.rooms == {"ROOM_001": "Kitchen", "ROOM_002": "ROOM_002"}
        assert result.image == map_files[MAP_IMAGE_FILE]

    def test_defaults_when_metadata_empty(self, map_files):
        """Test a metadata file without origin or resolution still decodes."""
        map_files[MAP_METADATA_FILE] = b"{}"
        map_files[MAP_INFO_FILE] = b"{}"
        result = parse_map(map_files)
        assert result.resolution == 0.05
        assert result.origin == (0.0, 0.0)
        assert result.rotation == 0


class TestCoordinates:
    """Test the world-to-pixel transform."""

    @pytest.fixture
    def sample(self):
        """Return a map with a known origin and resolution."""
        return SwitchBotMap(
            image=b"",
            width=400,
            height=300,
            resolution=0.05,
            origin=(-10.0, -5.0),
            rotation=0,
        )

    def test_origin_maps_to_bottom_left(self, sample):
        """Test the world origin lands on the bottom-left pixel."""
        assert sample.to_pixel(-10.0, -5.0) == (0.0, 299.0)

    def test_x_grows_right(self, sample):
        """Test one metre of world X is one over resolution pixels."""
        assert sample.to_pixel(-9.0, -5.0)[0] == pytest.approx(20.0)

    def test_y_grows_upward(self, sample):
        """Test world Y increases as the pixel row decreases."""
        assert sample.to_pixel(-10.0, -4.0)[1] == pytest.approx(279.0)

    def test_calibration_points(self, sample):
        """Test three non-collinear calibration pairs are produced."""
        points = sample.calibration_points
        assert len(points) == 3
        assert points[0] == {"vacuum": {"x": 0.0, "y": 0.0}, "map": {"x": 200.0, "y": 199.0}}
        assert points[1]["map"]["x"] == pytest.approx(220.0)
        assert points[2]["map"]["y"] == pytest.approx(179.0)


class TestRoomShapes:
    """Test room outlines decoded from labels.json."""

    def test_geometry_is_chunked_into_pairs(self):
        """Test the flat geometry array becomes coordinate pairs."""
        labels = json.dumps(
            {
                "data": [
                    {
                        "id": "ROOM_001",
                        "name": "Kitchen",
                        "colorType": 1,
                        "geometry": [0.0, 0.0, 1.0, 0.0, 1.0, 1.0],
                    }
                ]
            }
        ).encode()
        rooms = parse_room_shapes(labels)
        assert len(rooms) == 1
        assert rooms[0].polygon == [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
        assert rooms[0].color == ROOM_COLORS[1]

    def test_non_rooms_and_degenerate_shapes_are_skipped(self):
        """Test carpets and shapes too small to fill are ignored."""
        labels = json.dumps(
            {
                "data": [
                    {"id": "CARPET_1", "geometry": [0, 0, 1, 0, 1, 1]},
                    {"id": "ROOM_002", "geometry": [0, 0, 1, 0]},
                ]
            }
        ).encode()
        assert parse_room_shapes(labels) == []

    def test_unknown_color_type_does_not_raise(self):
        """Test a colorType outside the palette wraps instead of failing."""
        labels = json.dumps(
            {"data": [{"id": "ROOM_003", "colorType": 99, "geometry": [0, 0, 1, 0, 1, 1]}]}
        ).encode()
        assert parse_room_shapes(labels)[0].color in ROOM_COLORS


class TestPath:
    """Test the robot route decoded from track.json."""

    def test_points_become_a_run(self):
        """Test consecutive points form one polyline."""
        track = json.dumps([[0.0, 0.0, 0, 0, 0, 2], [1.0, 1.0, 0, 0, 0, 2]]).encode()
        assert parse_path(track) == [[(0.0, 0.0), (1.0, 1.0)]]

    def test_return_to_dock_leg_splits_runs(self):
        """Test the drive home is excluded rather than drawn across the floor."""
        track = json.dumps(
            [
                [0.0, 0.0, 0, 0, 0, 2],
                [5.0, 5.0, 0, 0, 0, 5],
                [1.0, 1.0, 0, 0, 0, 2],
            ]
        ).encode()
        assert parse_path(track) == [[(0.0, 0.0)], [(1.0, 1.0)]]

    def test_missing_and_malformed_input(self):
        """Test absent or unexpected track data yields no path."""
        assert parse_path(None) == []
        assert parse_path(b"{}") == []
        assert parse_path(json.dumps([[0.0]]).encode()) == []


class TestRenderSvg:
    """Test the composed SVG."""

    def _map(self, **overrides):
        """Build a map with a single room and route."""
        base = {
            "image": b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (20).to_bytes(4, "big") + (10).to_bytes(4, "big"),
            "width": 20,
            "height": 10,
            "resolution": 0.05,
            "origin": (0.0, 0.0),
            "rotation": 0,
            "room_shapes": [
                Room(id="ROOM_001", name="Kitchen", polygon=[(0, 0), (1, 0), (1, 1)], color="#92C9FF")
            ],
            "path": [[(0.0, 0.0), (0.5, 0.5)]],
            "markers": [Marker(id="CHARGE_1", kind="CHARGE", points=[(0.2, 0.2)])],
        }
        return SwitchBotMap(**{**base, **overrides})

    def test_contains_each_layer(self):
        """Test raster, rooms, route, label and dock are all drawn."""
        svg = render_svg(self._map()).decode()
        assert svg.startswith("<svg")
        assert 'viewBox="0 0 20 10"' in svg
        assert "data:image/png;base64," in svg
        assert '<polygon class="room" fill="#92C9FF"' in svg
        assert '<polyline class="route"' in svg
        assert ">Kitchen</text>" in svg
        assert "<circle" in svg

    def test_room_names_are_escaped(self):
        """Test a name containing markup cannot break the document."""
        map_data = self._map(
            room_shapes=[
                Room(id="ROOM_001", name="Bath & <Shower>", polygon=[(0, 0), (1, 0), (1, 1)], color="#92C9FF")
            ]
        )
        svg = render_svg(map_data).decode()
        assert "Bath &amp; &lt;Shower&gt;" in svg
        assert "<Shower>" not in svg

    def test_renders_without_overlays(self):
        """Test a map with no rooms, route or markers still produces valid SVG."""
        svg = render_svg(self._map(room_shapes=[], path=[], markers=[])).decode()
        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")
        assert "polygon" not in svg

    def test_single_point_run_is_not_drawn(self):
        """Test a one-point run is skipped rather than emitting an empty polyline."""
        svg = render_svg(self._map(path=[[(0.0, 0.0)]])).decode()
        assert "polyline" not in svg
