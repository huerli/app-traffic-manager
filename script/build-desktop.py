#!/usr/bin/env python3
"""Build native Flow installers with a matching Python sidecar and Rust target."""
import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', required=True, choices=['linux', 'windows', 'macos'])
    parser.add_argument('--check', action='store_true', help='Check prerequisites without building')
    args = parser.parse_args()
    current = {'linux': 'linux', 'win32': 'windows', 'darwin': 'macos'}.get(sys.platform)
    if current != args.platform:
        parser.error(f'Run this script on {args.platform}; current platform: {current}')
    if sys.version_info < (3, 10):
        parser.error('Python 3.10 or later is required')
    tools = {name: shutil.which(name) for name in ('node', 'npm', 'cargo', 'rustc')}
    missing = [name for name, path in tools.items() if not path]
    if missing:
        parser.error('Install required tools first: ' + ', '.join(missing))
    architecture = platform.machine().lower()
    architecture = {'amd64': 'x86_64', 'arm64': 'aarch64'}.get(architecture, architecture)
    suffix = {'linux': 'unknown-linux-gnu', 'windows': 'pc-windows-msvc', 'macos': 'apple-darwin'}[current]
    target = f'{architecture}-{suffix}'
    host_info = subprocess.check_output([tools['rustc'], '-vV'], text=True)
    host = next(line.split(': ', 1)[1] for line in host_info.splitlines() if line.startswith('host: '))
    if target != host:
        parser.error(f'Python architecture requires {target}, but Rust host is {host}. Use matching native tools.')
    if current == 'macos':
        subprocess.run(['xcode-select', '-p'], check=True)
    elif current == 'linux':
        subprocess.run(['pkg-config', '--exists', 'webkit2gtk-4.1', 'gtk+-3.0'], check=True)
        if not shutil.which('patchelf'):
            parser.error('Install patchelf first')
    print(f'Building Flow for {target}', flush=True)
    if args.check:
        print('Prerequisite checks passed. See README for platform SDK requirements.')
        return
    env = os.environ.copy()
    env['TAURI_TARGET_TRIPLE'] = target
    env['PYTHONUTF8'] = '1'
    venv = ROOT / ('.build-venv-win' if current == 'windows' else '.build-venv')
    python = venv / ('Scripts/python.exe' if current == 'windows' else 'bin/python')

    def run(command):
        subprocess.run([str(item) for item in command], cwd=ROOT, env=env, check=True)

    if not python.exists():
        run([sys.executable, '-m', 'venv', venv])
    run([python, '-m', 'pip', 'install', '-r', 'requirements.txt', 'pyinstaller==6.22.3'])
    run([tools['npm'], 'install', '--no-package-lock'])
    run([python, 'script/build-sidecar.py'])
    bundles = {'linux': 'deb,rpm,appimage', 'windows': 'nsis,msi', 'macos': 'app,dmg'}[current]
    run([tools['npm'], 'run', 'tauri:build', '--', '--target', target, '--bundles', bundles])
    print(f'Installers: {ROOT / "src-tauri/target" / target / "release/bundle"}')


if __name__ == '__main__':
    try:
        main()
    except (subprocess.CalledProcessError, OSError) as error:
        print(f'Build failed: {error}', file=sys.stderr)
        sys.exit(1)
