"""
Tests for seaworthy.ps module.

Please note that these are "core" tests and thus may not depend on anything
that isn't already a non-optional dependency of Seaworthy itself.
"""

import unittest

from docker.models.containers import ExecResult

from seaworthy.ps import (
    PsException, PsRow, PsTree, build_process_tree, list_container_processes)


def mkrow(pid, ppid, ruser='root', args=None):
    if args is None:
        args = 'args for pid {}'.format(pid)
    return PsRow(pid, ppid, ruser, args)


class TestPsRow(unittest.TestCase):
    def test_columns(self):
        """
        The PsRow class knows what columns it requires from ps.
        """
        self.assertEqual(PsRow.columns(), ['pid', 'ppid', 'ruser', 'args'])

    def test_fields(self):
        """
        A PsRow can be created from field values of various types.
        """
        ps_row = PsRow('1', '0', 'root', 'tini -- true')
        self.assertEqual(
            (ps_row.pid, ps_row.ppid, ps_row.ruser, ps_row.args),
            (1, 0, 'root', 'tini -- true'))

        ps_row = PsRow(1, 0, 'root', 'tini -- true')
        self.assertEqual(
            (ps_row.pid, ps_row.ppid, ps_row.ruser, ps_row.args),
            (1, 0, 'root', 'tini -- true'))


class FakePsContainer:
    """
    A container object stub that emits canned process lists.
    """

    def __init__(self, rows):
        self.rows = rows

    def exec_run(self, cmd):
        # We only allow our own ps command to be run.
        assert cmd == ['ps', 'ax', '-o', 'pid,ppid,ruser,args']
        return ExecResult(0, b'\n'.join(self.rows))


class TestListContainerProcessesFunc(unittest.TestCase):
    def test_no_processes(self):
        """
        If we somehow get no processes other than the ps command, we return an
        empty list.
        """
        con = FakePsContainer([
            b'PID   PPID  RUSER    COMMAND',
            b'    6     0 root     ps ax -o pid,ppid,ruser,args',
        ])
        self.assertEqual(list_container_processes(con), [])

    def test_header_alignment(self):
        """
        Different ps implementations use different alignments for the column
        headers.
        """
        ps_rows = [PsRow(1, 0, 'root', 'sleep 2')]

        busybox_con = FakePsContainer([
            b'PID   PPID  RUSER    COMMAND',
            b'    1     0 root     sleep 2',
            b'    6     0 root     ps ax -o pid,ppid,ruser,args',
        ])
        self.assertEqual(ps_rows, list_container_processes(busybox_con))

        debian_con = FakePsContainer([
            b'  PID  PPID RUSER    COMMAND',
            b'    1     0 root     sleep 2',
            b'    6     0 root     ps ax -o pid,ppid,ruser,args',
        ])
        self.assertEqual(ps_rows, list_container_processes(debian_con))

    def test_header_alignment_long_pids(self):
        """
        For some header alignments, the pids may extend beyond the left edge of
        the column headers.
        """
        ps_rows = [
            PsRow(1, 0, 'root', 'tini -- foo'),
            PsRow(10000, 1, 'root', 'foo'),
            PsRow(10001, 10000, 'root', 'bar'),
        ]

        busybox_con = FakePsContainer([
            b'PID   PPID  RUSER    COMMAND',
            b'    1     0 root     tini -- foo',
            b'10000     1 root     foo',
            b'10001 10000 root     bar',
            b'    6     0 root     ps ax -o pid,ppid,ruser,args',
        ])
        self.assertEqual(ps_rows, list_container_processes(busybox_con))

        debian_con = FakePsContainer([
            b'  PID  PPID RUSER    COMMAND',
            b'    1     0 root     tini -- foo',
            b'10000     1 root     foo',
            b'10001 10000 root     bar',
            b'    6     0 root     ps ax -o pid,ppid,ruser,args',
        ])
        self.assertEqual(ps_rows, list_container_processes(debian_con))

    def test_many_processes(self):
        """
        If there are a lot of processes running in a container, we return all
        of them.
        """
        con = FakePsContainer([
            b'  PID  PPID RUSER    COMMAND',
            b'    1     0 root     tini -- django-entrypoint.sh args',
            b'    6     1 django   gunicorn master args',
            b'   17     6 root     nginx master args',
            b'   18     6 django   celery worker args',
            b'   19     6 django   celery beat args',
            b'   26    17 nginx    nginx worker args',
            b'   34     6 django   gunicorn worker args',
            b'   48     0 root     ps ax -o pid,ppid,ruser,args',
        ])
        self.assertEqual(list_container_processes(con), [
            PsRow(1, 0, 'root', 'tini -- django-entrypoint.sh args'),
            PsRow(6, 1, 'django', 'gunicorn master args'),
            PsRow(17, 6, 'root', 'nginx master args'),
            PsRow(18, 6, 'django', 'celery worker args'),
            PsRow(19, 6, 'django', 'celery beat args'),
            PsRow(26, 17, 'nginx', 'nginx worker args'),
            PsRow(34, 6, 'django', 'gunicorn worker args'),
        ])


class TestPsTree(unittest.TestCase):
    def test_count(self):
        """
        A PsTree knows how many entries it contains.
        """
        self.assertEqual(1, PsTree(mkrow(1, 0)).count())

        self.assertEqual(3, PsTree(mkrow(1, 0), [
            PsTree(mkrow(6, 1), [
                PsTree(mkrow(8, 6)),
            ]),
        ]).count())

        self.assertEqual(6, PsTree(mkrow(1, 0), [
            PsTree(mkrow(6, 1), [
                PsTree(mkrow(8, 6)),
            ]),
            PsTree(mkrow(9, 1), [
                PsTree(mkrow(11, 9)),
                PsTree(mkrow(12, 9)),
            ]),
        ]).count())


class TestBuildProcessTreeFunc(unittest.TestCase):
    def test_single_process(self):
        """
        We can build a PsTree for a single process.
        """
        ps_row = PsRow('1', '0', 'root', 'tini -- echo "hi"')
        ps_tree = build_process_tree([ps_row])

        self.assertEqual(ps_tree, PsTree(ps_row, children=[]))

    def test_simple_tree(self):
        """
        We can build a PsTree for a list of grandparent/parent/child processes.
        """
        ps_rows = [
            mkrow(1, 0, 'root', "tini -- nginx -g 'daemon off;'"),
            mkrow(6, 1, 'root', 'nginx: master process nginx -g daemon off;'),
            mkrow(8, 6, 'nginx', 'nginx: worker process'),
        ]
        ps_tree = build_process_tree(ps_rows)
        self.assertEqual(ps_tree, PsTree(ps_rows[0], [
            PsTree(ps_rows[1], [
                PsTree(ps_rows[2], []),
            ]),
        ]))

    def test_bigger_tree(self):
        """
        We can build a PsTree for a more complicated process list.
        """
        ps_rows = [
            None,  # Dummy entry so list indices match pids.
            mkrow(1, 0),
            mkrow(2, 1),
            mkrow(3, 1),
            mkrow(4, 2),
            mkrow(5, 3),
            mkrow(6, 3),
            mkrow(7, 4),
            mkrow(8, 2),
            mkrow(9, 1),
        ]
        ps_tree = build_process_tree(ps_rows[1:])
        self.assertEqual(ps_tree, PsTree(ps_rows[1], [
            PsTree(ps_rows[2], [
                PsTree(ps_rows[4], [
                    PsTree(ps_rows[7]),
                ]),
                PsTree(ps_rows[8]),
            ]),
            PsTree(ps_rows[3], [
                PsTree(ps_rows[5]),
                PsTree(ps_rows[6]),
            ]),
            PsTree(ps_rows[9]),
        ]))

    def test_no_root_pid(self):
        """
        We can't build a process tree if we don't have a root process.
        """
        with self.assertRaises(PsException) as cm:
            build_process_tree([])
        self.assertIn("No process tree root", str(cm.exception))

        with self.assertRaises(PsException) as cm:
            build_process_tree([
                mkrow(2, 1),
                mkrow(3, 1),
                mkrow(4, 2),
            ])
        self.assertIn("No process tree root", str(cm.exception))

    def test_multiple_root_pids(self):
        """
        We can't build a process tree if we have too many root processes.
        """
        with self.assertRaises(PsException) as cm:
            build_process_tree([
                mkrow(1, 0),
                mkrow(2, 0),
                mkrow(4, 2),
            ])
        self.assertIn("Too many process tree roots", str(cm.exception))

    def test_malformed_process_tree(self):
        """
        We can't build a process tree with disconnected processes.
        """
        with self.assertRaises(PsException) as cm:
            build_process_tree([
                mkrow(1, 0),
                mkrow(2, 1),
                mkrow(4, 3),
            ])
        self.assertIn("Unreachable processes", str(cm.exception))

    def test_duplicate_pids(self):
        """
        We can't build a process tree with duplicate pids.
        """
        with self.assertRaises(PsException) as cm:
            build_process_tree([
                mkrow(1, 0),
                mkrow(2, 1),
                mkrow(2, 1),
                mkrow(3, 2),
            ])
        self.assertIn("Duplicate pid found: 2", str(cm.exception))
