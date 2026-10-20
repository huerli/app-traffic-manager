"""Per-user background rules service registration; no administrator privileges."""
import base64
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import threading

import bypass as core
from runtime_paths import platform_name

UNIT = 'rustdesk-clash-bypass.service'
LABEL = 'local.flow.traffic-manager'


def service_command(data):
    if getattr(sys, 'frozen', False):
        command = [sys.executable]
    else:
        executable = Path(sys.executable)
        if os.name == 'nt' and executable.with_name('pythonw.exe').exists():
            executable = executable.with_name('pythonw.exe')
        script = Path(__file__).with_name('desktop_app.py').resolve()
        bootstrap = script.with_name('windows-bootstrap.py')
        command = [str(executable)] + ([str(bootstrap)] if os.name == 'nt' and bootstrap.exists() else []) + [str(script)]
    return command + ['--service', '--data-dir', str(Path(data).resolve())]


def parent_alive(pid):
    if not pid:
        return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class BackgroundService:
    def __init__(self, data):
        self.data = Path(data)
        self.state_path = self.data / 'background-service.json'
        self.system = platform_name()
        self.operation = threading.Lock()

    def registration_path(self):
        if self.system == 'Linux':
            return Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config')) / 'systemd/user' / UNIT
        if self.system == 'macOS':
            return Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
        startup = Path(os.environ.get('APPDATA', Path.home()/'AppData/Roaming')) / 'Microsoft/Windows/Start Menu/Programs/Startup'
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
                startup = Path(os.path.expandvars(winreg.QueryValueEx(key, 'Startup')[0]))
        except (ImportError, OSError):
            pass
        return startup / 'RustDeskClashBypass.vbs'

    def enabled(self):
        if self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding='utf-8')).get('enabled') is True
        path = self.registration_path()
        if self.system == 'Linux':
            return (path.parent/'default.target.wants'/UNIT).exists()
        return path.exists()

    def has_sessions(self):
        folder = self.data / 'desktop-sessions'
        alive = False
        if folder.exists():
            for lease in folder.glob('*.session'):
                if lease.stem.isdecimal() and parent_alive(int(lease.stem)):
                    alive = True
                else:
                    lease.unlink(missing_ok=True)
        return alive

    def public(self):
        enabled = self.enabled()
        return {'enabled': enabled, 'platform': self.system,
                'mechanism': {'Linux':'systemd 用户服务','macOS':'LaunchAgent','Windows':'用户登录启动项'}[self.system],
                'message': '后台常驻已启用，关闭 App 后继续维护规则，并在登录后自动启动。' if enabled else '随 App 运行；关闭 App 后停止规则维护。已应用的 Clash 规则仍保留。'}

    def _run(self, args, check=True, env_extra=None):
        env = os.environ.copy()
        if getattr(sys, 'frozen', False):
            for key in ('LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH'):
                env[key] = env.get(key + '_ORIG', '')
        env.update(env_extra or {})
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=15, env=env)
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError('无法访问当前用户的服务管理器，请确认在桌面登录会话中运行 App。') from None
        if check and result.returncode:
            raise ValueError('后台服务注册失败，请检查当前用户的服务管理器或登录项权限。')
        return result

    def configure(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError('后台常驻开关格式不正确。')
        if not self.operation.acquire(False):
            raise ValueError('后台服务设置正在更新，请稍后重试。')
        path = self.registration_path()
        previous = path.read_bytes() if path.exists() else None
        try:
            command = service_command(self.data)
            path.parent.mkdir(parents=True, exist_ok=True)
            if self.system == 'Linux':
                if enabled:
                    def quote(value):
                        return '"' + value.replace('\\','\\\\').replace('"','\\"').replace('%','%%').replace('$','$$') + '"'
                    if any('\n' in value or '\r' in value for value in command):
                        raise ValueError('服务路径不能包含换行。')
                    content = '[Unit]\nDescription=Flow background rules service\nAfter=default.target\n\n[Service]\nType=simple\nExecStart=' + ' '.join(map(quote, command)) + '\nRestart=on-failure\nRestartSec=5\nUMask=0077\n\n[Install]\nWantedBy=default.target\n'
                    core.atomic(path, content)
                    self._run(['systemctl','--user','daemon-reload'])
                    self._run(['systemctl','--user','enable',UNIT])
                else:
                    # The unit may already be gone (for example after an app upgrade);
                    # disabling must still clear the stored setting.
                    self._run(['systemctl','--user','disable',UNIT], check=False)
                    path.unlink(missing_ok=True)
            elif self.system == 'macOS':
                domain = f'gui/{os.getuid()}'
                if enabled:
                    content = {'Label':LABEL,'ProgramArguments':command,'RunAtLoad':True,'KeepAlive':True,
                               'ThrottleInterval':5,'Umask':63,
                               'StandardOutPath':str(self.data/'service.stdout.log'),
                               'StandardErrorPath':str(self.data/'service.stderr.log')}
                    path.write_bytes(plistlib.dumps(content))
                    self._run(['launchctl','enable',domain+'/'+LABEL])
                else:
                    self._run(['launchctl','disable',domain+'/'+LABEL], check=False)
                    path.unlink(missing_ok=True)
            else:
                if enabled:
                    line = subprocess.list2cmdline(command).replace('"','""')
                    if '\n' in line or '\r' in line:
                        raise ValueError('服务路径不能包含换行。')
                    path.write_text('CreateObject("WScript.Shell").Run "'+line+'", 0, False\n', encoding='utf-16')
                else:
                    path.unlink(missing_ok=True)
            core.atomic(self.state_path, json.dumps({'enabled':enabled}))
            return self.public()
        except Exception:
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(previous)
            raise
        finally:
            self.operation.release()

    def stop_legacy(self):
        """Only after the last native window closes; never interrupt an HTTP reply."""
        if self.system == 'Linux':
            path = self.registration_path()
            if not path.exists() or str(self.data.resolve()) not in path.read_text(encoding='utf-8'):
                return
            self._run(['systemctl','--user','stop',UNIT], check=False)
        elif self.system == 'macOS':
            path = self.registration_path()
            if path.exists() and str(self.data.resolve()) not in plistlib.loads(path.read_bytes()).get('ProgramArguments', []):
                return
            self._run(['launchctl','bootout',f'gui/{os.getuid()}/{LABEL}'], check=False)
        elif self.system == 'Windows':
            script = r"""Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -and $_.CommandLine.Contains($env:FLOW_LEGACY_SCRIPT) -and $_.CommandLine.Contains('watch') } | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }"""
            encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
            shell = Path(os.environ.get('SystemRoot', r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
            self._run([str(shell),'-NoProfile','-NonInteractive','-EncodedCommand',encoded], check=False,
                      env_extra={'FLOW_LEGACY_SCRIPT':str(self.data/'bypass.py')})
        # New headless workers observe the setting and their parent lifetime themselves.
