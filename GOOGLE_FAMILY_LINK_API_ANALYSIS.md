
# Google Family Link – API Analysis (consolidated)

> **Goal**: document observed endpoints, useful capabilities, **exact response structure** (particularly `timeLimit` & `appliedTimeLimits`), and provide a **robust parsing guide** + test scenarios.
> **Context**: deductions confirmed from real captures (logs/dumps) and the Family Link interface. This document targets _client_ exploitation (reading), not complete reverse engineering of the proprietary protocol.

---

## ⚠️ Warning
- The API is **not public** and may change without notice.
- Formats are **proto/JSON-like** with many **positional** arrays (index-sensitive).
- The examples below are **reliable** within the observed scope, but remain subject to evolution on Google's side.

---

## 🔐 Authentication & required headers (observed)

- `Authorization: SAPISIDHASH <hash>`
- `X-Goog-AuthUser: 0`
- `X-Goog-Api-Key: <key>`
- `Content-Type: application/json+protobuf` (or `application/json protobuf` depending on tool)
- `x-goog-ext-223261916-bin: ...`
- `x-goog-ext-202964622-bin: ...`
- `x-goog-ext-198889211-bin: ...`

> These `x-goog-ext-*` vary by session / browser. Keep as-is on client side, without logging in clear text.

---

## 🧭 Endpoints (read)

| Capability / Domain | Endpoint | Query / Notes |
|---|---|---|
| **Family members** | `/kidsmanagement/v1/families/mine/members` | Returns list of family members with `userId`, `profile.displayName`, `memberSupervisionInfo.isSupervisedMember`. |
| **Restrictions** (device policies) | `/kidsmanagement/v1/people/{childId}/restrictions:listByGroups` | Returns restrictions by groups (e.g. DISALLOW_ADD_USER, DISALLOW_DEBUGGING_FEATURES, etc.). |
| **Global settings (settings menu)** | `/kidsmanagement/v1/people/settingResources` | List of settings "sections" (Play, YouTube, Chrome/Web, Search, Communication, Assistant, Gemini, App limits, Location, Devices). |
| **Location – activation screen** | `/kidsmanagement/v1/people/{childId}/location/settings` *(via settingResources path)* | Information text + explanations per device. |
| **Family member photos** | `/kidsmanagement/v1/families/mine/familyMembersPhotos` | `pageSize`, `supportedPhotoOrigins=...` (GOOGLE_PROFILE, FAMILY_MEMBERS_PHOTO, etc.). |
| **Notifications** | `/kidsmanagement/v1/people/me/notificationElements?clientCapabilities=CAPABILITY_TIMEZONE&userTimeZone=Europe/Paris` | Events (e.g. _New app installed_). |
| **Apps & usage** | `/kidsmanagement/v1/people/{childId}/appsandusage?capabilities=CAPABILITY_APP_USAGE_SESSION&capabilities=CAPABILITY_SUPERVISION_CAPABILITIES` | List of apps (package, name, icon, devices) + **appUsageSessions** with daily screen time per app. |
| **Location** | `/kidsmanagement/v1/families/mine/location/{childId}?locationRefreshMode=...&supportedConsents=SUPERVISED_LOCATION_SHARING` | Child's GPS location + **battery level** of source device. |
| **TimeLimit (scheduling)** | `/kidsmanagement/v1/people/{childId}/timeLimit?capabilities=TIME_LIMIT_CLIENT_CAPABILITY_SCHOOLTIME&timeLimitKey.type=SUPERVISED_DEVICES` | **Scheduling** Bedtime & Schooltime + **global switches** (ON/OFF) via "revisions". |
| **AppliedTimeLimits (applied state)** | `/kidsmanagement/v1/people/{childId}/appliedTimeLimits?capabilities=TIME_LIMIT_CLIENT_CAPABILITY_SCHOOLTIME` | **Daily state per device**: daily limits, active windows, allowed/consumed aggregates, **bonus overrides**. |

> Other endpoints exist without being exhaustive here (capability list not public). This doc covers those necessary for reading **bedtime/schooltime/daily-limit** & app usage/notifications/photos.

---

## 🔧 Endpoints (write/control)

| Capability / Domain | Method | Endpoint | Payload Format | Notes |
|---|---|---|---|---|
| **Block/Unblock app** | POST | `/kidsmanagement/v1/people/{childId}/apps:updateRestrictions` | `[childId, [[[packageName], [1]]]]` for block<br>`[childId, [[[packageName], []]]]` for unblock | `[1]` = block, `[]` = unblock |
| **Set per-app time limit** | POST | `/kidsmanagement/v1/people/{childId}/apps:updateRestrictions` | `[childId, [[[packageName], null, [minutes, 1]]]]` for set<br>`[childId, [[[packageName], null, [0, 0]]]]` to remove | `minutes` = daily limit, `1` = enabled |
| **Device lock/unlock** | POST | `/kidsmanagement/v1/people/{childId}/timeLimitOverrides:batchCreate` | `[null, childId, [[null, null, action_code, deviceId]], [1]]` | `action_code`: 1=LOCK, 4=UNLOCK |
| **Add time bonus** | POST | `/kidsmanagement/v1/people/{childId}/timeLimitOverrides:batchCreate` | `[null, childId, [[null, null, 10, deviceId, null, null, null, null, null, null, null, null, null, [[bonus_seconds, 0]]]], [1]]` | Type 10 = time bonus. Bonus **replaces** normal time (doesn't add). |
| **Set daily limit duration** | POST | `/kidsmanagement/v1/people/{childId}/timeLimitOverrides:batchCreate` | `[null, childId, [[null, null, 8, deviceId, null, null, null, null, null, null, null, [2, minutes, day_code]]], [1]]` | Type 8 = set daily limit duration. **CRITICAL**: `day_code` MUST match current day (see Day Codes table below) |
| **Set bedtime schedule** | POST | `/kidsmanagement/v1/people/{childId}/timeLimitOverrides:batchCreate` | `[null, childId, [[null, null, 9, null, null, null, null, null, null, null, null, null, [2, [startH, startM], [endH, endM], day_code]]], [1]]` | Type 9 = set bedtime. Format: `[status, [startHour, startMin], [endHour, endMin], day_code]`. Status 2=enabled. |
| **Cancel time bonus** | POST | `/kidsmanagement/v1/people/{childId}/timeLimitOverride/{overrideId}?$httpMethod=DELETE` | No body | Google API convention: POST with $httpMethod=DELETE |
| **Enable/Disable bedtime** | PUT | `/kidsmanagement/v1/people/{childId}/timeLimit:update?$httpMethod=PUT` | `[null, childId, [[null, null, null, null], null, null, null, [null, [["487088e7-38b4-4f18-a5fb-4aab64ba9d2f", state]]]], null, [1]]` | UUID `487088e7-...` = bedtime policy.<br>state: 2=ON, 1=OFF |
| **Enable/Disable school time** | PUT | `/kidsmanagement/v1/people/{childId}/timeLimit:update?$httpMethod=PUT` | `[null, childId, [[null, null, null, null], null, null, null, [null, [["579e5e01-8dfd-42f3-be6b-d77984842202", state]]]], null, [1]]` | UUID `579e5e01-...` = school time policy.<br>state: 2=ON, 1=OFF |
| **Enable/Disable daily limit** | PUT | `/kidsmanagement/v1/people/{childId}/timeLimit:update?$httpMethod=PUT` | `[null, childId, [null, [[state, null, null, null]]], null, [1]]` | state: 2=ON, 1=OFF |

### Policy UUIDs (hardcoded)
- **Bedtime (Downtime)**: `487088e7-38b4-4f18-a5fb-4aab64ba9d2f`
- **School time (Evening limit)**: `579e5e01-8dfd-42f3-be6b-d77984842202`

### timeLimitOverrides:batchCreate action codes
- **1**: LOCK device
- **4**: UNLOCK device
- **8**: SET daily limit duration (per device)
- **9**: SET bedtime schedule (per child)
- **10**: ADD time bonus (per device)

### Day Codes (CAEQ* - for daily limit)
The `day_code` in the daily limit payload encodes the day of the week. **You MUST use the code corresponding to the current day** for the change to take effect immediately.

| Day | Code | ISO weekday |
|---|---|---|
| Monday | `CAEQAQ` | 1 |
| Tuesday | `CAEQAg` | 2 |
| Wednesday | `CAEQAw` | 3 |
| Thursday | `CAEQBA` | 4 |
| Friday | `CAEQBQ` | 5 |
| Saturday | `CAEQBg` | 6 |
| Sunday | `CAEQBw` | 7 |

> ⚠️ **Important**: If you send a day code that doesn't match the current day, the API will create an override for that day instead of the current day, resulting in **no visible change** to the daily limit. Always compute the day code dynamically based on the current date.

---

## 🧱 Data models — observed keys

### 1) `timeLimit` — **Scheduling** (theoretical)
- Contains **time slots** for each day + **revisions** indicating the **global ON/OFF** state of Bedtime & Schooltime.
- **Response structure**: Wrapped format `[[metadata], [real_data]]`
  - Real data is at index `[1]` of the response
  - Index `[0]` of real_data: Bedtime configuration
  - Index `[1]` of real_data: Daily limit + School time configuration
  - Last elements: Revisions (exactly 4 elements: `[policyId, type_flag, state_flag, timestamp]`)
- Two families of tuples (in a large array):
  - **Bedtime**: **`CAEQ*`** entries (per day)
  - **Schooltime**: **`CAMQ*`** entries (per day)

#### 1.1. `CAEQ*` tuples (Bedtime / Downtime)
```
["CAEQAQ"|"CAEQAg"|..., day, stateFlag, [startH,startM], [endH,endM], createdEpochMs, updatedEpochMs, policyId]
```
- `day`: 1..7 (Monday..Sunday)
- `stateFlag`: **2 = ON**, **1 = OFF** (for this day)
- `start/end`: local hours (24h)
- `policyId`: internal identifier (e.g. `487088e7-...`) — useful for cross-referencing with "revisions"

#### 1.2. `CAMQ*` tuples (Schooltime)
```
["CAMQAS..."|..., day, stateFlag, [startH,startM], [endH,endM], createdEpochMs, updatedEpochMs, policyId]
```
- Same semantics as `CAEQ*`, for the **Schooltime** domain.

#### 1.3. "Revisions" block (global ON/OFF states)
At the end of response, a block of tuples indicates the global state of switches:
```
[ policyId, type, state, [sec, nanos] ]
```
- `type`: **1 = Bedtime**, **2 = Schooltime**
- `state`: **2 = ON**, **1 = OFF**
- `policyId`: corresponds to the `policyId` seen in `CAEQ*/CAMQ*` tuples

> The **very first integer** of the 1st large block **often** reflects the global Bedtime state (`2` when ON, `1` when OFF). Don't rely on it alone: use **revisions** as the source of truth.

---

### 2) `appliedTimeLimits` — **Applied state today (per device)**
- Each **device** appears in a **block**. Inside, we find:
  - **Daily limit (minutes)** as a **`CAEQBg`** tuple with a **minutes value**.
  - **Bedtime** (window) via **`CAEQBg`** tuple but **with hours `[start],[end]`** (yes, same root key, different content).
  - **Schooltime** via a **`CAMQ*`** tuple (e.g. `CAMQBi...`) with **hours** and `stateFlag`.
  - **Lock state & Bonus override** at position `[0]` of each device block
  - **Used time** at position `[20]` (milliseconds as string)
  - **Aggregates** "allowed / consumed" for the day (often two close integers, sometimes `0` if OFF).

#### 2.1. Daily limit (per device & per day)
```
["CAEQBg", day, stateFlag, minutes, createdEpochMs, updatedEpochMs]
```
- `stateFlag`: **2 = ON**, **1 = OFF**
- `minutes`: daily quota (e.g. `120` for 2h)
- **ON** if `stateFlag == 2` **AND** `minutes > 0`

#### 2.2. Bedtime (applied window this day, per device)
```
["CAEQBg", day, stateFlag, [startH,startM], [endH,endM], createdEpochMs, updatedEpochMs, policyId]
```
- `stateFlag`: **2 = ON**, **1 = OFF**
- Hours in the tuple. Crosses midnight if `end < start`.

#### 2.3. Schooltime (applied window this day, per device)
```
["CAMQBi...", day, stateFlag, [startH,startM], [endH,endM], createdEpochMs, updatedEpochMs, policyId]
```
- `stateFlag`: **2 = ON**, **1 = OFF**

#### 2.4. Lock state & Bonus override (position [0] of device block)
Position `[0]` of each device block contains either:
- **Lock state**: `[null, null, action_code, device_id]`
  - `action_code`: **1 = LOCKED**, **4 = UNLOCKED**
- **Bonus override**: `[override_id, timestamp, 10, device_id, ..., [[bonus_seconds]]]`
  - Type **10** indicates time bonus
  - Bonus seconds at position `[0][13][0][0]` (string format: e.g., `"1800"` for 30 minutes)
  - **IMPORTANT**: Bonus **replaces** normal daily limit time (doesn't add to it)
  - When bonus active: `remaining_time = bonus_minutes` (ignoring daily_limit - used_time)
  - `override_id` is a UUID used to cancel the bonus via DELETE endpoint

#### 2.5. Used time (position [20])
- Position `[20]` contains used time in **milliseconds** as a **string**
- Example: `"3600000"` = 60 minutes = 1 hour
- Convert: `used_minutes = int(device_data[20]) // 60000`

#### 2.6. Daily limit activation rules
Daily limit is considered **active** if ALL conditions are met:
1. Tuple day matches **current day of week** (1=Monday, 7=Sunday)
2. Tuple appears at **index < 10** (active position, not historical config)
3. `stateFlag == 2` (enabled)

> **Note**: `appliedTimeLimits` may summarize several **policies** but doesn't guarantee a perfect "flatten". Rely on the **current day** and present tuples for **ON/OFF detection**.

---

## 🧭 Indexing (critical positions)

### Time window tuples (bedtime/schooltime)
```
[ key, day(1), stateFlag(2), start(3), end(4), createdMs(5), updatedMs(6), policyId(7) ]
```
- `stateFlag ∈ {1,2}`
- `start/end`: 2-tuples `[hh,mm]`

### Daily limit (minutes)
```
[ "CAEQBg", day(1), stateFlag(2), minutes(3), createdMs(4), updatedMs(5) ]
```

### Revisions (timeLimit, end of response)
```
[ policyId(0), type(1), state(2), [sec(3).0, nanos(3).1] ]
```

> In some dumps, additional fields precede/follow (null, zeros, timestamps) — **never index absolutely** on the entire line, but **locate the root key** (`"CAEQ..."`/`"CAMQ..."`) then parse **relatively**.

---

## ✅ Scenario matrix (verified)

| Scenario | Bedtime (global) | Schooltime (global) | Daily limit |
|---|---:|---:|---:|
| 1. Bedtime ON, School ON, Daily ON | `timeLimit: revisions → type=1, state=2` | `revisions → type=2, state=2` | `appliedTimeLimits: ["CAEQBg", d, 2, minutes>0]` |
| 2. Bedtime OFF, School ON, Daily ON | `revisions → type=1, state=1` | `revisions → type=2, state=2` | same (ON) |
| 3. Bedtime OFF, School OFF, Daily ON | `revisions → type=1, state=1` | `revisions → type=2, state=1` | same (ON) |
| 4. Daily OFF (per device) | (as previous) | (as previous) | `appliedTimeLimits: ["CAEQBg", d, 1, minutes]` **or** day aggregates at `0` |

> **Note**: the **scheduling** (the `CAEQ*/CAMQ*` tuples in `timeLimit`) remains **present** even if the **global switch** is OFF. It's the **global state** (revisions) that arbitrates application.

---

## 🧪 Parsing — Recommended algorithm (pseudo-code)

```python
def parse_time_limit(payload):
	# 1) Extract Bedtime (CAEQ*) and Schooltime (CAMQ*) scheduling
	bedtime = extract_schedules(payload, key_prefix="CAEQ")
	school  = extract_schedules(payload, key_prefix="CAMQ")

	# 2) Read global ON/OFF state via revisions (source of truth)
	globals = extract_revisions(payload)  # { bedtime: on/off, school: on/off }

	return {
		"bedtime_schedules": bedtime,   # [{day,start,end,policyId,stateFlag}]
		"schooltime_schedules": school, # same
		"global": globals               # {"bedtime": True/False, "schooltime": True/False}
	}

def parse_applied_time_limits(payload, today_day):
	devices = []
	for dev in iterate_devices(payload):
		daily = find_tuple(dev, key="CAEQBg", day=today_day, form="minutes")
		bed   = find_tuple(dev, key="CAEQBg", day=today_day, form="window")
		school= find_tuple(dev, key_prefix="CAMQ", day=today_day, form="window")

		devices.append({
			"device_id": extract_device_id(dev),
			"daily_limit_on": daily and daily.stateFlag == 2 and daily.minutes > 0,
			"daily_limit_minutes": daily.minutes if daily else 0,
			"bedtime_on": bed and bed.stateFlag == 2,
			"bedtime_window": bed and (bed.start, bed.end),
			"schooltime_on": school and school.stateFlag == 2,
			"schooltime_window": school and (school.start, school.end),
			"allowed_used_ms": extract_aggregates(dev)  # optional
		})
	return devices
```

**Interpretation rules**:
- `stateFlag == 2` → **ON**, `1` → **OFF** (valid for all tuple families).
- `minutes > 0` required to consider the **daily limit** active.
- **Hours** are local (Europe/Paris if user context; beware of DST).
- Windows `start > end` **cross midnight** (e.g. 20:30 → 07:30).

---

## 🧩 Aggregated fields (appliedTimeLimits)
In each device block, two integers (often contiguous) represent the **allowed/consumed** for the day (ms). They can be `0` if the limit is **OFF** even if a minute value exists in the tuple.

---

## 👨‍👩‍👧‍👦 Family Members (`families/mine/members`)

Returns the list of all family members (parents and supervised children).

### Response structure
```json
{
  "members": [
    {
      "userId": "123456789",
      "profile": {
        "displayName": "Child Name",
        "photoUrl": "https://..."
      },
      "memberSupervisionInfo": {
        "isSupervisedMember": true
      }
    }
  ]
}
```

### Key fields
- `userId`: Unique identifier for the family member (used as `childId` in other endpoints)
- `profile.displayName`: Display name
- `memberSupervisionInfo.isSupervisedMember`: Boolean indicating if this is a supervised child

---

## 📍 Location (`families/mine/location/{childId}`)

Returns the GPS location of a supervised child, along with battery information.

### Query parameters
- `locationRefreshMode`: `REFRESH` (forces fresh location, uses battery) or `DO_NOT_REFRESH` (cached)
- `supportedConsents`: `SUPERVISED_LOCATION_SHARING`

### Response structure (protobuf-like array)
```
[
    [null, "timestamp_ms"],                    // Metadata
    [
        "childId",                              // [0] Child account ID
        1,                                      // [1] Status
        [                                       // [2] Location data array
            [latitude, longitude],              // [0] Coordinates
            "timestamp_ms",                     // [1] Location timestamp
            "accuracy_meters",                  // [2] GPS accuracy
            "unknown",                          // [3] Unknown (e.g., "300000")
            null,                               // [4] null or place info
            "address_string",                   // [5] Full address
            "source_device_id",                 // [6] Device ID providing location
            null,                               // [7] null
            [battery_level, battery_state]      // [8] Battery info
        ],
        null,
        1
    ]
]
```

### Battery info (index [8])
- Position `[0]`: Battery level percentage (integer, e.g., `42`)
- Position `[1]`: Battery state (integer, suspected: `1`=not charging, `2`=charging — **not confirmed**)

### Key fields
| Index | Field | Type | Description |
|-------|-------|------|-------------|
| `[2][0]` | coordinates | `[lat, lng]` | GPS coordinates |
| `[2][1]` | timestamp | string | Milliseconds since epoch |
| `[2][2]` | accuracy | string | GPS accuracy in meters |
| `[2][5]` | address | string | Full address (may be null) |
| `[2][6]` | source_device_id | string | Device providing location |
| `[2][8][0]` | battery_level | int | Battery percentage (0-100) |
| `[2][8][1]` | battery_state | int | Charging state (unconfirmed) |

### Important notes
- Battery data corresponds to the **device selected for location tracking** in Family Link app
- In Family Link app, users can choose which device provides location ("Change device" screen) or let Family Link choose automatically
- Battery level is **not available per-device** — only for the location source device

---

## 🧷 Apps & Usage (`appsandusage`)

### Response structure
The endpoint returns three main sections:
1. **`apps`**: List of installed applications
2. **`deviceInfo`**: List of supervised devices
3. **`appUsageSessions`**: Daily screen time per app

### Apps list
- **App list** (package, label, icon, devices). Example item:
```
[ packageName, appName, iconUrl, [], installedEpochMs, null, 0, 1, null, null, deviceCount, [deviceIds...], stateFlag ]
```
- `stateFlag` (at end): per-app status on supervision side (observed 1/2).
- `supervisionSetting.hidden`: Boolean indicating if app is blocked

### Device info
- Contains device metadata: `deviceId`, `displayInfo.friendlyName`, `displayInfo.model`, `displayInfo.lastActivityTimeMillis`
- `capabilityInfo.capabilities`: Array of device capabilities

### App usage sessions
Each session represents daily usage for one app:
```json
{
  "date": {
    "year": 2025,
    "month": 1,
    "day": 17
  },
  "usage": "1809.5s",
  "appId": {
    "androidAppPackageName": "com.example.app"
  }
}
```
- `usage`: Format `"XXX.Xs"` where XXX is seconds (can have decimals)
- Parse: `float(usage.replace("s", ""))` to get seconds
- Sum all sessions for a given date to get total daily screen time

---

## ⏱️ Per-App Time Limits (`apps:updateRestrictions`)

### Endpoint
`POST /kidsmanagement/v1/people/{childId}/apps:updateRestrictions`

### Payload Format
```
[childId, [[[packageName], null, [minutes, enabled_flag]]]]
```

### Parameters
| Position | Field | Type | Description |
|----------|-------|------|-------------|
| `[0]` | childId | string | Child's user ID |
| `[1][0][0][0]` | packageName | string | Android package name |
| `[1][0][1]` | (reserved) | null | Always null for time limits |
| `[1][0][2][0]` | minutes | int | Daily limit in minutes (0-1440) |
| `[1][0][2][1]` | enabled_flag | int | 1 = enabled, 0 = disabled |

### Examples

**Set 60 minutes daily limit for TikTok:**
```json
["116774149781348048793", [[["com.zhiliaoapp.musically"], null, [60, 1]]]]
```

**Remove time limit (restore unlimited):**
```json
["116774149781348048793", [[["com.zhiliaoapp.musically"], null, [0, 0]]]]
```

### Response
```json
[[null, "1767881631499"]]
```
Returns a transaction ID/timestamp on success.

### Notes
- This endpoint is the same as block/unblock app but with different payload structure
- Setting a limit on an app without an existing limit will create the limit
- Setting `minutes: 0` with `enabled_flag: 0` removes the limit entirely
- The limit is **per-app, per-child** (not per-device)
- Updated limits are reflected in `sensor.<child>_apps_with_time_limits`

---

## 📣 Notifications (`notificationElements`)
- E.g. "New app installed" with **timestamp** (`["1763148569", 431000000]`) and **links** to the concerned app (`/member/{childId}/app/{package}`).
- `clientCapabilities=CAPABILITY_TIMEZONE` + `userTimeZone=Europe/Paris` recommended for local timestamps.

---

## 🖼️ Family photos (`familyMembersPhotos`)
- Response: `[ personId, null, photoUrl, origin, familyId, optionalColor ]`
- `supportedPhotoOrigins=`: `GOOGLE_PROFILE`, `FAMILY_MEMBERS_PHOTO`, `DEFAULT_SILHOUETTE`, `CHILD_DEFAULT_AVATAR`, `UNKNOWN_PHOTO_ORIGIN`.

---

## ❗ Key points & client best practices

- **Don't hardcode indexes** on the entire line: _match the root key_ (`"CAEQ..."` / `"CAMQ..."`) then interpret **relatively**.
- **Tolerance to `null`/missing fields**: provide `get()`/`try` on positions.
- **Hours**: always **normalize** `[hh,mm]` (0–23 / 0–59); handle **midnight** (`end < start`).
- **Timezones & DST**: convert epoch ms → local `datetime`; prefer timezone-aware utilities.
- **Secrets**: never log auth/key headers; mask in diagnostics.
- **Rate limiting**: bounded retries (429/5xx) + backoff + jitter; 401/403 → reauth/config.
- **Bonus time behavior**: Bonus **replaces** normal daily limit (doesn't add). Calculate: `remaining = bonus_minutes if bonus > 0 else max(0, daily_limit - used)`
- **Daily limit detection**: Only active if tuple day matches current weekday AND tuple index < 10 AND stateFlag == 2
- **timeLimit response**: Always unwrap from `response[1]` (real data), `response[0]` is metadata
- **Revisions identification**: Exactly 4 elements `[uuid, type_flag, state_flag, timestamp]`, filter by length to avoid confusion with schedules (7+ elements)
- **Policy UUIDs**: Hardcoded per policy type (bedtime, schooltime), same across all accounts
- **Device control**: Use action codes (1=LOCK, 4=UNLOCK) not boolean values
- **Set daily limit day code**: The CAEQ day code in `set_daily_limit` payload **MUST match the current day** (CAEQAQ=Monday...CAEQBw=Sunday). Using a hardcoded code will create an override for the wrong day!

---

## 🧪 Tests (recommended)
- **Fixtures** - Basic scenarios:
  1. Bedtime ON + School ON + Daily ON
  2. Bedtime OFF + School ON + Daily ON
  3. Bedtime OFF + School OFF + Daily ON
  4. Daily OFF (per device), with comparison between 2 devices
- **Fixtures** - Advanced scenarios:
  5. Device locked (action_code = 1)
  6. Device unlocked (action_code = 4)
  7. Time bonus active (type 10, with bonus_seconds)
  8. Time bonus + daily limit (verify bonus replaces, not adds)
  9. Daily limit tuple at index > 10 (should be ignored as historical)
  10. Daily limit tuple for different day (should be ignored)
- **Asserts** - Basic:
  - `daily_limit_on`, `daily_limit_minutes` correct per device/day.
  - `bedtime_on`, `schooltime_on` + windows `[start,end]`.
  - Mapping `revisions` (type=1/2 → state=2/1).
- **Asserts** - Advanced:
  - Lock state detection from position [0][2]
  - Bonus override parsing from position [0][13][0][0]
  - Used time parsing from position [20]
  - Bonus replaces behavior: `remaining = bonus` (not `daily_limit - used + bonus`)
  - Daily limit activation: only if day==current AND index<10 AND state==2
  - timeLimit unwrapping: data at response[1]
  - Revision filtering: exactly 4 elements

---

## 📝 Quick glossary
- **CAEQ***: Bedtime or Daily family (depending on payload: minutes vs window).
- **CAMQ***: Schooltime family.
- **stateFlag**: 2=ON, 1=OFF.
- **policyId**: rule identifier (link with revisions).

---

## ❓ Known gaps / Openings
- **Exhaustive capability list**: not public; document **as you use**.
- **Complete proto schema**: not available; remain defensive on parsing side.
- **Position [19] in appliedTimeLimits**: May contain bonus-related data or remaining time, needs further investigation.
- **Other override types**: Only types 1, 4, 8, 10 documented. Other types may exist.
- **Bedtime/Schooltime schedule updates**: Write endpoints for updating schedules (not just ON/OFF) not yet documented.
- **Daily limit per-device enable/disable**: Currently only global ON/OFF documented, per-device toggle may exist.
- **App blocking granularity**: Whitelist/blacklist modes not fully explored. Per-app time limits now documented (see section above).

---

*Last update: generated from analysis of concrete dumps and Family Link UI. PRs welcome if you observe variants.*
