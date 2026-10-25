#!/bin/sh
# Retakes the design-port screenshots from the debug demo hooks (CallDemo / ScreensDemo, no server needed).
# Needs a booted simulator with the Debug app installed (any `xcodebuild test -scheme Kin` run installs it).
# Usage: ios/screens/take.sh   (from the repo root)
set -eu
out=$(cd "$(dirname "$0")" && pwd)
xcrun simctl status_bar booted override --time 9:41 --batteryState charged --batteryLevel 100 --cellularBars 4
shot() {  # name state [appearance]
  xcrun simctl ui booted appearance "${3:-light}"
  xcrun simctl terminate booted dev.kin.app 2>/dev/null || true
  xcrun simctl launch booted dev.kin.app -demoCallScreen -demoState "$2" >/dev/null
  sleep 3
  xcrun simctl io booted screenshot "$out/$1.png" >/dev/null
}
shot call-demo whoBridge
shot call-who who
shot call-who-bridge whoBridge
shot call-storyline storyline
shot call-meaning meaning
shot call-paused paused
shot call-explain explain
shot app-people people
shot app-person-world world
shot app-messages messages
shot app-people-dark people dark
xcrun simctl ui booted appearance light
xcrun simctl terminate booted dev.kin.app 2>/dev/null || true
