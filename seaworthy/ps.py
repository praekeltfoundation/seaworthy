import re

import attr

from .utils import output_lines


@attr.s
class PsRow(object):
    pid = attr.ib()
    ppid = attr.ib()
    ruser = attr.ib()
    args = attr.ib()

    @classmethod
    def columns(cls):
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
    # Split on the start of the header title words
    spans = [(match.start(0), match.end(0))
             for match in re.finditer(r'\b\w+\s*', header)]
    spans[-1] = (spans[-1][0], None)  # Final span goes to the end of the line
    ps_entries = [
        [line[start:end].strip() for start, end in spans] for line in ps_lines]

    # Convert to PsRows
    ps_rows = [PsRow(*entry) for entry in ps_entries]

    # Filter out the row for ps itself
    cmd_string = ' '.join(cmd)
    ps_rows = [row for row in ps_rows if row.args != cmd_string]

    return ps_rows


@attr.s
class PsTree(object):
    row = attr.ib()
    children = attr.ib(default=[])

    def count(self):
        return 1 + sum(row.count() for row in self.children)


def _build_process_subtree(ps_rows, ps_tree):
    for row in ps_rows:
        if row.ppid == ps_tree.row.pid:
            tree = PsTree(row=row, children=[])
            ps_tree.children.append(tree)
            _build_process_subtree(ps_rows, tree)


def build_process_tree(ps_rows):
    """
    Build a tree structure from a list of PsRow objects.
    :param ps_rows: a list of PsRow objects
    :return: a PsTree object
    """
    ps_tree = None
    for row in ps_rows:
        if row.ppid == '0':
            assert ps_tree is None
            ps_tree = PsTree(row)
    assert ps_tree is not None
    _build_process_subtree(ps_rows, ps_tree)
    assert ps_tree.count() == len(ps_rows)
    return ps_tree


__all__ = ['build_process_tree', 'list_container_processes', 'PsRow', 'PsTree']
