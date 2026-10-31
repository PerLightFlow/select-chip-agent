#!/usr/bin/env python3
"""Run only in the operator's terminal, never through deployment logs."""
import json
from pathlib import Path

state = json.loads((Path(__file__).parent / 'operator/login.json').read_text())
print('地址：http://192.168.85.199:8080')
print('管理员邮箱：' + state['email'])
print('管理员密码：' + state['password'])
print('请在登录后修改密码；不要把此输出发送到聊天。')
invitation = state.get('invitation', {})
if invitation.get('invite_url'):
    print('员工注册邀请：' + invitation['invite_url'])
    print('邀请有效期：' + str(invitation.get('expires_at', '见空间成员管理页面')))
