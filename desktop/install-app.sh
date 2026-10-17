#!/usr/bin/env bash
# Register an unpacked Linux binary package in the current user's application menu.
set -euo pipefail
[[ "$(uname -s)" == Linux ]] || { echo 'This launcher installer is for Linux.' >&2; exit 1; }
flow_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ -x "$flow_dir/Flow" && -f "$flow_dir/_internal/desktop/flow.png" ]] || { echo 'Keep this script beside the Flow binary and its _internal directory.' >&2; exit 1; }
# Escape Desktop Entry argument and string metacharacters without shell evaluation.
flow_exec="${flow_dir//\\/\\\\}"
flow_exec="${flow_exec//\"/\\\"}"
flow_exec="${flow_exec//\$/\\\$}"
flow_exec="${flow_exec//\`/\\\`}"
flow_exec="${flow_exec//%/%%}"
flow_icon="${flow_dir//\\/\\\\}"
flow_icon="${flow_icon//$'\n'/\\n}"
flow_icon="${flow_icon//$'\r'/\\r}"
flow_entries="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$flow_entries"
cat > "$flow_entries/flow-traffic-manager.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Flow Traffic Manager
Comment=Application traffic manager
Exec="$flow_exec/Flow"
Icon=$flow_icon/_internal/desktop/flow.png
StartupWMClass=Flow-traffic-manager
StartupNotify=true
Terminal=false
Categories=Network;
EOF
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$flow_entries" || true
fi
printf 'Registered Flow. Keep this package at: %s\n' "$flow_dir"
