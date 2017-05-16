# (c) 2015, Ansible Inc,
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import sys
import copy

from ansible.plugins.action import ActionBase
from ansible.utils.path import unfrackpath
from ansible.plugins import connection_loader
from ansible.module_utils.basic import AnsibleFallbackNotFound
from ansible.module_utils.six import iteritems
from ansible.module_utils._text import to_bytes

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


class ActionModule(ActionBase):
    def run(self, tmp=None, task_vars=None):
        if self._play_context.connection != 'local':
            return dict(
                failed=True,
                msg='invalid connection specified, expected connection=local, '
                    'got %s' % self._play_context.connection
            )

        self.provider = self.load_provider('ios')

        self.pc = copy.deepcopy(self._play_context)
        self.pc.network_os = self.pc.network_os or self._get_network_os(task_vars)
        self.pc.connection = 'network_cli'
        self.pc.remote_addr = self.provider['host'] or self._play_context.remote_addr
        self.pc.port = self.provider['port'] or self._play_context.port or 22
        self.pc.remote_user = self.provider['username'] or self._play_context.connection_user
        self.pc.password = self.provider['password'] or self._play_context.password
        self.pc.private_key_file = self.provider['ssh_keyfile'] or self._play_context.private_key_file
        self.pc.timeout = self.provider['timeout'] or self._play_context.timeout
        self.pc.become = self.provider['authorize'] or False
        self.pc.become_pass = self.provider['auth_pass']

        display.vvv('using connection plugin %s' % self.pc.connection, self.pc.remote_addr)
        connection = self._shared_loader_obj.connection_loader.get('persistent',
                self.pc, sys.stdin)

        socket_path = self._get_socket_path(self.pc)
        display.vvvv('socket_path: %s' % socket_path, self.pc.remote_addr)

        if not os.path.exists(socket_path):
            # start the connection if it isn't started
            rc, out, err = connection.exec_command('open_shell()')
            display.vvvv('open_shell() returned %s %s %s' % (rc, out, err))
            if not rc == 0:
                return {'failed': True,
                        'msg': 'unable to open shell. Please see: ' +
                               'https://docs.ansible.com/ansible/network_debug_troubleshooting.html#unable-to-open-shell',
                        'rc': rc}
        else:
            # make sure we are in the right cli context which should be
            # enable mode and not config module
            rc, out, err = connection.exec_command('prompt()')
            if str(out).strip().endswith(')#'):
                display.vvvv('wrong context, sending exit to device', self._play_context.remote_addr)
                connection.exec_command('exit')

        task_vars['ansible_socket'] = socket_path

        if self._play_context.become_method == 'enable':
            self._play_context.become = False
            self._play_context.become_method = None

        result = super(ActionModule, self).run(tmp, task_vars)

        return result

    def _get_network_os(self, task_vars):
        pass

    def load_provider(self, network_os):
        pass

    def _fallback(self, fallback):
        strategy = fallback[0]
        args = []
        kwargs = {}

        for item in fallback[1:]:
            if isinstance(item, dict):
                kwargs = item
            else:
                args = item
        try:
            return strategy(*args, **kwargs)
        except AnsibleFallbackNotFound:
            pass
