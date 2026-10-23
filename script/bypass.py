#!/usr/bin/env python3
"""RustDesk peer learning and Clash Verge TUN bypass. Python >= 3.10 + PyYAML."""
import argparse
import datetime as dt
import http.client
import ipaddress
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import socket
import sys
import time
import threading
import urllib.parse
import yaml
from runtime_paths import Layout, APP_NAMES, VERSION, platform_name, socket_candidates

BEGIN = '// BEGIN RUSTDESK_AUTO_BYPASS'
END = '// END RUSTDESK_AUTO_BYPASS'
BLOCK = re.compile(r'\n?' + re.escape(BEGIN) + r'.*?' + re.escape(END) + r'\n?', re.S)
RULES = ['PROCESS-NAME,rustdesk,DIRECT', 'PROCESS-NAME,rustdesk.exe,DIRECT', 'PROCESS-NAME,RustDesk,DIRECT']
BUILTIN_TARGETS = {'DIRECT', 'REJECT', 'REJECT-DROP', 'PASS', 'COMPATIBLE', 'GLOBAL'}
EVENT = re.compile(r'(?:Punch (?:tcp|udp) hole to|create_relay requested from|Connection opened from|peer address:|Hole Punched [^=\r\n]{1,128}\s*=)\s+(\[[0-9a-fA-F:]+\]|[0-9.]+):\d+', re.I)
STAMP = re.compile(r'^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?:\.\d+)? ?[+-]\d\d:\d\d)\]')

def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.rd-tmp')
    temp.write_text(data, encoding='utf-8')
    os.replace(temp, path)

def read_yaml(path):
    value = yaml.safe_load(Path(path).read_text(encoding='utf-8-sig')) or {}
    if not isinstance(value, dict):
        raise ValueError(f'Expected YAML mapping: {path}')
    return value

def proxy_names(config):
    """Individual proxies that can be used directly as a Clash rule target."""
    groups = {g.get('name') for g in config.get('proxy-groups', []) if isinstance(g, dict)}
    names, seen = [], set()
    for item in config.get('proxies', []) or []:
        name = item.get('name') if isinstance(item, dict) else None
        if (isinstance(name, str) and name and name not in groups and name not in BUILTIN_TARGETS
                and name not in seen and not re.search(r'[,\x00-\x1f\x7f]', name)):
            seen.add(name)
            names.append(name)
    return names

def public_ip(value):
    try:
        ip = ipaddress.ip_address(value.strip('[]'))
        return str(ip) if ip.is_global else None
    except ValueError:
        return None

def events(text, now, ttl):
    result = {}
    for line in text.splitlines():
        match, stamp = EVENT.search(line), STAMP.search(line)
        if not match or not stamp:
            continue
        try:
            seen = dt.datetime.fromisoformat(stamp[1]).timestamp()
        except ValueError:
            continue
        ip = public_ip(match[1])
        if ip and now - ttl <= seen <= now + 300:
            result[ip] = max(result.get(ip, 0), min(seen, now))
    return result

def default_data():
    return Layout().data


def detect_clash():
    found = []
    for root in Layout().clash_roots:
        for name in APP_NAMES:
            p = root / name
            if (p / 'profiles/Script.js').exists() and (p / 'clash-verge.yaml').exists():
                found.append(p)
    found = list(dict.fromkeys(p.resolve() for p in found))
    if len(found) != 1:
        raise ValueError('Cannot uniquely locate Clash Verge; pass --clash-dir PATH. Candidates: ' + str(found))
    return found[0]


def default_logs():
    return Layout().rustdesk_logs


def server_files():
    return Layout().rustdesk_configs


def servers():
    result = set()
    for path in server_files():
        try:
            text = path.read_text(encoding='utf-8-sig')
        except OSError:
            continue
        for value in re.findall(r'^\s*(?:rendezvous_server|custom-rendezvous-server|relay-server)\s*=\s*[\'\"]([^\'\"]+)', text, re.M):
            host = urllib.parse.urlsplit('//' + value).hostname
            if not host:
                continue
            try:
                for item in socket.getaddrinfo(host, None):
                    ip = public_ip(item[4][0])
                    if ip:
                        result.add(ip)
            except OSError:
                logging.warning('Cannot resolve RustDesk server %s', host)
    return sorted(result)

class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=15)
        self.path = path
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)

def api(config, clash, method, endpoint, body=None, override=None):
    secret = config.get('secret', '')
    if os.name != 'nt' and not override:
        paths = socket_candidates(config, clash)
        conn = None
        for path in paths:
            if not Path(path).exists():
                continue
            candidate = UnixHTTP(path)
            try:
                candidate.connect()
                conn = candidate
                break
            except OSError:
                candidate.close()
        # Retry another transport only before issuing the HTTP request.
        # A write request must never be replayed after an ambiguous response.
    else:
        conn = None
    if conn is None:
        address = override or config.get('external-controller')
        if not address and (clash / 'config.yaml').exists():
            base = read_yaml(clash / 'config.yaml')
            address = base.get('external-controller')
            secret = secret or base.get('secret', '')
        if not address:
            raise ValueError('No local Clash API. Enable a loopback external-controller or set controller in settings.json.')
        parsed = urllib.parse.urlsplit(address if '://' in address else 'http://' + address)
        if parsed.scheme not in ['http', 'https']:
            raise ValueError('Controller must use http or https')
        if parsed.hostname not in ['localhost', '127.0.0.1', '::1']:
            raise ValueError('Controller must listen on loopback; use 127.0.0.1:PORT')
        cls = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
        conn = cls(parsed.hostname, parsed.port, timeout=15)
    headers = {'Content-Type': 'application/json'}
    if secret:
        headers['Authorization'] = 'Bearer ' + str(secret)
    try:
        conn.request(method, endpoint, None if body is None else json.dumps(body), headers)
        response = conn.getresponse()
        data = response.read()
        if not 200 <= response.status < 300:
            raise RuntimeError(f'Clash API returned HTTP {response.status}')
        return json.loads(data) if data else None
    finally:
        conn.close()

def wrapper(routes, rules=None):
    if rules is None:
        rules = RULES
    return '\n' + BEGIN + '''
const __rustdeskOriginalMain = main;
main = function(config, profileName) {
  config = __rustdeskOriginalMain(config, profileName) || config;
  config.tun = config.tun || {};
  config.tun["route-exclude-address"] = [...new Set([
    ...(config.tun["route-exclude-address"] || []), ...ROUTES
  ])];
  // Rules are global but profiles have different groups/nodes. Drop rules whose
  // target is absent here instead of failing validation for the whole profile.
  const targets = new Set(["DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE", "GLOBAL",
    ...(config.proxies || []).map(p => p && p.name).filter(Boolean),
    ...(config["proxy-groups"] || []).map(g => g && g.name).filter(Boolean)]);
  const injected = RULES.filter(rule => targets.has(rule.slice(rule.lastIndexOf(",") + 1)));
  config.rules = [...injected, ...(config.rules || []).filter(r => !RULES.includes(r))];
  return config;
};
'''.replace('ROUTES', json.dumps(routes)).replace('RULES', json.dumps(rules, ensure_ascii=False)) + END + '\n'

def direct_routes(policies):
    """IP/CIDR rules that resolve to DIRECT, as TUN route exclusions.

    TUN routing works on destination addresses only, so an IP/CIDR rule can be
    excluded from TUN exactly like a learned RustDesk peer: its traffic leaves
    through the physical NIC instead of entering the TUN stack. Domain and
    process rules cannot be excluded this way.
    """
    result = []
    for rule in policies.get('domains', []) or []:
        if (not isinstance(rule, dict) or rule.get('type') not in ('IP-CIDR', 'IP-CIDR6')
                or rule.get('target') != 'DIRECT'):
            continue
        try:
            result.append(str(ipaddress.ip_network(str(rule.get('value')), strict=False)))
        except ValueError:
            continue
    return list(dict.fromkeys(result))


class Watcher:
    def __init__(self, data):
        self.data = Path(data)
        self.settings = json.loads((self.data / 'settings.json').read_text(encoding='utf-8'))
        self.clash = Path(self.settings['clash_dir'])
        self.state_path = self.data / 'state.json'
        self.state = json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists() else {'peers': {}, 'managed_routes': [], 'managed_rules': []}
        self.policies_path = self.data / "policies.json"
        self.policies = json.loads(self.policies_path.read_text(encoding="utf-8")) if self.policies_path.exists() else {"apps": [], "rustdesk_bypass": True}
        self.last_error = None
        self.offsets = {}
        self.warned = False
        self.server_cache = []
        self.server_at = 0
    def save(self):
        atomic(self.state_path, json.dumps(self.state, indent=2))
    def scan(self):
        now = time.time()
        ttl = self.settings.get('peer_ttl_days', 7) * 86400
        peers = self.state['peers']
        count = 0
        for root in self.settings['log_dirs']:
            try:
                paths = list(Path(root).rglob('*CURRENT*.log'))
                paths += list(Path(root).rglob('*current*.log'))
            except OSError:
                continue
            for path in set(paths):
                try:
                    stat = path.stat()
                    key = str(path)
                    old_inode, offset = self.offsets.get(key, (None, max(0, stat.st_size - 524288)))
                    if old_inode is not None and (old_inode != stat.st_ino or stat.st_size < offset):
                        offset = 0
                    with path.open('rb') as f:
                        f.seek(offset)
                        chunk = f.read(524288)
                        # Leave incomplete final line for the next read.
                        end = chunk.rfind(b'\n') + 1
                        self.offsets[key] = (stat.st_ino, offset + end)
                    for ip, seen in events(chunk[:end].decode('utf-8', errors='replace'), now, ttl).items():
                        peers[ip] = max(peers.get(ip, 0), seen)
                    count += 1
                except OSError:
                    continue
        if not count and not self.warned:
            logging.warning('No readable RustDesk CURRENT logs; check log_dirs in settings.json and log permissions.')
            self.warned = True
        peers = {ip: seen for ip, seen in peers.items() if now - seen <= ttl and public_ip(ip)}
        self.state['peers'] = dict(sorted(peers.items(), key=lambda x: x[1], reverse=True)[:self.settings.get('max_peers', 64)])
        if now - self.server_at > 300:
            self.server_cache = servers()
            self.server_at = now
        ips = (set(self.state['peers']) | set(self.server_cache)) if self.policies.get("rustdesk_bypass", True) else set()
        return sorted(str(ipaddress.ip_network(ip + ('/128' if ':' in ip else '/32'))) for ip in ips)
    def apply(self, routes=None, uninstall=False):
        script_path = self.clash / 'profiles/Script.js'
        config_path = self.clash / 'clash-verge.yaml'
        old_script = script_path.read_text(encoding='utf-8-sig')
        base_script = BLOCK.sub('\n', old_script).rstrip() + '\n'
        desired_rules = list(dict.fromkeys([
            f"{rule['type']},{rule['value']},{rule['target']}" for rule in self.policies.get("domains", [])
        ] + [
            f"{app['type']},{app['value']},{app['target']}" for app in self.policies.get("apps", [])
        ] + RULES))
        # Both the learned RustDesk addresses and DIRECT IP/CIDR rules bypass TUN.
        desired = [] if uninstall else list(dict.fromkeys((routes or []) + direct_routes(self.policies)))
        new_script = base_script if uninstall else base_script + wrapper(desired, desired_rules)
        config = read_yaml(config_path)
        targets = BUILTIN_TARGETS | set(proxy_names(config)) | {
            g.get('name') for g in config.get('proxy-groups', []) if isinstance(g, dict)
        }
        active_rules = [r for r in desired_rules if r.rsplit(',', 1)[-1] in targets]
        tun = config.setdefault('tun', {})
        previous = self.state.get('managed_routes', [])
        original = tun.get('route-exclude-address', []) or []
        # Only remove entries previously added by this helper.
        baseline = [r for r in original if r not in previous]
        new_routes = list(dict.fromkeys(baseline + desired))
        rules = config.get('rules', [])
        owned_rules = self.state.get('managed_rules', [])
        new_rules = [r for r in rules if r not in owned_rules]
        if not uninstall:
            new_rules = list(dict.fromkeys(active_rules + new_rules))
        changed = new_routes != original or new_rules != rules
        if not changed and new_script == old_script:
            self.save()
            return
        if not (self.data / 'Script.js.original').exists():
            atomic(self.data / 'Script.js.original', old_script)
        tun['route-exclude-address'] = new_routes
        config['rules'] = new_rules
        payload = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
        # Verify access before modifying persistent files.
        api(config, self.clash, 'GET', '/version', override=self.settings.get('controller'))
        # Persist pending ownership first, so a crash cannot lose cleanup information.
        old_state = dict(self.state)
        self.state['managed_routes'] = [r for r in desired if r not in baseline]
        baseline_rules = [r for r in rules if r not in owned_rules]
        self.state['managed_rules'] = [] if uninstall else [r for r in active_rules if r not in baseline_rules]
        self.save()
        atomic(script_path, new_script)
        try:
            if changed:
                api(config, self.clash, 'PUT', '/configs?force=true', {'payload': payload}, self.settings.get('controller'))
                atomic(config_path, payload)
        except Exception:
            atomic(script_path, old_script)
            self.state = old_state
            self.save()
            raise
        logging.info('%s: %s', 'Removed helper' if uninstall else 'Applied TUN bypass', ', '.join(desired) or '(none)')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'once', 'watch', 'uninstall', 'doctor', 'open'])
    parser.add_argument('--data-dir', type=Path, default=default_data())
    parser.add_argument('--clash-dir', type=Path)
    parser.add_argument('--log-dir', action='append', type=Path)
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(args.data_dir / 'bypass.log', maxBytes=1000000, backupCount=2, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', handlers=[handler] + ([logging.StreamHandler()] if sys.stderr else []))
    if args.action == 'init':
        path = args.data_dir / 'settings.json'
        if path.exists():
            logging.info('Keeping existing settings: %s', path)
            return
        settings = {'clash_dir': str(args.clash_dir or detect_clash()), 'log_dirs': [str(p) for p in (args.log_dir or default_logs())], 'interval_seconds': 5, 'peer_ttl_days': 7, 'max_peers': 64, 'controller': None}
        atomic(path, json.dumps(settings, indent=2, ensure_ascii=False))
        logging.info('Settings created: %s', path)
        return
    if args.action in ['doctor', 'open']:
        settings = json.loads((args.data_dir / 'settings.json').read_text(encoding='utf-8'))
        url = f"http://127.0.0.1:{settings.get('web_port', 17891)}/"
        if args.action == 'open':
            from desktop_app import main as desktop_main
            desktop_main(['--data-dir', str(args.data_dir)])
            return
        report = {'version': VERSION, 'platform': platform_name(), 'dashboard': url,
                  'data_dir': str(args.data_dir), 'clash_dir': settings['clash_dir'],
                  'readable_log_dirs': [p for p in settings['log_dirs'] if os.access(p, os.R_OK)],
                  'api_connected': False}
        try:
            clash = Path(settings['clash_dir'])
            config = read_yaml(clash / 'clash-verge.yaml')
            live = api(config, clash, 'GET', '/version', override=settings.get('controller'))
            report.update(api_connected=True, core_version=live.get('version'),
                          mode=config.get('mode', 'rule'), process_mode=config.get('find-process-mode', 'strict'))
        except Exception as exc:
            report['error'] = str(exc)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if not report['api_connected']:
            raise SystemExit(1)
        return
    # Prevent competing watchers (OS releases the lock after a crash).
    lock = (args.data_dir / 'watcher.lock').open('a+b')
    if os.name == 'nt':
        import msvcrt
        lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    w = Watcher(args.data_dir)
    if args.action == 'uninstall':
        w.apply(uninstall=True)
        return
    guard = threading.RLock()
    if args.action == 'watch':
        from traffic_web import start_server
        start_server(w, guard)
    while True:
        try:
            with guard:
                w.apply(w.scan())
                w.last_error = None
        except Exception as exc:
            w.last_error = str(exc)
            logging.error('%s', exc)
            if args.action == 'once':
                raise
        if args.action == 'once':
            return
        time.sleep(max(3, w.settings.get('interval_seconds', 5)))

if __name__ == '__main__':
    main()
