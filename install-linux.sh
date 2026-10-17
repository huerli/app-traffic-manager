#!/usr/bin/env bash
set -euo pipefail
src_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ "$(uname -s)" == Linux ]] || { echo 'Use install-macos.sh on macOS.' >&2; exit 1; }
python3 -c 'import gi, cairo; gi.require_version("Gtk", "3.0"); gi.require_version("WebKit2", "4.1")' || { echo "Install GTK dependencies first: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1" >&2; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
app_dir="$(PYTHONPATH="$src_dir" python3 -c 'from runtime_paths import Layout; print(Layout().data)')"
mkdir -p "$app_dir" "$HOME/.config/systemd/user"
chmod 700 "$app_dir"
cp "$src_dir/bypass.py" "$src_dir/traffic_web.py" "$src_dir/webdav_sync.py" "$src_dir/runtime_paths.py" "$src_dir/open-manager.py" "$src_dir/desktop_app.py" "$src_dir/background_service.py" "$app_dir/"
mkdir -p "$app_dir/web"
cp "$src_dir/web/index.html" "$app_dir/web/index.html"
mkdir -p "$app_dir/desktop"
cp "$src_dir/desktop/startup.html" "$src_dir/desktop/flow.png" "$src_dir/desktop/flow.icns" "$app_dir/desktop/"
python3 -m venv --system-site-packages "$app_dir/venv"
if ! "$app_dir/venv/bin/python" -c 'import yaml' 2>/dev/null; then
  "$app_dir/venv/bin/python" -m pip install 'PyYAML>=6.0.2,<7'
fi
"$app_dir/venv/bin/python" -m pip install 'pywebview==6.2.1'
"$app_dir/venv/bin/python" "$app_dir/bypass.py" init --data-dir "$app_dir" "$@"
systemctl --user stop rustdesk-clash-bypass.service 2>/dev/null || true
"$app_dir/venv/bin/python" "$app_dir/bypass.py" once --data-dir "$app_dir"
"$app_dir/venv/bin/python" "$app_dir/desktop_app.py" --install-service --data-dir "$app_dir"
if "$app_dir/venv/bin/python" -c 'import json,sys; from pathlib import Path; sys.exit(0 if json.loads((Path(sys.argv[1])/"background-service.json").read_text())["enabled"] else 1)' "$app_dir"; then
  systemctl --user start rustdesk-clash-bypass.service
fi
"$app_dir/venv/bin/python" - "$app_dir" <<'PYOPEN'
from pathlib import Path
import json, sys
app = Path(sys.argv[1]); settings = json.loads((app / 'settings.json').read_text())
url = f"http://127.0.0.1:{settings.get('web_port',17891)}/"
def quote(s): return '"' + str(s).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%') + '"'
command = quote(app/'venv/bin/python') + ' ' + quote(app/'open-manager.py')
entry = '[Desktop Entry]\nType=Application\nName=Flow Traffic Manager\nComment=Application proxy and RustDesk TUN management\nExec=' + command + '\nIcon=' + str(app/'desktop/flow.png') + '\nStartupWMClass=Flow-traffic-manager\nStartupNotify=true\nTerminal=false\nCategories=Network;\n'
p = Path.home() / '.local/share/applications/flow-traffic-manager.desktop'
p.parent.mkdir(parents=True, exist_ok=True); p.write_text(entry)
print('Dashboard:', url)
PYOPEN
printf 'Installed. Log: %s/bypass.log\n' "$app_dir"
