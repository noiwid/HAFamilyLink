
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
| **Restrictions** (device policies) | `/kidsmanagement/v1/people/{childId}/restrictions:listByGroups` | Returns restrictions by groups (e.g. DISALLOW_ADD_USER, DISALLOW_DEBUGGING_FEATURES, etc.). |
| **Global settings (settings menu)** | `/kidsmanagement/v1/people/settingResources` | List of settings "sections" (Play, YouTube, Chrome/Web, Search, Communication, Assistant, Gemini, App limits, Location, Devices). |
| **Location – activation screen** | `/kidsmanagement/v1/people/{childId}/location/settings` *(via settingResources path)* | Information text + explanations per device. |
| **Family member photos** | `/kidsmanagement/v1/families/mine/familyMembersPhotos` | `pageSize`, `supportedPhotoOrigins=...` (GOOGLE_PROFILE, FAMILY_MEMBERS_PHOTO, etc.). |
| **Notifications** | `/kidsmanagement/v1/people/me/notificationElements?clientCapabilities=CAPABILITY_TIMEZONE&userTimeZone=Europe/Paris` | Events (e.g. _New app installed_). |
| **Apps & usage** | `/kidsmanagement/v1/people/{childId}/appsandusage?capabilities=CAPABILITY_APP_USAGE_SESSION&capabilities=CAPABILITY_SUPERVISION_CAPABILITIES` | List of apps (package, name, icon, devices) + (in other responses) **downtime/schooltime** schedules (hours). |
| **TimeLimit (scheduling)** | `/kidsmanagement/v1/people/{childId}/timeLimit?capabilities=TIME_LIMIT_CLIENT_CAPABILITY_SCHOOLTIME&timeLimitKey.type=SUPERVISED_DEVICES` | **Scheduling** Bedtime & Schooltime + **global switches** (ON/OFF) via "revisions". |
| **AppliedTimeLimits (applied state)** | `/kidsmanagement/v1/people/{childId}/appliedTimeLimits?capabilities=TIME_LIMIT_CLIENT_CAPABILITY_SCHOOLTIME` | **Daily state per device**: daily limits, active windows, allowed/consumed aggregates. |

> Other endpoints exist without being exhaustive here (capability list not public). This doc covers those necessary for reading **bedtime/schooltime/daily-limit** & app usage/notifications/photos.

---

## 🧱 Data models — observed keys

### 1) `timeLimit` — **Scheduling** (theoretical)
- Contains **time slots** for each day + **revisions** indicating the **global ON/OFF** state of Bedtime & Schooltime.
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

## 🧷 Apps & Usage (`appsandusage`)
- **App list** (package, label, icon, devices). Example item:
```
[ packageName, appName, iconUrl, [], installedEpochMs, null, 0, 1, null, null, deviceCount, [deviceIds...], stateFlag ]
```
- `stateFlag` (at end): per-app status on supervision side (observed 1/2).
- Other forms of this response may include **downtime/schooltime** windows (hours) and revisions (timestamped).

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

---

## 🧪 Tests (recommended)
- **Fixtures** 4 scenarios:
  1. Bedtime ON + School ON + Daily ON
  2. Bedtime OFF + School ON + Daily ON
  3. Bedtime OFF + School OFF + Daily ON
  4. Daily OFF (per device), with comparison between 2 devices
- **Asserts**:
  - `daily_limit_on`, `daily_limit_minutes` correct per device/day.
  - `bedtime_on`, `schooltime_on` + windows `[start,end]`.
  - Mapping `revisions` (type=1/2 → state=2/1).

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
- **"allowed/used ms" aggregates**: exact positions not guaranteed → detect by key/structure when present.

---

*Last update: generated from analysis of concrete dumps and Family Link UI. PRs welcome if you observe variants.*
