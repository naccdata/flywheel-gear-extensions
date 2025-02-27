from uploads.uploader import LabelTemplate


class TestLabelTemplate:

    def test_simple_template(self):
        template_string = "enrollment"
        template = LabelTemplate(template=template_string)
        assert template.instantiate({'alpha': 'beta'}) == template_string

    def test_template(self):
        template_string = "VISIT-$visitnum"
        template = LabelTemplate(template=template_string)
        try:
            template.instantiate({'alpha': 'beta'})
            assert False, "cannot instantiate template with data"  # noqa: B011
        except ValueError as error:
            assert str(
                error) == "Error creating label, missing column 'visitnum'"

        assert template.instantiate({'visitnum': 1}) == 'VISIT-1'

    def test_transform_template(self):
        template_string = "$module"
        template = LabelTemplate(template=template_string, transform='upper')
        value = 'enrollv1'
        assert template.instantiate({'module': value}) == value.upper()

    def test_environment(self):
        template_string = "$alpha"
        template = LabelTemplate(template=template_string)
        value = 'dummy'
        assert template.instantiate({'beta': 'one'},
                                    environment={'alpha': value}) == value

        try:
            template.instantiate({}, environment={})
            assert False, "cannot instatiate template"  # noqa: B011
        except ValueError as error:
            assert str(error) == "Error creating label, missing column 'alpha'"
