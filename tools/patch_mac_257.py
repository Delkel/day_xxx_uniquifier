from pathlib import Path
import re

root = Path('mac257')
apps = list(root.rglob('app.py'))
if not apps:
    raise SystemExit('app.py not found')
p = apps[0]
s = p.read_text(encoding='utf-8')
s = re.sub(r'APP_VERSION\s*=\s*["\'][^"\']+["\']', 'APP_VERSION = "2.5.7"', s, count=1)

# Fix the moved update button: updater code still referenced self.update_btn,
# while the visible footer button is self.compact_update_btn.
s = s.replace('self.update_btn.setEnabled(False)', 'self.compact_update_btn.setEnabled(False)')
s = s.replace('self.update_btn.setEnabled(True)', 'self.compact_update_btn.setEnabled(True)')

marker = 'self.compact_update_btn.clicked.connect(self.check_updates)'
if marker in s:
    if 'self.update_btn = self.compact_update_btn' not in s:
        s = s.replace(marker, marker + '\n        self.update_btn = self.compact_update_btn', 1)
else:
    anchor = 'side.addWidget(self.compact_update_btn)'
    if anchor not in s:
        raise SystemExit('compact update button anchor not found')
    s = s.replace(anchor, 'self.compact_update_btn.clicked.connect(self.check_updates)\n        self.update_btn = self.compact_update_btn\n        ' + anchor, 1)

# Keep all sidebar rows visually aligned.
replacements = {
    '＋  Добавить видео': 'Добавить видео',
    '＋  Добавить фото': 'Добавить фото',
    '↻  Обновить очередь': 'Обновить очередь',
    '⌂  Открыть папку исходников': 'Открыть папку исходников',
    '⇩  Открыть папку результатов': 'Открыть папку результатов',
    '⌫  Удалить готовые фото': 'Удалить готовые фото',
    '⌫  Удалить готовые видео': 'Удалить готовые видео',
    '↗  Перейти в команду': 'Перейти в команду',
    '↻ Обновить': 'Обновить',
}
for old, new in replacements.items():
    s = s.replace(old, new)

s = s.replace('self.compact_update_btn.setObjectName("compactUpdateButton")', 'self.compact_update_btn.setObjectName("sideButton")')
s = s.replace('self.compact_update_btn.setFixedHeight(30)', 'self.compact_update_btn.setFixedHeight(44)')

p.write_text(s, encoding='utf-8')
print(p)
