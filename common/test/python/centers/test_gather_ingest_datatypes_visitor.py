"""Tests for GatherIngestDatatypesVisitor."""

import pytest
from centers.center_group import (
    GatherIngestDatatypesVisitor,
    PageProjectMetadata,
)


class TestGatherIngestDatatypesVisitor:
    """Tests for GatherIngestDatatypesVisitor."""

    @pytest.fixture
    def visitor(self):
        """Create a visitor instance for testing."""
        return GatherIngestDatatypesVisitor()

    @pytest.fixture
    def page_project(self):
        """Create a PageProjectMetadata instance for testing."""
        return PageProjectMetadata(
            study_id="test-study",
            project_id="page-project-id",
            project_label="test-page-project",
            page_name="test-page",
        )

    def test_visit_page_project_is_callable(self, visitor, page_project):
        """Test that visit_page_project() is callable and doesn't raise errors.

        Validates: Requirements 4.5
        """
        # Should not raise any exceptions
        visitor.visit_page_project(page_project)

    def test_visit_page_project_does_not_affect_datatypes(self, visitor, page_project):
        """Test that visit_page_project() doesn't add datatypes to the visitor.

        Validates: Requirements 4.5
        """
        # Verify datatypes list is empty before
        assert visitor.datatypes == []

        # Call visit_page_project
        visitor.visit_page_project(page_project)

        # Verify datatypes list is still empty after
        assert visitor.datatypes == []

    def test_visit_page_project_via_apply(self, visitor, page_project):
        """Test that PageProjectMetadata.apply() correctly calls
        visit_page_project().

        Validates: Requirements 4.5
        """
        # Verify datatypes list is empty before
        assert visitor.datatypes == []

        # Use the apply method which should call visit_page_project
        page_project.apply(visitor)

        # Verify datatypes list is still empty after
        assert visitor.datatypes == []
