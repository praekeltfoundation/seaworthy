from seaworthy.ps import PsRow, PsTree
from seaworthy.testtools import MatchesPsTree


class TestMatchesPsTree(object):
    def test_minimal_tree(self):
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
