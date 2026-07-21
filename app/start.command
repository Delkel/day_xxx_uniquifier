#!/bin/sh
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/@day_xxx Uniquifier.app"
xattr -dr com.apple.quarantine "$DIR" 2>/dev/null || true
chmod +x "$APP/Contents/MacOS/day_xxx_uniquifier" 2>/dev/null || true
chmod +x "$APP/Contents/Resources/install_dependencies.sh" 2>/dev/null || true
open "$APP" || "$APP/Contents/MacOS/day_xxx_uniquifier"
