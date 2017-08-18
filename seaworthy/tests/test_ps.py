import pytest

from seaworthy.ps import PsException, PsRow, PsTree, build_process_tree


def mkrow(pid, ppid, ruser='root', args=None):
    if args is None:
        args = 'args for pid {}'.format(pid)
    return PsRow(pid, ppid, ruser, args)


class TestPsTree(object):
    def test_count(self):
        """
        A PsTree knows how many entries it contains.
        """
        assert 1 == PsTree(mkrow(1, 0)).count()

        assert 3 == PsTree(mkrow(1, 0), [
            PsTree(mkrow(6, 1), [
                PsTree(mkrow(8, 6)),
            ]),
        ]).count()

        assert 6 == PsTree(mkrow(1, 0), [
            PsTree(mkrow(6, 1), [
                PsTree(mkrow(8, 6)),
            ]),
            PsTree(mkrow(9, 1), [
                PsTree(mkrow(11, 9)),
                PsTree(mkrow(12, 9)),
            ]),
        ]).count()


class TestBuildProcessTreeFunc(object):
    def test_single_process(self):
        """
        We can build a PsTree for a single process.
        """
        ps_row = PsRow('1', '0', 'root', 'tini -- echo "hi"')
        ps_tree = build_process_tree([ps_row])

        assert ps_tree == PsTree(ps_row, children=[])

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
        assert ps_tree == PsTree(ps_rows[0], [
            PsTree(ps_rows[1], [
                PsTree(ps_rows[2], []),
            ]),
        ])

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
        assert ps_tree == PsTree(ps_rows[1], [
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
        ])

    def test_no_root_pid(self):
        """
        We can't build a process tree if we don't have a root process.
        """
        with pytest.raises(PsException) as e:
            build_process_tree([])
        assert "No process tree root" in str(e.value)

        with pytest.raises(PsException) as e:
            build_process_tree([
                mkrow(2, 1),
                mkrow(3, 1),
                mkrow(4, 2),
            ])
        assert "No process tree root" in str(e.value)

    def test_multiple_root_pids(self):
        """
        We can't build a process tree if we have too many root processes.
        """
        with pytest.raises(PsException) as e:
            build_process_tree([
                mkrow(1, 0),
                mkrow(2, 0),
                mkrow(4, 2),
            ])
        assert "Too many process tree roots" in str(e.value)

    def test_malformed_process_tree(self):
        """
        We can't build a process tree with disconnected processes.
        """
        with pytest.raises(PsException) as e:
            build_process_tree([
                mkrow(1, 0),
                mkrow(2, 1),
                mkrow(4, 3),
            ])
        assert "Unreachable processes" in str(e.value)

    def test_duplicate_pids(self):
        """
        We can't build a process tree with duplicate pids.
        """
        with pytest.raises(PsException) as e:
            build_process_tree([
                mkrow(1, 0),
                mkrow(2, 1),
                mkrow(2, 1),
                mkrow(3, 2),
            ])
        assert "Duplicate pid found: 2" in str(e.value)
