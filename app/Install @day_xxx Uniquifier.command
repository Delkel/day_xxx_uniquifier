#!/bin/sh
set -eu

DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="@day_xxx Uniquifier.app"
APP_SRC="$DIR/$APP_NAME"
APP_DST="$HOME/Applications/$APP_NAME"
DEPS="$APP_SRC/Contents/Resources/install_dependencies.sh"
SOURCE_SETTINGS="$DIR/settings.json"
WORK_ROOT="$HOME/Movies/day_xxx_uniquifier"
WORK_SETTINGS="$WORK_ROOT/settings.json"

echo "== @day_xxx Uniquifier installer =="
echo

if [ ! -d "$APP_SRC" ]; then
  echo "Не нашла $APP_NAME рядом с установщиком."
  read -r -p "Нажми Enter, чтобы закрыть окно..." _
  exit 1
fi

echo "Ставлю зависимости..."
sh "$DEPS"

echo
echo "Копирую приложение в ~/Applications..."
mkdir -p "$HOME/Applications"
if [ -d "$APP_DST" ]; then
  rm -rf "$APP_DST"
fi
cp -R "$APP_SRC" "$APP_DST"
chmod +x "$APP_DST/Contents/MacOS/day_xxx_uniquifier"
chmod +x "$APP_DST/Contents/Resources/install_dependencies.sh"
xattr -dr com.apple.quarantine "$APP_DST" 2>/dev/null || true

echo
echo "Готовлю настройки обновлений..."
mkdir -p "$WORK_ROOT"
python3 - "$SOURCE_SETTINGS" "$WORK_SETTINGS" <<'PY'
import json
import sys
from pathlib import Path

source_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])

source = {}
target = {}
if source_path.exists():
    try:
        source = json.loads(source_path.read_text(encoding="utf-8"))
    except Exception:
        source = {}
if target_path.exists():
    try:
        target = json.loads(target_path.read_text(encoding="utf-8"))
    except Exception:
        target = {}

if source.get("updateManifestUrl") and not target.get("updateManifestUrl"):
    target["updateManifestUrl"] = source["updateManifestUrl"]

if not target_path.exists() or target:
    target_path.write_text(json.dumps(target or source, ensure_ascii=False, indent=2), encoding="utf-8")
PY

echo
echo "Готово. Открываю приложение."
open "$APP_DST"
