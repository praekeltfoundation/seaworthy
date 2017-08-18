from seaworthy.ps import PsRow, PsTree
from seaworthy.testtools import MatchesPsTree


class TestMatchesPsTree(object):
    def test_minimal_tree_matches(self):
        """
        MatchesPsTree can match a single-process tree.
        """
        ps_tree = PsTree(PsRow(1, 0, 'root', 'tini -- echo "hi"'))

        matcher = MatchesPsTree('root', 'tini -- echo "hi"')
        assert matcher.match(ps_tree) is None

        matcher = MatchesPsTree('root', 'tini -- echo "hi"', 0)
        assert matcher.match(ps_tree) is None

        matcher = MatchesPsTree('root', 'tini -- echo "hi"', pid=1)
        assert matcher.match(ps_tree) is None

        matcher = MatchesPsTree('root', 'tini -- echo "hi"', 0, 1)
        assert matcher.match(ps_tree) is None

        matcher = MatchesPsTree('root', 'tini -- echo "hi"', 0, 1, children=[])
        assert matcher.match(ps_tree) is None

    def test_minimal_tree_mismatches(self):
        """
        MatchesPsTree can match a single-process tree.
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
