#!/usr/bin/env bash
set -euo pipefail
[[ "$(uname -s)" == Darwin ]] || { echo 'This installer requires macOS.' >&2; exit 1; }
src_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON_BIN:-python3}"
"$python_bin" -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
app_dir="$(PYTHONPATH="$src_dir" "$python_bin" -c 'from runtime_paths import Layout; print(Layout().data)')"
agent="$HOME/Library/LaunchAgents/local.flow.traffic-manager.plist"
domain="gui/$(id -u)"
launchctl bootout "$domain" "$agent" 2>/dev/null || true
mkdir -p "$app_dir/web" "$HOME/Library/LaunchAgents"
chmod 700 "$app_dir"
cp "$src_dir/bypass.py" "$src_dir/traffic_web.py" "$src_dir/webdav_sync.py" "$src_dir/runtime_paths.py" "$src_dir/open-manager.py" "$src_dir/desktop_app.py" "$src_dir/background_service.py" "$app_dir/"
cp "$src_dir/web/index.html" "$app_dir/web/index.html"
mkdir -p "$app_dir/desktop"
cp "$src_dir/desktop/startup.html" "$src_dir/desktop/flow.png" "$src_dir/desktop/flow.icns" "$app_dir/desktop/"
"$python_bin" -m venv "$app_dir/venv"
if ! "$app_dir/venv/bin/python" -c 'import yaml' 2>/dev/null; then
  "$app_dir/venv/bin/python" -m pip install 'PyYAML>=6.0.2,<7'
fi
"$app_dir/venv/bin/python" -m pip install 'pywebview==6.2.1'
"$app_dir/venv/bin/python" "$app_dir/bypass.py" init --data-dir "$app_dir" "$@"
"$app_dir/venv/bin/python" "$app_dir/bypass.py" once --data-dir "$app_dir"
"$app_dir/venv/bin/python" - "$app_dir" "$agent" <<'PY'
import json, pathlib, plistlib, sys, shlex
app, agent = map(pathlib.Path, sys.argv[1:])
settings=json.loads((app/'settings.json').read_text());url=f"http://127.0.0.1:{settings.get('web_port',17891)}/"
bundle=pathlib.Path.home()/'Applications/Flow Traffic Manager.app'
macos=bundle/'Contents/MacOS';macos.mkdir(parents=True,exist_ok=True)
launcher=macos/'Flow'
launcher.write_text('#!/bin/sh\nexec '+shlex.quote(str(app/'venv/bin/python'))+' '+shlex.quote(str(app/'open-manager.py'))+'\n')
launcher.chmod(0o755)
resources=bundle/'Contents/Resources';resources.mkdir(exist_ok=True)
(resources/'flow.icns').write_bytes((app/'desktop/flow.icns').read_bytes())
(bundle/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleName':'Flow Traffic Manager','CFBundleDisplayName':'Flow Traffic Manager','CFBundleIdentifier':'local.flow.traffic-manager','CFBundleExecutable':'Flow','CFBundleIconFile':'flow.icns','CFBundlePackageType':'APPL','CFBundleVersion':'2.1.0','NSHighResolutionCapable':True}))
(app/'Flow Traffic Manager.webloc').unlink(missing_ok=True)
print('Dashboard:', url)
PY
"$app_dir/venv/bin/python" "$app_dir/desktop_app.py" --install-service --data-dir "$app_dir"
if "$app_dir/venv/bin/python" -c 'import json,sys; from pathlib import Path; sys.exit(0 if json.loads((Path(sys.argv[1])/"background-service.json").read_text())["enabled"] else 1)' "$app_dir"; then
  launchctl bootstrap "$domain" "$agent"
fi
printf 'Installed. Open: %s/Applications/Flow Traffic Manager.app\n' "$HOME"
