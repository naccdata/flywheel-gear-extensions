"""Unit tests for filter_approved_records().

Tests that the function correctly filters records based on the
permissions_approval and archive_contact fields, retaining records where
permissions_approval == '1' or archive_contact == '1'.

Requirements: 1.1, 1.2, 2.1, 2.2, 4.1
"""

from directory_app.main import filter_approved_records


class TestFilterApprovedRecords:
    """Tests for filter_approved_records()."""

    def test_empty_list_returns_empty(self) -> None:
        """Empty input returns empty output."""
        assert filter_approved_records([]) == []

    def test_all_approved_returns_all(self) -> None:
        """All approved records are retained."""
        records = [
            {"email": "a@test.com", "permissions_approval": "1"},
            {"email": "b@test.com", "permissions_approval": "1"},
            {"email": "c@test.com", "permissions_approval": "1"},
        ]
        result = filter_approved_records(records)
        assert result == records

    def test_mixed_records_returns_only_approved(self) -> None:
        """Only records with permissions_approval == '1' are returned."""
        approved = {"email": "approved@test.com", "permissions_approval": "1"}
        unapproved_zero = {"email": "zero@test.com", "permissions_approval": "0"}
        unapproved_empty = {"email": "empty@test.com", "permissions_approval": ""}
        unapproved_yes = {"email": "yes@test.com", "permissions_approval": "Yes"}

        records = [approved, unapproved_zero, unapproved_empty, unapproved_yes]
        result = filter_approved_records(records)
        assert result == [approved]

    def test_missing_key_excludes_record(self) -> None:
        """Records missing the permissions_approval key are excluded."""
        approved = {"email": "approved@test.com", "permissions_approval": "1"}
        missing_key = {"email": "nokey@test.com"}

        records = [approved, missing_key]
        result = filter_approved_records(records)
        assert result == [approved]

    def test_order_is_preserved(self) -> None:
        """Output records maintain the same order as in the input."""
        records = [
            {"email": "first@test.com", "permissions_approval": "1"},
            {"email": "skip@test.com", "permissions_approval": "0"},
            {"email": "second@test.com", "permissions_approval": "1"},
            {"email": "third@test.com", "permissions_approval": "1"},
        ]
        result = filter_approved_records(records)
        assert [r["email"] for r in result] == [
            "first@test.com",
            "second@test.com",
            "third@test.com",
        ]


class TestFilterApprovedRecordsArchiveContact:
    """Tests for archive_contact bypass in filter_approved_records().

    Requirements: 1.1, 1.2, 4.1
    """

    def test_archived_unapproved_record_is_retained(self) -> None:
        """Archived record with permissions_approval='0' is retained."""
        record = {
            "email": "archived@test.com",
            "permissions_approval": "0",
            "archive_contact": "1",
        }
        result = filter_approved_records([record])
        assert result == [record]

    def test_archived_approved_record_is_retained(self) -> None:
        """Archived record with permissions_approval='1' is retained."""
        record = {
            "email": "archived@test.com",
            "permissions_approval": "1",
            "archive_contact": "1",
        }
        result = filter_approved_records([record])
        assert result == [record]

    def test_non_archived_unapproved_record_is_excluded(self) -> None:
        """Non-archived record with permissions_approval='0' is excluded."""
        record = {
            "email": "active@test.com",
            "permissions_approval": "0",
            "archive_contact": "0",
        }
        result = filter_approved_records([record])
        assert result == []
