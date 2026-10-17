#!/usr/bin/env python3
"""Build a self-contained Flow app on the target operating system."""
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                '--distpath', str(root/'dist'), '--workpath', str(root/'build'),
                str(root/'desktop/flow.spec')], cwd=root, check=True)
if sys.platform.startswith('linux'):
    launcher = root/'dist/Flow/install-app.sh'
    shutil.copy2(root/'desktop/install-app.sh', launcher)
    launcher.chmod(0o755)
print('Desktop application:', root/'dist'/('Flow.app' if sys.platform=='darwin' else 'Flow'))
