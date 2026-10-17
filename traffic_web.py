"""Loopback-only application traffic dashboard; no third-party web dependencies."""
import base64
import ntpath
import subprocess
import configparser
import hashlib
from functools import lru_cache
import shlex
import time
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import re
import secrets
import threading
import urllib.parse
import bypass as core
from runtime_paths import platform_name, VERSION, canonical_match


@lru_cache(maxsize=1)
def installed_icons(epoch):
    """Read desktop metadata only; never execute desktop commands."""
    roots = [Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))]
    roots += [Path(p) for p in os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':') if p]
    roots += [Path('/var/lib/flatpak/exports/share'), Path.home() / '.local/share/flatpak/exports/share']
    names, images = {}, {}
    for root in roots:
        for entry in sorted((root / 'applications').glob('*.desktop')):
            try:
                cfg = configparser.ConfigParser(interpolation=None, strict=False)
                cfg.read(entry, encoding='utf-8')
                app = cfg['Desktop Entry']
                icon = app.get('Icon', '')
                if not icon:
                    continue
                candidates = [Path(icon)] if Path(icon).is_absolute() else []
                if not candidates and '/' not in icon and icon not in ('.', '..'):
                    for base in roots:
                        for size in ('48x48', '64x64', '128x128', '256x256', '512x512', '1024x1024', 'scalable', '32x32'):
                            for ext in ('.png', '.svg', '.xpm'):
                                candidates.append(base / 'icons/hicolor' / size / 'apps' / (icon if Path(icon).suffix else icon + ext))
                        candidates.extend(base / 'pixmaps' / (icon if Path(icon).suffix else icon + ext) for ext in ('.png', '.svg'))
                image = next((p for p in candidates if p.suffix.lower() in ('.png', '.svg', '.ico', '.jpg', '.jpeg') and p.is_file() and p.stat().st_size <= 4 * 1024 * 1024), None)
                if image is None:
                    continue
                data = image.read_bytes()
                kind = {'.png':'image/png', '.svg':'image/svg+xml', '.ico':'image/x-icon', '.jpg':'image/jpeg', '.jpeg':'image/jpeg'}[image.suffix.lower()]
                key = hashlib.sha256(data).hexdigest()
                images[key] = (data, kind)
                aliases = [entry.stem, app.get('Name', ''), app.get('StartupWMClass', '')]
                command = shlex.split(app.get('Exec', ''))
                if command:
                    aliases.append(Path(command[0]).name)
                if entry.stem == 'google-chrome':
                    aliases.append('chrome')
                if entry.stem == 'chatgpt':
                    aliases.append('codex')
                for alias in aliases:
                    if alias:
                        names.setdefault(alias.casefold(), '/api/icon/' + key)
            except (OSError, ValueError, configparser.Error, KeyError):
                continue
    return names, images


@lru_cache(maxsize=1)
def windows_icons(requests, epoch):
    """Extract local EXE icons in one bounded, cached Windows PowerShell call."""
    if not requests:
        return {}
    script = r'''
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Drawing
$items = [Console]::In.ReadToEnd() | ConvertFrom-Json
$result = @{}
foreach ($item in $items) {
    $icon = $null; $bitmap = $null; $stream = $null
    try {
        $path = [string]$item.path
        $name = [string]$item.name
        if (!$path) {
            $processName = [IO.Path]::GetFileNameWithoutExtension($name)
            $path = Get-Process -Name $processName -ErrorAction SilentlyContinue |
                Where-Object { $_.Path } | Select-Object -First 1 -ExpandProperty Path
            if (!$path) {
                $exe = $processName + '.exe'
                foreach ($root in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths')) {
                    $key = Get-Item -LiteralPath ($root + '\' + $exe) -ErrorAction SilentlyContinue
                    if ($key) { $path = $key.GetValue(''); if ($path) { break } }
                }
            }
        }
        # Never resolve network shares or invoke an executable.
        if (!$path -or $path -notmatch '^[A-Za-z]:[\\/]' -or [IO.Path]::GetExtension($path) -ine '.exe' -or !(Test-Path -LiteralPath $path -PathType Leaf)) { continue }
        $icon = [Drawing.Icon]::ExtractAssociatedIcon($path)
        if (!$icon) { continue }
        $bitmap = $icon.ToBitmap()
        $stream = New-Object IO.MemoryStream
        $bitmap.Save($stream, [Drawing.Imaging.ImageFormat]::Png)
        $url = 'data:image/png;base64,' + [Convert]::ToBase64String($stream.ToArray())
        # Path keys distinguish installations with identical executable names.
        if ($item.path) { $result[([string]$item.path).Replace('/', '\').ToLowerInvariant()] = $url }
        if ($name -and !$result.ContainsKey($name.ToLowerInvariant())) { $result[$name.ToLowerInvariant()] = $url }
    } catch {
        # Missing files, protected processes and absent icons retain the UI fallback.
    } finally {
        if ($stream) { $stream.Dispose() }
        if ($bitmap) { $bitmap.Dispose() }
        if ($icon) { $icon.Dispose() }
    }
}
ConvertTo-Json -InputObject $result -Compress
'''
    try:
        encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        shell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        completed = subprocess.run(
            [str(shell), '-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
            input=json.dumps([{'name': name, 'path': path} for name, path in requests], ensure_ascii=False),
            capture_output=True, encoding='utf-8', timeout=12,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=True)
        result = json.loads(completed.stdout.lstrip('\ufeff'))
        if not isinstance(result, dict):
            return {}
        return {key: value for key, value in result.items()
                if isinstance(key, str) and isinstance(value, str) and value.startswith('data:image/png;base64,') and len(value) <= 1024 * 1024}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


def application_icons(apps, policies):
    if platform_name() != 'Windows':
        return installed_icons(int(time.monotonic() // 60))[0]
    requests = {(app.get('process', ''), app.get('path', '')) for app in apps}
    for rule in policies.get('apps', []):
        path = rule['value'] if rule['type'] == 'PROCESS-PATH' else ''
        requests.add((ntpath.basename(rule['value']), path))
    requests.discard(('', ''))
    return windows_icons(tuple(sorted(requests))[:256], int(time.monotonic() // 60))


def validate_policies(value, groups):
    if not isinstance(value, dict) or not isinstance(value.get('apps'), list):
        raise ValueError('应用规则格式不正确')
    if len(value['apps']) > 128:
        raise ValueError('最多保存 128 条应用规则')
    if not isinstance(value.get('rustdesk_bypass'), bool):
        raise ValueError('RustDesk 绕过 TUN 开关格式不正确')
    apps, seen = [], set()
    bypass = value['rustdesk_bypass']
    for app in value['apps']:
        if not isinstance(app, dict) or app.get('type') not in ['PROCESS-NAME', 'PROCESS-PATH']:
            raise ValueError('仅支持进程名称或完整路径')
        name, target = app.get('value'), app.get('target')
        if not isinstance(name, str) or not name.strip() or len(name) > 1024 or re.search(r'[,\x00-\x1f\x7f]', name):
            raise ValueError('进程名称或路径不能为空，且不能包含逗号或控制字符')
        name = name.strip()
        if not isinstance(target, str) or target not in ['DIRECT'] + groups:
            raise ValueError('请选择当前存在的代理组或直连')
        key = (app['type'], canonical_match(name, app['type']))
        if key in seen:
            raise ValueError('同一个进程不能重复添加规则')
        seen.add(key)
        is_rd = name.replace('\\', '/').rsplit('/', 1)[-1].lower() in ['rustdesk', 'rustdesk.exe']
        if is_rd and target != 'DIRECT':
            bypass = False
        apps.append({'type': app['type'], 'value': name, 'target': target})
    domains = value.get('domains', [])
    if not isinstance(domains, list) or len(domains) > 128:
        raise ValueError('域名规则必须为列表，最多 128 条')
    normalized, seen_domains = [], set()
    for rule in domains:
        if not isinstance(rule, dict) or rule.get('type') not in ('DOMAIN', 'DOMAIN-SUFFIX'):
            raise ValueError('请选择精确域名或域名及子域名')
        name = rule.get('value')
        if not isinstance(name, str):
            raise ValueError('请输入有效域名')
        try:
            name = name.strip().rstrip('.').encode('idna').decode('ascii').lower()
        except UnicodeError:
            raise ValueError('请输入有效域名')
        if len(name) > 253 or '.' not in name or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in name.split('.')):
            raise ValueError('请输入域名，不含协议、端口或页面路径')
        if rule.get('target') not in ['DIRECT'] + groups:
            raise ValueError('请选择当前存在的代理组或直连')
        key = (rule['type'], name)
        if key in seen_domains:
            raise ValueError('同一个域名不能重复添加规则')
        seen_domains.add(key)
        normalized.append({'type': rule['type'], 'value': name, 'target': rule['target']})
    result = {'apps': apps, 'rustdesk_bypass': bypass}
    if 'domains' in value:
        result['domains'] = normalized
    return result


def matches(app, meta):
    candidate = meta.get('processPath' if app['type'] == 'PROCESS-PATH' else 'process', '')
    return canonical_match(candidate, app['type']) == canonical_match(app['value'], app['type'])


def snapshot(w):
    config = core.read_yaml(w.clash / 'clash-verge.yaml')
    groups = [g['name'] for g in config.get('proxy-groups', []) if isinstance(g.get('name'), str) and not re.search(r'[,\x00-\x1f]', g['name'])]
    error = w.last_error
    connections, mode = [], config.get('mode', 'rule')
    try:
        connections = core.api(config, w.clash, 'GET', '/connections', override=w.settings.get('controller')).get('connections', [])
        live = core.api(config, w.clash, 'GET', '/configs', override=w.settings.get('controller'))
        mode = live.get('mode', mode)
        connected = True
    except Exception as exc:
        error, connected = str(exc), False
    grouped = {}
    for item in connections:
        meta = item.get('metadata', {})
        process, path = meta.get('process') or '', meta.get('processPath') or ''
        key = (process, path)
        row = grouped.setdefault(key, {'process': process, 'path': path, 'connections': 0, 'upload': 0, 'download': 0, 'chains': [], 'destinations': []})
        row['connections'] += 1
        row['upload'] += item.get('upload', 0)
        row['download'] += item.get('download', 0)
        for chain in item.get('chains', []):
            if chain not in row['chains']:
                row['chains'].append(chain)
        host = meta.get('host') or meta.get('destinationIP')
        if host and host not in row['destinations'] and len(row['destinations']) < 4:
            row['destinations'].append(host)
    return {'connected': connected, 'mode': mode, 'error': error, 'groups': groups,
            'icons': application_icons(list(grouped.values()), w.policies),
            'policies': w.policies, 'apps': sorted(grouped.values(), key=lambda r: -r['connections']),
            'peers': [{'ip': ip, 'last_seen': seen} for ip, seen in w.state['peers'].items()],
            'servers': w.server_cache, 'routes': w.state.get('managed_routes', []),
            'total_connections': len(connections), 'platform': platform_name(), 'version': VERSION, 'process_mode': config.get('find-process-mode', 'strict')}


def start_server(w, guard):
    from background_service import BackgroundService
    service = BackgroundService(w.data)
    from webdav_sync import WebDAVSync, SyncError, Conflict
    sync = WebDAVSync(w, guard, validate_policies)
    port = w.settings.get('web_port', 17891)
    if not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError('web_port must be between 1024 and 65535')
    token_path = w.data / 'web-token'
    if not token_path.exists():
        core.atomic(token_path, secrets.token_urlsafe(32))
        if os.name != 'nt':
            token_path.chmod(0o600)
    token = token_path.read_text().strip()
    address = f'127.0.0.1:{port}'
    allowed_hosts = {address, f'localhost:{port}'}
    index = Path(__file__).with_name('web') / 'index.html'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if args and str(args[1] if len(args) > 1 else '').startswith('5'):
                logging.warning('Dashboard: ' + fmt, *args)
        def reply(self, status, body, kind='application/json; charset=utf-8', cookie=False, cache=False):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'private, max-age=3600' if cache else 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if cookie:
                self.send_header('Set-Cookie', f'rd_session={token}; HttpOnly; SameSite=Strict; Path=/')
            self.end_headers()
            self.wfile.write(body)
        def allowed(self, mutation=False):
            if self.headers.get('Host') not in allowed_hosts:
                self.reply(403, {'error': '仅允许本机访问'})
                return False
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                self.reply(403, {'error': '不接受跨站请求'})
                return False
            if self.path.startswith('/api/'):
                cookies = dict(p.strip().split('=', 1) for p in self.headers.get('Cookie', '').split(';') if '=' in p)
                if not hmac.compare_digest(cookies.get('rd_session', ''), token):
                    self.reply(401, {'error': '请先打开管理页面'})
                    return False
            if mutation:
                origin = self.headers.get('Origin', '')
                expected = 'http://' + self.headers['Host']
                if origin != expected or self.headers.get('X-Requested-With') != 'RustDeskTrafficManager':
                    self.reply(403, {'error': '请求来源无效，请刷新本机页面'})
                    return False
            return True
        def do_GET(self):
            if not self.allowed():
                return
            if self.path in ['/', '/index.html']:
                self.reply(200, index.read_bytes(), 'text/html; charset=utf-8', cookie=True)
            elif self.path == '/health':
                self.reply(200, {'application': 'flow-traffic-manager', 'version': VERSION})
            elif self.path == '/api/service':
                self.reply(200, service.public())
            elif self.path == '/api/sync':
                self.reply(200, sync.public())
            elif self.path == '/api/state':
                try:
                    with guard:
                        data = snapshot(w)
                    self.reply(200, data)
                except Exception:
                    logging.exception('Dashboard read failed')
                    self.reply(503, {'error': '读取 Clash 状态失败，请检查后台日志'})
            elif self.path.startswith('/api/icon/'):
                key = self.path[len('/api/icon/'):]
                image = installed_icons(int(time.monotonic() // 60))[1].get(key)
                if image:
                    self.reply(200, image[0], image[1], cache=True)
                else:
                    self.reply(404, {'error': '未找到应用图标'})
            elif self.path == '/favicon.ico':
                self.reply(204, b'', 'image/x-icon')
            else:
                self.reply(404, {'error': '页面不存在'})
        def do_POST(self):
            if not self.allowed(mutation=True):
                return
            if self.path not in ('/api/policies', '/api/sync', '/api/service'):
                self.reply(404, {'error': '接口不存在'})
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 65536 or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError('请求格式不正确或内容过大')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('请求格式必须为对象')
                if self.path == '/api/service':
                    self.reply(200, service.configure(data.get('enabled')))
                    return
                if self.path == '/api/sync':
                    try:
                        self.reply(200, sync.run(data.get('action'), data))
                    except Conflict as exc:
                        self.reply(409, {'error': str(exc), 'conflict': True})
                    except SyncError as exc:
                        self.reply(400, {'error': str(exc)})
                    return
                with guard:
                    cfg = core.read_yaml(w.clash / 'clash-verge.yaml')
                    groups = [g['name'] for g in cfg.get('proxy-groups', [])]
                    data.setdefault('domains', w.policies.get('domains', []))
                    policies = validate_policies(data, groups)
                    old = w.policies
                    w.policies = policies
                    try:
                        w.apply(w.scan())
                        core.atomic(w.policies_path, json.dumps(policies, ensure_ascii=False, indent=2))
                        w.last_error = None
                    except Exception:
                        w.policies = old
                        try:
                            w.apply(w.scan())
                        except Exception:
                            logging.exception('Dashboard rollback failed')
                        raise
                    closed, close_error = 0, None
                    close_match = data.get('disconnect')
                    # Only close the explicitly selected application, never all connections.
                    if isinstance(close_match, dict) and close_match.get('type') in ['PROCESS-NAME', 'PROCESS-PATH'] and isinstance(close_match.get('value'), str):
                        try:
                            result = core.api(cfg, w.clash, 'GET', '/connections', override=w.settings.get('controller'))
                            for conn in result.get('connections', []):
                                if matches(close_match, conn.get('metadata', {})):
                                    core.api(cfg, w.clash, 'DELETE', '/connections/' + urllib.parse.quote(conn['id'], safe=''), override=w.settings.get('controller'))
                                    closed += 1
                        except Exception:
                            close_error = '规则已保存，但部分已有连接未能断开。请手动重连应用。'
                            logging.exception('Closing selected app connections failed')
                self.reply(200, {'ok': True, 'policies': policies, 'closed': closed, 'warning': close_error})
            except (ValueError, KeyError, TypeError) as exc:
                self.reply(400, {'error': str(exc)})
            except Exception:
                logging.exception('Dashboard update failed')
                self.reply(503, {'error': '应用配置失败，已尝试恢复原配置。请检查 Clash 是否运行及后台日志。'})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    original_close = server.server_close
    def close():
        sync.stop.set()
        original_close()
    server.server_close = close
    threading.Thread(target=sync.worker, name='webdav-auto-upload', daemon=True).start()
    thread = threading.Thread(target=server.serve_forever, name='traffic-dashboard', daemon=True)
    thread.start()
    logging.info('Application traffic dashboard: http://%s', address)
    return server
