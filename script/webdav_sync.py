"""WebDAV policy snapshots. Credentials and machine runtime data stay local."""
import base64
import copy
import hashlib
import json
import os
import socket
import ssl
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import bypass as core

LIMIT = 262144


class SyncError(ValueError):
    pass


class Conflict(SyncError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def portable(policies):
    return {key: copy.deepcopy(policies.get(key, [])) for key in ('apps', 'domains')}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SyncError('WebDAV 地址发生重定向，请填写最终服务地址后重试。')


def connection_error(reason):
    if isinstance(reason, ssl.SSLCertVerificationError):
        detail = getattr(reason, 'verify_message', '')
        if getattr(reason, 'verify_code', None) == 64 or 'IP address mismatch' in detail or 'Hostname mismatch' in detail:
            return 'WebDAV 证书与服务地址不匹配，请使用证书绑定的域名访问。'
        return 'WebDAV HTTPS 证书验证失败，请检查证书是否过期、证书链是否完整，以及本机是否信任签发机构。'
    if isinstance(reason, ssl.SSLError):
        return 'WebDAV 服务器 TLS 握手失败，尚未验证账号密码。请检查 HTTPS 端口；使用 IP 时请改用服务器证书绑定的域名，并检查服务器 TLS 配置。'
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return '连接 WebDAV 超时，请检查服务端口、防火墙和网络。'
    if isinstance(reason, socket.gaierror):
        return '无法解析 WebDAV 域名，请检查地址与 DNS。'
    if isinstance(reason, ConnectionRefusedError):
        return 'WebDAV 端口拒绝连接，请检查服务是否启动以及端口是否正确。'
    return '无法连接 WebDAV，请检查服务地址、端口和网络。'


class WebDAVSync:
    def __init__(self, watcher, guard, validate):
        self.w, self.guard, self.validate = watcher, guard, validate
        self.path = watcher.data / 'webdav.json'
        self.config = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        self.operation = threading.Lock()
        self.stop = threading.Event()
        self.status = {'message': '尚未同步', 'last_sync': None, 'last_action': None}
        self.known_remote = None
        self.uploaded = None

    def public(self):
        return {'config': {k: self.config.get(k, default) for k, default in
                [('url', ''), ('username', ''), ('directory', 'flow-sync'), ('profile', 'default'), ('auto_upload', False)]},
                'has_password': bool(self.config.get('password')), 'status': dict(self.status)}

    def save(self, value):
        config = {}
        for key, default in [('url', ''), ('username', ''), ('directory', 'flow-sync'), ('profile', 'default')]:
            item = value.get(key, default)
            if not isinstance(item, str) or len(item) > 2048:
                raise SyncError('同步设置格式不正确。')
            config[key] = item.strip()
        url = urllib.parse.urlsplit(config['url'])
        if url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise SyncError('请输入完整的 HTTP 或 HTTPS WebDAV 地址，不要在地址中包含账号密码。')
        for key in ('directory', 'profile'):
            parts = config[key].strip('/').split('/')
            if not all(p and p not in ('.', '..') and '\\' not in p and not any(ord(c) < 32 for c in p) for p in parts):
                raise SyncError('远程目录与配置档名称不能为空，也不能包含相对路径。')
            if key == 'profile' and len(parts) != 1:
                raise SyncError('配置档名称不能包含斜杠。')
            config[key] = '/'.join(parts)
        password = value.get('password', self.config.get('password', ''))
        if not isinstance(password, str) or len(password) > 4096:
            raise SyncError('密码格式不正确。')
        config['password'] = password
        config['auto_upload'] = value.get('auto_upload', False) is True
        # Private temporary file, including on systems with a permissive umask.
        temp = self.path.with_suffix('.tmp')
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False)
        os.replace(temp, self.path)
        self.config = config
        self.known_remote = self.uploaded = None
        self.status['message'] = '同步设置已保存'
        return self.public()

    def urls(self):
        if not self.config.get('url'):
            raise SyncError('请先保存 WebDAV 设置。')
        base = self.config['url'].rstrip('/') + '/'
        segments = self.config['directory'].split('/') + [self.config['profile']]
        dirs = []
        for segment in segments:
            base += urllib.parse.quote(segment, safe='') + '/'
            dirs.append(base)
        return dirs, base + 'policies-v1.json'

    def request(self, method, url, body=None, headers=None):
        auth = base64.b64encode((self.config.get('username', '') + ':' + self.config.get('password', '')).encode()).decode()
        request = urllib.request.Request(url, data=body, method=method, headers={
            'Authorization': 'Basic ' + auth, 'User-Agent': 'Flow-Traffic-Manager', **(headers or {})})
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
                data = response.read(LIMIT + 1)
                if len(data) > LIMIT:
                    raise SyncError('远程文件过大，已停止同步。')
                return data, response.headers.get('ETag')
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 405, 412):
                raise
            if exc.code in (401, 403):
                raise SyncError('WebDAV 认证失败或没有访问权限，请检查账号与应用密码。') from None
            raise SyncError(f'WebDAV 请求失败（HTTP {exc.code}）。') from None
        except urllib.error.URLError as exc:
            raise SyncError(connection_error(exc.reason)) from None
        except OSError as exc:
            raise SyncError(connection_error(exc)) from None

    def remote(self):
        _, url = self.urls()
        try:
            raw, etag = self.request('GET', url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None, None
            raise SyncError(f'读取远程配置失败（HTTP {exc.code}）。') from None
        try:
            snapshot = json.loads(raw)
            if not isinstance(snapshot, dict) or snapshot.get('format') != 'flow-policies' or snapshot.get('version') != 1:
                raise ValueError()
            policy = snapshot['policies']
            if not isinstance(policy, dict) or not isinstance(policy.get('apps'), list) or not isinstance(policy.get('domains'), list):
                raise ValueError()
            return snapshot, etag
        except (ValueError, KeyError, TypeError):
            raise SyncError('远程文件不是支持的 Flow 规则快照，已停止同步。') from None

    def summary(self, snapshot):
        if snapshot is None:
            with self.guard:
                return {'empty': True, 'remote_hash': None, 'local_hash': digest(portable(self.w.policies))}
        policies = snapshot['policies']
        with self.guard:
            cfg = core.read_yaml(self.w.clash / 'clash-verge.yaml')
            groups = {g['name'] for g in cfg.get('proxy-groups', [])}
            targets = groups | set(core.proxy_names(cfg)) | {'DIRECT'}
            local_hash = digest(portable(self.w.policies))
        missing = sorted({r.get('target', '') for r in policies['apps'] + policies['domains'] if isinstance(r, dict)} - targets)
        return {'empty': False, 'apps': len(policies['apps']), 'domains': len(policies['domains']),
                'updated_at': snapshot.get('updated_at'), 'remote_hash': digest(snapshot), 'local_hash': local_hash,
                'missing_groups': missing, 'available_groups': sorted(groups),
                'rules': [{'type': r.get('type'), 'value': r.get('value'), 'target': r.get('target')}
                          for r in (policies['domains'] + policies['apps'])[:20] if isinstance(r, dict)]}

    def upload(self, force=False, expected=None):
        snapshot, etag = self.remote()
        remote_hash = digest(snapshot) if snapshot else None
        with self.guard:
            policies = portable(self.w.policies)
        if force and expected is not None:
            if expected.get('remote_hash') != remote_hash or expected.get('local_hash') != digest(policies):
                raise Conflict('本机或远程规则已变化，请重新查看摘要后上传。')
        if snapshot and snapshot['policies'] == policies:
            self.known_remote, self.uploaded = remote_hash, digest(policies)
            return {'message': '本机与远程规则一致。'}
        if snapshot and remote_hash != self.known_remote and not force:
            raise Conflict('远程已有不同规则，请先查看远程摘要，再下载或确认覆盖上传。')
        if snapshot and (not etag or etag.startswith('W/')):
            raise SyncError('服务器未提供强 ETag，无法安全覆盖已有配置，请换用新的配置档。')
        dirs, url = self.urls()
        for directory in dirs:
            try:
                self.request('MKCOL', directory)
            except urllib.error.HTTPError as exc:
                if exc.code != 405:
                    raise SyncError(f'创建远程目录失败（HTTP {exc.code}）。') from None
        payload = {'format': 'flow-policies', 'version': 1, 'updated_at': int(time.time()), 'policies': policies}
        encoded = json.dumps(payload, ensure_ascii=False).encode()
        if len(encoded) > LIMIT:
            raise SyncError('规则快照过大，已停止上传。')
        headers = {'Content-Type': 'application/json', **({'If-Match': etag} if snapshot else {'If-None-Match': '*'})}
        try:
            self.request('PUT', url, encoded, headers)
        except urllib.error.HTTPError as exc:
            if exc.code == 412:
                raise Conflict('远程规则刚被另一台设备修改，请重新查看远程摘要。') from None
            raise SyncError(f'上传失败（HTTP {exc.code}）。') from None
        self.known_remote, self.uploaded = digest(payload), digest(policies)
        return {'message': '规则已上传到 WebDAV。'}

    def download(self, value):
        snapshot, _ = self.remote()
        if snapshot is None:
            raise SyncError('远程尚无规则，请先在另一台设备上传。')
        if digest(snapshot) != value.get('remote_hash'):
            raise Conflict('远程规则已变化，请重新查看摘要后下载。')
        with self.guard:
            if digest(portable(self.w.policies)) != value.get('local_hash'):
                raise Conflict('本机规则已变化，请重新查看摘要后下载。')
            cfg = core.read_yaml(self.w.clash / 'clash-verge.yaml')
            groups = [g['name'] for g in cfg.get('proxy-groups', [])]
            proxies = core.proxy_names(cfg)
            local_targets = ['DIRECT'] + groups + proxies
            mapping = value.get('group_mapping', {})
            if not isinstance(mapping, dict) or any(not isinstance(source, str) or target not in groups for source, target in mapping.items()):
                raise SyncError('请选择本机已有的代理组进行映射。')
            incoming = copy.deepcopy(snapshot['policies'])
            for rule in incoming['apps'] + incoming['domains']:
                if isinstance(rule, dict) and rule.get('target') not in local_targets:
                    target = rule.get('target')
                    if target not in mapping:
                        raise SyncError(f'本机缺少代理组或节点 {target}，请先选择对应的本机代理组。')
                    rule['target'] = mapping[target]
            policies = self.validate({**incoming, 'rustdesk_bypass': self.w.policies.get('rustdesk_bypass', True)}, groups, proxies)
            old = copy.deepcopy(self.w.policies)
            backup = self.w.data / 'policies-before-sync.json'
            core.atomic(backup, json.dumps(old, ensure_ascii=False, indent=2))
            self.w.policies = policies
            try:
                self.w.apply(self.w.scan())
                core.atomic(self.w.policies_path, json.dumps(policies, ensure_ascii=False, indent=2))
            except Exception:
                self.w.policies = old
                try:
                    self.w.apply(self.w.scan())
                except Exception:
                    pass
                raise SyncError('应用下载规则失败，已恢复原规则；请检查 Clash 状态。') from None
            self.known_remote, self.uploaded = digest(snapshot), digest(portable(policies))
        return {'message': '远程规则已下载并应用；原规则已备份。', 'policies': policies}

    def run(self, action, value):
        if not self.operation.acquire(blocking=False):
            raise Conflict('另一个同步操作正在进行，请稍后重试。')
        try:
            if action == 'save':
                return self.save(value)
            if action == 'test':
                self.urls()
                self.request('PROPFIND', self.config['url'], headers={'Depth': '0'})
                result = {'message': 'WebDAV 连接与认证成功。'}
            elif action == 'preview':
                snapshot, _ = self.remote()
                return {'remote': self.summary(snapshot)}
            elif action == 'upload':
                result = self.upload(value.get('force') is True, value)
            elif action == 'download':
                result = self.download(value)
            else:
                raise SyncError('未知同步操作。')
            self.status = {'message': result['message'], 'last_sync': int(time.time()), 'last_action': action}
            return {**result, **self.public()}
        except urllib.error.HTTPError as exc:
            error = f'WebDAV 请求失败（HTTP {exc.code}）。'
            self.status['message'] = error
            raise SyncError(error) from None
        except SyncError as exc:
            self.status['message'] = str(exc)
            raise
        finally:
            self.operation.release()

    def worker(self):
        while not self.stop.wait(10):
            if not self.config.get('auto_upload') or not self.config.get('url'):
                continue
            with self.guard:
                changed = digest(portable(self.w.policies)) != self.uploaded
            if changed:
                try:
                    self.run('upload', {})
                except (SyncError, OSError):
                    pass
