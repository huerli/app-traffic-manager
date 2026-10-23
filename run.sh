#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
# Prefer the Linux system interpreter so GTK is available even inside Conda.
if [[ "$(uname -s)" == Linux && -x /usr/bin/python3 ]]; then
    flow_python=/usr/bin/python3
else
    flow_python=python3
fi
if [[ ! -x .run-venv/bin/python ]]; then
    "$flow_python" -m venv --system-site-packages .run-venv
fi
if ! .run-venv/bin/python -c 'import yaml, webview; from importlib.metadata import version; assert version("pywebview") == "6.2.1"' >/dev/null 2>&1; then
    .run-venv/bin/python -m pip install -r requirements-desktop.txt
fi
if [[ "$(uname -s)" == Linux ]] && ! .run-venv/bin/python -c 'import gi; import cairo; gi.require_version("Gtk", "3.0"); gi.require_version("WebKit2", "4.1"); from gi.repository import Gtk, WebKit2' >/dev/null 2>&1; then
    echo '缺少 GTK / WebKit 系统依赖。Ubuntu / Debian 请执行：' >&2
    echo 'sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1' >&2
    exit 1
fi
exec .run-venv/bin/python script/open-manager.py "$@"
