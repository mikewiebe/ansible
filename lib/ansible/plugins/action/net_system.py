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

from ansible.plugins.action.network_base import ActionModule as _ActionModule
from ansible.utils.path import unfrackpath
from ansible.plugins import connection_loader
from ansible.module_utils.basic import AnsibleFallbackNotFound
from ansible.module_utils.six import iteritems
from ansible.module_utils._text import to_bytes
from ansible.utils.network import get_implementation_module
from importlib import import_module

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


class ActionModule(_ActionModule):
    def run(self, tmp=None, task_vars=None):
        result = super(ActionModule, self).run(tmp, task_vars)

        module = get_implementation_module(self.pc.network_os, 'net_system')

        if not module:
            result['failed'] = True
            result['msg'] = 'Could not find net_system implementation module for %s' % self.pc.network_os
        else:
            new_module_args = self._task.args.copy()
            if 'network_os' in new_module_args:
                del new_module_args['network_os']

            display.vvvv('Running implementation module %s' % module)
            result.update(self._execute_module(module_name=module,
                module_args=new_module_args, task_vars=task_vars,
                wrap_async=self._task.async))

        display.vvvv('Caching network OS %s in facts' % self.pc.network_os)
        result['ansible_facts'] = {'network_os': self.pc.network_os}

        return result

    def _get_network_os(self, task_vars):
        if ('network_os' in self._task.args and self._task.args['network_os']):
            display.vvvv('Getting network OS from task argument')
            network_os = self._task.args['network_os']
        elif ('network_os' in task_vars['ansible_facts'] and
                task_vars['ansible_facts']['network_os']):
            display.vvvv('Getting network OS from fact')
            network_os = task_vars['ansible_facts']['network_os']
        else:
            display.vvvv('Getting network OS from net discovery')
            network_os = None

        return network_os

    def _get_socket_path(self, play_context):
        ssh = connection_loader.get('ssh', class_only=True)
        cp = ssh._create_control_path(play_context.remote_addr, play_context.port, play_context.remote_user)
        path = unfrackpath("$HOME/.ansible/pc")
        return cp % dict(directory=path)

    def load_provider(self, network_os):
        module = import_module('ansible.module_utils.' + network_os)
        argspec = getattr(module, network_os + '_argument_spec')

        provider = self._task.args.get('provider', {})
        for key, value in iteritems(argspec):
            if key != 'provider' and key not in provider:
                if key in self._task.args:
                    provider[key] = self._task.args[key]
                elif 'fallback' in value:
                    provider[key] = self._fallback(value['fallback'])
                elif key not in provider:
                    provider[key] = None
        return provider
