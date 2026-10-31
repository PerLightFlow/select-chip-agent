#!/usr/bin/env python3
"""Switch only the two known project stacks, retain old volumes for rollback."""
import argparse
import json
import subprocess
import time

from common import ROOT, read_env, save_env, save_json
from acceptance import check_ui

OLD_PROJECTS = ('select-chip-agent-yongjun', 'select-chip-weknora')


def command(*args, capture=False):
    if capture:
        return subprocess.check_output(args, text=True).strip()
    subprocess.run(args, check=True)


def compose(*args):
    return command('docker', 'compose', '--project-directory', str(ROOT), *args)


def restore(state):
    compose('stop', 'frontend')
    env = read_env(ROOT / '.env')
    env.update(UI_BIND='127.0.0.1', UI_PORT='18082')
    save_env(ROOT / '.env', env)
    if state['old_running_ids']:
        command('docker', 'start', *state['old_running_ids'])
    compose('up', '-d', '--no-deps', '--no-build', 'frontend')
    (ROOT / 'active.json').unlink(missing_ok=True)
    print('Old containers restarted; native frontend is back on loopback port 18082.')


def switch():
    gate = json.loads((ROOT / 'acceptance.json').read_text())
    if gate.get('passed') is not True or time.time() - gate['timestamp'] > 3600:
        raise RuntimeError('A successful native smoke gate from the last hour is required')
    credentials = json.loads((ROOT / 'admin.json').read_text())
    if not credentials.get('team_registration_configured'):
        raise RuntimeError('Team registration must be configured before cutover')
    old_ids = []
    for project in OLD_PROJECTS:
        old_ids.extend(command('docker', 'ps', '-q', '--filter',
                               'label=com.docker.compose.project=' + project, capture=True).split())
    all_ids = command('docker', 'ps', '-q', capture=True).split()
    if all_ids:
        containers = json.loads(command('docker', 'inspect', *all_ids, capture=True))
        for c in containers:
            owns_port = any(p.get('HostPort') == '8080' for bindings in
                           c['NetworkSettings']['Ports'].values() for p in (bindings or []))
            if owns_port and not any(c['Id'].startswith(i) for i in old_ids):
                raise RuntimeError('Port 8080 belongs to an unrecognized container; no changes made')
    state = {'old_running_ids': old_ids, 'timestamp': time.time()}
    save_json(ROOT / 'cutover.json', state)
    try:
        if old_ids:
            command('docker', 'stop', '--time', '30', *old_ids)
        env = read_env(ROOT / '.env')
        env.update(UI_BIND='192.168.85.199', UI_PORT='8080')
        save_env(ROOT / '.env', env)
        compose('up', '-d', '--no-deps', '--no-build', 'frontend')
        for attempt in range(30):
            try:
                check_ui('http://192.168.85.199:8080')
                break
            except (OSError, ValueError, RuntimeError):
                if attempt == 29:
                    raise
                time.sleep(2)
        save_json(ROOT / 'active.json', {'url': 'http://192.168.85.199:8080',
                  'version': 'v0.9.0', 'timestamp': time.time(), 'capacity_accepted': False})
    except BaseException:
        restore(state)
        raise
    print('Native WeKnora is active at http://192.168.85.199:8080')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('switch', 'rollback'))
    args = parser.parse_args()
    if args.action == 'rollback':
        restore(json.loads((ROOT / 'cutover.json').read_text()))
    else:
        switch()
