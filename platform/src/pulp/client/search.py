# -*- coding: utf-8 -*-
#
# Copyright © 2012 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.

from gettext import gettext as _
try:
    import json
except ImportError:
    import simplejson as json

from okaara.cli import CommandUsage, OptionGroup

from pulp.client import validators
from pulp.client.extensions.extensions import PulpCliCommand, PulpCliOption
from pulp.client import parsers

_LIMIT_DESCRIPTION = _('max number of items to return')
_SKIP_DESCRIPTION = _('number of items to skip')
_FILTERS_DESCRIPTION = _("""filters provided as JSON in mongo syntax. This will
override any options specified from the 'Filters' section
below.""").replace('\n', ' ')
_FIELDS_DESCRIPTION = _("""comma-separated list of resource fields. Do not
include spaces. Default is all fields.""".replace('\n', ' '))
_SORT_DESCRIPTION = _("""field name, a comma, and either the word "ascending" or
"descending". The comma and direction are optional, and the direction
defaults to ascending. Do not put a space before or after the comma. For
multiple fields, use this option multiple times. Each one will be applied in
the order supplied.""".replace('\n', ' '))
_SEARCH_DESCRIPTION = _("""search items while optionally specifying sort, limit,
skip, and requested fields""".replace('\n', ' '))
_USAGE = _("""These are basic filtering options that will be AND'd together.
These will be ignored if --filters= is specified. Any option may be specified
multiple times. The value for each option should be a field name and value to
match against, specified as "name=value".
Example: $ pulp-admin repo search --gt='content_unit_count=0'
""").replace('\n', ' ')

class SearchCommand(PulpCliCommand):
    """
    This command contains only the search features provided by the server. See
    SearchCommand for additional features such as sort, limit, skip, and fields.
    """
    def __init__(self, method, filtering=True, criteria=True, *args, **kwargs):
        """
        :param method:  A method to call when this command is executed. See
                        okaara docs for more info
        :type  method:  callable
        :param filtering:   If True, the command will add all filtering options
        :type  filtering:   bool
        :param criteria:    If True, the command will add all non-filter
                            criteria options such as limit, seek, sort, etc.
        :type  criteria:    bool

        """
        name = kwargs.pop('name', None) or 'search'
        description = kwargs.pop('description', None) or _SEARCH_DESCRIPTION

        super(SearchCommand, self).__init__(name, description,
            method, *args, **kwargs)

        if filtering:
            self.add_filtering()
        if criteria:
            self.add_full_criteria_options()

    def add_filtering(self):
        self.add_option(PulpCliOption('--filters', _FILTERS_DESCRIPTION,
            required=False, parse_func=json.loads))

        filter_group = OptionGroup('Filters', _(_USAGE))

        m = 'match where a named attribute equals a string value exactly.'
        filter_group.add_option(PulpCliOption('--str-eq', _(m), required=False,
            allow_multiple=True, parse_func=self._parse_key_value))

        m = 'match where a named attribute equals an int value exactly.'
        filter_group.add_option(PulpCliOption('--int-eq', _(m), required=False,
            allow_multiple=True, parse_func=self._parse_key_value))

        m = 'for a named attribute, match a regular expression using the mongo regex engine.'
        filter_group.add_option(PulpCliOption('--match', _(m), required=False,
            allow_multiple=True, parse_func=self._parse_key_value))

        m = 'for a named attribute, match where value is in the provided list of values, expressed as one row of CSV'
        filter_group.add_option(PulpCliOption('--in', _(m), required=False,
            allow_multiple=True, parse_func=self._parse_key_value))

        m = 'field and expression to omit when determining units for inclusion'
        filter_group.add_option(PulpCliOption('--not', _(m), required=False,
            allow_multiple=True, parse_func=self._parse_key_value))

        m = 'matches resources whose value for the specified field is greater than the given value'
        filter_group.add_option(PulpCliOption('--gt', _(m), required=False,
            allow_multiple=True, parse_func=self._parse_key_value))

        m = 'matches resources whose value for the specified field is greater than or equal to the given value'
        filter_group.add_option(PulpCliOption('--gte', _(m), required=False,
            allow_multiple=True, parse_func=self._parse_key_value))

        m = 'matches resources whose value for the specified field is less than the given value'
        filter_group.add_option(PulpCliOption('--lt', _(m), required=False,
            allow_multiple=True, parse_func=self._parse_key_value))

        m = 'matches resources whose value for the specified field is less than or equal to the given value'
        filter_group.add_option(PulpCliOption ('--lte', _(m), required=False,
            allow_multiple=True, parse_func=self._parse_key_value))

        self.add_option_group(filter_group)

    def add_full_criteria_options(self):
        """
        Add the full set of criteria-based search features to this command,
        including limit, skip, sort, and fields.
        """
        self.add_option(PulpCliOption('--limit', _LIMIT_DESCRIPTION,
            required=False, parse_func=int,
            validate_func=validators.positive_int_validator))
        self.add_option(PulpCliOption('--skip', _SKIP_DESCRIPTION,
            required=False, parse_func=int,
            validate_func=validators.non_negative_int_validator))
        self.add_option(PulpCliOption('--sort', _SORT_DESCRIPTION,
            required=False, allow_multiple=True,
            validate_func=self._validate_sort,
            parse_func=self._parse_sort))
        self.add_option(PulpCliOption('--fields', _FIELDS_DESCRIPTION,
            required=False, validate_func=str,
            parse_func=lambda x: x.split(',')))

    @staticmethod
    def _parse_key_value(args):
        """
        parses the raw user input, taken as a list of strings in the format
        'name=value', into a list of tuples in the format (name, value).

        :param args:    list of raw strings passed by the user on the command
                        line.
        :type  args:    list of basestrings

        :return:    new list of tuples in the format (name, value)
        """
        ret = []
        for arg in args:
            components = arg.split('=', 1)
            if len(components) != 2:
                raise ValueError('key and value must be separated by "="')
            ret.append(components)
        return ret

    @classmethod
    def _validate_sort(cls, sort_args):
        """
        validates that each individual sort arg starts with a field name, and
        if a direction is included, that it is either 'ascending' or
        'descending'.

        @param sort_args:   list of search arguments. Each is in the format
                            'field_name,direction' where direction is
                            'ascending' or 'descending'.
        @type  sort_args:   list
        """
        for arg in sort_args:
            field_name, direction = cls._explode_sort_arg_pieces(str(arg))
            if len(field_name) == 0:
                raise ValueError(_('field name must be specified'))
            if direction not in ('ascending', 'descending'):
                raise ValueError(_('direction must be "ascending" or "descending"'))

    @classmethod
    def _parse_sort(cls, sort_args):
        """
        Parse the sort argument to a search command

        @param sort_args:   list of search arguments. Each is in the format
                            'field_name,direction' where direction is
                            'ascending' or 'descending'.
        @type  sort_args:   list

        @return:    list of sort arguments in the format expected by Criteria
        @rtype:     list
        """
        ret = []
        for value in sort_args:
            field_name, direction = cls._explode_sort_arg_pieces(value)
            if direction not in ('ascending', 'descending'):
                # validation should have caught this
                raise CommandUsage()
            ret.append((field_name, direction))

        return ret

    @staticmethod
    def _explode_sort_arg_pieces(sort_arg):
        """
        Takes an individual sort argument and returns the two components:
        field_name, and direction. If direction is not supplied, it defaults
        to 'ascending'.

        @param sort_arg:    argument passed from user as --sort=
        @type  sort_arg:    basestring

        @return:    tuple of field name and direction
        @rtype:     tuple of 2 basestrings
        """
        pieces = sort_arg.lower().split(',')
        field_name = pieces[0]
        # the join just helps us create a string from an array with
        # one or zero members.
        direction = ''.join(pieces[1:2]) or 'ascending'
        return field_name, direction


class UnitSearchCommand(SearchCommand):
    def __init__(self, method, *args, **kwargs):
        super(UnitSearchCommand, self).__init__(method, *args, **kwargs)

        self.add_option(PulpCliOption('--repo-id',
            _('identifies the repository to search within'), required=True))

        m = 'matches units added to the source repository on or after the given time; '\
            'specified as a timestamp in iso8601 format'
        self.create_option('--after', _(m), ['-a'], required=False,
            allow_multiple=False, parse_func=parsers.iso8601)

        m = 'matches units added to the source repository on or before the given time; '\
            'specified as a timestamp in iso8601 format'
        self.create_option('--before', _(m), ['-b'], required=False,
            allow_multiple=False, parse_func=parsers.iso8601)


class UnitCopyCommand(UnitSearchCommand):
    def __init__(self, *args, **kwargs):
        kwargs['criteria'] = False
        super(UnitCopyCommand, self).__init__(*args, **kwargs)
        self.options = [opt for opt in self.options if opt.name != '--repo-id']

        m = 'source repository from which units will be copied'
        self.create_option('--from-repo-id', _(m), ['-f'], required=True)

        m = 'destination repository to copy units into'
        self.create_option('--to-repo-id', _(m), ['-t'], required=True)


class UnitSearchAllCommand(UnitSearchCommand):
    def __init__(self, *args, **kwargs):
        kwargs['filtering'] = False
        super(UnitSearchAllCommand, self).__init__(*args, **kwargs)
        OPTIONS_TO_REMOVE = set(['--sort', '--fields'])
        self.options = [opt for opt in self.options if opt.name not in OPTIONS_TO_REMOVE]
