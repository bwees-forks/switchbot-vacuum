"""Constants for the SwitchBot Vacuum integration."""
from typing import Final

DOMAIN: Final = "switchbot_vacuum"

# Config
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_DEVICE_MAC: Final = "device_mac"
CONF_PRODUCT_KEY: Final = "product_key"
CONF_CACHED_ROOMS: Final = "cached_rooms"

# API
API_AUTH_HOST: Final = "https://account.api.switchbot.net"
CLIENT_ID: Final = "5nnwmhmsa9xxskm14hd85lm9bm"
APP_VERSION: Final = "8.6.1"
API_TIMEOUT: Final = 30
DEVICE_TYPE_S10: Final = "WoSweeperOrigin"
DEVICE_TYPE_S20: Final = "W1106000"
DEVICE_TYPE_S20PRO: Final = "W1107000"
DEVICE_TYPE_K10: Final = "WoSweeperMini"
DEVICE_TYPE_K10PRO: Final = "WoSweeperMiniPro"

# The S20/S20 Pro are protocol-identical to the S10: the app routes all three to the
# same WoSweeperDevice model and "com.switch.bot.sweeper" module, and exposes the same
# shadow properties, function IDs and scene actions for each.
S10_FAMILY_DEVICE_TYPES: Final = frozenset(
    {DEVICE_TYPE_S10, DEVICE_TYPE_S20, DEVICE_TYPE_S20PRO}
)
K10_FAMILY_DEVICE_TYPES: Final = frozenset({DEVICE_TYPE_K10, DEVICE_TYPE_K10PRO})
SUPPORTED_DEVICE_TYPES: Final = S10_FAMILY_DEVICE_TYPES | K10_FAMILY_DEVICE_TYPES

DEVICE_TYPE_TO_MODEL: Final = {
    DEVICE_TYPE_S10: "Floor Cleaning Robot S10",
    DEVICE_TYPE_S20: "Floor Cleaning Robot S20",
    DEVICE_TYPE_S20PRO: "Floor Cleaning Robot S20 Pro",
    DEVICE_TYPE_K10: "Mini Robot Vacuum K10+",
    DEVICE_TYPE_K10PRO: "Mini Robot Vacuum K10+ Pro",
}

# K10+ WorkingStatus values (verified from APK VacuumUtil.smali)
# isCleaning  → [1, 2, 3]
# isPaused    → [4]
# isGoCharging→ [5]
# isCharging  → [6]  (also isDocking)
# isDocking   → [6, 7, 11]
# isCollecting→ [11]
K10_WORK_STATUS_CLEANING: Final = 1
K10_WORK_STATUS_CLEANING_2: Final = 2
K10_WORK_STATUS_CLEANING_3: Final = 3
K10_WORK_STATUS_PAUSED: Final = 4
K10_WORK_STATUS_GO_CHARGE: Final = 5
K10_WORK_STATUS_CHARGING: Final = 6
K10_WORK_STATUS_DOCKED: Final = 7
K10_WORK_STATUS_COLLECTING_DUST: Final = 11
K10_WORK_STATUS_STANDBY: Final = 0  # fallback

# Commands
CMD_CLEAN: Final = 1001
CMD_GO_CHARGE: Final = 1022
CMD_CONTROL: Final = 1009
CMD_CHANGE_MODE: Final = 1043

# Work Status (property 1010), per SweeperUtil.getWorkStatusText in the app
WORK_STATUS_STANDBY: Final = 1
WORK_STATUS_CHARGING: Final = 2
WORK_STATUS_CHARGE_DONE: Final = 3
WORK_STATUS_LAUNCHING: Final = 4
WORK_STATUS_WETTING_MOP: Final = 5
WORK_STATUS_RELOCATING: Final = 7
WORK_STATUS_CLEANING: Final = 8
WORK_STATUS_SWEEPING: Final = 9
WORK_STATUS_MOPPING: Final = 10
WORK_STATUS_PAUSED: Final = 11
WORK_STATUS_GO_CHARGE: Final = 15
WORK_STATUS_WASHING_MOP: Final = 16
WORK_STATUS_DOCKING: Final = 19
WORK_STATUS_DRYING_MOP: Final = 20

# Human-readable names for property 1010, mirroring SweeperUtil.getWorkStatusText in
# the app. Shared by the whole S10 family (S10 / S20 / S20 Pro).
WORK_STATUS_NAMES: Final[dict[int, str]] = {
    1: "standby",
    2: "charging",
    3: "charge_done",
    4: "launching",
    5: "wetting_mop",
    6: "exploring",
    7: "relocating",
    8: "sweeping_mopping",
    9: "sweeping",
    10: "mopping",
    11: "paused",
    12: "escaping_trap",
    13: "fault",
    14: "backing_to_wash_mop",
    15: "backing_to_charge",
    16: "deeply_washing_mop",
    17: "collecting_sewage",
    18: "filling_clean_water",
    19: "collecting_dust",
    20: "drying_mop",
    21: "sleeping",
    22: "configuring",
    23: "remote_control",
    24: "backing_to_base",
    25: "backing_to_shut_down",
    26: "going_to_water_station",
    27: "flushing_strainer",
    29: "adding_water",
    30: "adding_water",
    31: "firmware_upgrading",
    32: "paused",
    35: "scanning",
    36: "water_station_charging",
    37: "going_to_water_station",
}

# Properties
PROP_ONLINE: Final = 1003
PROP_BATTERY: Final = 1004
PROP_WORK_STATUS: Final = 1010
PROP_ERROR_CODE: Final = 1019
PROP_S3_BUCKET: Final = 1028
PROP_AWS_REGION: Final = 1031
PROP_TASK_INFO: Final = 1032
PROP_ROOM_PLANS: Final = 1038
PROP_MAP_INFO: Final = 1055
PROP_CLEAN_MODE: Final = 1053
PROP_CLEAN_SUMMARY: Final = 1052
PROP_AWS_CREDS: Final = 1130
PROP_FIRMWARE: Final = 1002

K10PRO_PROP_ONLINE: Final = 66
K10PRO_PROP_BATTERY: Final = 820
K10PRO_PROP_SUCTION_POW_LEVEL: Final = 4601
K10PRO_PROP_WORK_STATUS: Final = 4602
K10PRO_PROP_DUST_COLECT_FREQUENCY: Final = 4609
K10PRO_PROP_CHILD_LOCK: Final = 4610
K10PRO_PROP_DUST_COLECT_TIME: Final = 4614
K10PRO_PROP_AUTO_RESTART: Final = 4615

# Fan speed mapping (S10). HA renders these strings verbatim in the UI, so they are
# capitalized; the lowercase aliases below keep pre-0.7 automations working.
FAN_SPEEDS: Final = {
    "Quiet": 1,
    "Standard": 2,
    "Strong": 3,
    "Max": 4,
}
FAN_SPEED_LIST: Final = list(FAN_SPEEDS.keys())

# Fan speed mapping (K10+) — SuctionPowLevel 0-3 (confirmed via app: quiet/standard/strong/max)
K10_FAN_SPEEDS: Final = {
    "Quiet": 0,
    "Standard": 1,
    "Strong": 2,
    "Max": 3,
}
K10_FAN_SPEED_LIST: Final = list(K10_FAN_SPEEDS.keys())
K10_FAN_LEVEL_TO_SPEED: Final = {v: k for k, v in K10_FAN_SPEEDS.items()}

FAN_SPEED_ALIASES: Final = {name.lower(): level for name, level in FAN_SPEEDS.items()}
K10_FAN_SPEED_ALIASES: Final = {
    name.lower(): level for name, level in K10_FAN_SPEEDS.items()
}

# Clean types accepted in the "type" field of property 1053 / function 1043
CLEAN_TYPE_SWEEP: Final = "sweep"
CLEAN_TYPE_MOP: Final = "mop"
CLEAN_TYPE_SWEEP_MOP: Final = "sweep_mop"
CLEAN_TYPE_SWEEP_THEN_MOP: Final = "first_sweep_then_mop"
CLEAN_TYPES: Final = [
    CLEAN_TYPE_SWEEP,
    CLEAN_TYPE_MOP,
    CLEAN_TYPE_SWEEP_MOP,
    CLEAN_TYPE_SWEEP_THEN_MOP,
]

# Water output levels for the "water_level" field of property 1053 / function 1043
WATER_LEVELS: Final = {"low": 1, "medium": 2, "high": 3}
WATER_LEVEL_LIST: Final = list(WATER_LEVELS.keys())
WATER_LEVEL_TO_NAME: Final = {v: k for k, v in WATER_LEVELS.items()}

# Cleaning passes for the "times" field
CLEAN_PASSES: Final = {"1": 1, "2": 2}
CLEAN_PASS_LIST: Final = list(CLEAN_PASSES.keys())

# Work status indicating fault (S10)
WORK_STATUS_FAULT: Final = 13

# Error codes (property 1019) — from APK feature_sweeper (sweeperErrorEnd_XXXX)
# Codes with known descriptions from APK string analysis; unknown codes logged for discovery.
ERROR_CODES: Final[dict[int, str]] = {
    0: "none",
    # Low codes — operational status indicators, NOT actual errors
    11: "drying_mop",                 # Base station drying mop (normal operation)
    # sweeperErrorEnd_2000 – 2012: Qihoo 360 SDK error codes
    2000: "stuck",                      # Robot is stuck
    2001: "wheel_stuck",                # Wheel stuck or suspended
    2002: "side_brush_stuck",           # Side brush tangled/stuck
    2003: "main_brush_stuck",           # Main brush/roller tangled/stuck
    2004: "bumper_stuck",               # Bumper stuck — check for debris
    2005: "dust_bin_missing",           # Dust bin not installed
    2006: "filter_clogged",             # Filter needs cleaning
    2007: "cliff_sensor_error",         # Cliff/drop sensor error
    2008: "low_battery",               # Battery too low to continue
    2009: "charging_error",             # Cannot charge — check dock contacts
    2010: "internal_error",             # Internal system error
    2011: "laser_sensor_error",         # LDS/laser sensor error
    2012: "path_blocked",              # Cannot find path / navigation error
    # S10-specific base station errors
    2728: "clean_water_tank_empty",     # Clean water tank empty
    2739: "dirty_water_tank_full",      # Dirty water tank full
    2740: "dirty_water_tank_removed",   # Dirty water tank removed
}

# Status codes in PROP_ERROR_CODE that are NOT actual errors (normal operation).
# Only codes NOT in this set should trigger the problem binary sensor.
NON_ERROR_STATUS_CODES: Final = frozenset({0, 11})

# Separate operational failure reasons (from APK operateFail* strings)
# These appear as transient conditions checked before/during commands.
OPERATIONAL_ERRORS: Final[dict[str, str]] = {
    "operateFailLowBattery": "Low battery",
    "operateFailClearWaterEmpty": "Clean water tank empty",
    "operateFailDirtWaterFull": "Dirty water tank full",
    "operateFailNoClearWater": "No clean water tank",
    "operateFailNoDirtWater": "No dirty water tank",
    "operateFailOutBaseStation": "Robot not at base station",
    "operateFailOutStation": "Robot not at station",
    "operateFailRepeatControl": "Duplicate command",
}

# S3
S3_REGION: Final = "eu-central-1"

# Timings
UPDATE_INTERVAL_SECONDS: Final = 30
TOKEN_REFRESH_SECONDS: Final = 5400  # 1.5 hours
ROOM_REFRESH_SECONDS: Final = 86400  # 24 hours
