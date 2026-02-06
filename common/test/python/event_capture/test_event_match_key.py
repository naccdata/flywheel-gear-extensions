"""Tests for EventMatchKey matching logic."""

from datetime import datetime

import pytest
from event_capture.models import EventMatchKey, UnmatchedSubmitEvents
from event_capture.visit_events import ACTION_SUBMIT, VisitEvent
from nacc_common.error_models import VisitMetadata


class TestEventMatchKey:
    """Tests for EventMatchKey creation and matching."""

    def test_from_visit_metadata_creates_key(self):
        """Test that EventMatchKey can be created from VisitMetadata."""
        metadata = VisitMetadata(
            ptid="NACC123456",
            date="2024-01-15",
            module="UDS",
            visitnum="v1",
            packet="I",
        )

        key = EventMatchKey.from_visit_metadata(metadata)

        assert key.ptid == "NACC123456"
        assert key.date == "2024-01-15"
        assert key.module == "UDS"

    def test_from_visit_metadata_normalizes_module_to_uppercase(self):
        """Test that module is normalized to uppercase for case-insensitive
        matching."""
        metadata = VisitMetadata(
            ptid="NACC123456", date="2024-01-15", module="uds", visitnum="v1"
        )

        key = EventMatchKey.from_visit_metadata(metadata)

        assert key.module == "UDS"

    def test_from_visit_metadata_raises_on_missing_ptid(self):
        """Test that ValueError is raised when ptid is missing."""
        metadata = VisitMetadata(
            ptid="", date="2024-01-15", module="UDS", visitnum="v1"
        )

        with pytest.raises(ValueError, match="ptid is required"):
            EventMatchKey.from_visit_metadata(metadata)

    def test_from_visit_metadata_raises_on_missing_date(self):
        """Test that ValueError is raised when date is missing."""
        metadata = VisitMetadata(
            ptid="NACC123456", date="", module="UDS", visitnum="v1"
        )

        with pytest.raises(ValueError, match="date is required"):
            EventMatchKey.from_visit_metadata(metadata)

    def test_from_visit_metadata_raises_on_missing_module(self):
        """Test that ValueError is raised when module is missing."""
        metadata = VisitMetadata(
            ptid="NACC123456", date="2024-01-15", module="", visitnum="v1"
        )

        with pytest.raises(ValueError, match="module is required"):
            EventMatchKey.from_visit_metadata(metadata)

    def test_keys_with_same_values_are_equal(self):
        """Test that keys with same ptid/date/module are equal."""
        key1 = EventMatchKey(ptid="NACC123456", date="2024-01-15", module="UDS")
        key2 = EventMatchKey(ptid="NACC123456", date="2024-01-15", module="UDS")

        assert key1 == key2
        assert hash(key1) == hash(key2)

    def test_keys_with_different_ptid_are_not_equal(self):
        """Test that keys with different ptid don't match."""
        key1 = EventMatchKey(ptid="NACC123456", date="2024-01-15", module="UDS")
        key2 = EventMatchKey(ptid="NACC999999", date="2024-01-15", module="UDS")

        assert key1 != key2

    def test_keys_with_different_date_are_not_equal(self):
        """Test that keys with different date don't match."""
        key1 = EventMatchKey(ptid="NACC123456", date="2024-01-15", module="UDS")
        key2 = EventMatchKey(ptid="NACC123456", date="2024-01-16", module="UDS")

        assert key1 != key2

    def test_keys_with_different_module_are_not_equal(self):
        """Test that keys with different module don't match."""
        key1 = EventMatchKey(ptid="NACC123456", date="2024-01-15", module="UDS")
        key2 = EventMatchKey(ptid="NACC123456", date="2024-01-15", module="LBD")

        assert key1 != key2

    def test_case_insensitive_module_matching(self):
        """Test that module matching is case-insensitive (UDS vs uds)."""
        # Create metadata with different case modules
        metadata_upper = VisitMetadata(
            ptid="NACC123456", date="2024-01-15", module="UDS", visitnum="v1"
        )
        metadata_lower = VisitMetadata(
            ptid="NACC123456", date="2024-01-15", module="uds", visitnum="v1"
        )
        metadata_mixed = VisitMetadata(
            ptid="NACC123456", date="2024-01-15", module="Uds", visitnum="v1"
        )

        # Create keys from metadata - should normalize to uppercase
        key_upper = EventMatchKey.from_visit_metadata(metadata_upper)
        key_lower = EventMatchKey.from_visit_metadata(metadata_lower)
        key_mixed = EventMatchKey.from_visit_metadata(metadata_mixed)

        # All should be equal due to normalization
        assert key_upper == key_lower
        assert key_upper == key_mixed
        assert key_lower == key_mixed

        # Hash should also be the same
        assert hash(key_upper) == hash(key_lower)
        assert hash(key_upper) == hash(key_mixed)

        # All should have uppercase module
        assert key_upper.module == "UDS"
        assert key_lower.module == "UDS"
        assert key_mixed.module == "UDS"

    def test_direct_constructor_normalizes_module(self):
        """Test that direct constructor also normalizes module to uppercase."""
        # Create keys directly with different case modules
        key_upper = EventMatchKey(ptid="NACC123456", date="2024-01-15", module="UDS")
        key_lower = EventMatchKey(ptid="NACC123456", date="2024-01-15", module="uds")
        key_mixed = EventMatchKey(ptid="NACC123456", date="2024-01-15", module="Uds")

        # All should be equal due to automatic normalization
        assert key_upper == key_lower
        assert key_upper == key_mixed
        assert key_lower == key_mixed

        # Hash should also be the same
        assert hash(key_upper) == hash(key_lower)
        assert hash(key_upper) == hash(key_mixed)

        # All should have uppercase module
        assert key_upper.module == "UDS"
        assert key_lower.module == "UDS"
        assert key_mixed.module == "UDS"


class TestUnmatchedSubmitEvents:
    """Tests for UnmatchedSubmitEvents collection."""

    def _create_test_event(self, ptid: str, visit_date: str, module: str) -> VisitEvent:
        """Helper to create a test VisitEvent."""
        return VisitEvent(
            action=ACTION_SUBMIT,
            study="adrc",
            pipeline_adcid=1,
            project_label="test-project",
            center_label="test-center",
            gear_name="test-gear",
            ptid=ptid,
            visit_date=visit_date,
            visit_number="v1",
            datatype="form",
            module=module,
            packet=None,
            timestamp=datetime.now(),
        )

    def test_add_and_find_matching_event(self):
        """Test that submit events can be added and found with matching
        keys."""
        unmatched = UnmatchedSubmitEvents()
        event = self._create_test_event("NACC123456", "2024-01-15", "UDS")

        # Add event
        unmatched.add(event)
        assert unmatched.count() == 1

        # Find with matching key
        key = EventMatchKey(ptid="NACC123456", date="2024-01-15", module="UDS")
        found_event = unmatched.find_and_remove(key)

        assert found_event is not None
        assert found_event.ptid == "NACC123456"
        assert found_event.visit_date == "2024-01-15"
        assert found_event.module == "UDS"
        assert unmatched.count() == 0

    def test_find_and_remove_removes_event(self):
        """Test that find_and_remove removes the event from collection."""
        unmatched = UnmatchedSubmitEvents()
        event = self._create_test_event("NACC123456", "2024-01-15", "UDS")

        unmatched.add(event)
        key = EventMatchKey(ptid="NACC123456", date="2024-01-15", module="UDS")

        # First call should return the event
        first_result = unmatched.find_and_remove(key)
        assert first_result is not None

        # Second call with same key should return None
        second_result = unmatched.find_and_remove(key)
        assert second_result is None

    def test_find_with_non_matching_key_returns_none(self):
        """Test that find_and_remove returns None for non-matching keys."""
        unmatched = UnmatchedSubmitEvents()
        event = self._create_test_event("NACC123456", "2024-01-15", "UDS")

        unmatched.add(event)

        # Try to find with different ptid
        key = EventMatchKey(ptid="NACC999999", date="2024-01-15", module="UDS")
        result = unmatched.find_and_remove(key)

        assert result is None
        assert unmatched.count() == 1  # Event still in collection

    def test_case_insensitive_module_matching_in_collection(self):
        """Test that module matching is case-insensitive in
        UnmatchedSubmitEvents."""
        unmatched = UnmatchedSubmitEvents()

        # Add event with lowercase module - will be normalized to uppercase
        event = self._create_test_event("NACC123456", "2024-01-15", "uds")
        unmatched.add(event)

        # Find with uppercase module
        key = EventMatchKey(ptid="NACC123456", date="2024-01-15", module="UDS")
        found_event = unmatched.find_and_remove(key)

        assert found_event is not None
        # Module is normalized to uppercase in VisitEvent
        assert found_event.module == "UDS"

    def test_multiple_events_can_be_stored(self):
        """Test that multiple events with different keys can be stored."""
        unmatched = UnmatchedSubmitEvents()

        event1 = self._create_test_event("NACC123456", "2024-01-15", "UDS")
        event2 = self._create_test_event("NACC789012", "2024-01-16", "LBD")
        event3 = self._create_test_event("NACC123456", "2024-01-15", "LBD")

        unmatched.add(event1)
        unmatched.add(event2)
        unmatched.add(event3)

        assert unmatched.count() == 3

    def test_get_remaining_returns_all_unmatched_events(self):
        """Test that get_remaining returns all unmatched events."""
        unmatched = UnmatchedSubmitEvents()

        event1 = self._create_test_event("NACC123456", "2024-01-15", "UDS")
        event2 = self._create_test_event("NACC789012", "2024-01-16", "LBD")

        unmatched.add(event1)
        unmatched.add(event2)

        remaining = unmatched.get_remaining()

        assert len(remaining) == 2
        assert event1 in remaining
        assert event2 in remaining

    def test_get_remaining_after_removal(self):
        """Test that get_remaining reflects removals."""
        unmatched = UnmatchedSubmitEvents()

        event1 = self._create_test_event("NACC123456", "2024-01-15", "UDS")
        event2 = self._create_test_event("NACC789012", "2024-01-16", "LBD")

        unmatched.add(event1)
        unmatched.add(event2)

        # Remove one event
        key = EventMatchKey(ptid="NACC123456", date="2024-01-15", module="UDS")
        unmatched.find_and_remove(key)

        remaining = unmatched.get_remaining()

        assert len(remaining) == 1
        assert event2 in remaining
        assert event1 not in remaining

    def test_count_reflects_additions_and_removals(self):
        """Test that count accurately reflects the number of events."""
        unmatched = UnmatchedSubmitEvents()

        assert unmatched.count() == 0

        event1 = self._create_test_event("NACC123456", "2024-01-15", "UDS")
        unmatched.add(event1)
        assert unmatched.count() == 1

        event2 = self._create_test_event("NACC789012", "2024-01-16", "LBD")
        unmatched.add(event2)
        assert unmatched.count() == 2

        key = EventMatchKey(ptid="NACC123456", date="2024-01-15", module="UDS")
        unmatched.find_and_remove(key)
        assert unmatched.count() == 1

        key2 = EventMatchKey(ptid="NACC789012", date="2024-01-16", module="LBD")
        unmatched.find_and_remove(key2)
        assert unmatched.count() == 0
