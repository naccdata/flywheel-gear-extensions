from csv_app.uploader import LabelTemplate, UploadTemplateInfo


class TestLabelTemplate:

    def test_simple_template(self):
        template_string = "enrollment"
        template = LabelTemplate(
            UploadTemplateInfo(type='session', template=template_string))
        assert template.instantiate({'alpha': 'beta'}) == template_string

    def test_template(self):
        template_string = "VISIT-$visitnum"
        template = LabelTemplate(
            UploadTemplateInfo(type='session', template=template_string))
        try:
            template.instantiate({'alpha': 'beta'})
            assert False, "cannot instantiate template with data"  # noqa: B011
        except ValueError as error:
            assert str(
                error
            ) == "Error creating session label, missing column 'visitnum'"

        assert template.instantiate({'visitnum': 1}) == 'VISIT-1'

    def test_transform_template(self):
        template_string = "$module"
        template = LabelTemplate(
            UploadTemplateInfo(type='session',
                               template=template_string,
                               transform='upper'))
        value = 'enrollv1'
        assert template.instantiate({'module': value}) == value.upper()
