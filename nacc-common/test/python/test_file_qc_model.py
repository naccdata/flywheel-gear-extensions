"""Tests for FileQCModel and related QC models."""

from nacc_common.error_models import (
    FileQCModel,
    GearQCModel,
    ValidationModel,
)


class TestFileQCModel:
    """Tests for FileQCModel.get_file_status() method."""

    def test_get_file_status_all_pass(self):
        """Test that get_file_status returns PASS when all gears have PASS
        status."""
        file_qc = FileQCModel(
            qc={
                "gear1": GearQCModel(
                    validation=ValidationModel(data=[], state="PASS", cleared=[])
                ),
                "gear2": GearQCModel(
                    validation=ValidationModel(data=[], state="PASS", cleared=[])
                ),
                "gear3": GearQCModel(
                    validation=ValidationModel(data=[], state="PASS", cleared=[])
                ),
            }
        )

        assert file_qc.get_file_status() == "PASS"

    def test_get_file_status_any_fail(self):
        """Test that get_file_status returns FAIL when any gear has FAIL
        status."""
        file_qc = FileQCModel(
            qc={
                "gear1": GearQCModel(
                    validation=ValidationModel(data=[], state="PASS", cleared=[])
                ),
                "gear2": GearQCModel(
                    validation=ValidationModel(data=[], state="FAIL", cleared=[])
                ),
                "gear3": GearQCModel(
                    validation=ValidationModel(data=[], state="PASS", cleared=[])
                ),
            }
        )

        assert file_qc.get_file_status() == "FAIL"

    def test_get_file_status_fail_takes_precedence(self):
        """Test that FAIL takes precedence over IN REVIEW."""
        file_qc = FileQCModel(
            qc={
                "gear1": GearQCModel(
                    validation=ValidationModel(data=[], state="IN REVIEW", cleared=[])
                ),
                "gear2": GearQCModel(
                    validation=ValidationModel(data=[], state="FAIL", cleared=[])
                ),
                "gear3": GearQCModel(
                    validation=ValidationModel(data=[], state="PASS", cleared=[])
                ),
            }
        )

        assert file_qc.get_file_status() == "FAIL"

    def test_get_file_status_in_review_with_pass(self):
        """Test get_file_status returns IN REVIEW when at least one gear is IN
        REVIEW and none are FAIL."""
        file_qc = FileQCModel(
            qc={
                "gear1": GearQCModel(
                    validation=ValidationModel(data=[], state="PASS", cleared=[])
                ),
                "gear2": GearQCModel(
                    validation=ValidationModel(data=[], state="IN REVIEW", cleared=[])
                ),
                "gear3": GearQCModel(
                    validation=ValidationModel(data=[], state="PASS", cleared=[])
                ),
            }
        )

        assert file_qc.get_file_status() == "IN REVIEW"

    def test_get_file_status_all_in_review(self):
        """Test that get_file_status returns IN REVIEW when all gears are IN
        REVIEW."""
        file_qc = FileQCModel(
            qc={
                "gear1": GearQCModel(
                    validation=ValidationModel(data=[], state="IN REVIEW", cleared=[])
                ),
                "gear2": GearQCModel(
                    validation=ValidationModel(data=[], state="IN REVIEW", cleared=[])
                ),
            }
        )

        assert file_qc.get_file_status() == "IN REVIEW"

    def test_get_file_status_empty_qc(self):
        """Test that get_file_status returns PASS when there are no gears."""
        file_qc = FileQCModel(qc={})

        assert file_qc.get_file_status() == "PASS"

    def test_get_file_status_with_none_status(self):
        """Test that get_file_status treats None status as PASS."""
        file_qc = FileQCModel(
            qc={
                "gear1": GearQCModel(
                    validation=ValidationModel(data=[], state=None, cleared=[])
                ),
                "gear2": GearQCModel(
                    validation=ValidationModel(data=[], state="PASS", cleared=[])
                ),
            }
        )

        assert file_qc.get_file_status() == "PASS"

    def test_get_file_status_single_gear_pass(self):
        """Test that get_file_status returns PASS for a single gear with PASS
        status."""
        file_qc = FileQCModel(
            qc={
                "gear1": GearQCModel(
                    validation=ValidationModel(data=[], state="PASS", cleared=[])
                ),
            }
        )

        assert file_qc.get_file_status() == "PASS"

    def test_get_file_status_single_gear_fail(self):
        """Test that get_file_status returns FAIL for a single gear with FAIL
        status."""
        file_qc = FileQCModel(
            qc={
                "gear1": GearQCModel(
                    validation=ValidationModel(data=[], state="FAIL", cleared=[])
                ),
            }
        )

        assert file_qc.get_file_status() == "FAIL"

    def test_get_file_status_single_gear_in_review(self):
        """Test get_file_status returns IN REVIEW for a single gear with IN
        REVIEW status."""
        file_qc = FileQCModel(
            qc={
                "gear1": GearQCModel(
                    validation=ValidationModel(data=[], state="IN REVIEW", cleared=[])
                ),
            }
        )

        assert file_qc.get_file_status() == "IN REVIEW"
