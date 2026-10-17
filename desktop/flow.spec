# Run on the target OS: python build-desktop.py
from pathlib import Path
import sys
root = Path(SPECPATH).parent
analysis = Analysis([str(root/'desktop_app.py')], pathex=[str(root)],
    binaries=[], datas=[(str(root/'web'), 'web'), (str(root/'desktop/startup.html'), 'desktop'), (str(root/'desktop/flow.png'), 'desktop')],
    hiddenimports=['webdav_sync', 'traffic_web', 'background_service'],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'tkinter'],
    hookspath=[], hooksconfig={}, runtime_hooks=[], noarchive=False)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name='Flow',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root/'desktop/flow.ico') if sys.platform=='win32' else None)
collection = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name='Flow')
if sys.platform == 'darwin':
    app = BUNDLE(collection, name='Flow.app', icon=str(root/'desktop/flow.icns'), bundle_identifier='local.flow.traffic-manager',
                 info_plist={'CFBundleDisplayName':'Flow Traffic Manager',
                             'NSHighResolutionCapable':True, 'LSMinimumSystemVersion':'11.0'})
