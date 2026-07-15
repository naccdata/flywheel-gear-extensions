from dates.dates import normalize_date
from nacc_common.form_dates import DATE_FORMATS, DateFormatException, parse_date


class TestDateParsing:
    def test_parse_form_date(self):
        formats = DATE_FORMATS

        try:
            parse_date(date_string="10/06/2024", formats=formats)
            assert True, "format should match"
        except DateFormatException as error:
            assert False, f"should be no error, got {error}"  # noqa: B011

        try:
            parse_date(date_string="2024-10-06", formats=formats)
            assert True, "format should match"
        except DateFormatException as error:
            assert False, f"should be no error, got {error}"  # noqa: B011

        try:
            parse_date(date_string="20241006", formats=formats)
            assert False, "format should not match"  # noqa: B011
        except DateFormatException as error:
            assert True, f"should be error, got {error}"


class TestDateNormalization:
    def test_normalize_date(self):
        assert normalize_date("1/26/2025", "%Y-%m-%d") == "2025-01-26"
        assert normalize_date("2026/2/4", "%Y/%m/%d") == "2026/02/04"
        assert normalize_date("2026-04-29", "%m-%d-%Y") == "04-29-2026"
        assert normalize_date("3-13-2026", "%m/%d/%Y") == "03/13/2026"

        # with hour/minute/second
        assert normalize_date("05-01-2026", "%Y%m%d%H%M%S") == "20260501000000"
