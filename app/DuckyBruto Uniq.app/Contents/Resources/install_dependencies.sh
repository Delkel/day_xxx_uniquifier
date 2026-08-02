#!/bin/bash
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
if ! command -v brew >/dev/null 2>&1; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
fi
brew install python ffmpeg
python3 -m pip install --user --upgrade PySide6
osascript -e 'display dialog "Зависимости DuckyBruto Uniq 2.0 установлены. Теперь запустите приложение." buttons {"OK"} default button "OK" with icon note'
