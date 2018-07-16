"""
Some (optional) utilities for use with testtools.

While Seaworthy doesn't require testtools, we find it useful in downstream
container tests we write with Seaworthy. This module contains various bits and
pieces to make Seaworthy work better with testtools.
"""

from testtools.matchers import MatchesSetwise, MatchesStructure, Mismatch


class PsTreeMismatch(Mismatch):
    """
    Custom mismatch container for MatchesPsTree so we get somewhat more
    comprehensible failure messages.
    """

    def __init__(self, row_fields, child_count, fields_mm, children_mm):
        self.row_fields = row_fields
        self.child_count = child_count
        self.fields_mm = fields_mm
        self.children_mm = children_mm

    def describe(self):
        """
        Describe the mismatch.
        """
        rfs = ['{}={!r}'.format(k, v)
               for k, v in sorted(self.row_fields.items())]
        suffix = '' if self.child_count == 1 else 'ren'
        descriptions = ['PsTree({} with {} child{}) mismatch: ['.format(
            ', '.join(rfs), self.child_count, suffix)]
        if self.fields_mm is not None:
            for m in self.fields_mm.mismatches:
                for l in m.describe().splitlines():
                    descriptions.append('  ' + l.rstrip('\n'))
        if self.children_mm is not None:
            descriptions.append('  mismatches in children:')
            for l in self.children_mm.describe().splitlines():
                descriptions.append('    ' + l.rstrip('\n'))
        descriptions.append(']')
        return '\n'.join(descriptions)


class MatchesPsTree:
    """
    Matches a nested PsTree object in a sensible way.

    The `ruser` and `args` fields are always checked. The `pid` and `ppid`
    fields are only checked if non-None values are explicitly provided, because
    real pids are essentially arbitrary integers. The `children` field is
    always checked, but order is ignored.
    """

    def __init__(self, ruser, args, pid=None, ppid=None, children=()):
        self.row_fields = {'ruser': ruser, 'args': args}
        if pid is not None:
            self.row_fields['pid'] = pid
        if ppid is not None:
            self.row_fields['ppid'] = ppid
        self.children = children

    def __str__(self):
        rfs = ['{}={!r}'.format(k, v)
               for k, v in sorted(self.row_fields.items())]
        return '{}({}, children={})'.format(
            self.__class__.__name__, ', '.join(rfs), str(self.children))

    def match(self, value):
        """
        Return ``None`` if this matcher matches something, a
        :class:`PsTreeMismatch` otherwise.
        """
        fields_mm = MatchesStructure.byEquality(**self.row_fields).match(
            value.row)
        children_mm = MatchesSetwise(*self.children).match(value.children)
        if fields_mm is not None or children_mm is not None:
            return PsTreeMismatch(
                self.row_fields, len(self.children), fields_mm, children_mm)
