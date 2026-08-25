# The SwitchBot S10 map format

Everything below was read out of `index.android.bundle` from the SwitchBot **Sweeper**
React Native plugin **v1.0.43.0** (2.8 MB, fetched with `tools/fetch_rn_bundle.py`).
Quotes are the real minified source, reformatted only by inserting line breaks.
Byte offsets refer to that exact bundle.

Statements are tagged **CONFIRMED** (read directly in the plugin source),
**INFERRED** (a conclusion drawn from that source), or **UNKNOWN**.

---

## Design note: why an `image` entity and no custom card

**Chosen: option 1 — a stock Home Assistant `image` entity, no frontend code.**

The decisive fact is that **the robot uploads an already-rendered PNG**. The map
package is not an occupancy bitfield we have to rasterise; it contains
`refined_map.png`, and the app downloads that file and hands it straight to an
`<Image>`. So the integration's whole job is: fetch bytes, serve bytes.

That makes the entity choice easy:

* `homeassistant.components.image.ImageEntity` returns `bytes` from `async_image()`
  and signals freshness with `_attr_image_last_updated`. The HA frontend appends the
  entity state (which *is* that timestamp) to the proxy URL — verified in
  `frontend/src/data/image.ts`:

  ```ts
  export const computeImageUrl = (entity: ImageEntity): string | undefined =>
    entity.attributes.access_token
      ? `/api/image_proxy/${entity.entity_id}?token=${entity.attributes.access_token}&state=${entity.state}`
      : undefined;
  ```

  So bumping the timestamp is exactly the "periodically-updating rendered map"
  refresh mechanism. This is what HA core's Roborock integration does
  (`homeassistant/components/roborock/image.py`), and what
  `xiaomi_cloud_map_extractor` v3 moved to. A `camera` entity would work too, but it
  buys nothing here — there is no stream, and `frame_interval` is the wrong knob for
  something that changes every 60 seconds.

* The stock **`picture-entity`** card renders the `image` domain with zero config —
  verified in `hui-picture-entity-card.ts`, which whitelists
  `["camera", "image", "person"]` and calls `computeImageUrl()` for the `image` case.
  `picture-glance` and `picture-elements` do the same. There is no `image` card; a
  three-line `picture-entity` is the least-friction path:

  ```yaml
  type: picture-entity
  entity: image.<your_vacuum>_map
  show_state: false
  show_name: false
  ```

* The popular **`PiotrMachowski/lovelace-xiaomi-vacuum-map-card`** also accepts an
  `image` entity, despite the config key being called `camera`. Verified in its own
  source (`src/xiaomi-vacuum-map-card.ts`), which filters the picker on both domains
  and resolves the source through `entity_picture` — an attribute `ImageEntity`
  provides:

  ```ts
  .filter(e => ["camera", "image"].includes(e.substring(0, e.indexOf("."))))
  .filter(e => hass?.states[e].attributes["calibration_points"]);
  ```
  ```ts
  const url = this.hass.hassUrl(this.hass.states[config.map_source.camera].attributes.entity_picture);
  return `${url}&v=${+new Date()}`;
  ```

  Its calibration contract is three (or four) `{vacuum:{x,y}, map:{x,y}}` pairs read
  from `attributes["calibration_points"]` on that same entity. We can produce those
  exactly, because the plugin gave us the world-to-pixel transform (below). So the
  entity ships `calibration_points` from day one and the interactive card works with
  `map_source: {camera: image.<entity>}` and `calibration_source: {camera: true}` —
  still with no code from us.

A custom Lovelace card would have added a build step, a HACS frontend resource and a
maintenance burden to display a PNG that two stock cards already display. It is not
justified.

**Cost: zero new Python dependencies.** Serving the PNG verbatim means no Pillow, no
numpy. Image dimensions come from the 8-byte PNG IHDR header via `struct`.

---

## Where the map lives

**CONFIRMED.** The robot writes its map to S3 as a *directory of loose objects*, one
per map ID. The plugin reads five properties to locate it
(offset 1247236, `callDeviceReadMultiProperty`):

```js
var e=yield PMServiceModuleHelper.callDeviceReadMultiProperty({
    deviceId:Et,propertyIds:["1023","1028","1029","1051","1111"],params:{}});
...
NativeAsyncStorage.setItem(AsyncStorageKey.SWEEPER_S3_BUCKET, i.s3Bucket ?? ""),
NativeAsyncStorage.setItem(AsyncStorageKey.SWEEPER_S3_OBJECT, i.s3Object ?? ""),
NativeAsyncStorage.setItem(AsyncStorageKey.SWEEPER_S3_OBSTACLE_UPLOAD_URL, i.picUploadDir ?? "")
```

The full property-ID table is at offset 951645:

```js
m.exports={805:"autoUpgrade",1001:"deviceID",1002:"version",1003:"power",1004:"battery",
 ...,1022:"currentPose",1023:"mapID",1024:"taskCommand",...,
 1028:"s3Bucket",1029:"s3Object",1030:"s3AuthTokenUrl",1031:"awsRegion",...,
 1051:"cleanAreas",1052:"cleanProcess",1053:"clearMode",1055:"currentMapStatus",...,
 1081:"savedMapList",...,1111:"picUploadDir",...}
```

| Property | Name | Use |
|---|---|---|
| 1022 | `currentPose` | robot pose, JSON string `"[x, y, theta]"` |
| 1023 | `mapID` | the directory name under the S3 prefix |
| 1028 | `s3Bucket` | bucket (default `prod-eu-sweeper-origin`) |
| 1029 | `s3Object` | key prefix, of the form `{deviceId}/current_map` |
| 1031 | `awsRegion` | region (`eu-central-1` for EU accounts) |
| 1055 | `currentMapStatus` | `{mapID, mapName, snapshootUrl, backup, ...}` |
| 1130 | — | temporary AWS credentials (not named in the plugin) |

Objects are then addressed as `{s3Object}/{mapID}/{file}` (offset 991822):

```js
n=e.getSignedUrl({Bucket:E.S3Bucket,Key:`${E.S3Object}/${t}/refined_map.json`})||"",
s=e.getSignedUrl({Bucket:E.S3Bucket,Key:`${E.S3Object}/${t}/mapinfo.json`})||"",
c=e.getSignedUrl({Bucket:E.S3Bucket,Key:`${E.S3Object}/${t}/labels.json`})||"",
l=e.getSignedUrl({Bucket:E.S3Bucket,Key:`${E.S3Object}/${t}/markers.json`})||"",
C=e.getSignedUrl({Bucket:E.S3Bucket,Key:`${E.S3Object}/${t}/ai_objects.json`})||"";
```

and the image the same way, with an unsigned fallback URL that reveals the shape of
`s3Object` (offset 994660):

```js
c=`https://${s.S3Bucket}.s3.amazonaws.com/${BuzGlobalBean.DEVICE.deviceId}/current_map/${E}/refined_map.png`,
l=_?.getSignedUrl({Bucket:s.S3Bucket,Key:`${s.S3Object}/${E}/refined_map.png`})||c;
```

Per-clean-report maps are the same seven files packed into a zip, downloaded from
`currentMapStatus`-style `resource` keys and unzipped (offset 1028851):

```js
var D=yield unzip(t,`${DocumentDirectoryPath}/cleanReport/report`);
if(D){var $=yield Promise.all([f("labels.json",`${D}/`),f("markers.json",`${D}/`),
    f("refined_map.json",`${D}/`),f("mapinfo.json",`${D}/`),f("ai_objects.json",`${D}/`)]);
  l=$[0],o=$[1],c=$[2],s=$[4];var P=$[3];
  (yield exists(`${D}/track.json`))&&(p=yield f("track.json",`${D}/`)),
  y=Math.floor(180*P.rotation/Math.PI||0),h=`${D}/refined_map.png`}
...
return{labels:l,markers:o,mapInfo:c,pathData:p,mapUrl:h,rotation:y,obstacle:s}
```

This integration uses the loose-object path, because that is what the app uses for
the *live* map and it needs no zip. (The existing `async_refresh_rooms` still reads
`labels.json` out of the `currentMapStatus.resource` zip; that path is untouched.)

---

## Package contents

**CONFIRMED** — the seven names above are the complete set the plugin ever reads.

| File | Contents |
|---|---|
| `refined_map.png` | the map raster, already rendered by the robot |
| `refined_map.json` | raster metadata: `origin`, `resolution` |
| `mapinfo.json` | display metadata: `rotation` in radians |
| `labels.json` | rooms and carpets: id, name, polygon, bbox, thresholds |
| `markers.json` | dock, no-go zones, sills, carpets, furniture, water station |
| `ai_objects.json` | AI-detected obstacles |
| `track.json` | the cleaning path (clean reports only) |

Careful: the object the plugin calls `mapInfo` internally is **`refined_map.json`**,
not `mapinfo.json`. From `getMapData` (offset 991497), where `E` is the
`Promise.all` result in the order `refined_map.json, labels.json, markers.json,
mapinfo.json, ai_objects.json`:

```js
var c=E[3],l=Math.floor(180*(c?.rotation)/Math.PI||0);
if(void 0===c?.rotation)l=o??0;
return{mapinfo:E[0],labels:E[1],markers:E[2],obstacle:E[4],mapRotation:l,client:e}
```

`E[0]` (`refined_map.json`) becomes the `mapinfo` that every coordinate transform
takes as its `origin`/`resolution` source; `E[3]` (`mapinfo.json`) is consulted only
for `rotation`.

### `refined_map.json`

**CONFIRMED** fields: `origin` (array, at least `[x, y]`, defaulted to `[0,0,0]`) and
`resolution` (metres per pixel, defaulted to `1` in the transforms and to `0.05` at
every UI call site, e.g. `` (Ze?.resolution)||.05 ``).

**INFERRED:** this is the ROS `map_server` map-metadata convention — `origin` is the
world coordinate of the *bottom-left* pixel and `resolution` is metres per cell. The
transforms below match `map_server`'s exactly.

**UNKNOWN:** whether the file carries any other keys (`negate`, `occupied_thresh`,
`free_thresh`, `image`, `width`, `height` would all be conventional). The plugin
never reads them, so they may or may not be present. The decoder ignores anything
it does not recognise.

### `mapinfo.json`

**CONFIRMED:** `rotation`, in radians, converted to whole degrees with
`Math.floor(180*rotation/Math.PI)`. It is a *display* rotation applied on top of the
unrotated raster; the plugin only ever branches on 0/90/180/270. **UNKNOWN:** any
other keys.

### `refined_map.png`

**CONFIRMED:** it is a PNG, downloaded to disk and measured with React Native's
`Image.getSize` — so the raster's pixel dimensions are the grid dimensions
(offset 1918038):

```js
o.Image.getSize(`file:// ${p}?${(new Date).getTime()}`,function(e,t){
  var n=90===h||270===h?t:e, l=90===h||270===h?e:t,
      c=getLabelsInfo(h,l,n,i,u).rooms, ...
```

(`h` is the rotation in degrees; width and height are swapped for 90/270. The
integration serves the raster unrotated, so it uses the degree-0 transform.)

**UNKNOWN — and deliberately not guessed: the pixel encoding.** The renderer is a
*native* component, `MapImageView`, which is not in this bundle (it is imported from
host-app module `2871`, which the plugin bundle does not contain). All we can see is
its prop surface (offset 1929023):

```js
(0,v.jsx)(y,{style:{width:re.current,height:ie.current},scale:ke,
  backColor:"#92C4FF",barrierColor:"#788DA1",rooms:L,url:j,degree:O,
  isShowBarrierColor:!(Ce?.length&&Ce[0]),onDrawCompleted:...})
```

So the app recolours the raster at draw time: floor → `#92C4FF`, walls → `#788DA1`.
**INFERRED** from that plus the ROS metadata: the PNG is a greyscale/paletted
occupancy raster in the `map_server` idiom (free / occupied / unknown levels), which
is legible as-is. **This integration does not depend on that inference** — it serves
the file byte-for-byte and lets the browser decode it. If a real sample turns out to
be, say, mostly transparent, the fix is a recolouring pass in `map.py`, not a
different architecture.

### `labels.json`

**CONFIRMED** shape, from `getLabelsInfo` (offset 1389207):

```js
_e.getLabelsInfo=function(e,t,r,n,i){var o=cloneDeep(n?.data)||[],u=[],l="dark"===BuzGlobalBean.DARK_MODE;
 return o.forEach(function(a,n){if(a.id.includes(LabelsType.ROOM)){
   var s=CommonUtils.arrChange(2,a.geometry).map(function(a){var n=p(a,t,r,1,i,e);return[n.x,n.y]}),
       h=CommonUtils.arrChange(2,a.bbox||[])?.map(function(a){var n=p(a,t,r,1,i,e);return[n.x,n.y]}),
       y=a.threshold?.map(function(a){return a?.map(function(a){var n=p(a,t,r,1,i,e);return[n.x,n.y]})}),
       _=Object.assign({},a,{color:l?RoomColors[a?.colorType||0].dark:RoomColors[a?.colorType||0].light,
                             geometry:s,isSelected:!1,name:f(a.name),threshold:y});
   ...u.push(_)}
   a.id.includes(LabelsType.CARPET)}),{rooms:u}}
```

* Top level is `{"data": [ ... ]}`.
* Each entry has `id`, `name`, `geometry`, and optionally `bbox`, `threshold`,
  `colorType`.
* `id` is prefixed by its kind — `LabelsType = {ROOM:"ROOM", CARPET:"CARPET"}`
  (offset 1007750), matched with `id.includes(...)`, which is why the existing room
  code keys on the `ROOM_` prefix.
* `geometry` and `bbox` are **flat** arrays chunked into pairs
  (`arrChange(2, ...)`), in **world metres**.
* `threshold` is an array of such flat arrays (door thresholds).
* `colorType` indexes a five-entry palette (offset 1411441):
  ```js
  e.RoomColors=[DarkModeValue("#C8DBF7","#74ABE7"),DarkModeValue("#92C9FF","#528CDE"),
                DarkModeValue("#D2C2F2","#937DC7"),DarkModeValue("#AAAFF7","#6873D4"),
                DarkModeValue("#A9EBE7","#74C2BE")];
  ```
* `name` is run through a lookup that expands generic keys
  (`living_room`, `bedroom`, `kitchen`, ...) into localised names.

### `markers.json`

**CONFIRMED** shape, from `getMarkersInfo` (same module). Also `{"data":[...]}`, each
entry with `id`, `type`, `geometry` (flat pairs, world metres), and for furniture
`furnitureType` and `rotateAngle`. `type` is one of
`LabelType = {POINT:"point", LINE:"line", CIRCLE:"circle", POLYGON:"polygon", POSE:"pose"}`,
and the kind is again encoded in the `id` prefix
(`MarkerType = {CHARGE, PROHIBIT, NOWASH, WATER, HUMIDIFIER, SILL, CARPET, BLACK_CARPET, FURNITURE, COMBINED_BASE}`,
offset 1007750). For `CHARGE`/`WATER`/`HUMIDIFIER` the geometry is a pose:
`geometry[2]` is its heading.

Not currently decoded by the integration.

### `track.json` / `ai_objects.json`

**PARTIALLY CONFIRMED.** `track.json` is an array of path points; index 5 is the
segment type, filtered against
`PathType = {DEFAULT:0, EDGE_CLEANING:1, BOW_CLEANING:2, TRANS_REGIONAL:3, GET_OUT:4, GO_TO_BASE_STATION:5, PILE_ON:6, AI_OBSTACLE_AVOIDANCE:7, ...}`
(offset 1413454), and indices 0/1 are the world coordinate, index 2 the heading.
The meaning of indices 3 and 4 is **UNKNOWN**. `ai_objects.json` entries carry a
`name` (`cable`, `pedestal`, `feces`, `fabric`, ...) and a geometry; full shape
**UNKNOWN**. Neither is decoded.

---

## World ↔ pixel transform

**CONFIRMED.** Forward (world metres → image pixel), `transformCoordinate` at
offset 1401641, with `t` = image height, `r` = scale, `a` = `refined_map.json`:

```js
function o(e,t,r,a){var n=0,i=-1;
  switch(degree){
    case MapDegree.DEGREE_90:  n=1,  i=0;  break;
    case MapDegree.DEGREE_180: n=0,  i=1;  break;
    case MapDegree.DEGREE_270: n=-1, i=0;  break;
    case MapDegree.DEGREE_360: case MapDegree.DEGREE_0: default: n=0, i=-1}
  var o=a?.origin||[0,0,0], u=a?.resolution||1;
  return{x:r*(e[0]-o[0])/u+n, y:r*(t-(e[1]-o[1])/u)+i}}
```

Reverse (`transformCoordinateReversal`, offset 1402137):

```js
function u(e,t,a,n){var i=degree, o=[...e];
  switch(i){case DEGREE_90:o[0]-=1;break; case DEGREE_180:o[1]-=1;break;
            case DEGREE_270:o[0]+=1;break; default:o[1]+=1}
  var u=n?.origin||[0,0,0], l=n?.resolution||1;
  return{x:o[0]*l/a+u[0], y:(t-o[1]/a)*l+u[1]}}
```

At `scale = 1` and rotation 0 — which is how `getLabelsInfo` calls it
(`p(a, t, r, 1, i, e)`) — this reduces to:

```
px = (x_metres - origin[0]) / resolution
py = height - (y_metres - origin[1]) / resolution - 1
```

That is `map.py:SwitchBotMap.to_pixel`, and the three `calibration_points` are just
`(0,0)`, `(1,0)` and `(0,1)` metres pushed through it.

Non-zero `rotation` additionally pre-transforms the point via `getMapRotationLocation`
(offset 1404380), which for 90/180/270 mirrors and swaps axes about the origin. The
integration serves the raster unrotated, so it never needs those branches;
`rotation` is exposed as an attribute for information only.

**CONFIRMED — the units are metres.** `currentPose` (property 1022) is fed straight
into the same transform (offset 1249430):

```js
var y=JSON.parse(a.currentPose||"[]");
if(y?.length&&a.taskType===TaskType.STANDBY){var S=getLocation(y,yt.current),v=S.location,T=S.rotation;
  Ae(updateLocationAction(v,T))}
```

```js
_e.getLocation=function(e,t){var r=t.mapWidth,a=t.mapInfo,n=t.mapHeight,i=t.mapRotation,
      u=t.imageScaleRatio,l=t.location,c=t.rotation;
  if(!a)return{location:l,rotation:c};
  var s=o(h(e,n,r,i,a),n,u,a,i),f=s.x,p=s.y,y=E(e.length>=3?e[2]:0,i);
  return{location:{x:f,y:p},rotation:y}}
```

and headings are radians, converted by `sweeperRotation` (offset 1409139):

```js
function E(e){var t=(arguments[1]??0)+-MapDegree.DEGREE_180/Math.PI*e;
  return t>MapDegree.DEGREE_180&&(t-=MapDegree.DEGREE_360),t}
```

The same units are used the other way round: room-cleaning and area-cleaning payloads
send world-metre polygons (`cleanSomeAreas.areas[].polygon`, offset 996121).

---

## What the integration does with all this

`custom_components/switchbot_vacuum/map.py`
: reads `refined_map.png` (dimensions straight from the IHDR chunk),
  `origin`/`resolution` from `refined_map.json`, `rotation` from `mapinfo.json`, and
  the `ROOM_*` names from `labels.json`. No pixel data is touched.

`custom_components/switchbot_vacuum/coordinator.py`
: `async_fetch_map()` reads properties 1130/1028/1029/1023 and pulls the four objects
  from `{s3Object}/{mapID}/`. A background refresh runs at most every
  `MAP_REFRESH_SECONDS` (60 s) and calls `async_update_listeners()`.

`custom_components/switchbot_vacuum/image.py`
: an `ImageEntity` that returns those bytes, bumps `image_last_updated` only when the
  bytes change, and publishes `calibration_points`, `rooms`, `resolution` and
  `rotation` as attributes (kept out of the recorder via
  `_entity_component_unrecorded_attributes`).

Only the S10 family gets the entity; K10 and K10+ Pro have no S3 map.

---

## Verification status

The decoder has **not** been run against a real map. No S10 sample was available;
`tests/test_map.py` builds a synthetic package from the format above. To check it
against real data:

```sh
export SWITCHBOT_USERNAME='you@example.com'
export SWITCHBOT_PASSWORD='...'
python3 tools/dump_map.py
```

That lists everything under `{s3Object}/{mapID}/` — which is itself the check on the
file list above — and writes each object into `map_dump/` (gitignored; it is a floor
plan of your home). The two things worth eyeballing in the output are
`refined_map.json` (does it really have `origin` and `resolution`?) and
`refined_map.png` (does it open, and is it legible without recolouring?).
