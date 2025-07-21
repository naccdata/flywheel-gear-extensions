from dates.form_dates import DATE_FORMATS, DateFormatException, parse_date


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
