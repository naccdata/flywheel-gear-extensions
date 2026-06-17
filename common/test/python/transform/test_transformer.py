import json

from keys.keys import SysErrorCodes
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter
from transform.transformer import (
    DateTransformer,
    FieldTransformations,
    ReleaseDateFilter,
    VersionMap,
    VersionMapFilter,
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


class TestFieldFilter:
    def test_empty_fields(self):
        field_filter = VersionMapFilter(
            version_map=VersionMap(
                fieldname="dummy", value_map={"alpha-raw": "beta"}, default="alpha"
            ),
            fields={"alpha": [], "beta": []},
        )
        input_record = {
            "dummy": "alpha-raw",
        }
        error_writer = ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")
        record = field_filter.apply(input_record, error_writer, 1, "visitdate")

        assert record == input_record

    def test_drop_fields(self):
        field_filter = VersionMapFilter(
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
        record = field_filter.apply(input_record, error_writer, 1, "visitdate")
        assert record
        assert [k for k in record if k in input_record and k not in ["b1", "b2"]]

    def test_drop_fields_nofill_true(self):
        field_filter = VersionMapFilter(
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
        record = field_filter.apply(input_record, error_writer, 1, "visitdate")

        assert not record

    def test_diff_fields_nofill_false(self):
        field_filter = VersionMapFilter(
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
        record = field_filter.apply(input_record, error_writer, 1, "visitdate")

        assert record
        assert [k for k in record if k in input_record and k != "b1"]


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


class TestReleaseDateFilter:
    @staticmethod
    def __filter() -> ReleaseDateFilter:
        return ReleaseDateFilter(
            release_date="2026-05-01",
            mode_field="moded1c",
            fields=["d1c1", "d1c2"],
            header_fields=["frmdated1c"],
            retain_modes=["1", "2"],
        )

    @staticmethod
    def __error_writer() -> ListErrorWriter:
        return ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")

    def test_before_release_not_submitted_empty(self):
        """Pre-release, not submitted, data fields empty: data, header, and
        mode fields are dropped; unrelated fields kept."""
        release_filter = self.__filter()
        input_record = {
            "visitdate": "2025-01-01",
            "moded1c": "0",
            "d1c1": "",
            "d1c2": "",
            "frmdated1c": "2025-01-01",
            "ptid": "dummy-ptid",
        }
        record = release_filter.apply(
            input_record, self.__error_writer(), 1, "visitdate"
        )
        assert record == {"visitdate": "2025-01-01", "ptid": "dummy-ptid"}

    def test_before_release_not_submitted_data_filled_nofill(self):
        """Pre-release, not submitted, a data field is filled with nofill:
        record rejected with an EXCLUDED_FIELDS error."""
        release_filter = self.__filter()
        error_writer = self.__error_writer()
        input_record = {
            "naccid": "NACC000000",
            "ptid": "dummy-ptid",
            "adcid": "0",
            "visitdate": "2025-01-01",
            "moded1c": "0",
            "d1c1": "some-value",
            "d1c2": "",
        }
        record = release_filter.apply(input_record, error_writer, 1, "visitdate")
        assert record is None
        errors = error_writer.errors()
        assert len(errors) == 1
        assert errors[0].error_code == SysErrorCodes.EXCLUDED_FIELDS

    def test_before_release_not_submitted_header_filled_nofill(self):
        """Pre-release, not submitted, only a header field filled with nofill:
        no error; data, header, and mode fields dropped."""
        release_filter = self.__filter()
        error_writer = self.__error_writer()
        input_record = {
            "visitdate": "2025-01-01",
            "moded1c": "0",
            "d1c1": "",
            "d1c2": "",
            "frmdated1c": "2025-01-01",
        }
        record = release_filter.apply(input_record, error_writer, 1, "visitdate")
        assert record == {"visitdate": "2025-01-01"}
        assert not error_writer.errors()

    def test_before_release_not_submitted_data_filled_no_nofill(self):
        """Pre-release, not submitted, data field filled but nofill=False:
        fields dropped, no error."""
        release_filter = ReleaseDateFilter(
            release_date="2026-05-01",
            mode_field="moded1c",
            fields=["d1c1", "d1c2"],
            nofill=False,
        )
        error_writer = self.__error_writer()
        input_record = {
            "visitdate": "2025-01-01",
            "moded1c": "0",
            "d1c1": "some-value",
        }
        record = release_filter.apply(input_record, error_writer, 1, "visitdate")
        assert record == {"visitdate": "2025-01-01"}
        assert not error_writer.errors()

    def test_before_release_submitted(self):
        """Pre-release but submitted (mode == 1): nothing dropped."""
        release_filter = self.__filter()
        input_record = {
            "visitdate": "2025-01-01",
            "moded1c": "1",
            "d1c1": "some-value",
        }
        record = release_filter.apply(
            input_record, self.__error_writer(), 1, "visitdate"
        )
        assert record == input_record

    def test_before_release_alternate_retain_mode(self):
        """Pre-release with a second accepted retain mode (mode == 2):
        nothing dropped."""
        release_filter = self.__filter()
        input_record = {
            "visitdate": "2025-01-01",
            "moded1c": "2",
            "d1c1": "some-value",
        }
        record = release_filter.apply(
            input_record, self.__error_writer(), 1, "visitdate"
        )
        assert record == input_record

    def test_before_release_integer_mode_retained(self):
        """Mode value supplied as an integer that maps to a retain mode:
        nothing dropped (integer is coerced to string for comparison)."""
        release_filter = self.__filter()
        input_record = {
            "visitdate": "2025-01-01",
            "moded1c": 1,
            "d1c1": "some-value",
        }
        record = release_filter.apply(
            input_record, self.__error_writer(), 1, "visitdate"
        )
        assert record == input_record

    def test_before_release_integer_mode_dropped(self):
        """Mode value supplied as an integer not in retain modes: data, header,
        and mode fields are dropped (integer is coerced to string)."""
        release_filter = self.__filter()
        input_record = {
            "visitdate": "2025-01-01",
            "moded1c": 0,
            "d1c1": "",
            "d1c2": "",
            "frmdated1c": "2025-01-01",
        }
        record = release_filter.apply(
            input_record, self.__error_writer(), 1, "visitdate"
        )
        assert record == {"visitdate": "2025-01-01"}

    def test_on_or_after_release(self):
        """Visit on/after the release date: nothing dropped."""
        release_filter = self.__filter()
        input_record = {
            "visitdate": "2026-06-01",
            "moded1c": "0",
            "d1c1": "some-value",
        }
        record = release_filter.apply(
            input_record, self.__error_writer(), 1, "visitdate"
        )
        assert record == input_record

    def test_missing_visit_date(self):
        """No visit date: nothing dropped."""
        release_filter = self.__filter()
        input_record = {"moded1c": "0", "d1c1": "some-value"}
        record = release_filter.apply(
            input_record, self.__error_writer(), 1, "visitdate"
        )
        assert record == input_record


class TestFieldTransformations:
    def test_mixed_filter_union(self):
        """A module list containing both filter types parses to the correct
        concrete subclasses."""
        schema = {
            "UDS": [
                {
                    "version_map": {
                        "fieldname": "packet",
                        "value_map": {"F": "IVP"},
                        "default": "FVP",
                    },
                    "fields": {"FVP": ["newinf"], "IVP": ["birthmo"]},
                },
                {
                    "release_date": "2026-05-01",
                    "mode_field": "moded1c",
                    "fields": ["d1c1"],
                    "header_fields": ["frmdated1c"],
                },
            ]
        }
        transformations = FieldTransformations.model_validate_json(
            json.dumps(schema)
        )
        filters = transformations.get("UDS")
        assert len(filters) == 2
        assert isinstance(filters[0], VersionMapFilter)
        assert isinstance(filters[1], ReleaseDateFilter)
