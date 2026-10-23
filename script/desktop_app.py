"""Native Flow desktop entry point for macOS, Windows and Linux."""
import argparse
import http.cookiejar
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import signal
import subprocess
from pathlib import Path
import sys
import threading
import time
import urllib.error
import urllib.request

import bypass as core
from runtime_paths import Layout, VERSION, resource_root


APP_ID = 'local.flow.traffic-manager'
LINUX_APP_ID = 'flow-traffic-manager'
LINUX_WM_CLASS = 'Flow-traffic-manager'


def window_icon():
    """Return the native window icon format expected by the current platform."""
    name = 'flow.ico' if sys.platform == 'win32' else 'flow.png'
    icon = resource_root() / 'desktop' / name
    return str(icon) if icon.is_file() else None


def configure_app_identity():
    """Set OS application identity before importing or initializing the GUI."""
    if sys.platform.startswith('linux'):
        import gi
        gi.require_version('Gdk', '3.0')
        from gi.repository import GLib, Gdk
        GLib.set_prgname(LINUX_APP_ID)
        GLib.set_application_name('Flow Traffic Manager')
        Gdk.set_program_class(LINUX_WM_CLASS)
    elif sys.platform == 'win32':
        import ctypes
        set_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_id.argtypes = [ctypes.c_wchar_p]
        set_id.restype = ctypes.c_long
        result = set_id(APP_ID)
        if result != 0:
            raise OSError('Unable to set Flow application identity')


def local_url(data):
    settings = json.loads((Path(data) / 'settings.json').read_text(encoding='utf-8'))
    port = settings.get('web_port', 17891)
    if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
        raise ValueError('web_port 必须在 1024 到 65535 之间。')
    return f'http://127.0.0.1:{port}/'


def backend_ready(url):
    try:
        # Do not route local control requests through environment HTTP proxies.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + 'health', timeout=1) as response:
            return json.loads(response.read(4096)).get('application') == 'flow-traffic-manager'
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            return False
        # Older installed Flow services predate /health. Authenticate normally
        # and verify their dashboard and state before reusing the occupied port.
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            with opener.open(url, timeout=1) as response:
                if b'RustDeskTrafficManager' not in response.read(2_000_000):
                    return False
            with opener.open(url + 'api/state', timeout=1) as response:
                state = json.loads(response.read(4_000_000))
                return isinstance(state, dict) and all(key in state for key in
                    ('policies', 'apps', 'peers', 'routes', 'version'))
        except (OSError, ValueError, AttributeError):
            return False
    except (OSError, ValueError, AttributeError):
        return False


def initialize(data, clash=None):
    data = Path(data)
    data.mkdir(parents=True, exist_ok=True)
    if (data / 'settings.json').exists():
        return
    clash = Path(clash) if clash else core.detect_clash()
    if not (clash / 'profiles/Script.js').is_file() or not (clash / 'clash-verge.yaml').is_file():
        raise ValueError('请选择包含 clash-verge.yaml 和 profiles/Script.js 的 Clash Verge 配置目录。')
    settings = {'clash_dir': str(clash), 'log_dirs': [str(p) for p in core.default_logs()],
                'interval_seconds': 5, 'peer_ttl_days': 7, 'max_peers': 64, 'controller': None}
    core.atomic(data / 'settings.json', json.dumps(settings, ensure_ascii=False, indent=2))


class EmbeddedBackend:
    def __init__(self, data):
        self.data = Path(data)
        self.server = None
        self.lock = None
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        self.stop.clear()
        url = local_url(self.data)
        if backend_ready(url):
            return url
        self.lock = (self.data / 'watcher.lock').open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.lock.seek(0); self.lock.write(b'0'); self.lock.flush(); self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close(); self.lock = None
            for _ in range(15):
                if self.stop.wait(.3):
                    raise RuntimeError('App 已关闭。')
                if backend_ready(url):
                    return url
            raise RuntimeError('后台服务已运行但尚未就绪。请更新安装并重启 Flow 后重试。')
        try:
            from traffic_web import start_server
            watcher = core.Watcher(self.data)
            guard = threading.RLock()
            self.server = start_server(watcher, guard)
            def watch():
                while not self.stop.is_set():
                    try:
                        with guard:
                            watcher.apply(watcher.scan())
                            watcher.last_error = None
                    except Exception as exc:
                        watcher.last_error = str(exc)
                        logging.exception('Desktop watcher failed')
                    self.stop.wait(max(3, watcher.settings.get('interval_seconds', 5)))
            self.thread = threading.Thread(target=watch, name='flow-desktop-watcher', daemon=True)
            self.thread.start()
            return url
        except Exception:
            self.close()
            raise

    def close(self):
        self.stop.set()
        if self.server:
            self.server.shutdown(); self.server.server_close(); self.server = None
        if self.thread:
            # Keep the watcher lock until any current Clash update has completed.
            self.thread.join()
            self.thread = None
        if self.lock:
            self.lock.close(); self.lock = None


class DesktopBackend:
    """Use a detached headless worker, or reuse an existing installed service."""
    def __init__(self, data):
        self.data = Path(data)
        self.child = None
        self.lease = self.data/'desktop-sessions'/f'{os.getpid()}.session'

    def start(self):
        self.lease.parent.mkdir(parents=True, exist_ok=True)
        self.lease.touch()
        url = local_url(self.data)
        if backend_ready(url):
            return url
        from background_service import service_command
        command = service_command(self.data) + ['--parent-pid', str(os.getpid())]
        options = {'stdin':subprocess.DEVNULL, 'stdout':subprocess.DEVNULL, 'stderr':subprocess.DEVNULL}
        if os.name == 'nt':
            options['creationflags'] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        else:
            options['start_new_session'] = True
        self.child = subprocess.Popen(command, **options)
        for _ in range(60):
            if backend_ready(url):
                return url
            if self.child.poll() is not None:
                raise RuntimeError('后台内核启动失败，请检查 desktop.log。')
            time.sleep(.2)
        raise RuntimeError('后台内核尚未就绪，请检查端口和 desktop.log 后重试。')

    def close(self):
        from background_service import BackgroundService
        manager = BackgroundService(self.data)
        self.lease.unlink(missing_ok=True)
        if manager.state_path.exists() and not manager.enabled() and not manager.has_sessions():
            try:
                manager.stop_legacy()
            except ValueError:
                logging.exception('Could not stop legacy background service')
        # A worker follows this process while temporary, or stays alive when enabled.


def run_service(data, parent_pid=0):
    from background_service import BackgroundService, parent_alive
    manager = BackgroundService(data)
    if not parent_pid and not manager.enabled() and not manager.has_sessions() and os.environ.get('FLOW_TAURI') != '1':
        return
    backend = EmbeddedBackend(data)
    shutdown = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: shutdown.set())
    try:
        if os.environ.get('FLOW_TAURI') == '1':
            initialize(data)
        url = backend.start()
        if os.environ.get('FLOW_TAURI') == '1':
            print(json.dumps({'url': url}), flush=True)
        if backend.server is None:
            return  # An existing process already owns the controller and watcher lock.
        while not shutdown.wait(1):
            if not manager.enabled() and not parent_alive(parent_pid) and not manager.has_sessions():
                return
    finally:
        backend.close()


class DesktopController:
    def __init__(self, data, webview):
        self._data, self._webview = Path(data), webview
        self._backend = DesktopBackend(data)
        self._window = None
        self._operation = threading.Lock()
        self._ready = False
        self._tray = None
        self._quitting = False

    def setup_tray(self):
        if not sys.platform.startswith('linux'):
            return
        from gi.repository import GLib
        GLib.idle_add(self._create_linux_tray)

    def _create_linux_tray(self):
        if self._tray is not None:
            return False
        try:
            import gi
            try:
                gi.require_version('AyatanaAppIndicator3', '0.1')
                from gi.repository import AyatanaAppIndicator3 as Indicator
            except ValueError:
                gi.require_version('AppIndicator3', '0.1')
                from gi.repository import AppIndicator3 as Indicator
            from gi.repository import Gtk
            icon = str((resource_root() / 'desktop/flow.png').resolve())
            tray = Indicator.Indicator.new(APP_ID, icon, Indicator.IndicatorCategory.APPLICATION_STATUS)
            tray.set_title('Flow · 应用流量管理')
            menu = Gtk.Menu()
            show = Gtk.MenuItem(label='显示 Flow')
            show.connect('activate', lambda *_: self._show_from_tray())
            quit_item = Gtk.MenuItem(label='退出 Flow')
            quit_item.connect('activate', lambda *_: self._quit_from_tray())
            menu.append(show)
            menu.append(quit_item)
            menu.show_all()
            tray.set_menu(menu)
            tray.set_status(Indicator.IndicatorStatus.ACTIVE)
            self._tray = tray
        except Exception:
            logging.exception('Could not create system tray; keep taskbar access')
        return False

    def _show_from_tray(self):
        # Tray callbacks run on GTK's UI thread; avoid synchronous webview calls.
        native = self._window.native
        native.deiconify()
        native.show_all()
        native.present()

    def _quit_from_tray(self):
        self._quitting = True
        # Destroy through a worker: webview dispatches destruction back to GTK.
        threading.Thread(target=self._window.destroy, daemon=True).start()

    def _status(self, text):
        self._window.run_js('document.getElementById("status").textContent=' + json.dumps(text))

    def _launch(self, clash=None):
        if self._ready or not self._operation.acquire(False):
            return
        try:
            initialize(self._data, clash)
            url = self._backend.start()
            # Navigate the startup window instead of creating a second native
            # window and destroying the first while GTK is handling its load.
            # The startup page needs retry/select_clash, but the dashboard
            # uses HTTP APIs exclusively. pywebview 6.2.1 generates JS API
            # functions with new Function(), which the dashboard CSP forbids.
            # Detach the startup bridge before the next document is injected.
            startup_api = self._window._js_api
            self._window._js_api = None
            self._ready = True
            try:
                self._window.load_url(url)
            except Exception:
                self._window._js_api = startup_api
                self._ready = False
                raise
        except Exception as exc:
            logging.exception('Desktop startup failed')
            self._status(str(exc) + '\n请保持 Clash Verge 运行，再重试或选择配置目录。')
        finally:
            self._operation.release()

    def retry(self):
        self._launch()

    def select_clash(self):
        if self._ready:
            return
        if (self._data / 'settings.json').exists():
            self._status('已有配置保留在本机。请检查 Clash Verge 是否运行，或编辑数据目录中的 settings.json 后重试。')
            return
        selected = self._window.create_file_dialog(self._webview.FileDialog.FOLDER)
        if selected:
            self._launch(selected[0])

    def _on_closing(self):
        if self._quitting or not self._ready:
            return
        try:
            preferences = json.loads((self._data / 'desktop.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            preferences = {}
        if preferences.get('close_action') == 'minimize':
            if self._tray is not None:
                self._window.hide()
            else:
                self._window.minimize()
            return False

    def _close(self):
        self._backend.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Flow desktop application')
    parser.add_argument('--data-dir', type=Path, default=Layout().data)
    parser.add_argument('--install-service', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--service', action='store_true', help='Run the background rules engine without a window')
    parser.add_argument('--parent-pid', type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument('--check', action='store_true', help='Check desktop imports without opening a window')
    args = parser.parse_args(argv)
    if args.install_service:
        from background_service import BackgroundService
        manager = BackgroundService(args.data_dir)
        manager.configure(manager.enabled() if manager.state_path.exists() else True)
        return
    if args.service:
        args.data_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(
            args.data_dir / 'desktop.log', maxBytes=1000000, backupCount=2, encoding='utf-8')])
        run_service(args.data_dir, args.parent_pid)
        return
    if not args.check:
        configure_app_identity()
    import webview
    if args.check:
        print(f'Flow {VERSION}: desktop dependencies available on {sys.platform}')
        return
    args.data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(
        args.data_dir / 'desktop.log', maxBytes=1000000, backupCount=2, encoding='utf-8')])
    webview.settings['ALLOW_FILE_URLS'] = False
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True
    controller = DesktopController(args.data_dir, webview)
    html = (resource_root() / 'desktop/startup.html').read_text(encoding='utf-8')
    window = webview.create_window('Flow · 应用流量管理', html=html, js_api=controller,
                                  width=1280, height=880, min_size=(820, 600),
                                  background_color='#f5f6f8', text_select=True)
    controller._window = window
    window.events.closing += controller._on_closing
    # Start only after the first document exists, so errors can be shown in the window.
    window.events.loaded += controller.setup_tray
    window.events.loaded += controller._launch
    try:
        webview.start(gui='gtk' if sys.platform.startswith('linux') else None,
                      private_mode=True, debug=False, icon=window_icon())
    finally:
        controller._close()


if __name__ == '__main__':
    main()
