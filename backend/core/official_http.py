"""Bounded, HTTPS-only official-document fetcher. No ambient proxy or cookies."""
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, urljoin, unquote, quote
from urllib.robotparser import RobotFileParser

REGISTRY = json.loads((Path(__file__).with_name('official_sources.json')).read_text())
USER_AGENT = 'SelectChipAgent/0.2 (+official documentation research)'


class FetchError(ValueError):
    pass


def official_url(value, robots=False):
    if not isinstance(value, str) or not value or len(value) > 1000:
        raise FetchError('官网链接格式不正确')
    if re.search(r'[\x00-\x20\x7f\\]', value):
        raise FetchError('链接包含不允许的字符')
    try:
        p = urlsplit(value)
        if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
            raise FetchError('仅支持无登录信息的 HTTPS 官网链接')
        host = p.hostname or ''
    except ValueError as exc:
        raise FetchError('官网链接格式不正确') from exc
    paths = REGISTRY['hosts'].get(host)
    if not paths:
        raise FetchError('该域名不在官方来源清单中')
    path = unquote(p.path or '/')
    if '%' in path or '\\' in path or re.search(r'[\x00-\x1f\x7f]', path) or '..' in path.split('/'):
        raise FetchError('链接路径不合法')
    if host == 'github.com' and any(part in {'issues','pull','pulls','discussions'} for part in path.split('/')[3:]):
        raise FetchError('官方资料采集不包含用户讨论或拉取请求页面')
    if not (robots and path == '/robots.txt') and not any(
            prefix == '/' or path == prefix.rstrip('/') or path.startswith(prefix)
            for prefix in paths):
        raise FetchError('该路径不在官方来源清单中')
    if re.search(r'[\x00-\x1f\x7f]', unquote(p.query)):
        raise FetchError('查询参数不合法')
    return urlunsplit(('https', host, quote(path, safe="/:@-._~!$&'()*+,;="), p.query, ''))


def public_address(host):
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise FetchError('官网 DNS 解析失败') from exc
    addresses = sorted({r[4][0] for r in records})
    if not addresses or any(not ipaddress.ip_address(a).is_global or
            (':' in a and (ipaddress.ip_address(a).sixtofour or ipaddress.ip_address(a).teredo))
            for a in addresses):
        raise FetchError('拒绝访问非公网地址')
    return addresses[0]


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Use the previously validated IP; retain the hostname for SNI/certificate checks.
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


@dataclass
class Snapshot:
    url: str
    body: bytes
    content_type: str
    etag: str = ''
    last_modified: str = ''


class OfficialFetcher:
    def __init__(self, seconds=90, max_bytes=10 * 1024 * 1024):
        self.deadline = time.monotonic() + seconds
        self.max_bytes = max_bytes
        self.robots = {}
        self.last_request = {}
        self.visited_count = 0

    def remaining(self):
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise FetchError('本次联网查询达到时间上限，请缩小查询范围')
        return min(8, left)

    def _request(self, url, max_bytes):
        p = urlsplit(url)
        host = p.hostname
        delay = max(0, 1 - (time.monotonic() - self.last_request.get(host, 0)))
        if delay:
            if delay >= self.remaining():
                raise FetchError('本次查询达到时间上限')
            time.sleep(delay)
        address = public_address(host)
        connection = PinnedHTTPSConnection(host, address, self.remaining())
        try:
            self.last_request[host] = time.monotonic()
            connection.request('GET', urlunsplit(('', '', p.path or '/', p.query, '')),
                headers={'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity',
                         'Accept': 'text/html,application/pdf,text/plain,application/xhtml+xml'})
            response = connection.getresponse()
            headers = {k.lower(): v for k, v in response.getheaders()}
            if response.status != 200:
                return response.status, headers, b''
            if headers.get('content-encoding', 'identity').lower() not in ('', 'identity'):
                raise FetchError('官网返回不支持的压缩格式')
            length = headers.get('content-length', '')
            if length and (not length.isdigit() or int(length) > max_bytes):
                raise FetchError('官网资料超过大小限制')
            parts, total = [], 0
            while True:
                remaining = self.remaining()
                if connection.sock:
                    connection.sock.settimeout(remaining)
                part = response.read1(min(65536, max_bytes + 1 - total))
                if not part:
                    break
                total += len(part)
                if total > max_bytes:
                    raise FetchError('官网资料超过大小限制')
                parts.append(part)
            return response.status, headers, b''.join(parts)
        except (OSError, http.client.HTTPException) as exc:
            raise FetchError('官网连接失败或超时，请稍后重试') from exc
        finally:
            connection.close()

    def _robot_policy(self, url):
        host = urlsplit(url).hostname
        if host not in self.robots:
            robot_url = f'https://{host}/robots.txt'
            for _ in range(4):
                robot_url = official_url(robot_url, robots=True)
                status, headers, body = self._request(robot_url, 256 * 1024)
                if status in (301, 302, 303, 307, 308):
                    target = official_url(urljoin(robot_url, headers.get('location', '')), robots=True)
                    if urlsplit(target).hostname != host or urlsplit(target).path != '/robots.txt':
                        raise FetchError('robots 跳转需要人工核对')
                    robot_url = target
                    continue
                if status in (404, 410):
                    body = b'User-agent: *\nAllow: /'
                elif status != 200:
                    raise FetchError('无法确认官网 robots 规则，已停止自动采集')
                parser = RobotFileParser()
                parser.parse(body.decode('utf-8', errors='replace').splitlines())
                self.robots[host] = parser
                break
            else:
                raise FetchError('robots 跳转过多')
        parser = self.robots[host]
        if not parser.can_fetch(USER_AGENT, url):
            raise FetchError('官网 robots 规则不允许自动采集该页面')
        delay = parser.crawl_delay(USER_AGENT) or 1
        rate = parser.request_rate(USER_AGENT)
        if rate:
            delay = max(delay, rate.seconds / rate.requests)
        wait = delay - (time.monotonic() - self.last_request.get(host, 0))
        if wait > 0:
            if wait >= self.deadline - time.monotonic():
                raise FetchError('官网抓取间隔超出当前任务预算，请稍后重试')
            time.sleep(wait)

    def fetch(self, url):
        for _ in range(4):
            url = official_url(url)
            self.remaining()
            self._robot_policy(url)
            status, headers, body = self._request(url, self.max_bytes)
            if status in (301, 302, 303, 307, 308):
                location = headers.get('location')
                if not location:
                    raise FetchError('官网跳转缺少目标地址')
                url = urljoin(url, location)
                continue
            if status != 200:
                raise FetchError(f'官网返回 HTTP {status}')
            content_type = headers.get('content-type', '').split(';')[0].lower()
            if body.startswith(b'%PDF-'):
                content_type = 'application/pdf'
            if content_type not in ('text/html', 'application/xhtml+xml', 'application/pdf', 'text/plain', 'text/markdown'):
                raise FetchError('仅支持官网 HTML、PDF 或文本资料')
            self.visited_count += 1
            return Snapshot(url, body, content_type, headers.get('etag', '')[:300], headers.get('last-modified', '')[:100])
        raise FetchError('官网跳转次数过多')
