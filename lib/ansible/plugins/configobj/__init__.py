#
# Copyright (c) 2014-2017 Cisco and/or its affiliates.
# Copyright (c) 2017 Red Hat, Inc.
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
import os
import re
import copy
import operator
import collections

from ansible.template import Templar
from ansible.playbook.base import BaseMeta
from ansible.playbook.attribute import Attribute
from ansible.parsing.dataloader import DataLoader
from ansible.module_utils.network_common import dict_combine
from ansible.module_utils.six import iteritems, with_metaclass
from ansible.errors import AnsibleError, AnsibleUndefinedVariable

class ConfigAttr(with_metaclass(BaseMeta, object)):

    # descriptors
    _name = Attribute(isa='string')
    _kind = Attribute(isa='string', default='str')
    _default_value = Attribute(isa='string')
    _load_order = Attribute(isa='int')
    _multiple = Attribute(isa='boo', default=False)

    # templatable values
    _get_value = Attribute(isa='string')
    _set_value = Attribute(isa='string')
    _del_value = Attribute(isa='string')

    # cli getters
    _get_command = Attribute(isa='string')
    _get_context = Attribute(isa='string')

    # cli setters
    _set_command = Attribute(isa='string')
    _set_context = Attribute(isa='string')
    _set_items = Attribute(isa='list')

    def __init__(self):
        self._attributes = self._attributes.copy()

    def load_data(self, ds):
        assert ds is not None

        setattr(self, '_ds', ds)

        for name, attr in sorted(iteritems(self._valid_attrs), key=operator.itemgetter(1)):
            if name in ds:
                method = getattr(self, '_load_%s' % name, None)
                if method:
                    self._attributes[name] = method(name, ds[name])
                else:
                    self._attributes[name] = ds[name]

        return self


class ConfigObject(collections.Mapping):

    def __init__(self, data_format='cli', platform=None, base_dir=None):

        assert data_format in ('cli',)

        self.data_format = data_format
        self.platform = platform
        self.base_dir = None
        self._loader = None
        self._attributes = {}
        self._commands = set()

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_dir = os.path.join(base_dir, 'nxos')

    def __getitem__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        elif name in self.__dict__['_attributes']:
            return self.__dict__['_attributes'][name]
        else:
            raise AttributeError

    def __iter__(self):
        return iter(self._attributes)

    def __len__(self):
        return len(self._attributes)

    def load_data(self, cfgobj):
        if not self._loader:
            self._loader = DataLoader()

        fn = '%s.yaml' % cfgobj
        fp = os.path.join(self.base_dir, fn)

        ds = self._loader.load_from_file(fp)
        setattr(self, '_ds', ds)

        if '_global' in ds:
            base = self._platform_ds(ds['_global'])

        for key, values in iteritems(ds):
            if not key.startswith('_'):
                attr = self._platform_ds(values)
                if base:
                    attr = dict_combine(base, attr)
                cfgattr = ConfigAttr()
                cfgattr.load_data(attr)
                self._attributes[key] = cfgattr
                self._commands.add(cfgattr.get_command)


    def _platform_ds(self, entry):
        assert isinstance(entry, dict)
        platform = entry.get(self.platform, {})
        return dict_combine(entry, platform)

    def send_to_device(self, conn, obj=None, operation='merge'):
        commands = list()
        current = None

        if not self._loader:
            self._loader = DataLoader()

        templar = Templar(self._loader)

        if operation == 'delete':
            obj = self.load_from_device(conn)

        for key, value in iteritems(obj):
            variables = copy.deepcopy(obj)
            templar.set_available_variables(variables)

            try:
                attr = self[key]
            except KeyError:
                raise AnsibleError('invalid ConfigAttr specified')

            if attr.set_items:
                items = templar.template(attr.set_items)

                updates = list()
                if attr.set_context:
                    updates.append(templar.template(attr.set_context))

                for item in items:
                    variables['item'] = item
                    templar.set_available_variables(variables)

                    if operation == 'delete':
                        if attr.del_value:
                            command_string = attr.del_value
                        else:
                            command_string = 'no %s' % attr.set_value
                    else:
                        command_string = attr.set_value

                    updates.append(templar.template(command_string))

            else:
                updates = list()
                if attr.set_context:
                    updates.append(templar.template(attr.set_context))

                if operation == 'delete':
                    if attr.del_value:
                        command_string = attr.del_value
                    else:
                        command_string = 'no %s' % attr.set_value
                else:
                    command_string = attr.set_value

                updates.append(templar.template(command_string))


            if attr.load_order is None:
                commands.extend(updates)
            else:
                for command in updates:
                    commands.insert(attr.load_order, command)

        return commands

    def load_from_device(self, conn):
        # run the commands on the connection object and populate the responses
        # in the responses dict
        responses = dict()
        for item in self._commands:
            # FIXME once wired up to the network_cli connection plugin
            #responses[item] = conn.get(item)
            rc, out, err = conn.exec_command(item)
            responses[item] = out

        obj = {}

        if not self._loader:
            self._loader = DataLoader()

        templar = Templar(self._loader)

        for name, attr in iteritems(self._attributes):
            output = responses[attr.get_command]
            variables = {'output': output}

            if attr.get_context:
                if attr.multiple:
                    match = re.findall(attr.get_context, output, re.M)
                    variables['items'] = match
                else:
                    match = re.search(attr.get_context, output, re.M)
                    if match:
                        variables['items'] = list(match.groups())
                        variables.update(match.groupdict())

            templar.set_available_variables(variables)

            try:
                value = templar.template(attr.get_value)
            except AnsibleUndefinedVariable:
                value = None

            if value is None:
                obj[name] = attr.default_value
            elif attr.kind in ('bool', 'boolean'):
                obj[name] = value is not None
            elif attr.kind in ('int', 'integer'):
                obj[name] = int(value)
            elif attr.kind in ('str', 'string'):
                obj[name] = str(value)
            else:
                obj[name] = value

        return obj
