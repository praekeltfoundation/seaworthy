import unittest

from testtools.assertions import assert_that
from testtools.matchers import Not

from seaworthy.ps import PsRow, PsTree
from seaworthy.testtools import MatchesPsTree


class TestMatchesPsTree(unittest.TestCase):
    def test_minimal_tree_matches(self):
        """
        MatchesPsTree can match a single-process tree.
        """
        ps_tree = PsTree(PsRow(1, 0, 'root', 'tini -- echo "hi"'))

        matcher = MatchesPsTree('root', 'tini -- echo "hi"')
        assert matcher.match(ps_tree) is None

        matcher = MatchesPsTree('root', 'tini -- echo "hi"', 1)
        assert matcher.match(ps_tree) is None

        matcher = MatchesPsTree('root', 'tini -- echo "hi"', ppid=0)
        assert matcher.match(ps_tree) is None

        matcher = MatchesPsTree('root', 'tini -- echo "hi"', 1, 0)
        assert matcher.match(ps_tree) is None

        matcher = MatchesPsTree('root', 'tini -- echo "hi"', 1, 0, children=[])
        assert matcher.match(ps_tree) is None

    def test_minimal_tree_mismatches(self):
        """
        MatchesPsTree can detect a non-matching single-process tree.
        """
        ps_tree = PsTree(PsRow(1, 0, 'root', 'tini -- true'))

        matcher = MatchesPsTree('tuber', 'tini -- true')
        mismatch = matcher.match(ps_tree)
        assert "'root' != 'tuber': ruser" in mismatch.describe()

        matcher = MatchesPsTree('root', 'tini -- false')
        mismatch = matcher.match(ps_tree)
        assert "'tini -- true' != 'tini -- false': args" in mismatch.describe()

        matcher = MatchesPsTree('tuber', 'tini -- true', pid=7)
        mismatch = matcher.match(ps_tree)
        assert "1 != 7: pid" in mismatch.describe()

        matcher = MatchesPsTree('tuber', 'tini -- true', ppid=7)
        mismatch = matcher.match(ps_tree)
        assert "0 != 7: ppid" in mismatch.describe()

    def test_nested_tree_matches(self):
        """
        MatchesPsTree can match a multi-process tree.
        """
        ps_tree = PsTree(PsRow(1, 0, 'root', 'tini -- app'), [
            PsTree(PsRow(2, 1, 'root', 'app --arg'), [
                PsTree(PsRow(3, 2, 'appuser', 'app --child1')),
                PsTree(PsRow(4, 2, 'appuser', 'app --child2')),
            ]),
            PsTree(PsRow(5, 1, 'root', 'app2 --arg'), [
                PsTree(PsRow(6, 5, 'root', 'app2 --child')),
            ]),
        ])

        # Check children in the same order.
        matcher = MatchesPsTree('root', 'tini -- app', pid=1, children=[
            MatchesPsTree('root', 'app --arg', children=[
                MatchesPsTree('appuser', 'app --child1'),
                MatchesPsTree('appuser', 'app --child2'),
            ]),
            MatchesPsTree('root', 'app2 --arg', children=[
                MatchesPsTree('root', 'app2 --child'),
            ]),
        ])
        assert matcher.match(ps_tree) is None

        # Check children in a different order.
        matcher = MatchesPsTree('root', 'tini -- app', pid=1, children=[
            MatchesPsTree('root', 'app --arg', children=[
                MatchesPsTree('appuser', 'app --child2'),
                MatchesPsTree('appuser', 'app --child1'),
            ]),
            MatchesPsTree('root', 'app2 --arg', children=[
                MatchesPsTree('root', 'app2 --child'),
            ]),
        ])
        assert matcher.match(ps_tree) is None

        # Check different children in a different order.
        matcher = MatchesPsTree('root', 'tini -- app', pid=1, children=[
            MatchesPsTree('root', 'app2 --arg', children=[
                MatchesPsTree('root', 'app2 --child'),
            ]),
            MatchesPsTree('root', 'app --arg', children=[
                MatchesPsTree('appuser', 'app --child1'),
                MatchesPsTree('appuser', 'app --child2'),
            ]),
        ])
        assert matcher.match(ps_tree) is None

    def test_nested_tree_missing_child(self):
        """
        MatchesPsTree can detect a missing child process.
        """
        ps_tree = PsTree(PsRow(1, 0, 'root', 'tini -- app'), [
            PsTree(PsRow(2, 1, 'root', 'app --arg'), [
                PsTree(PsRow(3, 2, 'appuser', 'app --child1')),
            ]),
            PsTree(PsRow(5, 1, 'root', 'app2 --arg'), [
                PsTree(PsRow(6, 5, 'root', 'app2 --child')),
            ]),
        ])

        matcher = MatchesPsTree('root', 'tini -- app', pid=1, children=[
            MatchesPsTree('root', 'app --arg', children=[
                MatchesPsTree('appuser', 'app --child1'),
                MatchesPsTree('appuser', 'app --child2'),
            ]),
            MatchesPsTree('root', 'app2 --arg', children=[
                MatchesPsTree('root', 'app2 --child'),
            ]),
        ])
        mm = matcher.match(ps_tree).describe()
        assert "mismatches in children:" in mm
        assert "There was 1 matcher left over:" in mm

    def test_nested_tree_extra_child(self):
        """
        MatchesPsTree can detect an extra child process.
        """
        ps_tree = PsTree(PsRow(1, 0, 'root', 'tini -- app'), [
            PsTree(PsRow(2, 1, 'root', 'app --arg'), [
                PsTree(PsRow(3, 2, 'appuser', 'app --child1')),
                PsTree(PsRow(4, 2, 'appuser', 'app --child3')),
                PsTree(PsRow(7, 2, 'appuser', 'app --child2')),
            ]),
            PsTree(PsRow(5, 1, 'root', 'app2 --arg'), [
                PsTree(PsRow(6, 5, 'root', 'app2 --child')),
            ]),
        ])

        matcher = MatchesPsTree('root', 'tini -- app', pid=1, children=[
            MatchesPsTree('root', 'app --arg', children=[
                MatchesPsTree('appuser', 'app --child1'),
                MatchesPsTree('appuser', 'app --child2'),
            ]),
            MatchesPsTree('root', 'app2 --arg', children=[
                MatchesPsTree('root', 'app2 --child'),
            ]),
        ])
        mm = matcher.match(ps_tree).describe()
        assert "mismatches in children:" in mm
        assert "There was 1 value left over:" in mm

    def test_nested_tree_different_child(self):
        """
        MatchesPsTree can detect a child process that is different.
        """
        ps_tree = PsTree(PsRow(1, 0, 'root', 'tini -- app'), [
            PsTree(PsRow(2, 1, 'root', 'app --arg'), [
                PsTree(PsRow(3, 2, 'appuser', 'app --child1')),
                PsTree(PsRow(4, 2, 'appuser', 'app --child3')),
            ]),
            PsTree(PsRow(5, 1, 'root', 'app2 --arg'), [
                PsTree(PsRow(6, 5, 'root', 'app2 --child')),
            ]),
        ])

        matcher = MatchesPsTree('root', 'tini -- app', pid=1, children=[
            MatchesPsTree('root', 'app --arg', children=[
                MatchesPsTree('appuser', 'app --child1'),
                MatchesPsTree('appuser', 'app --child2'),
            ]),
            MatchesPsTree('root', 'app2 --arg', children=[
                MatchesPsTree('root', 'app2 --child'),
            ]),
        ])
        mm = matcher.match(ps_tree).describe()
        assert "mismatches in children:" in mm
        assert "'app --child3' != 'app --child2': args" in mm

    def test_using_assert_that(self):
        """
        MatchesPsTree can be used with assert_that() from testtools.
        """
        pst = PsTree(PsRow(1, 0, 'root', 'tini -- app'), [
            PsTree(PsRow(2, 1, 'root', 'app --arg'), [
                PsTree(PsRow(3, 2, 'appuser', 'app --child1')),
                PsTree(PsRow(4, 2, 'appuser', 'app --child2')),
            ]),
            PsTree(PsRow(5, 1, 'root', 'app2 --arg'), [
                PsTree(PsRow(6, 5, 'root', 'app2 --child')),
            ]),
        ])

        # This passes if the MatchesPsTree matcher matches.
        assert_that(pst, MatchesPsTree('root', 'tini -- app', children=[
            MatchesPsTree('root', 'app --arg', children=[
                MatchesPsTree('appuser', 'app --child1'),
                MatchesPsTree('appuser', 'app --child2'),
            ]),
            MatchesPsTree('root', 'app2 --arg', children=[
                MatchesPsTree('root', 'app2 --child'),
            ]),
        ]))

        # This passes if the MatchesPsTree matcher does not match.
        assert_that(pst, Not(MatchesPsTree('root', 'tini -- app', children=[
            MatchesPsTree('root', 'app --arg', children=[
                MatchesPsTree('appuser', 'app --child1'),
            ]),
            MatchesPsTree('root', 'app2 --arg', children=[
                MatchesPsTree('root', 'app2 --child'),
                MatchesPsTree('appuser', 'app --child2'),
            ]),
        ])))
