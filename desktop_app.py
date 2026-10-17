"""Native Flow desktop entry point for macOS, Windows and Linux."""
import argparse
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
from runtime_paths import Layout, VERSION


APP_ID = 'local.flow.traffic-manager'
LINUX_APP_ID = 'flow-traffic-manager'
LINUX_WM_CLASS = 'Flow-traffic-manager'


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
        backend.start()
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

    def _status(self, text):
        self._window.run_js('document.getElementById("status").textContent=' + json.dumps(text))

    def _launch(self, clash=None):
        if self._ready or not self._operation.acquire(False):
            return
        try:
            initialize(self._data, clash)
            url = self._backend.start()
            # The dashboard has no Python bridge. Keep its existing strict CSP.
            self._webview.create_window('Flow · 应用流量管理', url=url,
                width=1280, height=880, min_size=(820, 600),
                background_color='#f5f6f8', text_select=True)
            self._ready = True
            self._window.destroy()
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
    html = (Path(__file__).parent / 'desktop/startup.html').read_text(encoding='utf-8')
    window = webview.create_window('Flow · 应用流量管理', html=html, js_api=controller,
                                  width=1280, height=880, min_size=(820, 600),
                                  background_color='#f5f6f8', text_select=True)
    controller._window = window
    # Start only after the first document exists, so errors can be shown in the window.
    window.events.loaded += controller._launch
    try:
        webview.start(gui='gtk' if sys.platform.startswith('linux') else None,
                      private_mode=True, debug=False, icon=str(Path(__file__).parent/'desktop/flow.png'))
    finally:
        controller._close()


if __name__ == '__main__':
    main()
