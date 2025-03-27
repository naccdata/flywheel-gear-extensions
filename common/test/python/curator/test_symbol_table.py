from curator.symbol_table import SymbolTable


class TestSymbolTable:

    def test_empty(self):
        table = SymbolTable()
        assert table.get('dummy') is None

    def test_non_empty(self):
        table = SymbolTable({'a': {'b': {'c': 1}}})
        assert table.get('a') == {'b': {'c': 1}}
        assert table.get('a.b') == {'c': 1}
        assert table.get('a.b.c') == 1
        assert table.get('a.b.c.d') is None

    def test_set(self):
        table = SymbolTable()
        table['a.b.c'] = {'d': 1}
        assert table.get('a.b.c.d') == 1
        assert table['a.b.c.d'] == 1

        table['a.b.e.d'] = 2
        assert table.get('a.b.e.d') == 2

        table['a.b.c.d'] = 3
        assert table.get('a.b.c.d') == 3

    def test_initialized(self):
        table = SymbolTable({
            'a': {
                'b': {
                    'x': 1
                }
            },
            's': {
                'a': {
                    'y': 2,
                    'd': ['alpha', 'beta']
                }
            }
        })
        assert table.get('a.b.x') == 1
        assert table.get('s.a.y') == 2
        table['a.b.c'] = {'d': 1}
        assert table.get('a.b.c.d') == 1
        assert table['a.b.c.d'] == 1

        table['a.b.e.d'] = 2
        assert table.get('a.b.e.d') == 2

        table['a.b.c.d'] = 3
        assert table.get('a.b.c.d') == 3

        assert table.get('s.a.d') == ['alpha', 'beta']

    def test_zero_value(self):
        table = SymbolTable({'a': 0})
        assert table.get('a') is not None
        assert table.get('a') == 0
