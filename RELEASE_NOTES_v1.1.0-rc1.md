# v1.1.0-rc1 — Pre-release

**Integration v1.1.0-rc1 · Add-on v1.4.0**

Major update including security hardening, stability improvements, new features, and numerous bug fixes. This pre-release consolidates all changes since v1.0.1, including the previously unreleased fixes from v1.0.2-rc3 and v1.0.2-rc4.

---

## 🔐 Security

- **Credential redaction in logs** — SAPISID values, SAPISIDHASH, API keys, and request headers are no longer exposed in logs (#privacy)
- **Playwright service hardening** — CORS restricted to local HA addresses, optional API key auth on sensitive endpoints (`/api/cookies`, `/api/auth/start`), generic HTTP error messages
- **File permissions** — Encryption key and cookie files set to `0o600`, directories to `0o700`
- **VNC password** — Configurable via add-on config, removed from log output
- **Input validation** — `_validate_id()` prevents path injection via `account_id` in API URLs

## ✨ New Features

- **Configurable language and timezone** for auth browser — No longer hardcoded to `fr-FR`, configurable via add-on options (e.g. `en-US`, `fr-FR`, `de-DE`) (#75)
- **UUID-format device identifiers** — Support for devices returning UUID identifiers instead of CAEQ/CAMQ prefixes, fixing silent failures on daily limits and bedtime/schooltime windows (#74)

## 🐛 Bug Fixes

### Critical Fixes
- **child_id in sensors** — Added `child_id`/`child_name` to `extra_state_attributes` in 9 sensor classes so services (`block_app`, `unblock_app`, etc.) can target specific children (#73)
- **Day-of-week offset** — Fixed `DAYS_OF_WEEK` mapping from 0-indexed to 1-indexed matching Python's `isoweekday()` convention, which was causing incorrect day names in schedule attributes
- **Device locking race condition** — Added 1-second delay after bonus cancellation before lock attempt to let the Google API process the cancellation (#62)
- **Silent HTTP failures** — `fetch_applied_time_limits` now raises `NetworkError` instead of returning empty dict, preventing stale/wrong entity data

### Stability Fixes
- **Browser crashes in VMs** — GPU-disable flags, Skia/rendering flags, D-Bus disable, page load strategy change from `networkidle` to `load` (#68)
- **RPi4/ARM64 compatibility** — `--ozone-platform=x11` flag, D-Bus system bus auto-start, `dbus` package added to Docker images (#68, #76)
- **Segfault fix** — Removed `--single-process` and `--no-zygote` flags causing Signal 11 in HA add-on (#68)
- **Xvfb optimization** — Reduced color depth from 24-bit to 16-bit, added `shm_size: 2gb` to docker-compose
- **Session locking** — `asyncio.Lock` on `_get_session()` preventing race conditions on concurrent session close/recreate
- **Concurrent auth limit** — Max 1 auth session at a time (memory protection on RPi)
- **Browser session leak** — Replaced nulled-out session dict with minimal metadata, preventing unbounded memory growth

### Data & Entity Fixes
- **SAPISIDHASH staleness** — Auto-regeneration after 30 minutes to prevent stale auth tokens
- **Switch entity creation** — Removed early return that permanently blocked entity creation when first data fetch had no `children_data`
- **Epoch date display** — Check for None/falsy timestamps before converting, avoiding misleading `1970-01-01` dates
- **Birthday formatting** — Guard against None `year`/`month`/`day` values
- **Screen time parsing** — `rstrip("s")` instead of `replace("s","")`, with try/except for malformed values
- **Battery values** — try/except for non-numeric battery values from API
- **Timezone-aware datetime** — Replaced `datetime.now()` with `dt_util.now()` for correct day-of-week and screen time in non-UTC zones

### Robustness
- **Null client guards** — Added client None checks to all 6 switch toggle methods and all 13 service handlers, preventing `AttributeError` after auth failure
- **Optimistic state rollback** — Switch entities now rollback pending state on API failure
- **SessionExpiredError propagation** — Pass-through in broad except blocks so coordinator auth refresh triggers correctly
- **Config flow** — Set `unique_id` to prevent duplicate config entries
- **Bedtime validation** — Validate `start_time`/`end_time` format (HH:MM)
- **Button unique_id** — Added `child_id` for consistency with sensors
- **Coordinator** — Use `.get()` for child `userId` to prevent `KeyError`

## 🧹 Cleanup

- Removed unused exception classes (`DeviceNotFoundError`, `ConfigurationError`, `BrowserError`, `CookieError`, `ValidationError`)
- Removed unused service constants (`SERVICE_FORCE_UNLOCK`, `SERVICE_EMERGENCY_UNLOCK`)
- Removed dead `SessionManager` class
- Cleaned `utils/__init__.py` imports from non-existent modules
- Renamed `TimeoutError` to `FamilyLinkTimeoutError` to avoid shadowing Python built-in
- Cookie caches cleared in `async_cleanup()` to prevent stale data on reload

---

## Issues Referenced

| Issue | Description | Status |
|-------|-------------|--------|
| #62 | Device locking fails while unlocking works | Fixed |
| #68 | Browser crashes in VMs (Aw, Snap! / SEGV) | Fixed |
| #73 | Services affect all children instead of targeted child | Fixed |
| #74 | Silent failures with UUID-format device identifiers | Fixed |
| #75 | Browser language hardcoded to fr-FR | Fixed |
| #76 | RPi4/ARM64 blank screen / D-Bus issues | Fixed |

## Upgrade Notes

- **Integration**: Update via HACS or manually replace `custom_components/familylink/`
- **Add-on**: Update the FamilyLink Playwright add-on to v1.4.0
- If using VNC, set a password in the add-on configuration (no longer defaults to open access)

## Testing Checklist

- [ ] Fresh install from this branch
- [ ] Upgrade from v1.0.1
- [ ] Multi-child setup — verify sensors target correct child
- [ ] Lock/unlock device with active bonus
- [ ] Lock/unlock device without bonus
- [ ] Bedtime / School time toggle on/off
- [ ] Screen time sensors show correct values
- [ ] Auth flow via VNC in VM environment
- [ ] Auth flow on RPi4/ARM64
- [ ] Check logs for credential leaks (should be redacted)
- [ ] Reload integration — verify no stale data
