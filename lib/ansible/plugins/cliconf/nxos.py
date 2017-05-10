#
# (c) 2016 Red Hat Inc.
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
#
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import re

from itertools import chain

from ansible.plugins.cliconf import CliconfBase, enable_mode
from ansible.errors import AnsibleConnectionFailure
from ansible.module_utils.network_common import to_list


class Cliconf(CliconfBase):

    cliconf_stdout_re = [
        re.compile(r'[\r\n]?[a-zA-Z]{1}[a-zA-Z0-9-]*[>|#|%](?:\s*)$'),
        re.compile(r'[\r\n]?[a-zA-Z]{1}[a-zA-Z0-9-]*\(.+\)#(?:\s*)$')
    ]

    cliconf_stderr_re = [
        re.compile(r"% ?Error"),
        re.compile(r"^% \w+", re.M),
        re.compile(r"% ?Bad secret"),
        re.compile(r"invalid input", re.I),
        re.compile(r"(?:incomplete|ambiguous) command", re.I),
        re.compile(r"connection timed out", re.I),
        re.compile(r"[^\r\n]+ not found", re.I),
        re.compile(r"'[^']' +returned error code: ?\d+"),
        re.compile(r"syntax error"),
        re.compile(r"unknown command"),
        re.compile(r"user not present")
    ]

    def _on_open_shell(self):
        try:
            for cmd in ('cliconf length 0', 'cliconf width 511'):
                self.send_command(cmd)
        except AnsibleConnectionFailure:
            raise AnsibleConnectionFailure('unable to set cliconf parameters')

    @enable_mode
    def get_config(self, source='running'):
        lookup = {'running': 'running-config', 'startup': 'startup-config'}
        output = self.send_command('show %s' % lookup[source])
        return str(output).strip()

    @enable_mode
    def edit_config(self, commands):
        for command in chain(['configure'], to_list(commands), ['end']):
            self.send_command(command)
