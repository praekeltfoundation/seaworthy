"""
Tools for asserting on processes running in containers using ``ps``.
"""

import attr

from .utils import output_lines


class PsException(Exception):
    """
    Exception indicating problems operating on process lists and trees.
    """


@attr.s
class PsRow:
    """
    Representation of a process list entry, containing the details of a single
    process.
    """

    pid = attr.ib(converter=int)
    ppid = attr.ib(converter=int)
    ruser = attr.ib()
    args = attr.ib()

    @classmethod
    def columns(cls):
        """
        List the columns required to construct a suitable ``ps`` command.
        """
        return [a.name for a in attr.fields(cls)]


def list_container_processes(container):
    """
    List the processes running inside a container.
    We use an exec rather than `container.top()` because we want to run 'ps'
    inside the container. This is because we want to get PIDs and usernames in
    the container's namespaces. `container.top()` uses 'ps' from outside the
    container in the host's namespaces. Note that this requires the container
    to have a 'ps' that responds to the arguments we give it-- we use BusyBox's
    (Alpine's) 'ps' as a baseline for available functionality.
    :param container: the container to query
    :return: a list of PsRow objects
    """
    cmd = ['ps', 'ax', '-o', ','.join(PsRow.columns())]
    ps_lines = output_lines(container.exec_run(cmd))

    header = ps_lines.pop(0)
    # We can't trust the header alignment because different ps implementations
    # use different alignments, some of which depend on the alignment of the
    # columns. Instead, we assume that all columns are whitespace-separated and
    # that only the last column may contain spaces.
    maxsplit = len(header.strip().split()) - 1
    ps_entries = [line.strip().split(None, maxsplit) for line in ps_lines]

    # Convert to PsRows
    ps_rows = [PsRow(*entry) for entry in ps_entries]

    # Filter out the row for ps itself
    cmd_string = ' '.join(cmd)
    ps_rows = [row for row in ps_rows if row.args != cmd_string]

    return ps_rows


@attr.s
class PsTree:
    """
    Node in a process tree, linking a :class:`PsRow` to its child processes.
    """
    row = attr.ib()
    children = attr.ib(default=attr.Factory(list))

    def count(self):
        """
        Return the number of processes in this subtree.
        """
        return 1 + sum(row.count() for row in self.children)


def _build_process_subtree(ps_rows, ps_tree, pids_seen):
    for row in ps_rows:
        if row.ppid == ps_tree.row.pid:
            if row.pid in pids_seen:
                raise PsException("Duplicate pid found: {}".format(row.pid))
            pids_seen.add(row.pid)
            tree = PsTree(row=row, children=[])
            ps_tree.children.append(tree)
            _build_process_subtree(ps_rows, tree, pids_seen)


def build_process_tree(ps_rows):
    """
    Build a tree structure from a list of PsRow objects.
    :param ps_rows: a list of PsRow objects
    :return: a PsTree object
    """
    ps_tree = None
    for row in ps_rows:
        if row.ppid == 0:
            if ps_tree is not None:
                raise PsException("Too many process tree roots (ppid=0) found")
            ps_tree = PsTree(row)
    if ps_tree is None:
        raise PsException("No process tree root (ppid=0) found")
    _build_process_subtree(ps_rows, ps_tree, set([ps_tree.row.pid]))
    if ps_tree.count() < len(ps_rows):
        raise PsException("Unreachable processes detected")
    assert ps_tree.count() == len(ps_rows)
    return ps_tree


__all__ = [
    'build_process_tree', 'list_container_processes',
    'PsException', 'PsRow', 'PsTree',
]
