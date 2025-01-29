from curator.compute import SymbolTable


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
