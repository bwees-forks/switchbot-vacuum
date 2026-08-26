# SwitchBot Robot Vacuum Cloud API

Reverse-engineered from the React Native "Sweeper" plugin bundle the app downloads over the air.

**Source artifact:** `rn_bundle/unpacked/index.android.bundle` (2,820,883 bytes)
**Plugin version:** `Sweeper` v1.0.43.0, `appRegistryName: "com.switch.bot.sweeper"`, built 1784702553684 (`rn_bundle/bundle.config.json`)
**Applies to:** S10 / S20 / S20 Pro (`WoSweeperOrigin`, `W1106000`, `W1107000`). The K10+ family uses a different, smaller property space and is not covered by this bundle.

## How to read this document

Every claim is tagged:

- **[bundle]** — read directly out of `index.android.bundle`. A verbatim snippet and a byte offset are given. Offsets are into the raw file; recompute with `python3 -c "print(open(PATH,encoding='utf-8',errors='replace').read()[N:N+400])"`.
- **[device]** — confirmed against real hardware.
- **[inferred]** — reasoning from surrounding code. Not read literally. **Do not ship a command based on an [inferred] tag without testing it.**
- **[open]** — could not be determined from the bundle.

Where this document contradicts `custom_components/switchbot_vacuum/const.py`, the contradiction is called out explicitly in [Corrections to the integration](#corrections-to-the-integration).

---

## Transport

Commands are invoked with a single POST. [bundle @1436521]

```js
n.commonFuncInvoke = function*(e){ return n.post(r(d[10]).COMMON_FUNK_INVOKE, Object.assign({},e)) }
```

```
POST /command/cmd/api/v1/func/invoke
{ "deviceID": "<mac>", "functionID": <int>, "params": { "0": ..., "1": ... } }
```

`params` is an **object with stringified integer keys**, not an array. Functions taking no arguments send `params: {}`.

The app additionally attaches an MQTT notify channel so it can receive the function's return value, since the HTTP response only acknowledges the request. [bundle @1441300]

```js
builderParams(e){ var t={type:"mqtt", url:`v1_1/${BuzGlobalBean.COMMON.userId}/${BuzGlobalBean.COMMON.clientID}/${TopicName.FUN_RESPONSE}`};
                  return "string"!=typeof e ? Object.assign({},e,{notify:t}) : e }
```

Success on the MQTT reply is `payload.params[0] === 0`; the result is `payload.params[1]`, a JSON string or object. [bundle @1440300] The timeout is 30 s. **The `notify` field is optional** — the integration omits it and fire-and-forget commands work, because the HTTP layer returns its own `resultCode`. Only functions that *return data* (1012 `getTimeTask`, 1028 `getDNDModeTimeList`, 1066 `queryDryingTime`) need it. [inferred]

There is also a **LAN transport** that speaks the identical thing-model directly to the robot, bypassing the cloud. [bundle @2044347]

```js
var s={version:"1",code:3,deviceID:e,payload:{functionID:1023,requestID:Tools.genUuid(),
       timestamp:(new Date).getTime(),params:{0:t}}}, f=MD5(JSON.stringify(s)+r);
yield fetch(`http://${o}:${l}/thing_model/func_request`,{method:"POST",
    headers:{Accept:"application/json","Content-Type":"application/json",Auth:f},body:JSON.stringify(s)});
```

`ip`, `port` and `token` come from the return value of function 1021 (`enableLocalCommunication`); `Auth` is `MD5(body + token)`. Only `functionID: 1023` is sent this way in the shipped app — the envelope looks general but that is [inferred].

---

## Commands (function IDs)

All verified by reading the service class at bundle offsets **1432697–1438700**. Each `n.<name> = function(...)` line is a literal definition of the wire call.

### Cleaning — function 1001

Param `0` is a **`MapType` string** (see [MapType](#maptype)). Param `1`, where present, is the task payload. [bundle @1436854]

```js
cleanAllRooms      (n,e) -> functionID:1001, params:{0:MapType.cleanAll,  1:e}
cleanSomeAreas     (n,e) -> functionID:1001, params:{0:MapType.cleanAreas, 1:e}
cleanSomeRooms     (n,e) -> functionID:1001, params:{0:MapType.cleanRooms, 1:e}
markWaterStation   (n,e) -> functionID:1001, params:{0:MapType.mark,       1:e}
spotClean          (n,e) -> functionID:1001, params:{0:MapType.cleanHere,  1:e}
quicklyExplore      (n)  -> functionID:1001, params:{0:MapType.explore}
fillWater4Humidifier(n)  -> functionID:1001, params:{0:MapType.fillWaterForHumidifier}
cleanWithExplore    (n)  -> functionID:1001, params:{0:MapType.cleanWithExplore}
waterBaseCharge     (n)  -> functionID:1001, params:{0:MapType.waterBaseCharge}
```

#### Payload for `clean_rooms`

[bundle @1269179] — the call site, showing exactly how the app builds it:

```js
var s = X.current.getSelectedRooms().sort(function(e,t){return e.orderNumber-t.orderNumber});
var l = {custom_clean:!(null==st||!st.isOpen), force_order:!0, no_water_station_mode:Qe};
if (st.isOpen) { var u=getCurrentMapCleanPlan(s,st.cleanPlan,!0);
                 l.rooms = u.map(function(e){return {mode:e.mode, room_id:e.roomId}}); }
else           { l.rooms = s.map(function(e){return {mode:Ke, room_id:e.id}}); }
yield v.default.cleanSomeRooms(Et,l);
```

```jsonc
{
  "custom_clean": false,            // true only when a saved per-room clean plan is active
  "force_order": true,              // always true for room cleaning
  "no_water_station_mode": false,   // boolean; see property 1114
  "rooms": [
    { "room_id": "ROOM_xxx", "mode": { "type": "sweep_mop", "fan_level": 2, "water_level": 1, "times": 1 } }
  ]
}
```

- `mode` is **per room**, repeated in each element. There is no top-level `mode`.
- Rooms are sorted by `orderNumber` before mapping; `force_order: true` tells the robot to honour that sequence.
- `room_id` takes the room's `id` verbatim from the map data.
- **[device] Confirmed working against real hardware** as the integration currently sends it (`"clean_rooms"` + `{force_order, mode, rooms:[{room_id, mode}]}` with `ROOM_xxx` ids).

#### Payload for `clean_all`

Different shape — note it sends a **top-level `mode`**, not `rooms`. [bundle @1270507]

```js
var e={custom_clean:!(null==st||!st.isOpen), force_order:!(null==st||!st.isOpen), no_water_station_mode:Qe};
if (st.isOpen) { var a=getCurrentMapCleanPlan(Be,st.cleanPlan);
                 e.rooms=a.map(function(e){return {mode:e.mode, room_id:e.roomId}}); }
else           { e.mode = Object.assign({}, Ke, {times:1}); }
yield v.default.cleanAllRooms(Et,e);
```

```jsonc
{ "custom_clean": false, "force_order": false, "no_water_station_mode": false,
  "mode": { "type": "sweep_mop", "fan_level": 2, "water_level": 1, "times": 1 } }
```

`times` is **forced to 1** for whole-house cleaning. Corroborated at [bundle @1288693]: `me===MapType.cleanAll&&(i.times=1)`.

#### Payload for `clean_areas` and `clean_here`

[bundle @1269443] and [bundle @2045908]:

```js
var d={mode:Ke, force_order:!1, no_water_station_mode:Qe,
       areas:c.map(function(e){return {polygon:e.geometry, mode:Ke}})};
yield v.default.cleanSomeAreas(Et,d);
...
var t={mode:Object.assign({},E)}; yield c.default.spotClean(e,t);
```

`clean_areas`: `{mode, force_order:false, no_water_station_mode, areas:[{polygon, mode}]}`, where `polygon` is the area geometry from the map.
`clean_here`: `{mode}` only. The robot cleans around its current position.

### Task control — function 1009

[bundle @1438400]

```js
pauseTask (n) -> functionID:1009, params:{0:"pause"}
resumeTask(n) -> functionID:1009, params:{0:"resume"}
stopTask  (n) -> functionID:1009, params:{0:"stop"}
```

`TaskCommand` enum confirms only these three values. [bundle @1018522]
`e.TaskCommand=(function(_){return _.PAUSE="pause",_.STOP="stop",_.RESUME="resume",_})({})`

### Base-station: mop wash, drying, dust collection — function 1039

**This is the answer to the biggest known gap. These ARE cloud-callable.** They are not a dedicated function ID and not base-station-automatic-only — they are function **1039** (`selfCleaning`) with a single integer param.

Definition [bundle @1434474]:

```js
n.selfCleaning=function(e,o){return n.commonFuncInvoke({deviceID:e,functionID:1039,params:{0:o}})}
```

The values come from the station-control screen, where each button calls `h(n)` which is bound to `selfCleaning`. [bundle @1483400]

```js
de=function(){ ... : (F(1), null==h||h(1)) },                                   // "mop_clean" button
Se=function(){ if(k){ if(v.isDrying) return null==h||h(3), void F(0);
                      F(2), null==h||h(2) } ... },                             // "instant_drying" / "stop_drying"
ye=function*(){ ... (F(3), null==h||h(4)) ... }                                // "promptly_dust_collection"
```

| param `0` | Action | Evidence |
|---|---|---|
| `1` | Start mop wash / deep clean self | `de` → `h(1)`, button label `mop_clean` [bundle @1483400] |
| `2` | **Start mop drying** | `Se` → `h(2)` when not already drying, label `instant_drying` [bundle @1483400] |
| `3` | **Stop mop drying** | `Se` → `h(3)` when `v.isDrying`, label `stop_drying` [bundle @1483400] |
| `4` | **Start dust collection** | `ye` → `h(4)`, button label `promptly_dust_collection` [bundle @1483400] |

Two independent corroborations of the same numbering:

```js
// @1263992 — the wrapper that actually invokes it. Note the 4-specific rate-limit toast.
if(4===e && !(yield NativeAsyncStorage.getItem(AsyncStorageKey.SWEEPER_FIRST_DUST_COLLECTION))) ...
ai(gt.isDrying&&1===e, !0, function*(){ try{ yield v.default.selfCleaning(Et,e) }
   catch(a){ 4===e ? Toast.show(t("operation_frequently_tip")) : Toast.show(c("operation_failed")) } },
   t("stop_drying_task_tips"));
```

```js
// @1302246 — stop drying before starting a clean
ai(gt.isDrying&&!gt.isBreakpointContinuationScanCharging, !1, function*(){
   ln(!0), gt.isDrying&&(yield v.default.selfCleaning(Et,3)), yield oi(), ln(!1) }, t("stop_drying_task_tips"));
```

**Preconditions** the app enforces before enabling each button [bundle @1380770–1381449]:

```js
isDisabledMopClean:      workingStatus ∈ {DeeplyWashing, CollectingSewage, FillingWater, CollectingDust}
isDisabledDrying:        workingStatus ∈ {DeeplyWashing, CollectingSewage, FillingWater, CollectingDust}
isDisabledDustCollection:workingStatus ∈ {DeeplyWashing, CollectingSewage, FillingWater}
```

Drying and dust collection additionally require the robot to be on the base (`k` in `Se`/`ye`; otherwise the app shows `un_base_tip`). [bundle @1483600]

**[open] There is no "stop dust collection" or "stop mop wash" value.** Only `3` (stop drying) exists. Stopping the other two is [inferred] to be function 1009 `stop`, but this is **not** confirmed — do not ship it untested.

**[open] `selfCleaning(0)` and values ≥ 5 are never used in the bundle.** Do not send them.

### Base-station without a water station — function 1060

For setups running in "no water station mode". Param `0` is a task-name string; all four literals in the bundle:

| Value | Button | Offset |
|---|---|---|
| `"fill_water"` | `start_fill_water` | [bundle @1279382] |
| `"auto_clean"` | `start_clean_mop` | [bundle @1281521] |
| `"auto_clean_and_collect_dust_and_drying"` | `start_clean_self` (combined base) | [bundle @1283180] |
| `"collect_dust_and_drying"` | `dust_dry_mop` (dust base) | [bundle @1283510] |

These are an **alternative** path to drying/dust collection, gated on `supportList[1003]` and property `1114 noWaterStationMode`. Prefer 1039 for normal setups. [inferred]

### Manual drive — function 1023

Param `0` is a `DirectionType` string. [bundle @2052351]

```js
e.DirectionType=(function(t){return t.FORWARD="go_ahead",t.LEFT="turn_left",t.RIGHT="turn_right",
  t.BACKWARD="go_back",t.ENTER="enter",t.EXIT="exit",t.BRAKE="brake",t})({})
```

Protocol [bundle @2043187–2046511]: send `"enter"` first, repeat the direction every **500 ms** while held, `"brake"` on release, `"exit"` when done. The app pairs this with 1021/1024 to use the LAN transport, falling back to cloud 1023.

### Clean parameters — function 1043

[bundle @1288735 (object built) and @1289243 (call)] — the exact object:

```js
var i={type:e.type||Ke.type, fan_level:e.fanLevel||Ke.fan_level,
       water_level:e.waterLevel||Ke.water_level, times:e.times||Ke.times};
me===MapType.cleanAll && (i.times=1);
yield v.default.updateCleanDetail(i);
```

`params: {0: {type, fan_level, water_level, times}}`. Note the definition hardcodes the device ID from global state rather than taking it as an argument [bundle @1434200]:

```js
n.updateCleanDetail=function(e){return n.commonFuncInvoke({deviceID:BuzGlobalBean.DEVICE.deviceId,functionID:1043,params:{0:e}})}
```

Defaults [bundle @1024106]: `e.defaultClearMode={type:"sweep_mop",times:1,fan_level:2,water_level:1}`

`type` ∈ `CleanMode` [bundle @1023153]:
`e.CleanMode={mop:"mop",sweep_mop:"sweep_mop",sweep:"sweep",customClean:"custom_clean",first_sweep_then_mop:"first_sweep_then_mop"}`

`first_sweep_then_mop` is gated on `supportList[1007]`. [bundle @1304295]

`fan_level` is 1–4 and `water_level` is 1–3. This is **[inferred]** from the icon assets, which are the only enumeration in the bundle [bundle @1048108]: `fan_level_1..fan_level_4`, `water_level_1..water_level_3`. It agrees with the integration's existing mapping. The `optionData` matrix `[[0,1,2,5],[0,1],[0,1,2,5]]` at [bundle @1304366] is **not** fan levels — `w[0]`/`w[1]`/`w[2]` are indexed by clean-mode tab and passed as `itemList` (row visibility), per [bundle @1500070].

### Full function table

Definitions all in the service class, offsets 1432697–1438700.

| ID | Name | `params` | Notes |
|---|---|---|---|
| 1001 | clean | `{0:MapType, 1:payload}` | See above. Highest value. |
| 1006 | updateMapInfo (labels) | `{0:payload}` | `var t="label"===o?1006:1007` @1432697. Payload shape **[open]** — no call sites. |
| 1007 | updateMapInfo (markers) | `{0:payload}` | Payload shape **[open]**. |
| 1009 | taskControl | `{0:"pause"\|"resume"\|"stop"}` | |
| 1012 | getTimeTask | `{0:string}` | Returns schedule list. Needs MQTT notify. |
| 1013 | createTimeTask | `{0:JSON.stringify(obj)}` | See below. |
| 1014 | deleteTimeTask | `{0:JSON.stringify(obj)}` | |
| 1015 | enableTask | `{0:JSON.stringify(obj)}` | |
| 1019 | findRobot | `{}` | Locate / play sound. |
| 1021 | enableLocalCommunication | `{}` | Returns `{ip, port, token}` for the LAN transport. |
| 1022 | gotoCharge | `{}` | Return to dock. |
| 1023 | remoteOperator | `{0:DirectionType}` | See above. |
| 1024 | disableLocalCommunication | `{}` | |
| 1027 | checkVoice | `{0:o}` | Voice-pack check. |
| 1028 | getDNDModeTimeList | `{}` | Needs MQTT notify. |
| 1029 | updateDNDModeTimeList | `{0:JSON.stringify(obj)}` | See below. |
| 1030 | resetMap | `{}` | **Destructive** — wipes the map. |
| 1031 | setMapRotation | `{0:float}` | **Radians, not degrees**: `setMapRotation(Et, Math.PI*e/180)` @1258500. |
| 1032 | resetConsumable | `{0:string}` | `"strainer"\|"edgeBlush"\|"mainBlush"\|"sensor"` @1557060. |
| 1038 | goBackWaterStation | `{0:e}` | **[open]** — defined @1437631, zero call sites. Param value unknown. |
| 1039 | selfCleaning | `{0:1\|2\|3\|4}` | **Mop wash / drying / dust collection.** See above. |
| 1042 | responseQuestion | `{0:questionID, 1:1\|2}` | `1`=decline, `2`=confirm @1255970. `questionID` from property 1067. |
| 1043 | updateCleanDetail | `{0:{type,fan_level,water_level,times}}` | |
| 1046 | updateBaseVersion | `{0:o, 1:c}` | OTA. |
| 1048 | cancelMapUpdate | `{}` | |
| 1050 | otherOTAUpdate | `{0:url,1:md5,2:o,3:otaType,4:icType,5:version}` | OTA. `DeviceOTAType` @1024100. |
| 1055 | ignoreObstacle | `{0:obstacleId}` | App pauses the task first @1536748. |
| 1058 | startMaterPairMode | `{0:bool}` | Matter pairing. |
| 1059 | deleteBaseInfoList | `{0:o}` | |
| 1060 | noWaterTaskControl | `{0:string}` | See above. |
| 1061 | updateBaseInfoList | `{0:o}` | |
| 1062 | removeErrorCode | `{0:[int]}` | **Array** of error codes: `removeErrorCode(w,[V.code])` @1525431. |
| 1066 | queryDryingTime | `{}` | Returns `{time: seconds}` @1481656. Needs MQTT notify. |
| 1068 | updateObstacleReliability | `{0:obstacleId}` | |

#### 1013 createTimeTask payload

[bundle @1626469]

```js
var c = w ? w.taskID : Tools.genUuid().toLowerCase();
var u = { [c]: { enable:true, map_id:ce,
                 trigger:{ type:"timer", week: L ? "" : O.join(""), time: 60*M + I },
                 action:{ type: 1===le ? MapType.waterBaseCharge : ge.current.type, detail: e } } };
```

Top-level key is the task ID (lowercased UUID). `trigger.time` is **minutes since midnight**; `trigger.week` is a concatenated digit string such as `"135"`, empty for one-shot.

#### 1029 updateDNDModeTimeList payload

[bundle @2133201]

```js
var t={quiet_time_list: e.map(e=>({enable:e.enable, begin:e.begin, end:e.end, week:e.week}))};
```

`begin`/`end` are minutes since midnight [bundle @1596550]: `u.begin = 60*t.hour + t.minute`. An empty array disables DND.

---

## Properties

### The numeric property map

The shadow API returns numeric keys. The bundle carries the complete translation table as a standalone module. [bundle @950775 (module payload starts here), module id `1784702893599`]

```js
i.exports={805:"autoUpgrade",1001:"deviceID",1002:"version",1003:"power",1004:"battery",
1005:"batteryStatus",1006:"OSSPath",1007:"nextMapID",66:"networkStatus",1009:"workType",
1010:"workingStatus",1011:"errorCode",1012:"currentTaskID",1013:"taskType",1014:"taskSource",
1015:"lastTaskID",1016:"lastTrackIndex",1017:"lastDiffMapIndex",1018:"taskResult",
1019:"upgradeStatus",1020:"upgradeProgress",1021:"lastestVersion",1022:"currentPose",1023:"mapID",
1024:"taskCommand",1025:"taskDetail",1026:"exploreDone",1027:"initialize",1028:"s3Bucket",
1029:"s3Object",1030:"s3AuthTokenUrl",1031:"awsRegion",1032:"startTaskEvent",1033:"stopTaskEvent",
1034:"unbindEvent",1035:"timezoneOffset",1036:"scheduleResult",1037:"markersChanged",
1038:"allCleanPlan",1039:"volume",1040:"fanLevel",1041:"lightEnable",1042:"lessCollisionMode",
1043:"baseType",1045:"wifiName",1046:"IP",1047:"autoAddCleanLiquid",1048:"materialList",
1049:"sensorList",1050:"scheduleMaintain",1051:"cleanAreas",1052:"cleanProcess",1053:"clearMode",
1055:"currentMapStatus",1057:"keyEnable",1060:"carpetSuperchargeMode",1061:"carpetCleanMode",
1062:"dustCollectionEnable",1063:"intelligentDustCollectionMode",1064:"cleanType",
1065:"versionData",1066:"SN",1067:"askQuestion",1068:"dryEnable",1069:"dryMode",1070:"AIEnable",
1071:"strongCornerSweep",1072:"fineMopping",1073:"waterStationBattery",
1074:"isEnableBreakpointContinuationScan",1075:"lastVersionList",1076:"stageResult",
1080:"isBreakpointContinuationScanCharging",1081:"savedMapList",1088:"FillHumWaterEnable",
1089:"FillHumWaterMode",1090:"humiSleepFillWaterEnable",1091:"humiNoDisturbFillWaterEnable",
1092:"bindHumiMac",1094:"markPosition",1095:"inDNDMode",1098:"netInfo",1106:"bindMapHumiMac",
1107:"otherOTAProcess",1108:"supportList",1109:"errorDetail",1110:"backwashFrequency",
1111:"picUploadDir",1112:"firstWettingFillWater",1103:"dustCollectionFreq",1113:"aiAggresiveMode",
1114:"noWaterStationMode",1115:"noWaterStationTask",1116:"mapBaseInfo",1122:"baseInfoList",
1140:"AIRecognition",1142:"AIPrivacyVersion"}
```

This is the only such map in the bundle — verified by searching for `1001:"deviceID"` (1 match) and `"errorCode"` (2 matches, one here and one in the string-name enum). It is applied by `transformSweeperProperties` [bundle @950200].

### What the app polls

The home screen reads this exact set. [bundle @1247710]

```js
PMServiceModuleHelper.callDeviceReadMultiProperty({deviceId:Et,propertyIds:[
"66","1001","1002","1003","1004","1005","1010","1011","1012","1013","1015","1019","1020","1021",
"1022","1023","1030","1031","1032","1037","1038","1039","1040","1041","1042","1043","1045","1046",
"1047","1052","1053","1055","1057","1062","1063","1064","1065","1066","1067","1068","1069","1070",
"1071","1072","1073","1074","1075","1076","1081","1094","1095","1098","1107","1108","1109","1110",
"1112","1103","1113","1114","1115","1122","1140","1142"]});
```

### Properties worth surfacing in Home Assistant

| ID | Name | Meaning |
|---|---|---|
| 66 | networkStatus | `0`=OFF_LINE, `1`=CONNECTED [bundle @1008023]. **This is the online flag, not 1003.** |
| 1002 | version | Firmware version. |
| 1004 | battery | Battery percent. |
| 1005 | batteryStatus | `0`=NORMAL, `1`=CHARGING, `2`=FULL, `3`=LOW, `4`=UNKNOWN [bundle @1007868]. |
| 1010 | workingStatus | See [WorkingStatus](#workingstatus). |
| 1011 | errorCode | See [ErrorCode](#errorcode). **Not 1019.** |
| 1013 | taskType | See [TaskType](#tasktype). Needed to distinguish paused-mid-task from idle. |
| 1039 | volume | Speaker volume, int. Writable via shadow. |
| 1040 | fanLevel | Read-only telemetry. Set fan speed via function 1043, not here. |
| 1047 | autoAddCleanLiquid | bool. Writable. |
| 1052 | cleanProcess | Live progress of the current task. |
| 1053 | clearMode | Current `{type, fan_level, water_level, times}`. |
| 1057 | keyEnable | **Child lock, inverted** — `{1057: !e}` @1587768. |
| 1062 | dustCollectionEnable | bool. Writable. |
| 1063 | intelligentDustCollectionMode | `0`=standard, `1`=quick, `2`=super. Writable. |
| 1066 | SN | Serial number. |
| 1067 | askQuestion | Pending question; answer with function 1042. |
| 1068 | dryEnable | bool. Writable. |
| 1069 | dryMode | Drying duration in **hours**: `2`, `3` or `4`. Default `3`. Writable. |
| 1073 | waterStationBattery | Water-station battery percent. |
| 1095 | inDNDMode | bool — currently inside a do-not-disturb window. |
| 1103 | dustCollectionFreq | `0`=default, `15`, `20` minutes. Writable. |
| 1108 | supportList | Capability bitmap, see below. |
| 1109 | errorDetail | Structured error info alongside 1011. |
| 1110 | backwashFrequency | `BackwashMode`: `0`=AUTO, `1`=ROOM, `10`, `15`, `20` [bundle @1024106]. Writable. |
| 1114 | noWaterStationMode | bool. Changes which command family applies. |

### Writing properties (settings)

Settings are **shadow writes, not function invokes**. [bundle @1006667]

```
POST /device/v1/shadow/set   { "deviceID": <id>, "timestamp": <ms>, "property": { "<id>": <value> } }
POST /device/v1/shadow/get   { "deviceID": <id> }
POST /device/v1/shadow/getByIDs { "deviceID": <id>, "propertyIDs": ["1010", ...] }
```

Two properties use a different endpoint — `uploadDeviceShadow`, which also needs `deviceType` and nests under `payload`:

```
POST /device/device/v1/property/uploadChange
{ "deviceID": <id>, "deviceType": <type>, "payload": { "timestamp": <ms>, "property": {...} } }
```

Those two are **1094 `markPosition`** and **1114 `noWaterStationMode`**. [bundle @1250352, @1275749]

Verified write sites, with the exact literal written:

| Prop | Value written | Offset |
|---|---|---|
| 805 autoUpgrade | `{enable, startTime:120, timeLength:240}` | 1943403 |
| 1039 volume | int | 1694256 |
| 1047 autoAddCleanLiquid | bool | 1711866 |
| 1057 keyEnable (child lock) | `!e` — **inverted** | 1587768 |
| 1060 carpetSuperchargeMode | bool | 1895208 |
| 1061 carpetCleanMode | `0`=adapt to carpet, `1`=avoid carpet | 1895543 |
| 1062 dustCollectionEnable | bool | 2061348 |
| 1063 intelligentDustCollectionMode | `0`\|`1`\|`2` | 2061683 |
| 1068 dryEnable | bool | 2072520 |
| 1069 dryMode | `2`\|`3`\|`4` (hours) | 2072113 |
| 1070 AIEnable | bool | 1588134 |
| 1074 isEnableBreakpointContinuationScan | bool | 1587910 |
| 1103 dustCollectionFreq | `0`\|`15`\|`20` | 2192505 |
| 1110 backwashFrequency | `BackwashMode` | 2179230 |
| 1112 firstWettingFillWater | bool | 2179488 |
| 1113 aiAggresiveMode | bool | 1589481 |

**1040 `fanLevel` is never written via shadow.** Fan level, water level, clean type and pass count all go through function **1043**.

### supportList (property 1108)

A capability map keyed by integer. Every check in the bundle:

| Bit | Gates |
|---|---|
| 1003 | No-water-station mode; wider clean-option matrix |
| 1004 | Multiple / combined base stations |
| 1005 | Humidifier marking requires a secret key |
| 1007 | `first_sweep_then_mop` clean type is available |
| 1008 | Firmware upgrade allowed while off the base |
| 1010 | Digital-map privacy policy v2 |
| 1011 | AI Recognition setting visible |
| 1013 | Water-station charging (`MapType.waterBaseCharge`) |

Useful for feature-gating in HA rather than hardcoding per-model behaviour.

---

## Endpoints

Defined in one module. [bundle @1003882, module id `1784702893603`]

```js
e.BASE_URL_DOMAIN_NAME="deviceApi", e.BASE_CMD_DOMAIN_NAME="command", e.BASE_MAP_DOMAIN_NAME="sweeperOriginApi",
e.TEMP_TOKEN="/device/v1/adddevice/getTempToken",
e.COMMON_FUNK_INVOKE="/command/cmd/api/v1/func/invoke",
e.VOICE_PACK_LIST="/sweeper/v1/voicePack/listV2", e.VOICE_PACK_DOWNLOAD="/sweeper/v1/voicePack/download",
e.SHADOW_BY_IDS="/device/v1/shadow/getByIDs", e.SHADOW_GET="/device/v1/shadow/get",
e.SHADOW_SET="/device/v1/shadow/set", e.SHADOW_UPLOAD="/device/device/v1/property/uploadChange",
e.CREATE_DIGIT_MAP="/device/v1/digit_map/create",
e.TASK_RECORD_LIST="/sweeper/v1/taskRecord/list", e.TASK_GET_POLICY="/sweeper/v1/task/getPolicy",
e.DEVICE_UPGRADE="/device/v1/ota", e.STATION_DEVICE_UPGRADE="/sweeper/v1/base/ota",
e.DEBUG_LOG="/sweeper/v1/debug/collect",
e.MAP_LIST="/sweeper/v1/map/listMapv2", e.SAVE_MAP_LIST="/sweeper/v1/map/saveListMapv2",
e.UPDATE_MAP_LIST="/sweeper/v1/map/editListMap", e.CHECK_MAP_LIST="/sweeper/v1/map/loadListMap",
e.DELETE_MAP_LIST="/sweeper/v1/map/deleteListMap", e.SAVE_AS_MAP_LIST="/sweeper/v1/map/saveAsListMap",
e.GET_UPLOAD_SNAPSHOOT_URL="/sweeper/v1/map/getUploadSnapshootUrl",
e.BACKUP_MAP_URL="/sweeper/v1/map/backupMap", e.UPDATE_MAP_URL="/sweeper/v1/map/updateMap",
e.ROOM_MERGE_OR_DIVISION="/sweeper/v1/map/roomMergeOrDivision",
e.GET_TRACK_POSE="/sweeper/v1/map/getTrackPose", e.TRACK_POSE="/sweeper/v1/task/trackPose",
e.TRACK_MONITOR_OPEN="/sweeper/v1/task/monitor/open", e.TRACK_MONITOR_CLOSE="/sweeper/v1/task/monitor/close",
e.CONSUMABLE_LIST="/sweeper/v1/consumable/list", e.RESET_REMIND="/sweeper/v1/consumable/resetRemind",
e.FILL_WATER_FOR_HUMI="/sweeper/v1/task/fillWaterForHumi",
e.GET_USER_SETTINGS="/homepage/v1/userSettings/get", e.UPDATE_CONSENT_AGREE="/homepage/v1/consent/agree",
e.GET_CONFIG_EFFECTIVE="/homepage/v1/system/config/effective"
```

### `sweeperOriginApi` is dead code — the integration is right to ignore it

`BASE_URL_DOMAIN_NAME`, `BASE_CMD_DOMAIN_NAME` and `BASE_MAP_DOMAIN_NAME` each occur exactly twice in the bundle: once in the `= void 0` export declaration and once in the assignment above. The defining module has an **empty dependency list** (`},1784702893603,[]`) and **no module reads them**.

Instead, every HTTP class in the vacuum bundle declares the same module name:

```js
{key:"getModuleName",value:function(){return"wonderlabs"}}
```

at 8 sites (offsets 1003014, 1007485, 1436792, 1475286, 1734056, 1750065, 1889384, 2779419), covering the map API, the shadow/device API and `commonFuncInvoke`.

That module name becomes the `Domain-Name` header, which `RetrofitUrlManager` resolves against the account's endpoint list. The literals `deviceApi`, `command`, `sweeperOriginApi` and `homepage` appear in **zero** dex files across all 24 `classes*.dex`, so nothing native can resolve them either.

**Conclusion: all vacuum traffic — `/sweeper/v1/*`, `/device/v1/*`, `/command/cmd/api/v1/func/invoke` — goes to the `wonderlabs` host** (`https://wonderlabs.us.api.switchbot.net`, or the region host from the endpoint list). Routing by path prefix is done server-side. `sweeperOriginApi` serves nothing and exposes nothing the wonderlabs host does not. **No action needed.**

The one exception is the three `/homepage/v1/*` paths, which `WonderUrlInterceptor` redirects to the `wonderlabsV2` host. None of them are vacuum control.

### Auth

Applied natively by `CommonHeaderInterceptor`: `authorization` (Cognito bearer token), `uuid`, `requestID`, `appVersion`, `versionFlag`. Body is `application/json; charset=utf-8`. Response envelope is `{statusCode, message, body}`; the JS layer treats `code == 200 && statusCode == 100` as success. `statusCode == 20150122` forces re-login.

---

## Enums

### MapType

[bundle @1021699] — **strings, not integers.** [device] The string form is confirmed working against real hardware.

```js
e.MapType={explore:"explore",cleanWithExplore:"clean_with_explore",cleanAll:"clean_all",
cleanAreas:"clean_areas",cleanRooms:"clean_rooms",cleanHere:"clean_here",mark:"mark",
fillingWater:"filling_water",dischargeSewage:"discharge_sewage",deeplyWashing:"deeply_washing",
backingToCharge:"backing_to_charge",backingToWash:"backing_to_wash",washMop:"wash_mop",
dryMop:"dry_mop",collectDust:"collect_dust",remote:"remote",
fillWaterForHumidifier:"fill_water_for_humidifier",waterBaseCharge:"water_base_charge"}
```

Only 9 of these 18 are used as function-1001 arguments (the ones in the service class). The rest — `filling_water`, `discharge_sewage`, `deeply_washing`, `backing_to_charge`, `backing_to_wash`, `wash_mop`, `dry_mop`, `collect_dust`, `remote` — appear in the bundle only as values **read back** from `startTaskEvent.action` (property 1032) to describe what the robot is doing. [bundle @1252511]

> **Do not send `dry_mop` or `collect_dust` to function 1001.** They look like the drying and dust-collection commands but there is no evidence they are accepted as inputs, and the real commands are function 1039. This is the trap this document exists to prevent.

Leads for future features: `clean_areas` (zone cleaning), `clean_here` (spot clean), `explore` / `clean_with_explore` (mapping runs), `water_base_charge`, `fill_water_for_humidifier`.

### WorkingStatus (property 1010)

[bundle @1008326] — complete, 0 through 37.

```js
e.WorkingStatus=(function(_){return _[_.None=0]="None",_[_.Standby=1]="Standby",_[_.Charging=2]="Charging",
_[_.ChargeDone=3]="ChargeDone",_[_.Launching=4]="Launching",_[_.Wetting=5]="Wetting",
_[_.Exploring=6]="Exploring",_[_.Relocating=7]="Relocating",_[_.SweepingMopping=8]="SweepingMopping",
_[_.Sweeping=9]="Sweeping",_[_.Mopping=10]="Mopping",_[_.Pause=11]="Pause",
_[_.EscapingTrap=12]="EscapingTrap",_[_.Fault=13]="Fault",_[_.BackingToWash=14]="BackingToWash",
_[_.BackingToCharge=15]="BackingToCharge",_[_.DeeplyWashing=16]="DeeplyWashing",
_[_.CollectingSewage=17]="CollectingSewage",_[_.FillingWater=18]="FillingWater",
_[_.CollectingDust=19]="CollectingDust",_[_.Drying=20]="Drying",_[_.Sleeping=21]="Sleeping",
_[_.Configuration=22]="Configuration",_[_.RemoteControl=23]="RemoteControl",
_[_.BackingBase=24]="BackingBase",_[_.Shutdown=25]="Shutdown",_[_.Marking=26]="Marking",
_[_.FlushingStrainer=27]="FlushingStrainer",_[_.MarkingHumidifier=28]="MarkingHumidifier",
_[_.BackingToHumidifier=29]="BackingToHumidifier",_[_.FillingHumidifier=30]="FillingHumidifier",
_[_.OTAING=31]="OTAING",_[_.ChargePause=32]="ChargePause",_[_.DigitMapScanning=35]="DigitMapScanning",
_[_.WaterBaseCharging=36]="WaterBaseCharging",_[_.GoToWaterBaseCharge=37]="GoToWaterBaseCharge",_})({})
```

Differences from the integration's `WORK_STATUS_NAMES`: `0` = None is missing; `26` is **Marking**, not `backing_to_base`; `24` is **BackingBase**; `28` is **MarkingHumidifier** (absent); `29`/`30` are **BackingToHumidifier** / **FillingHumidifier**, not both `adding_water`.

### State derivation

The app derives HA-relevant booleans from `workingStatus` and `taskType`. Worth mirroring. [bundle @1374913–1381449]

```js
isPause:        workingStatus ∈ {Pause(11), ChargePause(32), Fault(13)}
isCharge:       workingStatus ∈ {Charging(2), ChargeDone(3)}
isGotoCharge:   workingStatus === BackingToCharge(15)
isDeepCleanSelf:workingStatus === DeeplyWashing(16)
isDrying:       workingStatus === Drying(20)
isCollectingDust:workingStatus === CollectingDust(19)
isSleeping:     workingStatus === Sleeping(21)
isStandby:      workingStatus === Standby(1)
isFault:        workingStatus === Fault(13)
isRemoteControl:workingStatus === RemoteControl(23)
isTasking:      taskType !== STANDBY && !isPause
isTaskPause:    taskType !== STANDBY && isPause
isWorking:      taskType ∈ {EXPLORING, CLEAN_ALL_ROOMS, CLEAN_SOME_AREAS, CLEAN_HERE, CLEAN_SOME_ROOMS,
                            CLEAN_WITH_EXPLORE, MARK, GO_HUMIDIFIER_WATER, MARK_HUMIDIFIER,
                            FILLING_WATER, BACK_TO_CHARGE, REMOTE_CONTROL, CREATE_DIGIT_MAP, WATER_BASE_CHARGE}
```

Note `isPause` **includes Fault(13)** — a faulted robot reads as paused, not as a distinct state.

### TaskType (property 1013)

[bundle @1017006]

```js
STANDBY=0, EXPLORING=1, CLEAN_SOME_AREAS=2, CLEAN_SOME_ROOMS=3, CLEAN_ALL_ROOMS=4, FILLING_WATER=5,
DEEP_CLEAN_SELF=6, BACK_TO_CHARGE=7, MARK=8, MOP_CLEANING=9, REMOTE_CONTROL=12, CLEAN_WITH_EXPLORE=13,
GO_HUMIDIFIER_WATER=14, MARK_HUMIDIFIER=15, CLEAN_HERE=16, CREATE_DIGIT_MAP=19, WATER_BASE_CHARGE=20
```

### ErrorCode (property 1011)

[bundle @1009598–1017005] — ~130 entries. The integration's current table is largely **wrong**: it maps 2000–2012 to Qihoo 360 SDK meanings that do not match this bundle at all.

Hardware / robot faults:
```
1001 FAN_EXCEPTION            1002 UNKNOWN_HARDWARE_FAILURE   1003 BATTER_EXCEPTION
2001 WATER_STATION_LEAK       2002 CLIFF_SENSOR_ANOMALY       2003 DEVICE_VACANT
2004 ROLLER_LOCK              2005 WHEEL_LOCK                 2006 LCD_LOCK
2007 SIDE_LOCK                2008 UN_INSTALL_DUST_BOX        2009 DEVICE_STUCK
2010 DEVICE_TILTED            2011 BUMPER_STRIP_LOCK          2012 RADAR_BE_LOCK
2013 RADAR_BE_COVERED         2014 CHARGEBACK_SENSOR_ANOMALY  2015 CARPET_DETECTION_SENSOR_ANOMALY
2016 OBSTACLE_AVOIDANCE_SENSOR_ANOMALY                        2017 WALL_SENSOR_ANOMALY
2018 CANNOT_FIND_DUST_STATION 2019 DUST_STATION_BLOCKED       2020 HOST_IN_FORBIDDEN_AREA
2022 CANNOT_FIND_WATER_STATION 2024 SYSTEMS_ERR               2025 ROLLER_UP_DOWN_LOCK
2026 WATER_STATION_COMMUNICATION_FAILURE                      2027 DUST_STATION_COMMUNICATION_FAILURE
2028 CONNECT_FAILED           2030 POSE_LOSE                  2031 UN_START_IN_CARPETED_AREAS
2032 NO_MAP_CHARGE            2033 CANNOT_FIND_HUMIDIFIER     2034-2036 DOCKING_STATION_FAIL
2037 NO_OPEN_2037             2038/2039 COMBINED_BASE_ERROR   2046 BASE_VERSION_LOW
2047 CURRENT_MAP_NOT_FULL_LOCATION_FAIL                       2048 CURRENT_MAP_NOT_CHANGE_BASE
```

Base-station / consumable faults:
```
3002 AREA_CANNOT_BE_REACHED   3003 FILLING_WATER_EXCEPTION    3004 SEWAGE_EXCEPTION
3005 UN_ROLLER                3006 UN_SLOP_BOX                3007 UN_SLOP_TANK
3008 DUST_BAG_NOT_INSTALL     3009 DUST_COVER_OPEN            3010 DUST_BAG_IS_FULL
3011 INSTALL_EXTERNAL_SEWAGE_SLOP_TANK                        3012 INSTALL_EXTERNAL_SEWAGE_PURGING_TANK
3013 SEWAGE_SLOP_TANK_FULL    3014 SEWAGE_PURGING_TANK_SHORTAGE
3015 HIGH_DRYING_TEMPERATURE  3016 CAMERA_EXCEPTION           3017 HOST_BLOCKED
3018 UNABLE_TO_WATER_STATION  3019 UNABLE_TO_DUST_STATION     3020 UNABLE_TO_HUMIDIFIER_STATION
3021 CLEAN_WATER_PUMP_CANNOT_WORK
3022-3031 WATER_STATION_COMMUNICATION_ERROR_22..31
3032-3038 DUST_STATION_COMMUNICATION_ERROR_32..38
3039-3040 HUMIDIFIER_COMMUNICATION_ERROR_39..40
3041-3061 COMBINED_BASE_ERROR_41..61                          3062 WATER_BASE_ERROR_62
```

Power / scheduling (mostly **not** hardware faults):
```
4001 CLEAR_WATER_TANK_SHORTAGE 4002 LOW_POWER_SHUT_DOWN      4004 LOW_POWER
4005 CHARGE_EXCEPTION          4006 DUST_STATION_PAIR_FAILED  4007 DUST_STATION_BIND_FAILED
4008 WATER_STATION_PAIR_FAILED 4009 WATER_STATION_BIND_FAILED 4010 WATER_STATION_LOW_POWER
4011 TASK_FAIL_BECAUSE_DND     4012 TASK_FAIL_BECAUSE_LOW_POWER 4013 TASK_FAIL_RESERVE
4014 COMBINED_BASE_ERROR_4014  4015 TASK_FAIL_RESERVE_4015
4018-4021 COMBINED_BASE_ERROR  4028 WATER_BASE_ERROR_4028     4029 SWEEPER_LOW_POWER
```

**[open] There is no code `11` in this enum.** The integration treats `11` as "drying mop, not an error". That may be a K10-family code or a misreading; it does not exist in the S10 error space.

### CleanResult (task outcome)

[bundle @1022220] — useful for a "last clean result" sensor.

```js
app_stop, low_battery_shutdown, be_put_on_base, app_recharge, button_recharge, low_battery_recharge,
fail, fault_timeout, unsure, success, pause_timeout, unstarted, check_fail, no_water_base,
no_humidifier_pose, no_combined_base_pose, task_conflict, relocation_fail,
cant_start_schedule_in_quiet, humi_offline, humi_water_full, humi_tilt, humi_no_water_tank,
humi_no_filter_center, humi_in_no_disturb, humi_in_sleep
```

### Other small enums

```js
BatteryStatus: NORMAL=0, CHARGING=1, FULL=2, LOW=3, UNKNOWN=4                    // @1007868
NetworkStatus: OFF_LINE=0, CONNECTED=1                                           // @1008023
TaskSource:    app, schedule, backend, scene                                     // @1017699
BackwashMode:  AUTO=0, ROOM=1, TEN=10, FIFTEEN=15, TWENTY=20                     // @1023957
ChargeBaseType:COMBINED_BASE_0=0, COMBINED_BASE_1=1, DUST_BASE=2                 // @1024178
MarkerType:    CHARGE, PROHIBIT, NOWASH, WATER, HUMIDIFIER, SILL, CARPET,
               BLACK_CARPET, FURNITURE, COMBINED_BASE                            // @1020927
Consumables:   strainer, edgeBlush, mainBlush, sensor                            // @1557060
```

---

## Corrections to the integration

Read against `custom_components/switchbot_vacuum/const.py`. **These are reports, not edits — I did not modify `custom_components/`.**

### Wrong property IDs

| Constant | Current | Should be | Evidence |
|---|---|---|---|
| `PROP_ERROR_CODE` | `1019` | **`1011`** | `1011:"errorCode"`. `1019` is `upgradeStatus`. [bundle @950966] |
| `PROP_ONLINE` | `1003` | **`66`** | `66:"networkStatus"`. `1003` is `power`. [bundle @950940] |
| `PROP_MAP_INFO` | `1055` | 1055 is `currentMapStatus` | Map data comes from the `/sweeper/v1/map/*` endpoints, not a shadow property. |
| `PROP_CLEAN_SUMMARY` | `1052` | 1052 is `cleanProcess` (live progress, not a summary) | Historical summaries are `/sweeper/v1/taskRecord/list`. |
| `PROP_TASK_INFO` | `1032` | 1032 is `startTaskEvent` | Name only; the ID is right. |
| `PROP_AWS_CREDS` | `1130` | **not in the map** | No `1130` entry exists. |

Correct as-is: `PROP_BATTERY` 1004, `PROP_WORK_STATUS` 1010, `PROP_FIRMWARE` 1002, `PROP_S3_BUCKET` 1028, `PROP_AWS_REGION` 1031, `PROP_ROOM_PLANS` 1038 (`allCleanPlan`), `PROP_CLEAN_MODE` 1053 (`clearMode`).

`PROP_ERROR_CODE` is the important one. Reading `1019` yields `upgradeStatus`, which is `0` (STANDBY) almost always — so the problem sensor silently never fires, and would misfire during an OTA.

### Wrong error-code table

`ERROR_CODES` maps 2000–2012 to Qihoo 360 meanings. Per this bundle: there is no `2000`; `2001` is `WATER_STATION_LEAK` (not "stuck"); `2008` is `UN_INSTALL_DUST_BOX` (not "low_battery"); `2009` is `DEVICE_STUCK` (not "charging_error"); `2011` is `BUMPER_STRIP_LOCK` (not "laser_sensor_error"). `2728`, `2739`, `2740` do not exist. Replace the table wholesale.

`NON_ERROR_STATUS_CODES = {0, 11}` — `11` is not in the S10 error enum. Better candidates for "not a real fault" are `4011` `TASK_FAIL_BECAUSE_DND`, `4012` `TASK_FAIL_BECAUSE_LOW_POWER`, `4013`/`4015` `TASK_FAIL_RESERVE`.

### `WORK_STATUS_NAMES` fixes

`26` → `marking` (currently `backing_to_base`); `24` → `backing_base`; add `0` → `none` and `28` → `marking_humidifier`; `29` → `backing_to_humidifier` and `30` → `filling_humidifier` (currently both `adding_water`).

### Missing constants

`CMD_SELF_CLEANING = 1039`, `CMD_FIND_ROBOT = 1019`, `CMD_RESET_CONSUMABLE = 1032`, `CMD_REMOVE_ERROR = 1062`, `CMD_QUERY_DRYING_TIME = 1066`, `CMD_REMOTE_OPERATOR = 1023`. Plus `SELF_CLEAN_MOP_WASH = 1`, `SELF_CLEAN_START_DRYING = 2`, `SELF_CLEAN_STOP_DRYING = 3`, `SELF_CLEAN_DUST_COLLECT = 4`.

### Confirmed correct

- `CMD_CLEAN` 1001, `CMD_GO_CHARGE` 1022, `CMD_CONTROL` 1009, `CMD_CHANGE_MODE` 1043.
- `MapType` as strings; `"clean_rooms"` and `"clean_all"`. [device]
- `CLEAN_TYPES` matches `CleanMode` exactly.
- `WATER_LEVELS` 1–3 and `FAN_SPEEDS` 1–4 agree with the icon assets. (The `FAN_SPEEDS` keys were recently capitalised with lowercase aliases; the integer levels are unchanged and remain correct.)
- Not using `sweeperOriginApi` — it is dead code.

---

## Prioritised: newly implementable in Home Assistant

1. **Fix `PROP_ERROR_CODE` to `1011` and replace `ERROR_CODES`.** Not a feature — a live bug. The problem sensor currently reads `upgradeStatus` and never fires. One-line ID change plus a table swap. Highest value per effort in this document.

2. **Mop drying: start / stop.** Function 1039 param `2` / `3`. Natural fit as a `switch` entity, with state from `workingStatus == 20`. Gate on `workingStatus ∉ {16,17,18,19}` and robot-on-base. Fully confirmed.

3. **Dust collection: start.** Function 1039 param `4`. A `button` entity; state from `workingStatus == 19`. Gate on `workingStatus ∉ {16,17,18}`. Expect an `operation_frequently` rejection if triggered too often. No stop command exists.

4. **Mop wash / deep clean self.** Function 1039 param `1`. A `button`; state from `workingStatus == 16`.

5. **Fix `PROP_ONLINE` to `66`.** Availability is currently keyed off `power`.

6. **Locate.** Function 1019, no params. Maps straight onto HA's existing `vacuum.locate`. Trivial.

7. **Station settings as HA entities** — all plain shadow writes to `/device/v1/shadow/set`, no new command plumbing:
   - `number`: drying duration 1069 (2/3/4 h), volume 1039, dust-collection frequency 1103 (0/15/20)
   - `switch`: child lock 1057 (**remember the inversion**), dust collection enable 1062, drying enable 1068, auto clean liquid 1047, carpet supercharge 1060
   - `select`: backwash frequency 1110, carpet mode 1061, intelligent dust mode 1063

8. **Richer diagnostic sensors** from properties already being polled: water-station battery 1073, DND active 1095, serial 1066, clean progress 1052, error detail 1109.

9. **Consumable life + reset.** `/sweeper/v1/consumable/list` for sensors, function 1032 or `/sweeper/v1/consumable/resetRemind` for reset buttons. Four consumables.

10. **Dismiss an error.** Function 1062 with `[code]`. Lets an automation clear a transient base-station fault without opening the app.

11. **Zone cleaning.** Function 1001 with `clean_areas`. Blocked on getting polygon geometry out of `/sweeper/v1/map/listMapv2`, which is why it ranks below the above.

12. **Schedules.** Functions 1012–1015. Well understood but large surface area for modest benefit — HA automations already cover this.

### Deliberately not recommended

- **Do not implement `goBackWaterStation` (1038).** Defined but never called; param unknown.
- **Do not implement map edit (1006/1007).** Payload shapes unknown.
- **Do not send `MapType.dry_mop` / `collect_dust` to function 1001.** Read-back values only.
- **Do not implement `resetMap` (1030).** Destructive and unrecoverable.
- **Do not guess a "stop dust collection" command.** None exists in the bundle.
