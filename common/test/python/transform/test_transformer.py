from keys.keys import FieldNames
from outputs.errors import ListErrorWriter
from transform.transformer import DateTransformer, FieldFilter, VersionMap


class TestVersionMap:

    def test_mismatch(self):
        version_map = VersionMap(fieldname='dummy',
                                 value_map={},
                                 default='dummy-value')
        version = version_map.apply({'dummy': 'blah'})
        assert version == 'dummy-value'

    def test_match(self):
        version_map = VersionMap(fieldname='dummy',
                                 value_map={'alpha': 'beta'},
                                 default='default-value')
        version = version_map.apply({'dummy': 'alpha'})
        assert version == 'beta'

    # TODO: should not having the fieldname as a key be an error?


class TestFieldFilter:

    def test_empty_fields(self):
        field_filter = FieldFilter(version_map=VersionMap(
            fieldname='dummy',
            value_map={'alpha-raw': 'beta'},
            default='alpha'),
                                   fields={
                                       'alpha': [],
                                       'beta': []
                                   })
        input_record = {
            'dummy': 'alpha-raw',
        }
        record = field_filter.apply(input_record)

        assert record == input_record

    def test_equal_fields(self):
        field_filter = FieldFilter(version_map=VersionMap(
            fieldname='dummy',
            value_map={'alpha-raw': 'beta'},
            default='alpha'),
                                   fields={
                                       'alpha': ['f1'],
                                       'beta': ['f1']
                                   })
        input_record = {'dummy': 'alpha-raw', 'f1': 'v1'}
        record = field_filter.apply(input_record)

        assert record == input_record

    def test_diff_fields(self):
        field_filter = FieldFilter(version_map=VersionMap(
            fieldname='dummy',
            value_map={'alpha-raw': 'beta'},
            default='alpha'),
                                   fields={
                                       'alpha': ['a1'],
                                       'beta': ['b1']
                                   })
        input_record = {'dummy': 'alpha-raw', 'a1': 'v1', 'b1': 'v2'}
        record = field_filter.apply(input_record)

        assert [k for k in record if k in input_record and k != 'b1']


class TestDateTransformer:

    def test_nodate(self):
        transformer = DateTransformer(
            ListErrorWriter(container_id='dummy', fw_path='dummy/dummy'))
        input_record = {'dummy': 'alpha-raw'}
        record = transformer.transform(input_record, 0)
        assert record == input_record

    def test_date(self):
        transformer = DateTransformer(
            ListErrorWriter(container_id='dummy', fw_path='dummy/dummy'))
        record = transformer.transform({FieldNames.DATE_COLUMN: '2024/1/1'}, 0)
        assert record
        assert record[FieldNames.DATE_COLUMN] == '2024-01-01'

        record = transformer.transform({FieldNames.DATE_COLUMN: '20240101'}, 0)
        assert record
        assert record[FieldNames.DATE_COLUMN] == '2024-01-01'

        record = transformer.transform({FieldNames.DATE_COLUMN: '01012024'}, 0)
        assert not record
