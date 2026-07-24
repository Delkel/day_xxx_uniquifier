#!/bin/sh
set -eu

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$REPO_DIR/.." && pwd)"
APP_DIR="$REPO_DIR/app"
RELEASE_DIR="$REPO_DIR/release"
PACKAGE="$RELEASE_DIR/day_xxx_uniquifier_macos_app.zip"
TARBALL="$RELEASE_DIR/day_xxx_uniquifier_macos_app.tar.gz"
WORKSPACE_PACKAGE="$WORKSPACE_DIR/day_xxx_uniquifier_macos_app.zip"
WORKSPACE_TARBALL="$WORKSPACE_DIR/day_xxx_uniquifier_macos_app.tar.gz"

mkdir -p "$RELEASE_DIR"
cd "$APP_DIR"
chmod +x "@day_xxx Uniquifier.app/Contents/MacOS/day_xxx_uniquifier"
chmod +x "@day_xxx Uniquifier.app/Contents/Resources/install_dependencies.sh"
chmod +x "Install @day_xxx Uniquifier.command"
chmod +x "start.command"

rm -f "$PACKAGE"
rm -f "$TARBALL"
rm -f "$WORKSPACE_PACKAGE"
rm -f "$WORKSPACE_TARBALL"
if command -v zip >/dev/null 2>&1; then
  zip -X -r "$PACKAGE" \
    "@day_xxx Uniquifier.app" \
    "Install @day_xxx Uniquifier.command" \
    "start.command" \
    "Если macOS пишет повреждено.txt" \
    "settings.json" \
    -x "*.DS_Store" "*__pycache__*"
else
  python3 - "$PACKAGE" <<'PY'
import os
import sys
import zipfile
from pathlib import Path

package = Path(sys.argv[1])
items = [
    Path("@day_xxx Uniquifier.app"),
    Path("Install @day_xxx Uniquifier.command"),
    Path("start.command"),
    Path("Если macOS пишет повреждено.txt"),
    Path("settings.json"),
]

with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for item in items:
        if item.is_dir():
            for path in item.rglob("*"):
                if path.name == ".DS_Store" or path.is_dir():
                    continue
                archive.write(path, path.as_posix())
        elif item.exists():
            archive.write(item, item.as_posix())
PY
fi

tar --exclude=".DS_Store" --exclude="__pycache__" -czf "$TARBALL" \
  "@day_xxx Uniquifier.app" \
  "Install @day_xxx Uniquifier.command" \
  "start.command" \
  "Если macOS пишет повреждено.txt" \
  "settings.json"

cp "$PACKAGE" "$WORKSPACE_PACKAGE"
cp "$TARBALL" "$WORKSPACE_TARBALL"

echo "$PACKAGE"
echo "$TARBALL"
echo "$WORKSPACE_PACKAGE"
echo "$WORKSPACE_TARBALL"
