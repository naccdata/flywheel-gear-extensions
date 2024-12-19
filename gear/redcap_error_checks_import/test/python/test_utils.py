"""Tests the util classes."""
import pytest
from redcap_error_checks_import_app.utils import ErrorCheckImportStats, ErrorCheckKey


@pytest.fixture(scope='function')
def stats():
    return ErrorCheckImportStats()


class TestErrorCheckKey:
    """Tests the ErrorCheckKey class.

    For creation, the tests in test_load_error_check_csv test the valid
    case thoroughly so not needed here.
    """

    def test_invalid_key(self):
        """Test invalid case."""
        key = "CSV/badmodule/test.csv"

        with pytest.raises(ValueError) as e:
            ErrorCheckKey.create_from_key(key)

        assert str(e.value) == (
            f"Cannot parse ErrorCheckKey components from {key}; " +
            "Expected to be of the form " +
            "CSV / MODULE / FORM_VER / PACKET / filename")

    def test_no_top_level_csv(self):
        """Test invalid case."""
        key = "JSON/module/1.0/dummy_packet/form_dummy_error_checks.json"

        with pytest.raises(ValueError) as e:
            ErrorCheckKey.create_from_key(key)

        assert str(e.value) == "Expected CSV at top level of S3 key"

    def test_get_visit_type(self):
        """Test get visit type."""
        base_key = \
            'CSV/module/1.0/REPLACE/form_dummy_error_checks.csv'

        for packet in ['F', 'FF', 'FL']:
            key = base_key.replace('REPLACE', packet)
            ec_key = ErrorCheckKey.create_from_key(key)
            assert ec_key.get_visit_type() == 'fvp'

        for packet in ['I', 'IF', 'IL']:
            key = base_key.replace('REPLACE', packet)
            ec_key = ErrorCheckKey.create_from_key(key)
            assert ec_key.get_visit_type() == 'ivp'

        key = base_key.replace('REPLACE', 'I4')
        ec_key = ErrorCheckKey.create_from_key(key)
        assert ec_key.get_visit_type() == 'i4vp'

    def test_get_visit_type_enrollment(self):
        """This get visit type on an enrollment form, which should result in a
        None visit type."""
        base_key = \
            'CSV/ENROLL/1.0/form_dummy_error_checks.csv'
        ec_key = ErrorCheckKey.create_from_key(base_key)
        assert ec_key.get_visit_type() is None


class TestErrorCheckImportStats:
    """Tests the ErrorCheckImportStats class.

    Mainly the add_error_codes method, as the others methods are
    trivial.
    """

    def test_add_error_codes_no_duplicates(self, stats):
        """Test adding error codes, no duplicates."""
        for code in range(10):
            assert stats.add_error_codes([code]) == []

        assert len(stats.all_error_codes) == 10

    def test_add_error_codes_duplicates(self, stats):
        """Test adding error codes with duplicates."""
        for code in range(10):
            assert stats.add_error_codes([code]) == []
        for code in range(10):
            assert stats.add_error_codes([code]) == [code]

        assert len(stats.all_error_codes) == 20
