"""Tests the validated-timestamp write/read contract.

The gear writes `file.info.validated-timestamp` as an aware datetime and
relies on the Flywheel metadata encoder to serialize it. Downstream
gears read it back with `parse_timestamp`. These tests pin that contract
so a change in the encoder's output format cannot break the readers
silently.
"""

import json
from datetime import datetime, timezone

from fw_gear.metadata import MetadataEncoder
from nacc_common.form_dates import parse_timestamp


def _serialize(info: dict) -> dict:
    """Serialize file.info the way Metadata.clean() does before upload."""
    return json.loads(json.dumps(info, cls=MetadataEncoder))


class TestValidatedTimestampRoundTrip:
    def test_datetime_is_serialized_to_iso_with_offset(self):
        """The encoder turns the datetime into an offset-bearing ISO string."""
        written = datetime(2026, 10, 7, 16, 51, 59, tzinfo=timezone.utc)

        stored = _serialize({"validated-timestamp": written})["validated-timestamp"]

        assert isinstance(stored, str)
        assert stored == "2026-10-07T16:51:59.000+00:00"

    def test_stored_value_is_readable_by_parse_timestamp(self):
        """What the gear writes is exactly what the readers can parse."""
        written = datetime.now(timezone.utc)

        stored = _serialize({"validated-timestamp": written})["validated-timestamp"]
        read_back = parse_timestamp(stored)

        # the encoder truncates to milliseconds
        assert read_back == written.replace(
            microsecond=(written.microsecond // 1000) * 1000
        )
        assert read_back.tzinfo is not None

    def test_legacy_format_still_readable(self):
        """Files written before this convention carry the older format.

        Those values are not rewritten, so readers must keep handling
        them.
        """
        assert parse_timestamp("2026-10-07 16:45:51") == datetime(
            2026, 10, 7, 16, 45, 51, tzinfo=timezone.utc
        )

    def test_cleared_sentinel_reads_as_none(self):
        """`reset_visit_qc_metadata` clears the key with an empty string."""
        stored = _serialize({"validated-timestamp": ""})["validated-timestamp"]

        assert parse_timestamp(stored) is None
