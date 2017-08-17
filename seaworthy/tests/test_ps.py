from seaworthy.ps import build_process_tree, PsRow, PsTree


class TestPsTree(object):
    def test_count(self):
        ps_tree = PsTree(
            row=PsRow('1', '0', 'root', "tini -- nginx -g 'daemon off;'"),
            children=[
                PsTree(
                    row=PsRow('6', '1', 'root',
                              'nginx: master process nginx -g daemon off;'),
                    children=[
                        PsTree(
                            row=('8', '6', 'nginx', 'nginx: worker process'),
                            children=[]
                        )]
                )]
        )
        assert ps_tree.count() == 3


class TestBuildProcessTreeFunc(object):
    def test_single_process(self):
        ps_row = PsRow('1', '0', 'root', 'tini -- echo "hi"')
        ps_tree = build_process_tree([ps_row])

        assert ps_tree == PsTree(row=ps_row, children=[])

    def test_simple_tree(self):
        ps_rows = [
            PsRow('1', '0', 'root', "tini -- nginx -g 'daemon off;'"),
            PsRow('6', '1', 'root',
                  'nginx: master process nginx -g daemon off;'),
            PsRow('8', '6', 'nginx', 'nginx: worker process'),
        ]
        ps_tree = build_process_tree(ps_rows)
        assert ps_tree == PsTree(
            row=ps_rows[0],
            children=[
                PsTree(
                    row=ps_rows[1],
                    children=[PsTree(row=ps_rows[2], children=[])]
                )]
        )
