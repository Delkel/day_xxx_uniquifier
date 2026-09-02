from pathlib import Path
import re

root = Path('mac260')
apps = list(root.rglob('app.py'))
if not apps:
    raise SystemExit('app.py not found')
p = apps[0]
s = p.read_text(encoding='utf-8')
s = re.sub(r'APP_VERSION\s*=\s*["\'][^"\']+["\']', 'APP_VERSION = "2.6.0"', s, count=1)

# Keep updater bound to the actual footer button.
s = s.replace('self.update_btn.setEnabled(False)', 'self.compact_update_btn.setEnabled(False)')
s = s.replace('self.update_btn.setEnabled(True)', 'self.compact_update_btn.setEnabled(True)')
marker = 'self.compact_update_btn.clicked.connect(self.check_updates)'
if marker in s and 'self.update_btn = self.compact_update_btn' not in s:
    s = s.replace(marker, marker + '\n        self.update_btn = self.compact_update_btn', 1)

# Give the logo its own space so the first action can never overlap it.
s = s.replace("logo.setFixedHeight(170)", "logo.setFixedHeight(190)")
s = s.replace("side.addWidget(logo)\n", "side.addWidget(logo)\n        side.addSpacing(20)\n", 1)

# Consistent sidebar action geometry.
start = s.find('    def side_button(self,text,fn):')
if start >= 0:
    end = s.find('\n    def ', start + 5)
    if end > start:
        block = """    def side_button(self,text,fn):
        b=QPushButton(text,objectName='sideButton')
        b.setFixedHeight(44)
        b.setMinimumWidth(0)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(fn)
        return b
"""
        s = s[:start] + block + s[end:]

# Footer/update row uses the same button geometry.
s = s.replace('self.compact_update_btn.setFixedHeight(30)', 'self.compact_update_btn.setFixedHeight(44)')
s = s.replace('self.compact_update_btn.setObjectName("compactUpdateButton")', 'self.compact_update_btn.setObjectName("sideButton")')

# Normalize status/footer backgrounds to the sidebar instead of separate black rectangles.
style = """
        QPushButton#sideButton {
            background: transparent;
            border: 1px solid transparent;
            border-radius: 9px;
            padding: 0 14px;
            min-height: 44px;
            max-height: 44px;
            text-align: left;
            font-size: 14px;
            font-weight: 600;
        }
        QPushButton#sideButton:hover { background:#17130e; border-color:#3f2f1a; }
        QPushButton#sideButton:pressed { background:#21190f; }
        QFrame#brandFooter { background: transparent; border: 0; }
        QLabel#footerBrand, QLabel#footerText, QLabel#ready { background: transparent; border: 0; }
"""
q1 = s.find('"""', s.find('def apply_style'))
q2 = s.find('"""', q1 + 3) if q1 >= 0 else -1
if q2 >= 0:
    s = s[:q2] + style + s[q2:]

p.write_text(s, encoding='utf-8')
print(p)
