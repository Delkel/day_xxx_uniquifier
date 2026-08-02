#!/bin/bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
SUPPORT_DIR="$HOME/Library/Application Support/DuckyBruto Uniq"
VENV_DIR="$SUPPORT_DIR/venv"

if ! command -v brew >/dev/null 2>&1; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
fi

brew install python@3.13 ffmpeg

BREW_PREFIX="$(brew --prefix)"
PYTHON="$BREW_PREFIX/opt/python@3.13/bin/python3.13"
if [ ! -x "$PYTHON" ]; then
  echo "Не найден Python 3.13: $PYTHON"
  exit 1
fi

mkdir -p "$SUPPORT_DIR"
rm -rf "$VENV_DIR"
"$PYTHON" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/python" -m pip install PySide6

"$VENV_DIR/bin/python" - <<'PY'
from PySide6.QtWidgets import QApplication
print("PySide6 установлен корректно")
PY

osascript -e 'display dialog "Зависимости DuckyBruto Uniq установлены. Теперь приложение будет использовать отдельное окружение Python." buttons {"OK"} default button "OK" with icon note'
