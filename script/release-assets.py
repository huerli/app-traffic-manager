"""Validate versions and stage only distributable Tauri installers for CI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tomllib

ROOT = Path(__file__).resolve().parent.parent
TARGETS = {
    'x86_64-pc-windows-msvc': ('.exe', '.msi'),
    'x86_64-unknown-linux-gnu': ('.AppImage', '.deb'),
    'x86_64-apple-darwin': ('.dmg',),
    'aarch64-apple-darwin': ('.dmg',),
}


def version():
    source = (ROOT / 'script/runtime_paths.py').read_text(encoding='utf-8')
    value = re.search(r"^VERSION = '([^']+)'$", source, re.MULTILINE).group(1)
    versions = [json.loads((ROOT / path).read_text())['version']
                for path in ('package.json', 'src-tauri/tauri.conf.json')]
    versions.append(tomllib.loads((ROOT / 'src-tauri/Cargo.toml').read_text())['package']['version'])
    if any(other != value for other in versions):
        raise ValueError(f'Application versions differ: {value}, {versions}')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?', value):
        raise ValueError(f'Invalid application version: {value}')
    ref = os.environ.get('GITHUB_REF', '')
    if ref.startswith('refs/tags/') and ref != f'refs/tags/v{value}':
        raise ValueError(f'Tag {ref} does not match version v{value}')
    return value


def asset_name(value, target, suffix):
    return f'Flow-{value}-{target}{suffix}'


def collect(bundle, output, target):
    value = version()
    sources = []
    for suffix in TARGETS[target]:
        # Select only installers in their format directory, never .app contents.
        folder = {'.exe': 'nsis', '.msi': 'msi', '.deb': 'deb',
                  '.AppImage': 'appimage', '.dmg': 'dmg'}[suffix]
        matches = list((bundle / folder).glob(f'*{suffix}'))
        if len(matches) != 1 or matches[0].stat().st_size == 0:
            raise ValueError(f'Expected exactly one nonempty {suffix} installer in {bundle / folder}')
        sources.append((matches[0], asset_name(value, target, suffix)))
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError(f'Staging directory must be empty: {output}')
    for source, name in sources:
        destination = output / name
        shutil.copy2(source, destination)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        (output / (name + '.sha256')).write_text(f'{digest}  {name}\n', encoding='utf-8')


def verify(directory):
    value = version()
    expected = {asset_name(value, target, suffix)
                for target, suffixes in TARGETS.items() for suffix in suffixes}
    expected |= {name + '.sha256' for name in tuple(expected)}
    actual = {path.name for path in directory.iterdir()}
    if actual != expected or any(not path.is_file() for path in directory.iterdir()):
        raise ValueError(f'Invalid release assets: missing={expected - actual}, unexpected={actual - expected}')
    for name in sorted(expected):
        if name.endswith('.sha256'):
            continue
        path = directory / name
        if path.stat().st_size == 0:
            raise ValueError(f'Empty installer: {name}')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if (directory / (name + '.sha256')).read_text().strip() != f'{digest}  {name}':
            raise ValueError(f'Checksum mismatch: {name}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('version')
    stage = commands.add_parser('collect')
    stage.add_argument('--bundle', type=Path, required=True)
    stage.add_argument('--output', type=Path, required=True)
    stage.add_argument('--target', choices=TARGETS, required=True)
    check = commands.add_parser('verify')
    check.add_argument('directory', type=Path)
    args = parser.parse_args()
    if args.command == 'version':
        print(version())
    elif args.command == 'collect':
        collect(args.bundle, args.output, args.target)
    else:
        verify(args.directory)
