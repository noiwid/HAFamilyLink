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

### 3. Update App Restrictions

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

## Summary

The Google Family Link API uses:
- **Base URL**: `https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1`
- **Authentication**: SAPISID cookie + SAPISIDHASH header
- **API Key**: `AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw`
- **Key Endpoints**:
  - `GET /families/mine/members` - Get family members
  - `GET /people/{id}/appsandusage` - Get apps, devices, and screen time
  - `POST /people/{id}/apps:updateRestrictions` - Update app restrictions

Screen time data is available in the `appUsageSessions` array with usage duration in seconds format (e.g., "1809.5s").
