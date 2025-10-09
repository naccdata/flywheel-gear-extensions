from outputs.outputs import StringCSVWriter


class TestStringCSVWriter:

    def test_writer(self):
        writer = StringCSVWriter()
        writer.write({"alpha": 1, "beta": "one"})
        content = writer.get_content()
        assert content == 'alpha,beta\n1,one\n'
