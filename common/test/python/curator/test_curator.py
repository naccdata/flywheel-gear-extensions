from curator.compute import ComputeDefinition
from curator.curator import (
    AnnotatedAttribute,
    AttributeCondition,
    AttributeCurator,
)


class TestCurator:

    def test_race_curator(self):
        is_udsv3 = AttributeCondition(predicate='is_form',
                                      arguments={
                                          'name': 'UDS',
                                          'version': '3.0'
                                      })
        race_curator = AttributeCurator(
            subject=[
                AnnotatedAttribute(
                    attribute='demographics.latest.race',
                    rule=ComputeDefinition(
                        compute='update_latest',
                        arguments={'attribute': '$session.demographics.race'}))
            ],
            session=[
                AnnotatedAttribute(attribute='demographics.race',
                                   rule=ComputeDefinition(
                                       compute='create_object',
                                       arguments={
                                           'attributes': {
                                               'race':
                                               '$file.demographics.race',
                                               'date': '$session.date'
                                           }
                                       }))
            ],
            file=[
                AnnotatedAttribute(attribute='demographics.race',
                                   condition=is_udsv3,
                                   rule=ComputeDefinition(
                                       compute='first_non_null',
                                       arguments={
                                           'attributes': [
                                               'file.form.racesec',
                                               'file.form.raceter',
                                               'file.form.race'
                                           ]
                                       })),
                AnnotatedAttribute(
                    attribute='form.race',
                    condition=is_udsv3,
                    rule=ComputeDefinition(
                        compute='apply',
                        arguments={
                            'attribute': 'forms.json.race',
                            'mapping': {
                                1: "White",
                                2: "Black or African American",
                                3: "American Indian or Alaska Native",
                                4: "Native Hawaiian or Other Pacific Islander",
                                5: "Asian"
                            },
                            'undefined': "Unknown or Not Reported"
                        })),
                AnnotatedAttribute(attribute='form.racesec',
                                   condition=is_udsv3,
                                   rule=ComputeDefinition(
                                       compute='is_not_null',
                                       arguments={
                                           'attribute': 'forms.json.racesec',
                                           'return': 'More Than One Race'
                                       })),
                AnnotatedAttribute(attribute='form.raceter',
                                   condition=is_udsv3,
                                   rule=ComputeDefinition(
                                       compute='is_not_null',
                                       arguments={
                                           'attribute': 'forms.json.raceter',
                                           'return': 'More Than One Race'
                                       }))
            ])
