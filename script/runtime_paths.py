"""Platform paths shared by the daemon, dashboard, and installers."""
import os
import ntpath
from pathlib import Path
import sys
import tempfile

VERSION = '2.1.1'


def resource_root():
    """Locate shared assets in the source checkout or PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent

APP_NAMES = ('io.github.clash-verge-rev.clash-verge-rev',
             'io.github.clash-verge-rev.clash-verge', 'clash-verge')


def platform_name():
    if sys.platform == 'win32':
        return 'Windows'
    if sys.platform == 'darwin':
        return 'macOS'
    if sys.platform.startswith('linux'):
        return 'Linux'
    raise RuntimeError('Supported platforms: Linux, Windows, macOS')


class Layout:
    def __init__(self, system=None, home=None, environ=None):
        self.system = system or platform_name()
        self.home = Path.home() if home is None else Path(home)
        self.env = os.environ if environ is None else environ
        if self.system not in ('Linux', 'Windows', 'macOS'):
            raise ValueError('Unsupported operating system')

    @property
    def data(self):
        if self.system == 'Windows':
            return Path(self.env.get('LOCALAPPDATA', self.home / 'AppData/Local')) / 'RustDeskClashBypass'
        if self.system == 'macOS':
            return self.home / 'Library/Application Support/RustDeskClashBypass'
        return Path(self.env.get('XDG_DATA_HOME', self.home / '.local/share')) / 'rustdesk-clash-bypass'

    @property
    def clash_roots(self):
        if self.system == 'Windows':
            return list(dict.fromkeys([Path(self.env.get('APPDATA', self.home / 'AppData/Roaming')),
                                       Path(self.env.get('LOCALAPPDATA', self.home / 'AppData/Local'))]))
        if self.system == 'macOS':
            return [self.home / 'Library/Application Support']
        return list(dict.fromkeys([Path(self.env.get('XDG_DATA_HOME', self.home / '.local/share')),
                                   Path(self.env.get('XDG_CONFIG_HOME', self.home / '.config'))]))

    @property
    def rustdesk_logs(self):
        if self.system == 'Windows':
            app = Path(self.env.get('APPDATA', self.home / 'AppData/Roaming'))
            local = Path(self.env.get('LOCALAPPDATA', self.home / 'AppData/Local'))
            win = Path(self.env.get('WINDIR', 'C:/Windows'))
            return [app / 'RustDesk/log', local / 'RustDesk/log',
                    win / 'ServiceProfiles/LocalService/AppData/Roaming/RustDesk/log',
                    win / 'System32/config/systemprofile/AppData/Roaming/RustDesk/log']
        if self.system == 'macOS':
            return [self.home / 'Library/Logs/RustDesk', Path('/var/root/Library/Logs/RustDesk')]
        return [self.home / '.local/share/logs/RustDesk', self.home / '.local/share/rustdesk/log',
                self.home / '.var/app/com.rustdesk.RustDesk/data/logs/RustDesk',
                Path('/root/.local/share/logs/RustDesk')]

    @property
    def rustdesk_configs(self):
        if self.system == 'Windows':
            win = Path(self.env.get('WINDIR', 'C:/Windows'))
            return [Path(self.env.get('APPDATA', self.home / 'AppData/Roaming')) / 'RustDesk/config/RustDesk2.toml',
                    win / 'ServiceProfiles/LocalService/AppData/Roaming/RustDesk/config/RustDesk2.toml',
                    win / 'System32/config/systemprofile/AppData/Roaming/RustDesk/config/RustDesk2.toml']
        if self.system == 'macOS':
            return [self.home / 'Library/Preferences/com.carriez.RustDesk/RustDesk2.toml',
                    Path('/var/root/Library/Preferences/com.carriez.RustDesk/RustDesk2.toml')]
        return [Path(self.env.get('XDG_CONFIG_HOME', self.home / '.config')) / 'rustdesk/RustDesk2.toml',
                self.home / '.var/app/com.rustdesk.RustDesk/config/rustdesk/RustDesk2.toml']


def socket_candidates(config, clash):
    if os.name == 'nt':
        return []
    uid = os.getuid()
    candidates = [f'/run/clash-verge-service/users/{uid}/verge-mihomo.sock',
                  f'/var/run/clash-verge-service/users/{uid}/verge-mihomo.sock',
                  config.get('external-controller-unix', ''), str(Path(clash) / 'verge-mihomo.sock')]
    if platform_name() == 'macOS':
        candidates.extend([str(Path(tempfile.gettempdir()) / 'verge-mihomo.sock'), '/tmp/verge/verge-mihomo.sock'])
    return list(dict.fromkeys(p for p in candidates if p))


def canonical_match(value, kind, system=None):
    if (system or platform_name()) != 'Windows':
        return value
    return ntpath.normcase(ntpath.normpath(value)) if kind == 'PROCESS-PATH' else value.casefold()
