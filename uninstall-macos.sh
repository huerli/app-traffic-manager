#!/usr/bin/env bash
set -euo pipefail
[[ "$(uname -s)" == Darwin ]] || { echo 'This uninstaller requires macOS.' >&2; exit 1; }
src_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app_dir="$(PYTHONPATH="$src_dir" "${PYTHON_BIN:-python3}" -c 'from runtime_paths import Layout; print(Layout().data)')"
agent="$HOME/Library/LaunchAgents/local.flow.traffic-manager.plist"
launchctl bootout "gui/$(id -u)" "$agent" 2>/dev/null || true
if [[ -f "$app_dir/settings.json" ]]; then
  "$app_dir/venv/bin/python" "$app_dir/bypass.py" uninstall --data-dir "$app_dir"
fi
rm -f "$agent" "$app_dir/Flow Traffic Manager.webloc"
rm -rf "$HOME/Applications/Flow Traffic Manager.app"
printf 'Uninstalled. Settings and backups retained in %s\n' "$app_dir"
