"""Decoding of the SwitchBot S10 map package stored in S3.

The layout and the world/pixel transform below were read out of the Sweeper React
Native plugin (v1.0.43.0). See docs/map-format.md for the quoted evidence.
"""
from __future__ import annotations

import base64
import json
import math
import struct
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

MAP_IMAGE_FILE = "refined_map.png"
MAP_METADATA_FILE = "refined_map.json"
MAP_INFO_FILE = "mapinfo.json"
MAP_LABELS_FILE = "labels.json"
MAP_MARKERS_FILE = "markers.json"
MAP_TRACK_FILE = "track.json"
MAP_FILES = (
    MAP_IMAGE_FILE,
    MAP_METADATA_FILE,
    MAP_INFO_FILE,
    MAP_LABELS_FILE,
    MAP_MARKERS_FILE,
    MAP_TRACK_FILE,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DEFAULT_RESOLUTION = 0.05

# The palette the app assigns by a room's colorType, light-mode variants.
ROOM_COLORS = ("#C8DBF7", "#92C9FF", "#D2C2F2", "#AAAFF7", "#A9EBE7")

# track.json points are [x, y, heading, ?, ?, path_type]; only the segments the robot
# cleans or traverses are drawn. 5 is the return-to-dock leg.
TRACK_X, TRACK_Y, TRACK_TYPE = 0, 1, 5
PATH_TYPE_GO_TO_BASE = 5

CHARGER_MARKER_PREFIX = "CHARGE"
NO_GO_MARKER_PREFIXES = ("PROHIBIT", "NOWASH")


@dataclass(frozen=True)
class Room:
    """A room outline, in world metres."""

    id: str
    name: str
    polygon: list[tuple[float, float]]
    color: str


@dataclass(frozen=True)
class Marker:
    """A point of interest such as the dock, in world metres."""

    id: str
    kind: str
    points: list[tuple[float, float]]


@dataclass(frozen=True)
class SwitchBotMap:
    """One decoded map package."""

    image: bytes
    width: int
    height: int
    resolution: float
    origin: tuple[float, float]
    rotation: int
    rooms: dict[str, str] = field(default_factory=dict)
    room_shapes: list[Room] = field(default_factory=list)
    path: list[list[tuple[float, float]]] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)

    def to_pixel(self, x: float, y: float) -> tuple[float, float]:
        """Convert a world coordinate in metres to a pixel of the map image."""
        # transformCoordinate() in the plugin, for an unrotated map:
        #   x = scale * (p[0] - origin[0]) / resolution + 0
        #   y = scale * (height - (p[1] - origin[1]) / resolution) - 1
        return (
            (x - self.origin[0]) / self.resolution,
            self.height - (y - self.origin[1]) / self.resolution - 1,
        )

    @property
    def calibration_points(self) -> list[dict[str, dict[str, float]]]:
        """Return world-to-pixel reference points for the Xiaomi vacuum map card."""
        points = []
        for x, y in ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)):
            pixel_x, pixel_y = self.to_pixel(x, y)
            points.append(
                {
                    "vacuum": {"x": x, "y": y},
                    "map": {"x": round(pixel_x, 3), "y": round(pixel_y, 3)},
                }
            )
        return points


def png_dimensions(image: bytes) -> tuple[int, int]:
    """Return (width, height) read from a PNG IHDR chunk."""
    if not image.startswith(PNG_SIGNATURE):
        raise ValueError("map image is not a PNG")
    width, height = struct.unpack(">II", image[16:24])
    return width, height


def parse_rooms(labels: bytes | None) -> dict[str, str]:
    """Return room ID to name mapping from labels.json."""
    if not labels:
        return {}
    data = json.loads(labels)
    return {
        room["id"]: room.get("name", room["id"])
        for room in data.get("data", [])
        if str(room.get("id", "")).startswith("ROOM_")
    }


def _pairs(flat: list[float]) -> list[tuple[float, float]]:
    """Chunk a flat [x, y, x, y, ...] array into coordinate pairs."""
    return [
        (float(flat[i]), float(flat[i + 1])) for i in range(0, len(flat) - 1, 2)
    ]


def parse_room_shapes(labels: bytes | None) -> list[Room]:
    """Return room outlines from labels.json."""
    if not labels:
        return []
    rooms = []
    for entry in json.loads(labels).get("data", []):
        room_id = str(entry.get("id", ""))
        if not room_id.startswith("ROOM_"):
            continue
        polygon = _pairs(entry.get("geometry") or [])
        if len(polygon) < 3:
            continue
        color_type = int(entry.get("colorType") or 0)
        rooms.append(
            Room(
                id=room_id,
                name=entry.get("name") or room_id,
                polygon=polygon,
                color=ROOM_COLORS[color_type % len(ROOM_COLORS)],
            )
        )
    return rooms


def parse_path(track: bytes | None) -> list[list[tuple[float, float]]]:
    """Return the robot's route from track.json, split into contiguous runs.

    The return-to-dock leg is dropped so the drawn path shows where the robot actually
    cleaned rather than how it got home.
    """
    if not track:
        return []
    points = json.loads(track)
    if not isinstance(points, list):
        return []

    runs: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for point in points:
        if not isinstance(point, list) or len(point) <= TRACK_Y:
            continue
        path_type = point[TRACK_TYPE] if len(point) > TRACK_TYPE else 0
        if path_type == PATH_TYPE_GO_TO_BASE:
            if current:
                runs.append(current)
                current = []
            continue
        current.append((float(point[TRACK_X]), float(point[TRACK_Y])))
    if current:
        runs.append(current)
    return runs


def parse_markers(markers: bytes | None) -> list[Marker]:
    """Return markers such as the dock and no-go zones from markers.json."""
    if not markers:
        return []
    result = []
    for entry in json.loads(markers).get("data", []):
        marker_id = str(entry.get("id", ""))
        points = _pairs(entry.get("geometry") or [])
        if not points:
            continue
        result.append(
            Marker(id=marker_id, kind=marker_id.split("_")[0], points=points)
        )
    return result


def parse_map(files: dict[str, bytes]) -> SwitchBotMap:
    """Build a SwitchBotMap from the raw objects of one map directory."""
    image = files[MAP_IMAGE_FILE]
    width, height = png_dimensions(image)
    metadata = json.loads(files[MAP_METADATA_FILE])
    info = json.loads(files.get(MAP_INFO_FILE) or b"{}")
    origin = metadata.get("origin") or [0.0, 0.0]

    return SwitchBotMap(
        image=image,
        width=width,
        height=height,
        resolution=float(metadata.get("resolution") or DEFAULT_RESOLUTION),
        origin=(float(origin[0]), float(origin[1])),
        rotation=int(math.degrees(float(info.get("rotation") or 0.0))),
        rooms=parse_rooms(files.get(MAP_LABELS_FILE)),
        room_shapes=parse_room_shapes(files.get(MAP_LABELS_FILE)),
        path=parse_path(files.get(MAP_TRACK_FILE)),
        markers=parse_markers(files.get(MAP_MARKERS_FILE)),
    )


def _points_attr(pixels: list[tuple[float, float]]) -> str:
    """Format pixel coordinates for an SVG points attribute."""
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pixels)


def render_svg(map_data: SwitchBotMap) -> bytes:
    """Draw the map as an SVG: raster underneath, rooms, route and markers on top.

    SVG keeps this dependency-free — the robot's own raster is embedded as a data URI
    and everything else is vector, so nothing has to composite pixels.
    """
    to_pixel = map_data.to_pixel
    raster = base64.b64encode(map_data.image).decode()
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {map_data.width} {map_data.height}" '
            f'width="{map_data.width}" height="{map_data.height}">'
        ),
        (
            "<style>"
            ".room{stroke:#5A7CA8;stroke-width:1.2;stroke-linejoin:round;"
            "fill-opacity:0.45}"
            ".route{fill:none;stroke:#FFFFFF;stroke-width:1.6;stroke-opacity:0.85;"
            "stroke-linecap:round;stroke-linejoin:round}"
            ".label{font:600 9px sans-serif;fill:#1B3A5C;text-anchor:middle;"
            "paint-order:stroke;stroke:#FFFFFF;stroke-width:2.5;stroke-linejoin:round}"
            ".nogo{fill:#E5484D;fill-opacity:0.25;stroke:#E5484D;stroke-width:1.2}"
            "</style>"
        ),
        (
            f'<image href="data:image/png;base64,{raster}" x="0" y="0" '
            f'width="{map_data.width}" height="{map_data.height}" '
            'image-rendering="pixelated"/>'
        ),
    ]

    for room in map_data.room_shapes:
        pixels = [to_pixel(x, y) for x, y in room.polygon]
        parts.append(
            f'<polygon class="room" fill="{room.color}" '
            f'points="{_points_attr(pixels)}"/>'
        )

    for marker in map_data.markers:
        if marker.kind in NO_GO_MARKER_PREFIXES and len(marker.points) >= 3:
            pixels = [to_pixel(x, y) for x, y in marker.points]
            parts.append(f'<polygon class="nogo" points="{_points_attr(pixels)}"/>')

    for run in map_data.path:
        if len(run) < 2:
            continue
        pixels = [to_pixel(x, y) for x, y in run]
        parts.append(f'<polyline class="route" points="{_points_attr(pixels)}"/>')

    for room in map_data.room_shapes:
        pixels = [to_pixel(x, y) for x, y in room.polygon]
        center_x = sum(x for x, _ in pixels) / len(pixels)
        center_y = sum(y for _, y in pixels) / len(pixels)
        parts.append(
            f'<text class="label" x="{center_x:.1f}" y="{center_y:.1f}">'
            f"{escape(room.name)}</text>"
        )

    for marker in map_data.markers:
        if marker.kind == CHARGER_MARKER_PREFIX:
            x, y = to_pixel(*marker.points[0])
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#2F6F3E" '
                'stroke="#FFFFFF" stroke-width="1.5"/>'
            )

    parts.append("</svg>")
    return "".join(parts).encode()
