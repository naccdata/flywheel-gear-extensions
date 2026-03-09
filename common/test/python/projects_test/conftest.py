"""Test fixtures and builders for projects tests.

This module provides pytest fixtures and builder classes for creating
test data for StudyModel, PageProjectMetadata, and Flywheel components.
"""

from typing import Callable, List, Optional
from unittest.mock import Mock

import pytest
from centers.center_group import PageProjectMetadata
from projects.study import StudyCenterModel, StudyModel

# Builder Classes


class StudyModelBuilder:
    """Builder for creating test StudyModel instances with fluent interface.

    Provides sensible defaults and allows customization through method chaining.

    Example:
        study = (
            StudyModelBuilder()
            .with_pages(["enrollment"])
            .with_study_type("primary")
            .build()
        )
    """

    def __init__(self):
        """Initialize builder with sensible defaults."""
        self._name = "Test Study"
        self._study_id = "test-study"
        self._centers = [StudyCenterModel(center_id="center-01")]
        self._datatypes = ["clinical"]
        self._dashboards = None
        self._pages = None
        self._mode = "aggregation"
        self._study_type = "primary"
        self._legacy = True
        self._published = False

    def with_name(self, name: str) -> "StudyModelBuilder":
        """Set the study name.

        Args:
            name: The study name

        Returns:
            Self for method chaining
        """
        self._name = name
        return self

    def with_study_id(self, study_id: str) -> "StudyModelBuilder":
        """Set the study ID.

        Args:
            study_id: The study identifier

        Returns:
            Self for method chaining
        """
        self._study_id = study_id
        return self

    def with_centers(self, centers: List[str]) -> "StudyModelBuilder":
        """Set the centers list.

        Args:
            centers: List of center IDs

        Returns:
            Self for method chaining
        """
        self._centers = [StudyCenterModel(center_id=c) for c in centers]
        return self

    def with_datatypes(self, datatypes: List[str]) -> "StudyModelBuilder":
        """Set the datatypes list.

        Args:
            datatypes: List of datatype names

        Returns:
            Self for method chaining
        """
        self._datatypes = datatypes
        return self

    def with_dashboards(self, dashboards: Optional[List[str]]) -> "StudyModelBuilder":
        """Set the dashboards list.

        Args:
            dashboards: List of dashboard names or None

        Returns:
            Self for method chaining
        """
        self._dashboards = dashboards
        return self

    def with_pages(self, pages: Optional[List[str]]) -> "StudyModelBuilder":
        """Set the pages list.

        Args:
            pages: List of page names or None

        Returns:
            Self for method chaining
        """
        self._pages = pages
        return self

    def with_mode(self, mode: str) -> "StudyModelBuilder":
        """Set the study mode.

        Args:
            mode: Study mode ("aggregation" or "distribution")

        Returns:
            Self for method chaining
        """
        self._mode = mode
        return self

    def with_study_type(self, study_type: str) -> "StudyModelBuilder":
        """Set the study type.

        Args:
            study_type: Study type ("primary" or "affiliated")

        Returns:
            Self for method chaining
        """
        self._study_type = study_type
        return self

    def with_legacy(self, legacy: bool) -> "StudyModelBuilder":
        """Set the legacy flag.

        Args:
            legacy: Whether this is a legacy study

        Returns:
            Self for method chaining
        """
        self._legacy = legacy
        return self

    def with_published(self, published: bool) -> "StudyModelBuilder":
        """Set the published flag.

        Args:
            published: Whether this study is published

        Returns:
            Self for method chaining
        """
        self._published = published
        return self

    def build(self) -> StudyModel:
        """Build the StudyModel instance.

        Returns:
            A StudyModel instance with configured values
        """
        return StudyModel(
            name=self._name,  # pyright: ignore[reportCallIssue]
            study_id=self._study_id,
            centers=self._centers,
            datatypes=self._datatypes,
            dashboards=self._dashboards,
            pages=self._pages,
            mode=self._mode,
            study_type=self._study_type,
            legacy=self._legacy,
            published=self._published,
        )


class PageProjectMetadataBuilder:
    """Builder for creating test PageProjectMetadata instances with fluent
    interface.

    Provides sensible defaults and allows customization through method chaining.

    Example:
        metadata = (
            PageProjectMetadataBuilder()
            .with_page_name("enrollment")
            .with_study_id("nacc-uds")
            .build()
        )
    """

    def __init__(self):
        """Initialize builder with sensible defaults."""
        self._study_id = "test-study"
        self._project_id = "test-project-id"
        self._project_label = "page-test"
        self._page_name = "test-page"

    def with_study_id(self, study_id: str) -> "PageProjectMetadataBuilder":
        """Set the study ID.

        Args:
            study_id: The study identifier

        Returns:
            Self for method chaining
        """
        self._study_id = study_id
        return self

    def with_project_id(self, project_id: str) -> "PageProjectMetadataBuilder":
        """Set the project ID.

        Args:
            project_id: The Flywheel project ID

        Returns:
            Self for method chaining
        """
        self._project_id = project_id
        return self

    def with_project_label(self, project_label: str) -> "PageProjectMetadataBuilder":
        """Set the project label.

        Args:
            project_label: The project label

        Returns:
            Self for method chaining
        """
        self._project_label = project_label
        return self

    def with_page_name(self, page_name: str) -> "PageProjectMetadataBuilder":
        """Set the page name.

        Args:
            page_name: The page name

        Returns:
            Self for method chaining
        """
        self._page_name = page_name
        return self

    def build(self) -> PageProjectMetadata:
        """Build the PageProjectMetadata instance.

        Returns:
            A PageProjectMetadata instance with configured values
        """
        return PageProjectMetadata(
            study_id=self._study_id,
            project_id=self._project_id,
            project_label=self._project_label,
            page_name=self._page_name,
        )


# Mock Factory Functions


def create_mock_project(
    project_id: str = "test-project-id", label: str = "test-label", **kwargs
) -> Mock:
    """Factory for creating mock Flywheel projects with defaults.

    Args:
        project_id: The project ID (default: "test-project-id")
        label: The project label (default: "test-label")
        **kwargs: Additional attributes to set on the mock

    Returns:
        A Mock object configured as a Flywheel project

    Example:
        project = create_mock_project(project_id="123", label="page-enrollment")
    """
    project = Mock()
    project.id = project_id
    project.label = label
    for key, value in kwargs.items():
        setattr(project, key, value)
    return project


def create_mock_center(
    center_id: str = "center-01", is_active: bool = True, **kwargs
) -> Mock:
    """Factory for creating mock CenterGroup instances with defaults.

    Args:
        center_id: The center ID (default: "center-01")
        is_active: Whether the center is active (default: True)
        **kwargs: Additional attributes to set on the mock

    Returns:
        A Mock object configured as a CenterGroup

    Example:
        center = create_mock_center(center_id="center-02", is_active=False)
    """
    center = Mock()
    center.id = center_id
    center.is_active.return_value = is_active

    # Default add_project behavior returns a mock project
    def default_add_project(label):
        return create_mock_project(project_id=f"project-{label}", label=label)

    center.add_project.side_effect = default_add_project

    for key, value in kwargs.items():
        setattr(center, key, value)
    return center


def create_mock_flywheel_proxy(**kwargs) -> Mock:
    """Factory for creating mock FlywheelProxy instances with defaults.

    Args:
        **kwargs: Additional attributes to set on the mock

    Returns:
        A Mock object configured as a FlywheelProxy

    Example:
        proxy = create_mock_flywheel_proxy()
    """
    proxy = Mock()
    for key, value in kwargs.items():
        setattr(proxy, key, value)
    return proxy


# Pytest Fixtures


@pytest.fixture
def build_study_model() -> Callable[[], StudyModelBuilder]:
    """Fixture that returns a StudyModelBuilder factory.

    Returns:
        A factory function that creates StudyModelBuilder instances

    Example:
        def test_something(build_study_model):
            study = build_study_model().with_pages(["enrollment"]).build()
    """

    def _build() -> StudyModelBuilder:
        return StudyModelBuilder()

    return _build


@pytest.fixture
def build_page_project_metadata() -> Callable[[], PageProjectMetadataBuilder]:
    """Fixture that returns a PageProjectMetadataBuilder factory.

    Returns:
        A factory function that creates PageProjectMetadataBuilder instances

    Example:
        def test_something(build_page_project_metadata):
            metadata = (
                build_page_project_metadata()
                .with_page_name("enrollment")
                .build()
            )
    """

    def _build() -> PageProjectMetadataBuilder:
        return PageProjectMetadataBuilder()

    return _build


@pytest.fixture
def mock_flywheel_proxy() -> Mock:
    """Fixture that returns a mock FlywheelProxy with sensible defaults.

    Returns:
        A Mock object configured as a FlywheelProxy

    Example:
        def test_something(mock_flywheel_proxy):
            mapper = AggregationMapper(study=study, proxy=mock_flywheel_proxy, ...)
    """
    return create_mock_flywheel_proxy()


@pytest.fixture
def mock_center() -> Mock:
    """Fixture that returns a mock CenterGroup with sensible defaults.

    Returns:
        A Mock object configured as an active CenterGroup

    Example:
        def test_something(mock_center):
            mapper.map_center_pipelines(center=mock_center, ...)
    """
    return create_mock_center()


@pytest.fixture
def mock_project() -> Mock:
    """Fixture that returns a mock Flywheel project with sensible defaults.

    Returns:
        A Mock object configured as a Flywheel project

    Example:
        def test_something(mock_project):
            assert mock_project.id == "test-project-id"
    """
    return create_mock_project()
