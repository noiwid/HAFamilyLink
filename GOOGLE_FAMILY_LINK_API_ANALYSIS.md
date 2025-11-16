# Google Family Link API - Reverse Engineering Analysis

This document provides a comprehensive analysis of the Google Family Link API based on the implementation found in the `tducret/familylink` Python package and the `Vortitron/HAFamilyLink` repository.

## Overview

Google Family Link does **not** have an official public API. However, the web interface at `https://families.google.com` uses internal APIs that can be accessed with proper authentication.

## API Base Information

### Base URL
```
https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1
```

### Origin
```
https://familylink.google.com
```

## Authentication

The API uses Google's SAPISID cookie-based authentication system.

### Required Cookies

The authentication requires cookies from a logged-in Google session. The most important cookie is:

- **SAPISID**: A session cookie from `.google.com` domain

### Authentication Header Generation

```python
import hashlib
import time

def generate_sapisidhash(sapisid: str, origin: str) -> str:
    """Generate the SAPISIDHASH token for Google API authorization.

    Args:
        sapisid: The SAPISID cookie value from browser
        origin: The origin URL (e.g., 'https://familylink.google.com')

    Returns:
        The SAPISIDHASH string in format: "{timestamp}_{sha1_hash}"
    """
    timestamp = int(time.time() * 1000)  # Current time in milliseconds
    to_hash = f"{timestamp} {sapisid} {origin}"
    sha1_hash = hashlib.sha1(to_hash.encode("utf-8")).hexdigest()
    return f"{timestamp}_{sha1_hash}"

# Usage
sapisid = "YOUR_SAPISID_COOKIE_VALUE"
origin = "https://familylink.google.com"
sapisidhash = generate_sapisidhash(sapisid, origin)
authorization = f"SAPISIDHASH {sapisidhash}"
```

### Required HTTP Headers

```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Origin": "https://familylink.google.com",
    "Content-Type": "application/json+protobuf",
    "X-Goog-Api-Key": "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw",
    "Authorization": "SAPISIDHASH {timestamp}_{sha1_hash}",
}
```

### Cookie Extraction

Cookies can be extracted from the browser using libraries like `browser_cookie3`:

```python
import browser_cookie3

# Extract cookies from Firefox
cookies = browser_cookie3.firefox()

# Find SAPISID cookie
sapisid = None
for cookie in cookies:
    if cookie.name == "SAPISID" and cookie.domain == ".google.com":
        sapisid = cookie.value
        break
```

## API Endpoints

### 1. Get Family Members

**Endpoint:** `GET /families/mine/members`

**Purpose:** Retrieve list of all family members, including supervised children.

**Request:**
```python
import httpx

response = httpx.get(
    "https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1/families/mine/members",
    headers={
        "Content-Type": "application/json",
        "X-Goog-Api-Key": "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw",
        "Authorization": f"SAPISIDHASH {sapisidhash}",
    },
    cookies=cookies
)
```

**Response Structure:**
```json
{
    "members": [
        {
            "userId": "12345678901234567890",
            "role": "parent",
            "profile": {
                "displayName": "Parent Name",
                "profileImageUrl": "https://...",
                "email": "parent@example.com",
                "familyName": "LastName",
                "givenName": "FirstName",
                "standardGender": "male",
                "birthday": {
                    "day": 1,
                    "month": 1,
                    "year": 1980
                },
                "defaultProfileImageUrl": "https://..."
            },
            "state": "active"
        },
        {
            "userId": "09876543210987654321",
            "role": "child",
            "profile": {
                "displayName": "Child Name",
                "profileImageUrl": "https://...",
                "email": "child@example.com",
                "familyName": "LastName",
                "givenName": "FirstName",
                "standardGender": "female",
                "birthday": {
                    "day": 15,
                    "month": 6,
                    "year": 2010
                },
                "defaultProfileImageUrl": "https://..."
            },
            "state": "active",
            "ageBandLabel": "Child",
            "memberSupervisionInfo": {
                "isSupervisedMember": true,
                "isGuardianLinkedAccount": false
            },
            "memberAttributes": {
                "showParentalPasswordReset": true
            },
            "uiCustomizations": {
                "settingsGroup": ["DEVICE", "APPS", "CONTENT"],
                "supervisedUserType": "child"
            }
        }
    ],
    "apiHeader": {
        "serverTimestampMillis": "1699999999999"
    },
    "myUserId": "12345678901234567890"
}
```

**Key Fields:**
- `userId`: Unique identifier for the member (use this for subsequent API calls)
- `memberSupervisionInfo.isSupervisedMember`: Boolean indicating if this is a supervised child

### 2. Get Apps and Usage Data (Including Screen Time)

**Endpoint:** `GET /people/{account_id}/appsandusage`

**Purpose:** Retrieve all apps, usage data, screen time, and device information for a supervised account.

**Request:**
```python
account_id = "09876543210987654321"  # Child's user ID from members endpoint

params = {
    "capabilities": [
        "CAPABILITY_APP_USAGE_SESSION",
        "CAPABILITY_SUPERVISION_CAPABILITIES",
    ],
}

response = httpx.get(
    f"https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1/people/{account_id}/appsandusage",
    headers={
        "Content-Type": "application/json",
        "X-Goog-Api-Key": "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw",
        "Authorization": f"SAPISIDHASH {sapisidhash}",
    },
    params=params,
    cookies=cookies
)
```

**Response Structure:**
```json
{
    "apiHeader": {
        "serverTimestampMillis": "1699999999999"
    },
    "apps": [
        {
            "packageName": "com.spotify.music",
            "title": "Spotify: Music and Podcasts",
            "iconUrl": "https://play-lh.googleusercontent.com/...",
            "supervisionSetting": {
                "hidden": false,
                "hiddenSetExplicitly": false,
                "usageLimit": {
                    "dailyUsageLimitMins": 30,
                    "enabled": true
                },
                "alwaysAllowedAppInfo": null,
                "googleSearchDisabled": false
            },
            "installTimeMillis": "1699000000000",
            "enforcedEnabledStatus": "enabled",
            "appSource": "googlePlay",
            "supervisionCapabilities": [
                "capabilityAlwaysAllowApp",
                "capabilityBlock",
                "capabilityUsageLimit"
            ],
            "adSupportStatus": "adsSupported",
            "deviceIds": ["device_123"],
            "iapSupportStatus": "iapSupported"
        },
        {
            "packageName": "com.youtube.android",
            "title": "YouTube",
            "iconUrl": "https://play-lh.googleusercontent.com/...",
            "supervisionSetting": {
                "hidden": true,
                "hiddenSetExplicitly": true,
                "usageLimit": null,
                "alwaysAllowedAppInfo": null
            },
            "installTimeMillis": "1699000000000",
            "enforcedEnabledStatus": "disabled",
            "appSource": "googlePlay",
            "supervisionCapabilities": [
                "capabilityAlwaysAllowApp",
                "capabilityBlock",
                "capabilityUsageLimit"
            ],
            "adSupportStatus": "adsSupported",
            "deviceIds": ["device_123"],
            "iapSupportStatus": "iapSupported"
        },
        {
            "packageName": "com.android.calculator2",
            "title": "Calculator",
            "iconUrl": "https://play-lh.googleusercontent.com/...",
            "supervisionSetting": {
                "hidden": false,
                "hiddenSetExplicitly": false,
                "usageLimit": null,
                "alwaysAllowedAppInfo": {
                    "alwaysAllowedState": "alwaysAllowedStateEnabled"
                }
            },
            "installTimeMillis": "1699000000000",
            "enforcedEnabledStatus": "enabled",
            "appSource": "googlePlay",
            "supervisionCapabilities": [
                "capabilityAlwaysAllowApp",
                "capabilityBlock",
                "capabilityUsageLimit"
            ],
            "adSupportStatus": "noAds",
            "deviceIds": ["device_123"],
            "iapSupportStatus": "noIap"
        }
    ],
    "lastActivityRefreshTimestampMillis": "1699999999999",
    "deviceInfo": [
        {
            "deviceId": "device_123",
            "displayInfo": {
                "model": "Pixel 7",
                "friendlyName": "Child's Phone",
                "lastActivityTimeMillis": "1699999999999"
            },
            "capabilityInfo": {
                "capabilities": [
                    "CAPABILITY_DEVICE_LOCK",
                    "CAPABILITY_LOCATION",
                    "CAPABILITY_APP_MANAGEMENT"
                ]
            }
        }
    ],
    "appUsageSessions": [
        {
            "usage": "1809.5s",
            "appId": {
                "androidAppPackageName": "com.spotify.music"
            },
            "deviceMudId": "device_123",
            "modeType": "USAGE_MODE_TYPE_UNLOCKED",
            "date": {
                "year": 2024,
                "month": 11,
                "day": 7
            }
        },
        {
            "usage": "3600.2s",
            "appId": {
                "androidAppPackageName": "com.instagram.android"
            },
            "deviceMudId": "device_123",
            "modeType": "USAGE_MODE_TYPE_UNLOCKED",
            "date": {
                "year": 2024,
                "month": 11,
                "day": 7
            }
        }
    ]
}
```

**Key Fields for Screen Time:**

- `appUsageSessions`: Array of app usage sessions
  - `usage`: Duration in seconds with decimal (e.g., "1809.5s" = 30 minutes 9.5 seconds)
  - `appId.androidAppPackageName`: Package name of the app
  - `date`: Date of the usage (year, month, day)
  - `modeType`: Usage mode type (typically "USAGE_MODE_TYPE_UNLOCKED")

**Calculating Total Daily Screen Time:**

```python
from datetime import datetime

def get_total_screen_time_today(app_usage_response):
    """Calculate total screen time for today in seconds."""
    today = datetime.now().date()
    total_seconds = 0

    for session in app_usage_response["appUsageSessions"]:
        session_date = session["date"]
        if (session_date["year"] == today.year and
            session_date["month"] == today.month and
            session_date["day"] == today.day):
            # Extract seconds from "1809.5s" format
            usage_seconds = float(session["usage"].replace("s", ""))
            total_seconds += usage_seconds

    # Convert to hours, minutes, seconds
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)

    return {
        "total_seconds": total_seconds,
        "formatted": f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    }
```

**App Supervision Settings:**

- `supervisionSetting.hidden`: `true` if app is blocked
- `supervisionSetting.usageLimit.dailyUsageLimitMins`: Daily time limit in minutes
- `supervisionSetting.alwaysAllowedAppInfo`: Non-null if app is always allowed

#### Alternative Response Format (Array-based)

**Note:** The `appsandusage` endpoint may also return data in an array format (appears to be Protocol Buffers serialization). Each app is represented as an array row with positional values.

**Example - Real Response Extract (anonymized):**
```json
[
  [
    "com.IndexEducation.Pronote",
    "PRONOTE",
    "https://lh3.googleusercontent.com/...",
    [],
    "1756717091222",
    null,
    0,
    1,
    null,
    null,
    1,
    ["aannnppawiuhqf4xa3v2huxcxko66oux4zpxabjfgldq"],
    1
  ],
  [
    "com.lemon.lvoverseas",
    "CapCut - Éditeur vidéo",
    "https://lh3.googleusercontent.com/...",
    [],
    "1763148569222",
    null,
    0,
    1,
    null,
    null,
    1,
    ["aannnppapwuz...xfxxba"],
    2
  ]
]
```

**Column Mapping (observed):**

| Index | Field Name (interpretation)    | Example Value                       | Description                                      |
|-------|-------------------------------|-------------------------------------|--------------------------------------------------|
| 0     | `package`                     | `"com.IndexEducation.Pronote"`      | Package name                                     |
| 1     | `label`                       | `"PRONOTE"`                         | App display name                                 |
| 2     | `iconUrl`                     | `"https://lh3.googleusercontent..."`| Icon URL                                         |
| 3     | `tags`                        | `[]`                                | Tags/badges array                                |
| 4     | `installedAtMs`               | `"1756717091222"`                   | Installation timestamp (epoch ms)                |
| 5     | `totalUsageMs`                | `null`                              | Total usage time (may be null)                   |
| 6     | `blocked`                     | `0`                                 | Block flag (0=not blocked, 1=blocked)            |
| 7     | `allowed`                     | `1`                                 | Allowed flag (0=not allowed, 1=allowed)          |
| 8     | `category`                    | `null`                              | App category (optional)                          |
| 9     | `contentClass`                | `null`                              | Content rating/age band (optional)               |
| 10    | `statusType`                  | `1` or `2`                          | Status type enum (approval/visibility)           |
| 11    | `deviceIds`                   | `["aannnppawiuh..."]`               | Array of device IDs where app is installed       |
| 12    | `state`                       | `1` or `2`                          | State enum (observed values: 1, 2)               |

**Notes:**
- Indices 10 and 12 vary between apps (values 1 or 2) - likely approval/visibility status
- `totalUsageMs` may be `null` in this listing format
- Session usage data may appear in additional columns or sub-arrays (not observed in this extract)
- `deviceIds` array shows which device(s) have the app installed

**Logical Schema (generalized):**
```json
{
  "apps": [
    {
      "package": "com.app",
      "label": "Human Name",
      "iconUrl": "https://...",
      "tags": [],
      "installedAtMs": "1756717091222",
      "totalUsageMs": null,
      "blocked": 0,
      "allowed": 1,
      "category": null,
      "contentClass": null,
      "statusType": 1,
      "deviceIds": ["..."],
      "state": 1
    }
  ]
}
```

### 3. Get Restrictions by Groups (Android Device Rules)

**Endpoint:** `GET /kidsmanagement/v1/people/{childId}/restrictions:listByGroups`

**Purpose:** List system restrictions (DISALLOW_...) per supervised device.

**Request:**
```python
child_id = "116774149781348048793"

response = httpx.get(
    f"https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1/people/{child_id}/restrictions:listByGroups",
    headers={
        "Content-Type": "application/json+protobuf",
        "X-Goog-Api-Key": "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw",
        "Authorization": f"SAPISIDHASH {sapisidhash}",
    },
    cookies=cookies
)
```

**Response Structure:**
```json
{
  "meta": { "ts": "1763148569000" },
  "groups": [
    {
      "deviceId": "aannnppapwuz...xfxxba",
      "rules": [
        {
          "code": "DISALLOW_ADD_USER,DISALLOW_REMOVE_USER",
          "title": "Ajouter/Supprimer un utilisateur",
          "state": 0,
          "ui": { "on_text": "...", "off_text": "...", "warnings": ["..."] },
          "policyKeyB64": "base64"
        },
        { "code": "DISALLOW_INSTALL_UNKNOWN_SOURCES", "state": 0 },
        { "code": "DISALLOW_DEBUGGING_FEATURES", "state": 0 },
        { "code": "DATE_TIME_EDIT", "state": 0 },
        { "code": "DEFAULT_APPS_EDIT", "state": 0 }
      ]
    }
  ]
}
```

**Example Response:**
```json
{
  "groups":[
    {
      "deviceId":"aannnppapwuz...xfxxba",
      "rules":[
        { "code":"DISALLOW_ADD_USER,DISALLOW_REMOVE_USER","state":0 },
        { "code":"DISALLOW_INSTALL_UNKNOWN_SOURCES","state":0 },
        { "code":"DISALLOW_DEBUGGING_FEATURES","state":0 },
        { "code":"DATE_TIME_EDIT","state":0 }
      ]
    },
    {
      "deviceId":"aannnppawiuh...gbldq",
      "rules":[
        { "code":"DISALLOW_ADD_USER,DISALLOW_REMOVE_USER","state":0 },
        { "code":"DISALLOW_INSTALL_UNKNOWN_SOURCES","state":0 },
        { "code":"DISALLOW_DEBUGGING_FEATURES","state":0 },
        { "code":"DATE_TIME_EDIT","state":0 },
        { "code":"DEFAULT_APPS_EDIT","state":0 }
      ]
    }
  ]
}
```

**Key Fields:**
- `deviceId`: Unique identifier for each supervised device
- `rules[].code`: One or more restriction codes (comma-separated)
- `rules[].state`: State of the restriction (0 = active, 1 = inactive)
- `rules[].policyKeyB64`: Base64-encoded policy key for updating

### 4. Get Setting Resources (Menu Hierarchy)

**Endpoint:** `GET /kidsmanagement/v1/people/settingResources`

**Purpose:** Retrieve the Family Link settings menu structure/hierarchy (Play, YouTube, Chrome, Search, Communication, App Limits, Gemini, Assistant, Location, Devices).

**Request:**
```python
response = httpx.get(
    "https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1/people/settingResources",
    headers={
        "Content-Type": "application/json",
        "X-Goog-Api-Key": "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw",
        "Authorization": f"SAPISIDHASH {sapisidhash}",
    },
    cookies=cookies
)
```

**Response Structure:**
```json
{
  "root": {
    "id":"210",
    "childrenIds":["15","19","16","17","213","246","237","18","27","212"]
  },
  "nodes":[
    { "id":"246","title":"Bloquer ou limiter des applications","path":"/member/{childId}/app_limits" },
    { "id":"27","title":"Paramètres de localisation","path":"/member/{childId}/location/settings" },
    { "id":"212","title":"Appareils connectés à votre compte","path":"/member/{childId}/devices" },
    { "id":"15","title":"Google Play" },
    { "id":"19","title":"YouTube" },
    { "id":"16","title":"Google Chrome et Web" },
    { "id":"17","title":"Recherche Google" },
    { "id":"213","title":"Contacts, appels et messages" },
    { "id":"237","title":"Gemini" },
    { "id":"18","title":"Assistant Google" }
  ]
}
```

**Key Fields:**
- `root.id`: Root node ID
- `root.childrenIds`: Array of child node IDs
- `nodes[].id`: Unique node identifier
- `nodes[].title`: Display title for the setting
- `nodes[].path`: Navigation path (optional, for clickable items)

### 5. Get Notifications (with Timezone)

**Endpoint:** `GET /kidsmanagement/v1/people/me/notificationElements`

**Purpose:** Retrieve the event stream (e.g., app installations, activity alerts).

**Request:**
```python
params = {
    "clientCapabilities": "CAPABILITY_TIMEZONE",
    "userTimeZone": "Europe/Paris"
}

response = httpx.get(
    "https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1/people/me/notificationElements",
    headers={
        "Content-Type": "application/json",
        "X-Goog-Api-Key": "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw",
        "Authorization": f"SAPISIDHASH {sapisidhash}",
    },
    params=params,
    cookies=cookies
)
```

**Response Structure:**
```json
{
  "notifications": [
    {
      "id":"ad72a921a7b2d72c",
      "timestamp":{"sec":"1763148569","nanos":431000000},
      "title":"Nouvelle application installée",
      "message":"Macéo a installé CapCut - Éditeur vidéo",
      "personId":"116774149781348048793",
      "severity":2,
      "links":["/member/116774149781348048793/app/com.lemon.lvoverseas"]
    }
  ]
}
```

**Key Fields:**
- `id`: Unique notification identifier
- `timestamp.sec`: Unix timestamp in seconds (string)
- `timestamp.nanos`: Nanoseconds component
- `title`: Notification title
- `message`: Notification message
- `personId`: Child ID associated with the notification
- `severity`: Severity level (1=info, 2=warning, etc.)
- `links`: Array of related navigation paths

### 6. Get Applied Time Limits (Daily Quotas & Active Windows)

**Endpoint:** `GET /kidsmanagement/v1/people/{childId}/appliedTimeLimits`

**Purpose:** For each device: daily quota, consumption, active downtime/schooltime windows, and bonus time.

**Request:**
```python
child_id = "116774149781348048793"

params = {
    "capabilities": "TIME_LIMIT_CLIENT_CAPABILITY_SCHOOLTIME"
}

response = httpx.get(
    f"https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1/people/{child_id}/appliedTimeLimits",
    headers={
        "Content-Type": "application/json+protobuf",
        "X-Goog-Api-Key": "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw",
        "Authorization": f"SAPISIDHASH {sapisidhash}",
    },
    params=params,
    cookies=cookies
)
```

**Response Structure:**
```json
{
  "meta":{"ts":"1763148569000"},
  "devices":[
    {
      "deviceId":"aannnppapwuz...xfxxba",
      "totalDailyAllowedMs":"7200000",
      "dailyUsedMs":"3600000",
      "downtimeWindow":{"start":"1763148000000","end":"1763176800000"},
      "schooltimeWindow":null,
      "overrides":[
        {
          "durationSec":"1800",
          "status":1,
          "policyKey":"CAEQBg",
          "uuid":"550e8400-e29b-41d4-a716-446655440000"
        }
      ]
    }
  ]
}
```

**Key Fields:**
- `deviceId`: Device identifier
- `totalDailyAllowedMs`: Total allowed time for the day in milliseconds
- `dailyUsedMs`: Time already consumed in milliseconds
- `downtimeWindow`: Current active downtime window (if any)
  - `start`: Start timestamp in epoch milliseconds
  - `end`: End timestamp in epoch milliseconds
- `schooltimeWindow`: Current active schooltime window (if any)
- `overrides[]`: Array of active time bonuses
  - `durationSec`: Bonus duration in seconds (1800 = 30min, 3600 = 1h)
  - `status`: Override status (1=active, 2=consumed)
  - `policyKey`: Policy key for the override
  - `uuid`: Unique identifier for this override

**Calculating Remaining Time:**
```python
def get_remaining_time(device):
    """Calculate remaining screen time for a device."""
    total_allowed = int(device['totalDailyAllowedMs'])
    daily_used = int(device['dailyUsedMs'])
    remaining_ms = total_allowed - daily_used

    hours = remaining_ms // 3600000
    minutes = (remaining_ms % 3600000) // 60000

    return {
        'remaining_ms': remaining_ms,
        'formatted': f"{hours:02d}:{minutes:02d}"
    }
```

### 7. Get Time Limit Rules (Weekly Downtime & Schooltime)

**Endpoint:** `GET /kidsmanagement/v1/people/{childId}/timeLimit`

**Purpose:** Retrieve the scheduled weekly rules: Downtime (bedtime/wake) + Schooltime.

**Request:**
```python
child_id = "116774149781348048793"

params = {
    "capabilities": "TIME_LIMIT_CLIENT_CAPABILITY_SCHOOLTIME",
    "timeLimitKey.type": "SUPERVISED_DEVICES"
}

response = httpx.get(
    f"https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1/people/{child_id}/timeLimit",
    headers={
        "Content-Type": "application/json+protobuf",
        "X-Goog-Api-Key": "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw",
        "Authorization": f"SAPISIDHASH {sapisidhash}",
    },
    params=params,
    cookies=cookies
)
```

**Response Structure:**
```json
{
  "downtime": [
    { "day":1, "start":[20,30], "end":[7,30], "policyId":"4870..." },
    { "day":2, "start":[20,30], "end":[7,30], "policyId":"4871..." },
    { "day":3, "start":[20,30], "end":[7,30], "policyId":"4872..." },
    { "day":4, "start":[20,30], "end":[7,30], "policyId":"4873..." },
    { "day":5, "start":[20,30], "end":[7,30], "policyId":"4874..." },
    { "day":6, "start":[23,0], "end":[10,0], "policyId":"4875..." },
    { "day":7, "start":[23,0], "end":[10,0], "policyId":"4876..." }
  ],
  "schooltime": [
    { "day":1, "start":[8,0], "end":[15,0], "policyId":"579e..." },
    { "day":2, "start":[8,0], "end":[15,0], "policyId":"579f..." },
    { "day":3, "start":[8,0], "end":[15,0], "policyId":"57a0..." },
    { "day":4, "start":[8,0], "end":[15,0], "policyId":"57a1..." },
    { "day":5, "start":[8,0], "end":[15,0], "policyId":"57a2..." },
    { "day":6, "start":[8,0], "end":[15,0], "policyId":"57a3..." },
    { "day":7, "start":[8,0], "end":[15,0], "policyId":"57a4..." }
  ],
  "revisions":[
    {
      "policyId":"4870...",
      "kind":"downtime",
      "at":{"sec":"1763213724","nanos":816339000}
    },
    {
      "policyId":"579e...",
      "kind":"schooltime",
      "at":{"sec":"1763213884","nanos":207470000}
    }
  ]
}
```

**Key Fields:**
- `day`: Day of week (ISO-8601: 1=Monday, 2=Tuesday, ..., 7=Sunday)
- `start`: [hour, minute] in 24h format (local time)
- `end`: [hour, minute] in 24h format (if end < start, spans midnight)
- `policyId`: Optional identifier to link with revisions
- `revisions[].at`: Timestamp of last policy update
  - `sec`: Unix timestamp in seconds (string)
  - `nanos`: Nanoseconds component (integer)

**Example - Real Data:**
```json
{
  "downtime":[
    { "day":1, "start":[20,30], "end":[7,30] },
    { "day":2, "start":[20,30], "end":[7,30] },
    { "day":3, "start":[20,30], "end":[7,30] },
    { "day":4, "start":[20,30], "end":[7,30] },
    { "day":5, "start":[20,30], "end":[7,30] },
    { "day":6, "start":[23,0], "end":[10,0] },
    { "day":7, "start":[23,0], "end":[10,0] }
  ],
  "schooltime":[
    { "day":1, "start":[8,0], "end":[15,0] },
    { "day":2, "start":[8,0], "end":[15,0] },
    { "day":3, "start":[8,0], "end":[15,0] },
    { "day":4, "start":[8,0], "end":[15,0] },
    { "day":5, "start":[8,0], "end":[15,0] },
    { "day":6, "start":[8,0], "end":[15,0] },
    { "day":7, "start":[8,0], "end":[15,0] }
  ]
}
```

**Note:** This endpoint returns weekly rules. For current active windows and real-time consumption, see endpoint #6 (Applied Time Limits).

### 8. Get Family Members Photos (Avatars & Location Settings)

**Endpoint:** `GET /kidsmanagement/v1/families/mine/familyMembersPhotos`

**Purpose:** Retrieve family member avatars and location settings information.

**Request:**
```python
response = httpx.get(
    "https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1/families/mine/familyMembersPhotos",
    headers={
        "Content-Type": "application/json",
        "X-Goog-Api-Key": "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw",
        "Authorization": f"SAPISIDHASH {sapisidhash}",
    },
    cookies=cookies
)
```

**Response Structure:**

**Photos Array:**
```json
{
  "photos": [
    {
      "personId":"1009057...",
      "photoUrl":"https://lh3.googleusercontent.com/a/...",
      "origin":2
    },
    {
      "personId":"116774149781348048793",
      "photoUrl":"https://lh6.googleusercontent.com/proxy/...",
      "origin":4,
      "accentColor":[0.2039,0.6588,0.3255]
    }
  ]
}
```

**Location Settings Block (may be included):**
```json
{
  "locationSettings": {
    "enabled": true,
    "infoHtml": "La localisation de l'appareil sera activée...",
    "devices":[
      {
        "deviceId":"aannnppapwuz...xfxxba",
        "blurb":"Cela permettra ... Galaxy Tab",
        "privacy":"..."
      },
      {
        "deviceId":"aannnppawiuh...gbldq",
        "blurb":"Cela permettra ... SM-S916B",
        "privacy":"..."
      }
    ]
  }
}
```

**Key Fields:**
- `photos[].personId`: Family member ID
- `photos[].photoUrl`: Avatar URL
- `photos[].origin`: Source of the photo (2=Google account, 4=custom)
- `photos[].accentColor`: RGB color array (optional)
- `locationSettings.enabled`: Whether location tracking is enabled
- `locationSettings.devices[]`: Location-enabled devices

### 9. Create Time Limit Override (Bonus Time)

**Endpoint:** `POST /kidsmanagement/v1/people/{childId}/timeLimitOverrides:batchCreate`

**Purpose:** Create a time bonus for a specific device.

**Request:**
```python
child_id = "116774149781348048793"
device_id = "aannnppapwuz...xfxxba"

payload = {
    "overrides": [
        {
            "policyKey": "CAEQBg",
            "durationSec": 1800,  # 30 minutes
            "deviceId": device_id
        }
    ]
}

response = httpx.post(
    f"https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1/people/{child_id}/timeLimitOverrides:batchCreate",
    headers={
        "Content-Type": "application/json+protobuf",
        "X-Goog-Api-Key": "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw",
        "Authorization": f"SAPISIDHASH {sapisidhash}",
        "Origin": "https://familylink.google.com",
    },
    json=payload,
    cookies=cookies
)
```

**Request Body Structure:**
```json
{
  "overrides":[
    {
      "policyKey":"CAEQBg",
      "durationSec":1800,
      "deviceId":"aannnppapwuz...xfxxba"
    }
  ]
}
```

**Effect:**
- The bonus appears in `appliedTimeLimits.overrides[]` (see endpoint #6)
- Increases `totalDailyAllowedMs` for the device
- Common durations:
  - `1800` = 30 minutes
  - `3600` = 1 hour

**Example - Grant 1 hour bonus:**
```python
def grant_bonus_time(client, child_id, device_id, minutes=30):
    """Grant bonus time to a device."""
    duration_sec = minutes * 60

    payload = {
        "overrides": [{
            "policyKey": "CAEQBg",
            "durationSec": duration_sec,
            "deviceId": device_id
        }]
    }

    response = client.post(
        f"{BASE_URL}/people/{child_id}/timeLimitOverrides:batchCreate",
        json=payload
    )

    return response.json()
```

### 10. Update App Restrictions

**Endpoint:** `POST /people/{account_id}/apps:updateRestrictions`

**Purpose:** Set time limits, block apps, or always allow apps.

**Request Format:**

The request body uses a JSON array format (appears to be Protocol Buffers over JSON):

```python
import json

account_id = "09876543210987654321"
package_name = "com.spotify.music"

# Example 1: Set time limit (30 minutes)
payload = json.dumps([
    account_id,
    [
        [
            [package_name],     # App package name
            None,                # Reserved field
            [30, 1]             # [minutes, enabled_flag]
        ]
    ]
])

# Example 2: Block app
payload = json.dumps([
    account_id,
    [
        [
            [package_name],     # App package name
            [1]                  # [block_flag]
        ]
    ]
])

# Example 3: Always allow app
payload = json.dumps([
    account_id,
    [
        [
            [package_name],     # App package name
            None,                # Reserved field
            None,                # Reserved field
            [1]                  # [always_allow_flag]
        ]
    ]
])

# Make request
response = httpx.post(
    f"https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1/people/{account_id}/apps:updateRestrictions",
    headers={
        "Content-Type": "application/json+protobuf",
        "X-Goog-Api-Key": "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw",
        "Authorization": f"SAPISIDHASH {sapisidhash}",
        "Origin": "https://familylink.google.com",
    },
    content=payload,
    cookies=cookies
)
```

**Request Examples:**

```python
# Set 30-minute daily limit for Spotify
data = [
    "09876543210987654321",
    [
        [
            ["com.spotify.music"],
            None,
            [30, 1]
        ]
    ]
]

# Block YouTube
data = [
    "09876543210987654321",
    [
        [
            ["com.youtube.android"],
            [1]
        ]
    ]
]

# Always allow Calculator
data = [
    "09876543210987654321",
    [
        [
            ["com.android.calculator2"],
            None,
            None,
            [1]
        ]
    ]
]
```

## Complete Implementation Example

Here's a complete example showing how to authenticate and fetch screen time data:

```python
import hashlib
import time
from datetime import datetime
import httpx
import browser_cookie3

class GoogleFamilyLinkClient:
    """Client for Google Family Link API."""

    BASE_URL = "https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1"
    ORIGIN = "https://familylink.google.com"
    API_KEY = "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw"

    def __init__(self, browser="firefox"):
        """Initialize client with browser cookies."""
        # Extract cookies from browser
        self._cookies = getattr(browser_cookie3, browser)()

        # Find SAPISID cookie
        sapisid = None
        for cookie in self._cookies:
            if cookie.name == "SAPISID" and cookie.domain == ".google.com":
                sapisid = cookie.value
                break

        if not sapisid:
            raise ValueError("Could not find SAPISID cookie in browser")

        # Generate authorization header
        sapisidhash = self._generate_sapisidhash(sapisid, self.ORIGIN)

        # Setup headers
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
            "Origin": self.ORIGIN,
            "Content-Type": "application/json+protobuf",
            "X-Goog-Api-Key": self.API_KEY,
            "Authorization": f"SAPISIDHASH {sapisidhash}",
        }

        # Create HTTP client
        self._session = httpx.Client(
            headers=self._headers,
            cookies=self._cookies
        )

    def _generate_sapisidhash(self, sapisid: str, origin: str) -> str:
        """Generate SAPISIDHASH token."""
        timestamp = int(time.time() * 1000)
        to_hash = f"{timestamp} {sapisid} {origin}"
        sha1_hash = hashlib.sha1(to_hash.encode("utf-8")).hexdigest()
        return f"{timestamp}_{sha1_hash}"

    def get_family_members(self):
        """Get list of family members."""
        response = self._session.get(
            f"{self.BASE_URL}/families/mine/members",
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()

    def get_supervised_child_id(self):
        """Get the first supervised child's user ID."""
        members = self.get_family_members()
        for member in members["members"]:
            supervision_info = member.get("memberSupervisionInfo")
            if supervision_info and supervision_info.get("isSupervisedMember"):
                return member["userId"]
        raise ValueError("No supervised child found")

    def get_apps_and_usage(self, account_id):
        """Get apps and usage data for an account."""
        params = {
            "capabilities": [
                "CAPABILITY_APP_USAGE_SESSION",
                "CAPABILITY_SUPERVISION_CAPABILITIES",
            ],
        }
        response = self._session.get(
            f"{self.BASE_URL}/people/{account_id}/appsandusage",
            headers={"Content-Type": "application/json"},
            params=params
        )
        response.raise_for_status()
        return response.json()

    def get_daily_screen_time(self, account_id, target_date=None):
        """Get total screen time for a specific date.

        Args:
            account_id: User ID of the supervised child
            target_date: datetime.date object (defaults to today)

        Returns:
            dict with total_seconds and formatted time
        """
        if target_date is None:
            target_date = datetime.now().date()

        data = self.get_apps_and_usage(account_id)
        total_seconds = 0
        app_breakdown = {}

        for session in data.get("appUsageSessions", []):
            session_date = session["date"]
            if (session_date["year"] == target_date.year and
                session_date["month"] == target_date.month and
                session_date["day"] == target_date.day):

                # Extract seconds
                usage_seconds = float(session["usage"].replace("s", ""))
                total_seconds += usage_seconds

                # Track per-app usage
                package_name = session["appId"]["androidAppPackageName"]
                app_breakdown[package_name] = app_breakdown.get(package_name, 0) + usage_seconds

        # Convert to hours, minutes, seconds
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)

        return {
            "total_seconds": total_seconds,
            "formatted": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
            "hours": hours,
            "minutes": minutes,
            "seconds": seconds,
            "app_breakdown": app_breakdown,
            "date": target_date
        }

    def get_devices(self, account_id):
        """Get list of devices for an account."""
        data = self.get_apps_and_usage(account_id)
        return data.get("deviceInfo", [])

    def close(self):
        """Close HTTP session."""
        self._session.close()

# Usage example
if __name__ == "__main__":
    # Initialize client
    client = GoogleFamilyLinkClient(browser="firefox")

    # Get supervised child
    child_id = client.get_supervised_child_id()
    print(f"Child ID: {child_id}")

    # Get today's screen time
    screen_time = client.get_daily_screen_time(child_id)
    print(f"\nTotal screen time today: {screen_time['formatted']}")
    print(f"Total seconds: {screen_time['total_seconds']}")

    # Show per-app breakdown
    print("\nPer-app usage:")
    for package, seconds in sorted(
        screen_time['app_breakdown'].items(),
        key=lambda x: x[1],
        reverse=True
    ):
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        print(f"  {package}: {hours:02d}:{mins:02d}:{secs:02d}")

    # Get devices
    devices = client.get_devices(child_id)
    print("\nDevices:")
    for device in devices:
        print(f"  - {device['displayInfo']['friendlyName']} ({device['displayInfo']['model']})")

    # Close client
    client.close()
```

## Data Models (Pydantic)

For proper type safety, here are Pydantic models for the API responses:

```python
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

class AppSupervisionCapability(str, Enum):
    ALWAYS_ALLOW = "capabilityAlwaysAllowApp"
    BLOCK = "capabilityBlock"
    USAGE_LIMIT = "capabilityUsageLimit"

class AlwaysAllowedState(str, Enum):
    ENABLED = "alwaysAllowedStateEnabled"

class AlwaysAllowedAppInfo(BaseModel):
    always_allowed_state: AlwaysAllowedState = Field(alias="alwaysAllowedState")

class UsageLimit(BaseModel):
    daily_usage_limit_mins: int = Field(alias="dailyUsageLimitMins")
    enabled: bool

class SupervisionSetting(BaseModel):
    hidden: bool = False
    hidden_set_explicitly: bool = Field(False, alias="hiddenSetExplicitly")
    usage_limit: UsageLimit | None = Field(None, alias="usageLimit")
    always_allowed_app_info: AlwaysAllowedAppInfo | None = Field(None, alias="alwaysAllowedAppInfo")

class App(BaseModel):
    package_name: str = Field(alias="packageName")
    title: str
    icon_url: str = Field(alias="iconUrl")
    supervision_setting: SupervisionSetting = Field(alias="supervisionSetting")
    install_time_millis: str = Field(alias="installTimeMillis")
    supervision_capabilities: list[AppSupervisionCapability] = Field(alias="supervisionCapabilities")
    device_ids: list[str] | None = Field(default_factory=list, alias="deviceIds")

class AppId(BaseModel):
    android_app_package_name: str = Field(alias="androidAppPackageName")

class UsageDate(BaseModel):
    year: int
    month: int
    day: int

class AppUsageSession(BaseModel):
    usage: str  # Duration in seconds (e.g., "1809.5s")
    app_id: AppId = Field(alias="appId")
    device_mud_id: str = Field(alias="deviceMudId")
    mode_type: str = Field(alias="modeType")
    date: UsageDate

class DeviceDisplayInfo(BaseModel):
    model: str
    friendly_name: str = Field(alias="friendlyName")
    last_activity_time_millis: str = Field(alias="lastActivityTimeMillis")

class DeviceCapabilityInfo(BaseModel):
    capabilities: list[str]

class DeviceInfo(BaseModel):
    device_id: str = Field(alias="deviceId")
    display_info: DeviceDisplayInfo = Field(alias="displayInfo")
    capability_info: DeviceCapabilityInfo = Field(alias="capabilityInfo")

class ApiHeader(BaseModel):
    server_timestamp_millis: str = Field(alias="serverTimestampMillis")

class AppUsageResponse(BaseModel):
    api_header: ApiHeader = Field(alias="apiHeader")
    apps: list[App]
    last_activity_refresh_timestamp_millis: str = Field(alias="lastActivityRefreshTimestampMillis")
    device_info: list[DeviceInfo] = Field(alias="deviceInfo")
    app_usage_sessions: list[AppUsageSession] = Field(alias="appUsageSessions")

class MemberSupervisionInfo(BaseModel):
    is_supervised_member: bool = Field(alias="isSupervisedMember")
    is_guardian_linked_account: bool = Field(alias="isGuardianLinkedAccount")

class Profile(BaseModel):
    display_name: str = Field(alias="displayName")
    profile_image_url: str = Field(alias="profileImageUrl")
    email: str
    family_name: str = Field(alias="familyName")
    given_name: str = Field(alias="givenName")

class Member(BaseModel):
    user_id: str = Field(alias="userId")
    role: str
    profile: Profile
    state: str
    member_supervision_info: MemberSupervisionInfo | None = Field(None, alias="memberSupervisionInfo")

class MembersResponse(BaseModel):
    members: list[Member]
    api_header: ApiHeader = Field(alias="apiHeader")
    my_user_id: str = Field(alias="myUserId")
```

## Integration with Home Assistant

For the HAFamilyLink integration, here's how to implement the API client:

```python
# /home/user/HAFamilyLink/custom_components/familylink/client/api.py

import hashlib
import json
import time
from datetime import datetime
from typing import Any

import aiohttp

class FamilyLinkClient:
    """Client for Google Family Link API."""

    BASE_URL = "https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1"
    ORIGIN = "https://familylink.google.com"
    API_KEY = "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw"

    def __init__(self, cookies: list[dict[str, Any]]):
        """Initialize with cookies from addon."""
        self._cookies = cookies
        self._session: aiohttp.ClientSession | None = None
        self._account_id: str | None = None

    async def async_get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None:
            # Extract SAPISID cookie
            sapisid = None
            cookie_jar = {}

            for cookie in self._cookies:
                cookie_jar[cookie["name"]] = cookie["value"]
                if cookie["name"] == "SAPISID" and ".google.com" in cookie.get("domain", ""):
                    sapisid = cookie["value"]

            if not sapisid:
                raise ValueError("SAPISID cookie not found")

            # Generate authorization
            sapisidhash = self._generate_sapisidhash(sapisid, self.ORIGIN)

            # Create session
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Origin": self.ORIGIN,
                "Content-Type": "application/json+protobuf",
                "X-Goog-Api-Key": self.API_KEY,
                "Authorization": f"SAPISIDHASH {sapisidhash}",
            }

            self._session = aiohttp.ClientSession(
                headers=headers,
                cookies=cookie_jar,
                timeout=aiohttp.ClientTimeout(total=30)
            )

        return self._session

    def _generate_sapisidhash(self, sapisid: str, origin: str) -> str:
        """Generate SAPISIDHASH token."""
        timestamp = int(time.time() * 1000)
        to_hash = f"{timestamp} {sapisid} {origin}"
        sha1_hash = hashlib.sha1(to_hash.encode("utf-8")).hexdigest()
        return f"{timestamp}_{sha1_hash}"

    async def async_get_members(self) -> dict[str, Any]:
        """Get family members."""
        session = await self.async_get_session()
        async with session.get(
            f"{self.BASE_URL}/families/mine/members",
            headers={"Content-Type": "application/json"}
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def async_get_supervised_child_id(self) -> str:
        """Get first supervised child's ID."""
        if self._account_id:
            return self._account_id

        members = await self.async_get_members()
        for member in members["members"]:
            supervision_info = member.get("memberSupervisionInfo")
            if supervision_info and supervision_info.get("isSupervisedMember"):
                self._account_id = member["userId"]
                return self._account_id

        raise ValueError("No supervised child found")

    async def async_get_apps_and_usage(self, account_id: str | None = None) -> dict[str, Any]:
        """Get apps and usage data."""
        if not account_id:
            account_id = await self.async_get_supervised_child_id()

        session = await self.async_get_session()
        params = {
            "capabilities": [
                "CAPABILITY_APP_USAGE_SESSION",
                "CAPABILITY_SUPERVISION_CAPABILITIES",
            ],
        }

        async with session.get(
            f"{self.BASE_URL}/people/{account_id}/appsandusage",
            headers={"Content-Type": "application/json"},
            params=params
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def async_get_daily_screen_time(
        self,
        account_id: str | None = None,
        target_date: datetime | None = None
    ) -> dict[str, Any]:
        """Get daily screen time in seconds."""
        if target_date is None:
            target_date = datetime.now()

        data = await self.async_get_apps_and_usage(account_id)
        total_seconds = 0

        for session in data.get("appUsageSessions", []):
            session_date = session["date"]
            if (session_date["year"] == target_date.year and
                session_date["month"] == target_date.month and
                session_date["day"] == target_date.day):

                usage_seconds = float(session["usage"].replace("s", ""))
                total_seconds += usage_seconds

        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)

        return {
            "total_seconds": total_seconds,
            "formatted": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
            "hours": hours,
            "minutes": minutes,
        }

    async def async_cleanup(self):
        """Close session."""
        if self._session:
            await self._session.close()
            self._session = None
```

## Important Notes

1. **No Official API**: This is reverse-engineered from the web interface and may break at any time
2. **Rate Limiting**: Google may rate limit requests; implement appropriate delays
3. **Cookie Expiration**: SAPISID cookies typically expire after 24 hours to several weeks
4. **Terms of Service**: Using this API may violate Google's Terms of Service
5. **Security**: Never expose cookies or API keys publicly
6. **Error Handling**: Always implement proper error handling for network requests

## References

- Original Python package: https://github.com/tducret/familylink
- HAFamilyLink repository: https://github.com/Vortitron/HAFamilyLink
- Google Family Link web interface: https://families.google.com

## Endpoint Quick Reference

### Read-Only Endpoints (GET)

1. **Get Family Members**
   - `GET /families/mine/members`
   - Returns: List of family members with supervision info

2. **Get Apps and Usage**
   - `GET /people/{childId}/appsandusage`
   - Returns: Apps, usage sessions, devices
   - Note: May return JSON object or array format

3. **Get Restrictions by Groups**
   - `GET /people/{childId}/restrictions:listByGroups`
   - Returns: Android system restrictions per device

4. **Get Setting Resources**
   - `GET /people/settingResources`
   - Returns: Menu hierarchy/navigation structure

5. **Get Notifications**
   - `GET /people/me/notificationElements`
   - Returns: Event stream (installations, alerts)
   - Params: `clientCapabilities=CAPABILITY_TIMEZONE`, `userTimeZone=Europe/Paris`

6. **Get Applied Time Limits**
   - `GET /people/{childId}/appliedTimeLimits`
   - Returns: Current quotas, consumption, active windows, bonuses

7. **Get Time Limit Rules**
   - `GET /people/{childId}/timeLimit`
   - Returns: Weekly downtime/schooltime schedule

8. **Get Family Members Photos**
   - `GET /families/mine/familyMembersPhotos`
   - Returns: Avatars and location settings

### Write Endpoints (POST)

9. **Create Time Limit Override**
   - `POST /people/{childId}/timeLimitOverrides:batchCreate`
   - Purpose: Grant bonus time to device

10. **Update App Restrictions**
    - `POST /people/{childId}/apps:updateRestrictions`
    - Purpose: Set limits, block, or allow apps

## Common Headers Reference

All API requests require these headers:

```python
headers = {
    "Content-Type": "application/json+protobuf",  # or "application/json" for some endpoints
    "X-Goog-Api-Key": "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw",
    "X-Goog-AuthUser": "0",
    "Authorization": f"SAPISIDHASH {sapisidhash}",
    "Origin": "https://familylink.google.com",
}
```

## Useful Mappings & Constants

### Device Identifiers (Example)
- Tablet: `aannnppapwuz...xfxxba`
- Phone: `aannnppawiuh...gbldq`

### Time Limit Policy Keys
- **Downtime (by day)**: `CAEQAQ` (Mon), `CAEQAg` (Tue), `CAEQAw` (Wed), `CAEQBa` (Thu), `CAEQBg` (Fri), `CAEQBw` (Sat), `CAMQ...` (Sun)
- **Schooltime**: `CAMQ...` prefix (varies by day)
- **Override/Bonus**: `CAEQBg` (common policy key for bonuses)

### Time Measurements
- **Applied Time Limits**: Milliseconds (`totalDailyAllowedMs`, `dailyUsedMs`)
- **Time Overrides**: Seconds (`durationSec`: 1800 = 30min, 3600 = 1h)
- **Usage Sessions**: Seconds with decimals (`"1809.5s"`)

### Day of Week (ISO-8601)
- 1 = Monday
- 2 = Tuesday
- 3 = Wednesday
- 4 = Thursday
- 5 = Friday
- 6 = Saturday
- 7 = Sunday

### Common Capabilities
- `CAPABILITY_APP_USAGE_SESSION` - Enable usage session data
- `CAPABILITY_SUPERVISION_CAPABILITIES` - Enable supervision settings
- `TIME_LIMIT_CLIENT_CAPABILITY_SCHOOLTIME` - Enable schooltime data
- `CAPABILITY_TIMEZONE` - Enable timezone support in notifications

## Summary

The Google Family Link API uses:
- **Base URL**: `https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1`
- **Authentication**: SAPISID cookie + SAPISIDHASH header
- **API Key**: `AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw`
- **Total Endpoints Documented**: 10 (8 GET, 2 POST)

### Key Capabilities:
- Monitor screen time and app usage
- Manage app restrictions (block, limit, always allow)
- Control device settings and restrictions
- Access time limit schedules (downtime/schooltime)
- Grant bonus time overrides
- Receive notifications about child activity
- Access location and device information

Screen time data is available in the `appUsageSessions` array with usage duration in seconds format (e.g., "1809.5s").
