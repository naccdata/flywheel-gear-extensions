import yaml
from curator.curator import AttributeCondition, ComputeDefinition, ValueDefinition


class TestSerialization:

    def test_compute(self):
        compute = ComputeDefinition(compute='create_object',
                                    arguments={
                                        'attributes': {
                                            'race': '$file.demographics.race',
                                            'date': '$session.date'
                                        }
                                    })
        yaml_dump = yaml.safe_dump(compute.model_dump(),
                                   allow_unicode=True,
                                   default_flow_style=False,
                                   sort_keys=False)
        assert yaml_dump == ('compute: create_object\n'
                             'arguments:\n'
                             '  attributes:\n'
                             '    race: $file.demographics.race\n'
                             '    date: $session.date\n')

    def test_value(self):
        value = ValueDefinition(attribute='form.race')
        yaml_dump = yaml.safe_dump(value.model_dump(),
                                   allow_unicode=True,
                                   default_flow_style=False,
                                   sort_keys=False)
        assert yaml_dump == 'attribute: form.race\n'

    def test_predicate(self):
        predicate = AttributeCondition(predicate='is_form')
        yaml_dump = yaml.safe_dump(predicate.model_dump(exclude_none=True),
                                   allow_unicode=True,
                                   default_flow_style=False,
                                   sort_keys=False)
        assert yaml_dump == 'predicate: is_form\n'

        predicate = AttributeCondition(predicate='is_form',
                                       arguments={'name': 'UDS'})
        yaml_dump = yaml.safe_dump(predicate.model_dump(),
                                   allow_unicode=True,
                                   default_flow_style=False,
                                   sort_keys=False)
        assert yaml_dump == ('predicate: is_form\n'
                             'arguments:\n'
                             '  name: UDS\n')

        predicate = AttributeCondition(predicate='is_form',
                                       arguments={
                                           'name': 'UDS',
                                           'version': '3.0'
                                       })
        yaml_dump = yaml.safe_dump(predicate.model_dump(),
                                   allow_unicode=True,
                                   default_flow_style=False,
                                   sort_keys=False)
        assert yaml_dump == ('predicate: is_form\n'
                             'arguments:\n'
                             '  name: UDS\n'
                             "  version: '3.0'\n")
