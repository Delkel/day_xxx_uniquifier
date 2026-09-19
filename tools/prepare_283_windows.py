from pathlib import Path
import re

p = Path("win/app.py")
s = p.read_text(encoding="utf-8")

s = re.sub(r'APP_VERSION\s*=\s*["\'][^"\']+["\']', 'APP_VERSION = "2.8.3"', s, count=1)

required = ["Добавить видео", "Добавить фото", "Обработка файлов", "Обработать", "Обновления", "Доступно обновление"]
missing = [x for x in required if x not in s]
if missing:
    raise SystemExit("Required Russian UI strings missing: " + ", ".join(missing))

mojibake_markers = ["Р”Р", "РЎР", "Р°Р", "РµР", "СЂР", "СЃС"]
score = sum(s.count(x) for x in mojibake_markers)
if score > 5:
    raise SystemExit(f"Refusing mojibake Windows UI: score={score}")

p.write_text(s, encoding="utf-8", newline="\n")
check = p.read_text(encoding="utf-8")
assert 'APP_VERSION = "2.8.3"' in check
for item in required:
    assert item in check
print("Windows UTF-8 UI validation OK; APP_VERSION 2.8.3")
