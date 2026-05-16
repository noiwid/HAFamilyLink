#!/bin/bash
# Display a welcome banner on the Xvfb display so noVNC users see clear
# instructions instead of a black screen before the auth flow is started.

set -e

# Require DISPLAY to be set (we expect Xvfb to be running on :99)
DISPLAY="${DISPLAY:-:99}"
export DISPLAY

# Make sure xterm is installed; if not, exit silently (non-critical)
if ! command -v xterm >/dev/null 2>&1; then
    echo "xterm not installed, skipping welcome banner"
    exit 0
fi

# Wait briefly for X server / window manager to settle
sleep 1

# Geometry: roughly centered on a 1280x1024 Xvfb display
xterm \
    -geometry 84x22+220+250 \
    -fa "Liberation Mono" -fs 13 \
    -bg "#0f172a" -fg "#22d3ee" -bd "#22d3ee" \
    -title "Family Link Auth — Welcome" \
    -e bash -c '
cat <<MSG
============================================================
   Google Family Link — Authentication Service
============================================================

   noVNC is connected. The Google login window will appear
   here AFTER you start the authentication flow.

   STEP 1 — Open the Web UI in a separate browser tab:
            http://<your-host>:8099

   STEP 2 — Click  "Start Authentication"  on that page.

   STEP 3 — Come back to THIS noVNC tab to complete the
            Google login that appears.

============================================================

Tip: this welcome message will stay visible until Chromium
opens. It is normal — nothing is broken.

MSG
# Keep the window open until the container stops
while true; do sleep 3600; done
' >/dev/null 2>&1 &

echo "✓ Welcome banner launched on display ${DISPLAY}"
