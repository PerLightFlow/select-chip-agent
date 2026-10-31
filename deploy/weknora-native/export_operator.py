#!/usr/bin/env python3
"""Give the SSH operator only the deployment evidence and initial login details."""
import json
import os
from pathlib import Path
import pwd

from common import ROOT, save_json


def export_operator(root, destination, uid, gid):
    root, destination = Path(root), Path(destination)
    if destination.resolve() != destination.absolute():
        raise ValueError('Operator output directory must not contain symbolic links')
    acceptance = json.loads((root / 'acceptance.json').read_text())
    active = json.loads((root / 'active.json').read_text())
    if acceptance.get('passed') is not True or active.get('url') != 'http://192.168.85.199:8080':
        raise ValueError('Successful deployment evidence is required before exporting login details')
    admin = json.loads((root / 'admin.json').read_text())
    invitation = admin.get('invitation', {})
    login = {key: admin[key] for key in ('email', 'password')}
    login['invitation'] = {key: invitation[key] for key in ('invite_url', 'expires_at')
                           if key in invitation}
    destination.mkdir(mode=0o700, parents=False, exist_ok=True)
    os.chmod(destination, 0o700)
    for name, value in [('acceptance.json', acceptance), ('active.json', active), ('login.json', login)]:
        path = destination / name
        save_json(path, value)
        os.chown(path, uid, gid)
    os.chown(destination, uid, gid)


if __name__ == '__main__':
    operator = pwd.getpwnam('solexai1')
    export_operator(ROOT, Path(__file__).parent / 'operator', operator.pw_uid, operator.pw_gid)
