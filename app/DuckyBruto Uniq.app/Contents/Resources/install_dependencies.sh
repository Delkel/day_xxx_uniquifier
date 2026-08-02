#!/bin/bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export PIP_USE_DEPRECATED=legacy-certs
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

brew install python@3.12 ffmpeg

BREW_PREFIX="$(brew --prefix)"
PYTHON_312="$BREW_PREFIX/opt/python@3.12/bin/python3.12"
PYTHON_313="$BREW_PREFIX/opt/python@3.13/bin/python3.13"
PYTHON_SYSTEM="$(command -v python3 || true)"

mkdir -p "$SUPPORT_DIR"
rm -rf "$VENV_DIR"

create_venv() {
  rm -rf "$VENV_DIR"
  if "$PYTHON" -m venv "$VENV_DIR"; then
    return 0
  fi

  echo "venv через ensurepip не создался, пробую запасной режим без ensurepip..."
  rm -rf "$VENV_DIR"
  "$PYTHON" -m venv --without-pip "$VENV_DIR"
  GET_PIP="$SUPPORT_DIR/get-pip.py"
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$GET_PIP"
  ARCH="$(uname -m)"
  if [ "$ARCH" = "arm64" ]; then
    export _PYTHON_HOST_PLATFORM="macosx-13.0-arm64"
  else
    export _PYTHON_HOST_PLATFORM="macosx-13.0-x86_64"
  fi
  export MACOSX_DEPLOYMENT_TARGET="13.0"
  "$VENV_DIR/bin/python" "$GET_PIP" --use-deprecated=legacy-certs
  rm -f "$GET_PIP"
}

setup_with_python() {
  PYTHON="$1"
  if [ ! -x "$PYTHON" ]; then
    return 1
  fi

  echo "Пробую Python: $PYTHON"
  "$PYTHON" --version

  create_venv

  "$VENV_DIR/bin/python" -m pip --version
  "$VENV_DIR/bin/python" -m pip install --use-deprecated=legacy-certs --upgrade pip setuptools wheel
  "$VENV_DIR/bin/python" -m pip install --use-deprecated=legacy-certs PySide6
}

SUCCESS=0
for CANDIDATE in "$PYTHON_312" "$PYTHON_313" "$PYTHON_SYSTEM"; do
  if setup_with_python "$CANDIDATE"; then
    SUCCESS=1
    break
  fi
  echo "Этот Python не подошел: $CANDIDATE"
done

if [ "$SUCCESS" -ne 1 ]; then
  echo "Не удалось создать рабочее Python-окружение. Попробуй выполнить: brew reinstall python@3.12"
  exit 1
fi

"$VENV_DIR/bin/python" - <<'PY'
from PySide6.QtWidgets import QApplication
print("PySide6 установлен корректно")
PY

osascript -e 'display dialog "Зависимости DuckyBruto Uniq установлены. Теперь приложение будет использовать отдельное окружение Python." buttons {"OK"} default button "OK" with icon note'
