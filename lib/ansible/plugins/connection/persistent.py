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

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import pty
import subprocess
import sys
import uuid
import json

from functools import partial

from ansible.module_utils._text import to_bytes
from ansible.module_utils.six.moves import cPickle, StringIO
from ansible.plugins.connection import ConnectionBase
from ansible.errors import AnsibleError

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


class Connection(ConnectionBase):
    ''' Local based connections '''

    transport = 'persistent'
    has_pipelining = False

    def __getattr__(self, name):
        try:
            return self.__dict__[name]
        except KeyError:
            if name.startswith('_'):
                raise AttributeError("'%s' object has no attribute '%s'" % (self.__class__.__name__, name))
            return partial(self._do_rpc, name)

    def _connect(self):
        self._connected = True
        return self

    def _do_rpc(self, name, *args, **kwargs):
        reqid = str(uuid.uuid4())
        req = {'jsonrpc': '2.0', 'method': name, 'id': reqid}

        params = list(args) or kwargs or None
        if params:
            req['params'] = params

        display.display('sending %s' % req, log_only=True)

        (rc, out, err) = self.exec_command(json.dumps(req))

        display.display('received %s %s %s' % (rc, out, err), log_only=True)

        try:
            reply = json.loads(out)
        except ValueError as exc:
            raise AnsibleError(err)

        if reply['id'] != reqid:
            raise AnsiblError('invalid id received')

        if 'error' in reply:
            msg = reply['error'].get('data') or reply['error']['message']
            raise AnsibleError(msg)

        return reply['result']

    def _do_it(self, action):

        master, slave = pty.openpty()
        p = subprocess.Popen(["ansible-connection"], stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdin = os.fdopen(master, 'wb', 0)
        os.close(slave)

        src = StringIO()
        cPickle.dump(self._play_context.serialize(), src)
        stdin.write(src.getvalue())
        src.close()

        stdin.write(b'\n#END_INIT#\n')
        stdin.write(to_bytes(action))
        stdin.write(b'\n\n')
        stdin.close()
        (stdout, stderr) = p.communicate()

        return (p.returncode, stdout, stderr)

    def exec_command(self, cmd, in_data=None, sudoable=True):
        super(Connection, self).exec_command(cmd, in_data=in_data, sudoable=sudoable)
        return self._do_it('EXEC: ' + cmd)

    def put_file(self, in_path, out_path):
        super(Connection, self).put_file(in_path, out_path)
        self._do_it('PUT: %s %s' % (in_path, out_path))

    def fetch_file(self, in_path, out_path):
        super(Connection, self).fetch_file(in_path, out_path)
        self._do_it('FETCH: %s %s' % (in_path, out_path))

    def close(self):
        self._connected = False
