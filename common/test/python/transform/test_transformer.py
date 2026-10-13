import json

from configs.ingest_configs import FormReleaseDates
from keys.keys import SysErrorCodes
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_configs import uds_ingest_configs
from transform.transformer import (
    DateTransformer,
    ReleaseDateTransformation,
    TransformationSchema,
    VersionMap,
    VersionMapTransformation,
)


class TestVersionMap:
    def test_mismatch(self):
        version_map = VersionMap(fieldname="dummy", value_map={}, default="dummy-value")
        version = version_map.apply({"dummy": "blah"})
        assert version == "dummy-value"

    def test_match(self):
        version_map = VersionMap(
            fieldname="dummy", value_map={"alpha": "beta"}, default="default-value"
        )
        version = version_map.apply({"dummy": "alpha"})
        assert version == "beta"

    # TODO: should not having the fieldname as a key be an error?


class TestVersionMapTransformation:
    def test_empty_fields(self):
        field_filter = VersionMapTransformation(
            version_map=VersionMap(
                fieldname="dummy", value_map={"alpha-raw": "beta"}, default="alpha"
            ),
            fields={"alpha": [], "beta": []},
        )
        input_record = {
            "dummy": "alpha-raw",
        }
        error_writer = ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")
        record = field_filter.apply(input_record, error_writer, 1, uds_ingest_configs())

        assert record == input_record

    def test_drop_fields(self):
        field_filter = VersionMapTransformation(
            version_map=VersionMap(
                fieldname="dummy", value_map={"alpha-raw": "beta"}, default="alpha"
            ),
            fields={"alpha": ["a1", "a2"], "beta": ["b1", "b2"]},
        )
        input_record = {
            "dummy": "alpha-raw",
            "common1": "c1",
            "common2": "c2",
            "a1": "a1-val",
            "a2": "a2-val",
            "b1": "",
            "b2": "",
        }
        error_writer = ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")
        record = field_filter.apply(input_record, error_writer, 1, uds_ingest_configs())
        assert record
        assert "b1" not in record and "b2" not in record
        assert set(record.keys()) == {"dummy", "common1", "common2", "a1", "a2"}

    def test_drop_fields_nofill_true(self):
        field_filter = VersionMapTransformation(
            version_map=VersionMap(
                fieldname="dummy", value_map={"alpha-raw": "beta"}, default="alpha"
            ),
            nofill=True,
            fields={"alpha": ["a1"], "beta": ["b1"]},
        )
        input_record = {
            "dummy": "alpha-raw",
            "common1": "c1",
            "common2": "c2",
            "a1": "a1-val",
            "b1": "b1-val",
        }
        error_writer = ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")
        record = field_filter.apply(input_record, error_writer, 1, uds_ingest_configs())

        assert not record

    def test_diff_fields_nofill_false(self):
        field_filter = VersionMapTransformation(
            version_map=VersionMap(
                fieldname="dummy", value_map={"alpha-raw": "beta"}, default="alpha"
            ),
            nofill=False,
            fields={"alpha": ["a1"], "beta": ["b1"]},
        )
        input_record = {
            "dummy": "alpha-raw",
            "common1": "c1",
            "common2": "c2",
            "a1": "a1-val",
            "b1": "b1-val",
        }
        error_writer = ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")
        record = field_filter.apply(input_record, error_writer, 1, uds_ingest_configs())

        assert record
        assert [k for k in record if k in input_record and k != "b1"]

    def __mode_transformation(self, nofill: bool = True):
        """Creates a transformation where the indicator field is one of the
        fields it drops, as the COVID mode variables are configured."""
        return VersionMapTransformation(
            version_map=VersionMap(
                fieldname="modef2",
                value_map={"1": "F2_SUBMITTED", "2": "F2_SUBMITTED"},
                default="F2_NOT_SUBMITTED",
            ),
            nofill=nofill,
            fields={
                "F2_SUBMITTED": [],
                "F2_NOT_SUBMITTED": ["modef2", "c19cdr"],
            },
        )

    def test_indicator_field_exempt_from_nofill(self):
        """The indicator field is dropped without being checked for a value.

        Its value is what selected the fields to drop, so it is not
        stray data.
        """
        field_filter = self.__mode_transformation()
        input_record = {"modef2": "0", "c19cdr": "", "ptid": "dummy-ptid"}
        error_writer = ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")

        record = field_filter.apply(input_record, error_writer, 1, uds_ingest_configs())

        assert record == {"ptid": "dummy-ptid"}
        assert not error_writer.errors()

    def test_indicator_field_blank(self):
        """A blank indicator field drops the same fields."""
        field_filter = self.__mode_transformation()
        input_record = {"modef2": "", "c19cdr": "", "ptid": "dummy-ptid"}
        error_writer = ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")

        record = field_filter.apply(input_record, error_writer, 1, uds_ingest_configs())

        assert record == {"ptid": "dummy-ptid"}
        assert not error_writer.errors()

    def test_data_fields_still_checked(self):
        """Exempting the indicator field does not exempt the data fields."""
        field_filter = self.__mode_transformation()
        input_record = {"modef2": "0", "c19cdr": "5", "ptid": "dummy-ptid"}
        error_writer = ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")

        record = field_filter.apply(input_record, error_writer, 1, uds_ingest_configs())

        assert not record
        assert len(error_writer.errors()) == 1
        file_error = error_writer.errors()[0]
        assert file_error.error_code == SysErrorCodes.EXCLUDED_FIELDS
        # only the data field is reported, not the indicator field
        assert "c19cdr" in file_error.message
        assert "modef2" not in file_error.message

    def test_indicator_field_retained_when_submitted(self):
        """Nothing is dropped when the indicator selects an empty field
        list."""
        field_filter = self.__mode_transformation()
        input_record = {"modef2": "1", "c19cdr": "5", "ptid": "dummy-ptid"}
        error_writer = ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")

        record = field_filter.apply(input_record, error_writer, 1, uds_ingest_configs())

        assert record == input_record
        assert not error_writer.errors()


class TestDateTransformer:
    def test_nodate(self):
        transformer = DateTransformer(
            ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")
        )
        input_record = {"dummy": "alpha-raw"}
        record = transformer.transform(input_record, 0)
        assert record == input_record

    def test_date(self):
        transformer = DateTransformer(
            ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")
        )
        record = transformer.transform({FieldNames.DATE_COLUMN: "2024/1/1"}, 0)
        assert record
        assert record[FieldNames.DATE_COLUMN] == "2024-01-01"

        record = transformer.transform({FieldNames.DATE_COLUMN: "20240101"}, 0)
        assert record
        assert record[FieldNames.DATE_COLUMN] == "2024-01-01"

        record = transformer.transform({FieldNames.DATE_COLUMN: "01012024"}, 0)
        assert not record

    @staticmethod
    def __transformer(date_field: str | None = None) -> DateTransformer:
        return DateTransformer(
            ListErrorWriter(container_id="dummy", fw_path="dummy/dummy"),
            date_field=date_field,
        )

    def test_form_dates_normalized(self):
        """Any field named frmdate* is normalized along with the date field."""
        transformer = self.__transformer()
        record = transformer.transform(
            {
                FieldNames.DATE_COLUMN: "2024/1/1",
                "frmdated1c": "2024/1/2",
                "frmdatea1": "20240103",
            },
            1,
        )
        assert record == {
            FieldNames.DATE_COLUMN: "2024-01-01",
            "frmdated1c": "2024-01-02",
            "frmdatea1": "2024-01-03",
        }

    def test_form_date_blank_skipped(self):
        """A form date is blank when the form was not submitted, so a blank
        value is left as is and is not an error."""
        error_writer = ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")
        transformer = DateTransformer(error_writer)
        record = transformer.transform(
            {
                FieldNames.DATE_COLUMN: "2024/1/1",
                "frmdated1c": "",
                "frmdateb1": "   ",
            },
            1,
        )
        assert record == {
            FieldNames.DATE_COLUMN: "2024-01-01",
            "frmdated1c": "",
            "frmdateb1": "   ",
        }
        assert not error_writer.errors()

    def test_form_date_invalid_kept(self):
        """An unparsable form date is left as submitted without an error, and
        the remaining form dates are still normalized."""
        error_writer = ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")
        transformer = DateTransformer(error_writer)
        record = transformer.transform(
            {
                FieldNames.DATE_COLUMN: "2024/1/1",
                "frmdated1c": "01012024",
                "frmdatea1": "2024/1/3",
            },
            1,
        )
        assert record == {
            FieldNames.DATE_COLUMN: "2024-01-01",
            "frmdated1c": "01012024",
            "frmdatea1": "2024-01-03",
        }
        assert not error_writer.errors()

    def test_form_date_case_insensitive(self):
        """The field name is matched regardless of case."""
        record = self.__transformer().transform({"FRMDATED1C": "2024/1/2"}, 1)
        assert record == {"FRMDATED1C": "2024-01-02"}

    def test_invalid_date_skips_form_dates(self):
        """A record rejected for the date field is returned unnormalized."""
        error_writer = ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")
        transformer = DateTransformer(error_writer)
        input_record = {
            FieldNames.DATE_COLUMN: "01012024",
            "frmdated1c": "2024/1/2",
        }
        assert not transformer.transform(input_record, 1)
        assert input_record["frmdated1c"] == "2024/1/2"
        assert len(error_writer.errors()) == 1

    def test_no_date_field_normalizes_form_dates(self):
        """The form dates are normalized when the record has no date field."""
        record = self.__transformer().transform({"frmdated1c": "2024/1/2"}, 1)
        assert record == {"frmdated1c": "2024-01-02"}

    def test_form_date_as_date_field(self):
        """A form date configured as the date field is handled by the date
        field check, and is not reported twice."""
        error_writer = ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")
        transformer = DateTransformer(error_writer, date_field=FieldNames.ENRLFRM_DATE)
        assert not transformer.transform({FieldNames.ENRLFRM_DATE: "01012024"}, 1)
        assert len(error_writer.errors()) == 1


class TestReleaseDateTransformation:
    RELEASE_DATES = FormReleaseDates({"I": {"d1c": "2026-05-01"}})

    @staticmethod
    def __filter() -> ReleaseDateTransformation:
        return ReleaseDateTransformation(
            form_name="d1c",
            fields=["d1c1", "d1c2"],
            header_fields=["frmdated1c"],
            retain_modes=["1", "2"],
        )

    @staticmethod
    def __error_writer() -> ListErrorWriter:
        return ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")

    def __apply(self, release_filter, input_record, error_writer=None):
        module_configs = uds_ingest_configs().model_copy(
            update={"release_dates": self.RELEASE_DATES}
        )
        return release_filter.apply(
            input_record,
            error_writer or self.__error_writer(),
            1,
            module_configs,
        )

    def test_before_release_not_submitted_empty(self):
        """Pre-release, not submitted, data fields empty: data, header, and
        mode fields are dropped; unrelated fields kept."""
        input_record = {
            "packet": "I",
            "visitdate": "2025-01-01",
            "moded1c": "0",
            "d1c1": "",
            "d1c2": "",
            "frmdated1c": "2025-01-01",
            "ptid": "dummy-ptid",
        }
        record = self.__apply(self.__filter(), input_record)
        assert record == {
            "packet": "I",
            "visitdate": "2025-01-01",
            "ptid": "dummy-ptid",
        }

    def test_before_release_not_submitted_data_filled_nofill(self):
        """Pre-release, not submitted, a data field is filled with nofill:

        record rejected with an EXCLUDED_FIELDS error.
        """
        error_writer = self.__error_writer()
        input_record = {
            "packet": "I",
            "naccid": "NACC000000",
            "ptid": "dummy-ptid",
            "adcid": "0",
            "visitdate": "2025-01-01",
            "moded1c": "0",
            "d1c1": "some-value",
            "d1c2": "",
        }
        record = self.__apply(self.__filter(), input_record, error_writer)
        assert record is None
        errors = error_writer.errors()
        assert len(errors) == 1
        assert errors[0].error_code == SysErrorCodes.EXCLUDED_FIELDS

    def test_before_release_not_submitted_header_filled_nofill(self):
        """Pre-release, not submitted, only a header field filled with nofill:

        no error; data, header, and mode fields dropped.
        """
        error_writer = self.__error_writer()
        input_record = {
            "packet": "I",
            "visitdate": "2025-01-01",
            "moded1c": "0",
            "d1c1": "",
            "d1c2": "",
            "frmdated1c": "2025-01-01",
        }
        record = self.__apply(self.__filter(), input_record, error_writer)
        assert record == {"packet": "I", "visitdate": "2025-01-01"}
        assert not error_writer.errors()

    def test_before_release_not_submitted_data_filled_no_nofill(self):
        """Pre-release, not submitted, data field filled but nofill=False:

        fields dropped, no error.
        """
        release_filter = ReleaseDateTransformation(
            form_name="d1c",
            fields=["d1c1", "d1c2"],
            nofill=False,
        )
        error_writer = self.__error_writer()
        input_record = {
            "packet": "I",
            "visitdate": "2025-01-01",
            "moded1c": "0",
            "d1c1": "some-value",
        }
        record = self.__apply(release_filter, input_record, error_writer)
        assert record == {"packet": "I", "visitdate": "2025-01-01"}
        assert not error_writer.errors()

    def test_before_release_submitted(self):
        """Pre-release but submitted (mode == 1): nothing dropped."""
        input_record = {
            "packet": "I",
            "visitdate": "2025-01-01",
            "moded1c": "1",
            "d1c1": "some-value",
        }
        record = self.__apply(self.__filter(), input_record)
        assert record == input_record

    def test_before_release_alternate_retain_mode(self):
        """Pre-release with a second accepted retain mode (mode == 2):

        nothing dropped.
        """
        input_record = {
            "packet": "I",
            "visitdate": "2025-01-01",
            "moded1c": "2",
            "d1c1": "some-value",
        }
        record = self.__apply(self.__filter(), input_record)
        assert record == input_record

    def test_before_release_integer_mode_retained(self):
        """Mode value supplied as an integer that maps to a retain mode:

        nothing dropped (integer is coerced to string for comparison).
        """
        input_record = {
            "packet": "I",
            "visitdate": "2025-01-01",
            "moded1c": 1,
            "d1c1": "some-value",
        }
        record = self.__apply(self.__filter(), input_record)
        assert record == input_record

    def test_before_release_integer_mode_dropped(self):
        """Mode value supplied as an integer not in retain modes: data, header,
        and mode fields are dropped (integer is coerced to string)."""
        input_record = {
            "packet": "I",
            "visitdate": "2025-01-01",
            "moded1c": 0,
            "d1c1": "",
            "d1c2": "",
            "frmdated1c": "2025-01-01",
        }
        record = self.__apply(self.__filter(), input_record)
        assert record == {"packet": "I", "visitdate": "2025-01-01"}

    def test_on_or_after_release(self):
        """Visit on/after the release date: nothing dropped."""
        input_record = {
            "packet": "I",
            "visitdate": "2026-06-01",
            "moded1c": "0",
            "d1c1": "some-value",
        }
        record = self.__apply(self.__filter(), input_record)
        assert record == input_record

    def test_missing_visit_date(self):
        """No visit date: nothing dropped."""
        input_record = {"packet": "I", "moded1c": "0", "d1c1": "some-value"}
        record = self.__apply(self.__filter(), input_record)
        assert record == input_record

    def test_packet_not_in_release_dates(self):
        """Visit packet has no configured release date for the form: treated as
        already released, nothing dropped."""
        release_filter = self.__filter()
        input_record = {
            "packet": "F",
            "visitdate": "2025-01-01",
            "moded1c": "0",
            "d1c1": "some-value",
        }
        record = self.__apply(release_filter, input_record)
        assert record == input_record

    def test_form_not_in_release_dates(self):
        """Form has no configured release date: treated as already released,

        nothing dropped.
        """
        release_filter = self.__filter()
        input_record = {
            "packet": "I",
            "visitdate": "2025-01-01",
            "moded1c": "0",
            "d1c1": "some-value",
        }
        module_configs = uds_ingest_configs().model_copy(
            update={
                "release_dates": FormReleaseDates({"I": {"otherform": "2026-05-01"}})
            }
        )
        record = release_filter.apply(
            input_record,
            self.__error_writer(),
            1,
            module_configs,
        )
        assert record == input_record


class TestTransformationSchema:
    def test_grouped_transformations(self):
        """A module with both categories parses to the correct concrete
        transformation subclasses in each category list."""
        schema = {
            "UDS": {
                "field_transformations": [
                    {
                        "transform_type": "version_map",
                        "version_map": {
                            "fieldname": "packet",
                            "value_map": {"F": "IVP"},
                            "default": "FVP",
                        },
                        "fields": {"FVP": ["newinf"], "IVP": ["birthmo"]},
                    }
                ],
                "form_transformations": [
                    {
                        "transform_type": "release_date",
                        "form_name": "d1c",
                        "fields": ["d1c1"],
                        "header_fields": ["frmdated1c"],
                    }
                ],
            }
        }
        transformations = TransformationSchema.model_validate_json(json.dumps(schema))
        module_transforms = transformations.get("UDS")
        assert module_transforms
        assert len(module_transforms.field_transformations) == 1
        assert len(module_transforms.form_transformations) == 1
        assert isinstance(
            module_transforms.field_transformations[0], VersionMapTransformation
        )
        assert isinstance(
            module_transforms.form_transformations[0], ReleaseDateTransformation
        )

    def test_unknown_module_returns_none(self):
        """get() returns None for a module with no transformations."""
        transformations = TransformationSchema()
        assert transformations.get("UDS") is None
