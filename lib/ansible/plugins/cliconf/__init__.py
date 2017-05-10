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
import signal

from abc import ABCMeta, abstractmethod
from functools import wraps

from ansible.errors import AnsibleConnectionFailure
from ansible.module_utils.six import with_metaclass


def enable_mode(func):
    @wraps(func)
    def wrapped(self, *args, **kwargs):
        prompt = self.get_prompt()
        if not str(prompt).strip().endswith('#'):
            raise AnsibleError('operation requires privilege escalation')
        return func(self, *args, **kwargs)
    return wrapped


class CliconfBase(with_metaclass(ABCMeta, object)):

    # compiled regular expression as stdout
    terminal_stdout_re = []

    # compiled regular expression as stderr
    terminal_stderr_re = []

    # compiled regular expression to remove ANSI codes
    terminal_ansi_re = [
        re.compile(r'(\x1b\[\?1h\x1b=)'),
        re.compile(r'\x08.')
    ]

    def __init__(self, connection):
        self._connection = connection

    def _alarm_handler(self, signum, frame):
        raise AnsibleConnectionFailure('timeout waiting for command to complete')

    def start(self, timeout=30):
        """Start the connection to the remote device

        This method will open the connection to the remote device over SSH
        if it hasn't already been done.  If the connection is already open,
        subsequent calls to this method will be a noop
        """
        display.display('calling start(timeout=%s)' % timeout, log_only=True)
        while bool(timeout):
            display.display('checking if connection has started', log_only=True)
            if self._connection.connected:
                return
            timeout -= 1
            time.sleep(1)
        else:
            raise AnsibleConnectionFailure('time out waiting for connection to establish')

    def send_command(self, command, prompts=None, answer=None, send_only=False, timeout=30):
        """Executes a cli command and returns the results

        This method will execute the CLI command on the connection and return
        the results to the caller.  The command output will be returned as a
        string
        """
        signal.signal(signal.SIGALRM, self._alarm_handler)
        signal.alarm(timeout)
        resp = self._connection.send(command, prompts, answer, send_only)
        signal.alarm(0)
        return resp

    def get_prompt(self):
        """ Returns the current prompt from the device"""
        return self._connection._matched_prompt

    def _on_open_shell(self):
        """Called after the SSH session is established

        This method is called right after the invoke_shell() is called from
        the Paramiko SSHClient instance.  It provides an opportunity to setup
        cliconf parameters such as disbling paging for instance.
        """
        pass

    def _on_close_shell(self):
        """Called before the connection is closed

        This method gets called once the connection close has been requested
        but before the connection is actually closed.  It provides an
        opportunity to clean up any cliconf resources before the shell is
        actually closed
        """
        pass

    def _on_authorize(self, passwd=None):
        """Called when privilege escalation is requested

        This method is called when the privilege is requested to be elevated
        in the play context by setting become to True.  It is the responsibility
        of the cliconf plugin to actually do the privilege escalation such
        as entering `enable` mode for instance
        """
        pass

    def _on_deauthorize(self):
        """Called when privilege deescalation is requested

        This method is called when the privilege changed from escalated
        (become=True) to non escalated (become=False).  It is the responsibility
        of the this method to actually perform the deauthorization procedure
        """
        pass

    @abstractmethod
    def get_config(self, source='running'):
        """Retrieves the specified configuration from the device

        This method will retrieve the configuration specified by source and
        return it to the caller as a string.  Subsequent calls to this method
        will retrieve a new configuration from the device
        """
        pass

    @abstractmethod
    def edit_config(self, commands):
        """Loads the specified commands into the remote device

        This method will load the commands into the remote device.  This
        method will make sure the device is in the proper context before
        send the commands (eg config mode)
        """
        pass
