"""Tests for GearTags."""

from nacc_common.error_models import GearTags

TAGS = GearTags("my-gear")


class TestTagChanges:
    """Tests for GearTags.tag_changes."""

    def test_neither_tag_present(self):
        assert TAGS.tag_changes(["other"], "PASS") == (["my-gear-PASS"], [])

    def test_opposite_present(self):
        assert TAGS.tag_changes(["my-gear-FAIL"], "PASS") == (
            ["my-gear-PASS"],
            ["my-gear-FAIL"],
        )

    def test_new_present(self):
        assert TAGS.tag_changes(["my-gear-PASS"], "PASS") == ([], [])

    def test_both_present(self):
        assert TAGS.tag_changes(["my-gear-PASS", "my-gear-FAIL"], "FAIL") == (
            [],
            ["my-gear-PASS"],
        )

    def test_unknown_tags_are_unconditional(self):
        assert TAGS.tag_changes(None, "PASS") == (["my-gear-PASS"], ["my-gear-FAIL"])
        assert TAGS.tag_changes(None, "FAIL") == (["my-gear-FAIL"], ["my-gear-PASS"])

    def test_input_not_mutated(self):
        tags = ["my-gear-FAIL", "x"]
        TAGS.tag_changes(tags, "PASS")
        assert tags == ["my-gear-FAIL", "x"]


class TestUpdateTags:
    """update_tags is unchanged."""

    def test_replaces_status_tags(self):
        assert TAGS.update_tags(["my-gear-FAIL", "x"], "PASS") == ["x", "my-gear-PASS"]
