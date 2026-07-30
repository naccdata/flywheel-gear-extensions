"""Shared fixtures for gather_form_data tests."""

import io
from typing import Any
from unittest.mock import Mock

import pytest
from flywheel.models.subject import Subject
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gather_form_data_app.main import GatherConfig


def create_mock_proxy(
    *,
    projects: list[Any] | None = None,
    subjects_by_project: dict[str, list[Any]] | None = None,
) -> Mock:
    """Create a mock FlywheelProxy with configurable behavior.

    Args:
      projects: list of mock project objects returned by find_projects_with_pattern
      subjects_by_project: mapping of project_id -> list of Subject objects
        returned by find_subjects_by_labels
    """
    proxy = Mock(spec=FlywheelProxy)
    proxy.find_projects_with_pattern.return_value = projects or []
    proxy.get_files.return_value = []

    if subjects_by_project:

        def _find_subjects(labels, project_id, batch_size=100):
            all_subjects = subjects_by_project.get(project_id, [])
            # Filter to only return subjects whose label is in the query
            return [s for s in all_subjects if s.label in labels]

        proxy.find_subjects_by_labels.side_effect = _find_subjects
    else:
        proxy.find_subjects_by_labels.return_value = []

    return proxy


def create_mock_subject(*, label: str, subject_id: str, project_id: str) -> Mock:
    """Create a mock Subject with the given attributes."""
    subject = Mock(spec=Subject)
    subject.label = label
    subject.id = subject_id
    subject.parents = Mock()
    subject.parents.project = project_id
    return subject


def create_mock_project(*, project_id: str, label: str) -> Mock:
    """Create a mock Flywheel project."""
    project = Mock()
    project.id = project_id
    project.label = label
    return project


def make_csv_content(naccids: list[str]) -> io.StringIO:
    """Create a CSV file-like object with a naccid column."""
    lines = ["naccid", *naccids]
    return io.StringIO("\n".join(lines))


@pytest.fixture
def mock_proxy():
    """Fixture providing a basic mock FlywheelProxy."""
    return create_mock_proxy()


def create_gather_config(
    *,
    study_id: str = "adrc",
    project_names: list[str] | None = None,
    modules: set[str] | None = None,
    info_paths: list[str] | None = None,
    batch_size: int = 100,
    reload_workers: int = 10,
    formver_split: bool = False,
) -> GatherConfig:
    """Create a GatherConfig with sensible defaults for testing."""
    return GatherConfig(
        study_id=study_id,
        project_names=project_names or ["ingest-form"],
        modules=modules or {"UDS"},
        info_paths=info_paths or ["forms.json"],
        batch_size=batch_size,
        reload_workers=reload_workers,
        formver_split=formver_split,
    )
