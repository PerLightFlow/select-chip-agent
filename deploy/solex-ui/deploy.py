#!/usr/bin/env python3
"""Release only the native frontend. Never print credentials or response bodies."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
from urllib import request

ROOT = Path('/data/solexai/yongjun/weknora-native')
SOURCE = Path(__file__).resolve().parent
NATIVE_PROJECT = 'weknora-native'
NETWORK = 'weknora-native'
PUBLIC_URL = 'http://192.168.85.199:8080'
CANARY_URL = 'http://127.0.0.1:18084'
EXPECTED_OTHERS = {'app', 'postgres', 'redis', 'docreader', 'embedding', 'searxng'}
RUNTIME_KEYS = {'APP_HOST', 'APP_PORT', 'APP_SCHEME', 'DEFAULT_LOCALE', 'MAX_FILE_SIZE_MB', 'MAX_SKILL_BUNDLE_SIZE_MB'}


def command(*args, timeout=120):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Docker/Compose error output can echo interpolated configuration.
        raise RuntimeError(f'{args[0]} command failed (exit {result.returncode}); output omitted')
    return result.stdout.strip()


def private_write(path, value):
    path = Path(path)
    if path.is_symlink() or path.parent.resolve() != path.parent.absolute():
        raise RuntimeError('Refusing a symbolic link in deployment state')
    temporary = path.with_name(path.name + '.pending')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(value if isinstance(value, bytes) else value.encode())
    temporary.replace(path)


def save_json(path, data):
    private_write(path, json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def image_setting(raw):
    matches = re.findall(rb'(?m)^WEKNORA_UI_IMAGE=([^\r\n]*)', raw)
    if len(matches) != 1:
        raise RuntimeError('Expected one frontend image setting; environment left unchanged')
    words = shlex.split(matches[0].decode(), comments=True)
    if len(words) != 1:
        raise RuntimeError('Invalid frontend image setting')
    return words[0]


def replace_image_setting(raw, image):
    image_setting(raw)
    if not re.fullmatch(r'[a-zA-Z0-9._/@:+-]+', image):
        raise RuntimeError('Invalid frontend image reference')
    return re.sub(rb'(?m)^WEKNORA_UI_IMAGE=[^\r\n]*', b'WEKNORA_UI_IMAGE=' + image.encode(), raw)


def dist_digest(directory):
    digest = hashlib.sha256()
    for path in sorted(Path(directory).rglob('*')):
        if path.is_symlink():
            raise RuntimeError('Frontend artifacts must not contain symbolic links')
        if path.is_file():
            digest.update(path.relative_to(directory).as_posix().encode() + b'\0')
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


class PageAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title = ''
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title':
            self.in_title = True
        asset = attrs.get('src', '') if tag == 'script' else attrs.get('href', '') if tag == 'link' else ''
        if asset.startswith('/assets/'):
            self.assets.append(asset)

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False

    def handle_data(self, value):
        if self.in_title:
            self.title += value


def check_ui(base, branded=True):
    opener = request.build_opener(request.ProxyHandler({}))
    with opener.open(base + '/login', timeout=10) as response:
        page = response.read().decode()
    parsed = PageAssets()
    parsed.feed(page)
    if branded and (not parsed.title.startswith('SOLEX') or 'weknora' in parsed.title.lower()):
        raise RuntimeError('Frontend title did not match SOLEX')
    if not parsed.assets:
        raise RuntimeError('Frontend contains no compiled application assets')
    for path in parsed.assets:
        if '?' in path or '#' in path or '..' in path or not re.fullmatch(r'/assets/[a-zA-Z0-9._/-]+', path):
            raise RuntimeError('Unexpected asset path')
        with opener.open(base + path, timeout=10) as response:
            if 'html' in response.headers.get('Content-Type', '') or not response.read(128):
                raise RuntimeError('Frontend asset delivery failed')
    with opener.open(base + '/api/v1/auth/config', timeout=10) as response:
        config = json.load(response)
    if not isinstance(config, dict) or config.get('success') is False or 'registration_mode' not in config:
        raise RuntimeError('Frontend authentication API proxy failed')
    return config


def wait_ui(base, branded=True, expected_config=None, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            config = check_ui(base, branded)
            if expected_config is not None and config != expected_config:
                raise RuntimeError('Public authentication configuration changed')
            return
        except (OSError, ValueError, RuntimeError):
            time.sleep(2)
    raise RuntimeError('Frontend login/assets/API verification timed out')


def native_containers():
    ids = command('docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=' + NATIVE_PROJECT).split()
    if not ids:
        raise RuntimeError('Native deployment is missing')
    result = json.loads(command('docker', 'inspect', *ids))
    return {item['Config']['Labels'].get('com.docker.compose.service'): item for item in result}


def service_snapshot(containers):
    others = {service: item for service, item in containers.items() if service != 'frontend'}
    if set(others) != EXPECTED_OTHERS:
        raise RuntimeError('Unexpected native service inventory')
    snapshot = {}
    for service, item in others.items():
        state = item['State']
        if not state.get('Running') or state.get('Health', {}).get('Status') == 'unhealthy':
            raise RuntimeError('A native backend service is not healthy; no frontend cutover')
        snapshot[service] = {'id': item['Id'], 'image': item['Image'], 'started_at': state['StartedAt'], 'restart_count': item['RestartCount']}
    return snapshot


def assert_other_services(before):
    if service_snapshot(native_containers()) != before:
        raise RuntimeError('Another native service changed during frontend release')


def assert_frontend_image(expected):
    frontend = native_containers().get('frontend')
    if not frontend or not frontend['State'].get('Running') or frontend['Image'] != expected:
        raise RuntimeError('Running frontend image does not match the release')


def compose_frontend():
    command('docker', 'compose', '--project-directory', str(ROOT), 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'frontend', timeout=180)


def metadata():
    meta = json.loads((SOURCE / 'release.json').read_text())
    release_id = meta.get('release_id', '')
    if not re.fullmatch(r'solex-ui-[a-f0-9]{16}', release_id):
        raise RuntimeError('Invalid release identifier')
    if meta.get('image') != 'solex/solex-ui:' + release_id.removeprefix('solex-ui-'):
        raise RuntimeError('Unexpected SOLEX image tag')
    if not re.fullmatch(r'wechatopenai/weknora-ui@sha256:[a-f0-9]{64}', meta.get('runtime_image', '')):
        raise RuntimeError('A pinned frontend runtime is required')
    if not re.fullmatch(r'[a-f0-9]{40,64}', meta.get('source_revision', '')):
        raise RuntimeError('A full source revision is required')
    if dist_digest(SOURCE / 'dist') != meta.get('dist_sha256'):
        raise RuntimeError('Frontend artifact digest mismatch')
    page = PageAssets()
    page.feed((SOURCE / 'dist/index.html').read_text())
    if not page.title.startswith('SOLEX') or not page.assets:
        raise RuntimeError('Expected a built SOLEX frontend')
    return meta


def build_image(meta):
    # No registry pulls or dependency installation during the release.
    command('docker', 'image', 'inspect', meta['runtime_image'])
    command('docker', 'build', '--pull=false', '--network=none',
            '--build-arg', 'RUNTIME_IMAGE=' + meta['runtime_image'],
            '--build-arg', 'RELEASE_ID=' + meta['release_id'],
            '--build-arg', 'SOURCE_REVISION=' + meta['source_revision'],
            '-t', meta['image'], str(SOURCE), timeout=600)
    return json.loads(command('docker', 'image', 'inspect', meta['image']))[0]['Id']


def remove_canary(meta):
    name = meta['release_id'] + '-canary'
    ids = command('docker', 'ps', '-aq', '--filter', 'name=^/' + name + '$').split()
    if not ids:
        return
    item = json.loads(command('docker', 'inspect', ids[0]))[0]
    labels = item['Config'].get('Labels') or {}
    if labels.get('io.solex.ui.canary') != meta['release_id']:
        raise RuntimeError('Canary name belongs to an unrelated container')
    command('docker', 'rm', '-f', item['Id'])


def start_canary(meta, frontend):
    remove_canary(meta)
    args = ['docker', 'run', '-d', '--name', meta['release_id'] + '-canary',
            '--label', 'io.solex.ui.canary=' + meta['release_id'],
            '--network', NETWORK, '-p', '127.0.0.1:18084:80']
    settings = dict(item.split('=', 1) for item in frontend['Config']['Env'] if '=' in item)
    for key in sorted(RUNTIME_KEYS):
        if key in settings:
            args.extend(['-e', key + '=' + settings[key]])
    command(*args, meta['image'])


def release(canary_only=False):
    if ROOT.resolve() != ROOT.absolute() or not (ROOT / 'active.json').is_file():
        raise RuntimeError('Expected the active native deployment')
    meta = metadata()
    env_path = ROOT / '.env'
    if env_path.is_symlink():
        raise RuntimeError('Refusing a symbolic deployment environment')
    original_env = env_path.read_bytes()
    old_image = image_setting(original_env)
    containers = native_containers()
    frontend = containers.get('frontend')
    if not frontend or not frontend['State'].get('Running'):
        raise RuntimeError('Current frontend is not running')
    before = service_snapshot(containers)
    current_config = check_ui(PUBLIC_URL, branded=False)
    prior_image_id = json.loads(command('docker', 'image', 'inspect', old_image))[0]['Id']
    if frontend['Image'] != prior_image_id:
        raise RuntimeError('Current frontend does not match its saved image setting')
    state_dir = ROOT / 'ui-releases' / meta['release_id']
    if state_dir.parent.resolve() != state_dir.parent.absolute():
        raise RuntimeError('Refusing a symbolic release history directory')
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if state_dir.resolve() != state_dir.absolute():
        raise RuntimeError('Refusing a symbolic release state directory')
    existing_gate = state_dir / 'acceptance.json'
    if old_image == meta['image'] and existing_gate.is_file():
        previous = json.loads(existing_gate.read_text())
        if previous.get('passed') and previous.get('image_id') == frontend['Image']:
            wait_ui(PUBLIC_URL, expected_config=current_config)
            assert_other_services(before)
            print('This SOLEX frontend release is already active; its original rollback backup is retained.')
            return
    state = {'release_id': meta['release_id'], 'image': meta['image'], 'old_image': old_image,
             'old_image_id': prior_image_id, 'source_revision': meta['source_revision'],
             'dist_sha256': meta['dist_sha256'], 'other_services': before, 'timestamp': time.time()}
    switched = False
    canary_passed = False
    new_env = replace_image_setting(original_env, meta['image'])
    try:
        print('1/3 Building the SOLEX frontend from verified static artifacts.', flush=True)
        state['image_id'] = build_image(meta)
        start_canary(meta, frontend)
        wait_ui(CANARY_URL, expected_config=current_config)
        assert_other_services(before)
        state['canary_passed'] = True
        canary_passed = True
        if canary_only:
            save_json(state_dir / 'canary.json', state)
            print('SOLEX canary is ready on server loopback port 18084; public entry is unchanged.')
            return
        print('2/3 Canary passed; replacing only the frontend container.', flush=True)
        if env_path.read_bytes() != original_env:
            raise RuntimeError('Deployment environment changed during canary checks')
        private_write(state_dir / 'env.before', original_env)
        private_write(state_dir / 'env.after', new_env)
        save_json(state_dir / 'state.json', state)
        private_write(env_path, new_env)
        switched = True
        compose_frontend()
        wait_ui(PUBLIC_URL, expected_config=current_config)
        assert_frontend_image(state['image_id'])
        assert_other_services(before)
        state.update(passed=True, completed_at=time.time(), public_url=PUBLIC_URL)
        save_json(state_dir / 'acceptance.json', state)
        save_json(ROOT / 'solex-ui-active.json', state)
        print('3/3 SOLEX frontend is active; all six backend containers are unchanged.')
    except BaseException:
        if switched:
            if env_path.read_bytes() != new_env:
                raise RuntimeError('Release failed; environment changed externally, automatic restore refused') from None
            private_write(env_path, original_env)
            compose_frontend()
            wait_ui(PUBLIC_URL, branded=False, expected_config=current_config)
            assert_frontend_image(prior_image_id)
            assert_other_services(before)
            state.update(passed=False, rolled_back=True, completed_at=time.time())
            save_json(state_dir / 'acceptance.json', state)
            print('Frontend release failed; the previous image and environment were restored.')
        raise
    finally:
        if not canary_only or not canary_passed:
            remove_canary(meta)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['apply', 'canary'])
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('Use the approved root release helper')
    release(canary_only=args.action == 'canary')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        message = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        raise SystemExit('SOLEX frontend release failed: ' + message) from None
