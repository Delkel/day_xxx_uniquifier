#!/bin/sh
set -eu

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

echo "== DuckyBruto Uniq dependency installer =="
echo

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew не найден. Ставлю Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x /usr/local/bin/brew ]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi

echo
echo "Проверяю Python 3..."
if ! command -v python3 >/dev/null 2>&1; then
  brew install python
else
  python3 --version
fi

echo
echo "Проверяю графическую библиотеку Python..."
if ! python3 - <<'PY' >/dev/null 2>&1
import tkinter
PY
then
  TK_FORMULA="$(python3 - <<'PY'
import sys
print(f"python-tk@{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
  echo "tkinter не найден. Ставлю $TK_FORMULA..."
  brew install "$TK_FORMULA" || brew install python-tk
else
  python3 - <<'PY'
import tkinter
print("tkinter OK")
PY
fi

echo
echo "Проверяю FFmpeg..."
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  brew install ffmpeg
else
  ffmpeg -version | head -n 1
fi

echo
echo "Готово. Можно запускать DuckyBruto Uniq."
if [ "${DAYXXX_NO_PAUSE:-0}" != "1" ]; then
  read -r -p "Нажми Enter, чтобы закрыть окно..." _
fi
