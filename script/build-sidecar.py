#!/usr/bin/env python3
"""Build the Python backend sidecar expected by Tauri v2."""
from pathlib import Path
import os, shutil, subprocess, sys
scripts=Path(__file__).resolve().parent
root=scripts.parent
triple=os.environ.get('TAURI_TARGET_TRIPLE') or os.environ.get('RUST_TARGET')
if not triple:
    import platform
    triple={'linux':'x86_64-unknown-linux-gnu','win32':'x86_64-pc-windows-msvc','darwin':'x86_64-apple-darwin'}.get(sys.platform)
    if sys.platform=='darwin' and platform.machine()=='arm64': triple='aarch64-apple-darwin'
if not triple: raise SystemExit('TAURI_TARGET_TRIPLE is required')
sep=';' if os.name=='nt' else ':'
out=root/'src-tauri/binaries';out.mkdir(parents=True,exist_ok=True)
name='flow-backend-'+triple
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--name',name,'--paths',str(scripts),'--add-data',f'{root}/web{sep}web','--hidden-import','traffic_web','--hidden-import','webdav_sync','--hidden-import','background_service',str(scripts/'tauri_sidecar.py')],cwd=root,check=True)
ext='.exe' if os.name=='nt' else ''
shutil.copy2(root/'dist'/f'{name}{ext}',out/f'flow-backend-{triple}{ext}')
print(out/f'flow-backend-{triple}{ext}')
