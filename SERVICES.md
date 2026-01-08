# Google Family Link Services

This integration provides several services to control supervised devices: app management, time limits, and bedtime schedules.

## 📱 App Management Services

### 1. `familylink.block_device_for_school`
Blocks all apps except essential ones to simulate a device lock during school hours.

**Essential apps (always allowed by default):**
- Phone (`com.android.dialer`)
- Contacts (`com.android.contacts`)
- SMS/Messages (`com.android.mms`, `com.google.android.apps.messaging`)
- Settings (`com.android.settings`)
- Clock/Alarm (`com.android.deskclock`)
- Google Maps (`com.google.android.apps.maps`)
- Emergency (`com.android.emergency`)
- Essential system services

**Parameters:**
- `whitelist` (optional): List of additional apps to allow

**Example:**
```yaml
service: familylink.block_device_for_school
data:
  whitelist:
    - com.example.educationalapp
    - com.microsoft.teams
```

---

### 2. `familylink.unblock_all_apps`
Unblocks all apps to end school mode and restore normal device usage.

**Parameters:** None

**Example:**
```yaml
service: familylink.unblock_all_apps
```

---

### 3. `familylink.block_app`
Blocks a specific app by its package name. If no child is specified, blocks the app for **ALL supervised children**.

**Parameters:**
- `package_name` (required): Android package name (e.g., `com.youtube.android`)
- `entity_id` (optional): Select any Family Link entity for this child
- `child_id` (optional): Child's user ID - if not specified, applies to ALL children

**Examples:**
```yaml
# Block YouTube for ALL children
service: familylink.block_app
data:
  package_name: com.youtube.android

# Block YouTube for a specific child
service: familylink.block_app
data:
  package_name: com.youtube.android
  entity_id: sensor.emma_screen_time
```

---

### 4. `familylink.unblock_app`
Unblocks a specific app by its package name. If no child is specified, unblocks the app for **ALL supervised children**.

**Parameters:**
- `package_name` (required): Android package name
- `entity_id` (optional): Select any Family Link entity for this child
- `child_id` (optional): Child's user ID - if not specified, applies to ALL children

**Examples:**
```yaml
# Unblock YouTube for ALL children
service: familylink.unblock_app
data:
  package_name: com.youtube.android

# Unblock YouTube for a specific child
service: familylink.unblock_app
data:
  package_name: com.youtube.android
  child_id: "123456789012345678901"
```

---

### 5. `familylink.set_app_daily_limit`
Sets a daily time limit for a specific app. If no child is specified, applies to **ALL supervised children**.

**Parameters:**
- `package_name` (required): Android package name (e.g., `com.zhiliaoapp.musically` for TikTok)
- `minutes` (required): Daily limit in minutes (0-1440). Use `0` to remove the limit.
- `entity_id` (optional): Select any Family Link entity for this child
- `child_id` (optional): Child's user ID - if not specified, applies to ALL children

**Examples:**
```yaml
# Set TikTok to 60 minutes/day for ALL children
service: familylink.set_app_daily_limit
data:
  package_name: com.zhiliaoapp.musically
  minutes: 60

# Set TikTok to 45 minutes for a specific child
service: familylink.set_app_daily_limit
data:
  package_name: com.zhiliaoapp.musically
  minutes: 45
  entity_id: sensor.emma_screen_time

# Remove TikTok time limit (restore unlimited)
service: familylink.set_app_daily_limit
data:
  package_name: com.zhiliaoapp.musically
  minutes: 0
```

---

## ⏰ Time Management Services

### 6. `familylink.set_daily_limit`
Sets the daily screen time limit for a device.

**Parameters:**
- `daily_minutes` (required): Number of minutes allowed per day (0-1440)
  - Use `0` to disable the device for the day without fully locking it (unrestricted apps remain accessible)
- `entity_id` (optional): Select a Family Link device switch (recommended)
- `device_id` (optional): Device ID (if entity_id not provided)
- `child_id` (optional): Child's user ID

**Examples:**
```yaml
# Set 2 hours of screen time via entity
service: familylink.set_daily_limit
data:
  entity_id: switch.pixel_tablet
  daily_minutes: 120

# Disable device for the day (unrestricted apps remain accessible)
service: familylink.set_daily_limit
data:
  entity_id: switch.pixel_tablet
  daily_minutes: 0
```

---

### 7. `familylink.set_bedtime`
Sets bedtime start and end times for a specific day.

**Parameters:**
- `start_time` (required): Bedtime start time (e.g., "20:45")
- `end_time` (required): Bedtime end time (e.g., "07:30")
- `day` (optional): Day of the week (1=Monday, 7=Sunday). Defaults to today.
- `child_id` (optional): Child's user ID (optional if only one child)

**Examples:**
```yaml
# Set bedtime for today
service: familylink.set_bedtime
data:
  start_time: "20:45"
  end_time: "07:30"

# Set bedtime for Saturday (day 6)
service: familylink.set_bedtime
data:
  start_time: "22:00"
  end_time: "09:00"
  day: 6
```

---

### 8. `familylink.enable_bedtime` / `familylink.disable_bedtime`
Enables or disables bedtime restrictions for a child.

**Parameters:**
- `entity_id` (optional): Select any Family Link entity for this child
- `child_id` (optional): Child's user ID

**Example:**
```yaml
service: familylink.enable_bedtime
data:
  child_id: "123456789012345678901"
```

---

### 9. `familylink.add_time_bonus`
Adds bonus time to a device.

**Parameters:**
- `bonus_minutes` (required): Bonus minutes (1-1440)
- `entity_id` (optional): Select a Family Link device switch
- `device_id` (optional): Device ID
- `child_id` (optional): Child's user ID

**Example:**
```yaml
service: familylink.add_time_bonus
data:
  entity_id: switch.pixel_tablet
  bonus_minutes: 30
```

---

## 🤖 Automation Examples

### Automation: Block phone during school hours

```yaml
automation:
  - alias: "Block phone during class"
    description: "Blocks all apps except essentials from 8am to 3:30pm on weekdays"
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: time
        weekday:
          - mon
          - tue
          - wed
          - thu
          - fri
    action:
      - service: familylink.block_device_for_school
        data:
          whitelist:
            - com.microsoft.teams  # Allow Teams for school
      - service: notify.mobile_app_parent_phone
        data:
          title: "School Mode Activated"
          message: "Phone is locked until 3:30pm"

  - alias: "Unblock after school"
    description: "Unblocks phone after school"
    trigger:
      - platform: time
        at: "15:30:00"
    condition:
      - condition: time
        weekday:
          - mon
          - tue
          - wed
          - thu
          - fri
    action:
      - service: familylink.unblock_all_apps
      - service: notify.mobile_app_parent_phone
        data:
          title: "School Mode Ended"
          message: "Phone is unlocked"
```

### Automation: Block YouTube after 9pm

```yaml
automation:
  - alias: "Block YouTube at night"
    trigger:
      - platform: time
        at: "21:00:00"
    action:
      - service: familylink.block_app
        data:
          package_name: com.youtube.android
      - service: familylink.block_app
        data:
          package_name: com.google.android.youtube

  - alias: "Unblock YouTube in the morning"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: familylink.unblock_app
        data:
          package_name: com.youtube.android
      - service: familylink.unblock_app
        data:
          package_name: com.google.android.youtube
```

### Automation: Block based on screen time

```yaml
automation:
  - alias: "Block if too much screen time"
    trigger:
      - platform: state
        entity_id: sensor.family_link_daily_screen_time
    condition:
      - condition: numeric_state
        entity_id: sensor.family_link_daily_screen_time
        above: 120  # 2 hours in minutes
    action:
      - service: familylink.block_device_for_school
      - service: notify.mobile_app_parent_phone
        data:
          title: "Screen Time Limit Reached"
          message: >
            Screen time: {{ states('sensor.family_link_screen_time_formatted') }}
            Device has been locked.
```

### Automation: Extend bedtime on weekends

```yaml
automation:
  - alias: "Weekend bedtime - Friday"
    trigger:
      - platform: time
        at: "18:00:00"
    condition:
      - condition: time
        weekday: fri
    action:
      - service: familylink.set_bedtime
        data:
          start_time: "22:00"
          end_time: "09:00"
          day: 5  # Friday
      - service: familylink.set_bedtime
        data:
          start_time: "22:00"
          end_time: "09:00"
          day: 6  # Saturday
```

---

## 🔍 How to Find Package Names

1. **Via `sensor.family_link_installed_apps`:**
   - Check sensor attributes in Developer Tools → States
   - Search for the app in the list

2. **Via `sensor.family_link_blocked_apps`:**
   - Blocked apps show their name and package

3. **Via `sensor.family_link_top_app_X`:**
   - Check the `package_name` attribute of each top app

4. **Via Google Play Store:**
   - App URL: `https://play.google.com/store/apps/details?id=com.example.app`
   - The `id=` is the package name

---

## ⚠️ Important Notes

1. **Delay between blocks:** Services add a 0.1s delay between each app to avoid Google rate limiting

2. **Automatic refresh:** After each service call, data is automatically refreshed

3. **System apps:** Some system apps cannot be blocked to avoid breaking the device

4. **Persistence:** Blocks persist until you manually unblock or via automation

5. **Multiple children:** App control services (`block_app`, `unblock_app`, `set_app_daily_limit`) apply to **ALL children** by default. Specify `entity_id` or `child_id` to target a specific child.

---

## 📊 Complementary Sensors

Use these sensors to create smart automations:

- `sensor.family_link_daily_screen_time` - Total screen time in minutes
- `sensor.family_link_screen_time_formatted` - Formatted time (HH:MM:SS)
- `sensor.family_link_installed_apps` - Number of installed apps
- `sensor.family_link_blocked_apps` - Number and list of blocked apps
- `sensor.family_link_apps_with_time_limits` - Apps with time limits
- `sensor.family_link_top_app_1` to `#10` - Top 10 most used apps
- `sensor.family_link_child_info` - Info about the supervised child

---

## 🆘 Troubleshooting

### Service doesn't block apps
- Verify authentication is active (add-on running and cookies valid)
- Check logs in Home Assistant: Configuration → Logs
- Search for `familylink` in logs

### Apps unblock by themselves
- Check for conflicting automations
- Verify parents haven't unblocked from the Family Link app

### Device is completely blocked
- Call the `familylink.unblock_all_apps` service
- If that doesn't work, unlock from the Family Link mobile app

---

## 🔄 Recommended Workflow

1. **Test manually first** from Developer Tools → Services
2. **Check logs** to confirm success
3. **Create automations** once tests pass
4. **Test automations** by temporarily changing times
5. **Enable in production** with actual school hours

---

## 📝 Complete Example: Full Screen Time Management

```yaml
# School schedule
automation:
  - id: school_mode_on
    alias: "Enable school mode"
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: time
        weekday: [mon, tue, wed, thu, fri]
    action:
      - service: familylink.block_device_for_school
      - service: notify.parent
        data:
          message: "📚 School mode activated"

  - id: school_mode_off
    alias: "Disable school mode"
    trigger:
      - platform: time
        at: "15:30:00"
    condition:
      - condition: time
        weekday: [mon, tue, wed, thu, fri]
    action:
      - service: familylink.unblock_all_apps
      - service: notify.parent
        data:
          message: "✅ School mode disabled"

# Bedtime
  - id: bedtime_block_apps
    alias: "Block apps at bedtime"
    trigger:
      - platform: time
        at: "21:00:00"
    action:
      - service: familylink.block_device_for_school
      - service: notify.parent
        data:
          message: "😴 Bedtime - Phone locked"

  - id: morning_unblock
    alias: "Unblock in the morning"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: familylink.unblock_all_apps
      - service: notify.parent
        data:
          message: "☀️ Good morning - Phone unlocked"

# Screen time limit
  - id: screen_time_limit
    alias: "Block if limit reached"
    trigger:
      - platform: numeric_state
        entity_id: sensor.family_link_daily_screen_time
        above: 180  # 3 hours
    action:
      - service: familylink.block_device_for_school
      - service: notify.parent
        data:
          title: "⏱️ Time limit reached"
          message: >
            Screen time today: {{ states('sensor.family_link_screen_time_formatted') }}
            Phone locked until tomorrow.
```
