#!/bin/sh
set -eu

DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
PACKAGE="$ROOT/day_xxx_uniquifier_macos_app.zip"
TARBALL="$ROOT/day_xxx_uniquifier_macos_app.tar.gz"

cd "$DIR"
chmod +x "@day_xxx Uniquifier.app/Contents/MacOS/day_xxx_uniquifier"
chmod +x "@day_xxx Uniquifier.app/Contents/Resources/install_dependencies.sh"
chmod +x "Install @day_xxx Uniquifier.command"
chmod +x "start.command"

rm -f "$PACKAGE"
rm -f "$TARBALL"
if command -v zip >/dev/null 2>&1; then
  zip -X -r "$PACKAGE" \
    "@day_xxx Uniquifier.app" \
    "Install @day_xxx Uniquifier.command" \
    "start.command" \
    "Если macOS пишет повреждено.txt" \
    "update-manifest.example.json" \
    "settings.json" \
    "README.md" \
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
    Path("update-manifest.example.json"),
    Path("settings.json"),
    Path("README.md"),
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
  "update-manifest.example.json" \
  "settings.json" \
  "README.md"

echo "$PACKAGE"
echo "$TARBALL"
