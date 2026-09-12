from pathlib import Path
import re

p = Path('win/app.py')
s = p.read_text(encoding='utf-8-sig')
s = re.sub(r'APP_VERSION\s*=\s*["\'][^"\']+["\']', 'APP_VERSION = "2.8.2"', s, count=1)

# Detect classic UTF-8 decoded as cp1252/latin1 mojibake before packaging.
bad = ('Ð', 'Ñ', 'Рђ', 'Р‘', 'Р’', 'Р“', 'Р”', 'Р•', 'Р–', 'Р—', 'Р?', 'СЂ', 'СЃ', 'С‚')
score = sum(s.count(x) for x in bad)
if score > 12:
    raise SystemExit(f'Refusing to package mojibake UI: score={score}')
required = ['Добавить видео', 'Настройки', 'Обработка']
missing = [x for x in required if x not in s]
if missing:
    raise SystemExit('Required Russian UI strings missing: ' + ', '.join(missing))

# Always write canonical UTF-8 without BOM. Never round-trip source through PowerShell.
p.write_text(s, encoding='utf-8', newline='\n')
print('UTF-8 UI validation OK; version 2.8.2')
