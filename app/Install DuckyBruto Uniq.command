#!/bin/sh
set -eu

DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="DuckyBruto Uniq.app"
OLD_APP_NAME="@day_xxx Uniquifier.app"
APP_SRC="$DIR/$APP_NAME"
APP_DST="$HOME/Applications/$APP_NAME"
OLD_APP_DST="$HOME/Applications/$OLD_APP_NAME"
DEPS="$APP_SRC/Contents/Resources/install_dependencies.sh"

echo "== DuckyBruto Uniq installer =="
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
if [ -d "$OLD_APP_DST" ]; then
  rm -rf "$OLD_APP_DST"
fi
if [ -d "$APP_DST" ]; then
  rm -rf "$APP_DST"
fi
cp -R "$APP_SRC" "$APP_DST"
chmod +x "$APP_DST/Contents/MacOS/day_xxx_uniquifier"
chmod +x "$APP_DST/Contents/Resources/install_dependencies.sh"
xattr -dr com.apple.quarantine "$APP_DST" 2>/dev/null || true

echo
echo "Готово. Открываю приложение."
open "$APP_DST"
