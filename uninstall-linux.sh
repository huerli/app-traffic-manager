#!/usr/bin/env bash
set -euo pipefail
src_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app_dir="$(PYTHONPATH="$src_dir" python3 -c 'from runtime_paths import Layout; print(Layout().data)')"
systemctl --user disable --now rustdesk-clash-bypass.service 2>/dev/null || true
if [[ -f "$app_dir/settings.json" ]]; then
  "$app_dir/venv/bin/python" "$app_dir/bypass.py" uninstall --data-dir "$app_dir"
fi
rm -f "$HOME/.config/systemd/user/rustdesk-clash-bypass.service"
rm -f "$HOME/.local/share/applications/flow-traffic-manager.desktop"
systemctl --user daemon-reload
printf 'Uninstalled. Settings and backup retained in %s\n' "$app_dir"
