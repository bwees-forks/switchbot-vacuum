"""Decoding of the SwitchBot S10 map package stored in S3.

The layout and the world/pixel transform below were read out of the Sweeper React
Native plugin (v1.0.43.0). See docs/map-format.md for the quoted evidence.
"""
from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass, field

MAP_IMAGE_FILE = "refined_map.png"
MAP_METADATA_FILE = "refined_map.json"
MAP_INFO_FILE = "mapinfo.json"
MAP_LABELS_FILE = "labels.json"
MAP_FILES = (MAP_IMAGE_FILE, MAP_METADATA_FILE, MAP_INFO_FILE, MAP_LABELS_FILE)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DEFAULT_RESOLUTION = 0.05


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
    )
