"""Tests for REDCapDisableVisitor."""

import pytest
from centers.center_group import (
    CenterMetadata,
    CenterStudyMetadata,
    DistributionProjectMetadata,
    FormIngestProjectMetadata,
    IngestProjectMetadata,
    REDCapFormProjectMetadata,
)
from users.redcap_disable_visitor import REDCapDisableVisitor


class TestREDCapDisableVisitor:
    """Tests for REDCapDisableVisitor.

    Validates: Requirements 3.1, 3.2
    """

    @pytest.fixture
    def visitor(self) -> REDCapDisableVisitor:
        """Create a fresh visitor instance."""
        return REDCapDisableVisitor()

    def test_collects_pids_from_form_ingest_project(
        self, visitor: REDCapDisableVisitor
    ) -> None:
        """Test visitor collects PIDs from FormIngestProjectMetadata with
        redcap_projects.

        Validates: Requirements 3.1
        """
        redcap_project = REDCapFormProjectMetadata(
            redcap_pid=100,
            label="module-a",
        )
        form_ingest = FormIngestProjectMetadata(
            study_id="study-1",
            project_id="proj-1",
            project_label="form-ingest-1",
            pipeline_adcid=1,
            datatype="form",
            redcap_projects={"module-a": redcap_project},
        )
        study = CenterStudyMetadata(
            study_id="study-1",
            study_name="Study One",
            ingest_projects={"form-ingest-1": form_ingest},
        )
        center = CenterMetadata(
            adcid=1,
            active=True,
            studies={"study-1": study},
        )

        center.apply(visitor)

        assert visitor.redcap_pids == [100]

    def test_returns_empty_list_when_no_form_ingest_projects(
        self, visitor: REDCapDisableVisitor
    ) -> None:
        """Test visitor returns empty list when no form ingest projects exist.

        Validates: Requirements 3.2
        """
        center = CenterMetadata(
            adcid=2,
            active=True,
            studies={},
        )

        center.apply(visitor)

        assert visitor.redcap_pids == []

    def test_skips_plain_ingest_projects(self, visitor: REDCapDisableVisitor) -> None:
        """Test visitor skips non-form ingest projects (IngestProjectMetadata).

        Validates: Requirements 3.2
        """
        ingest = IngestProjectMetadata(
            study_id="study-1",
            project_id="proj-ingest",
            project_label="ingest-project",
            pipeline_adcid=1,
            datatype="dicom",
        )
        study = CenterStudyMetadata(
            study_id="study-1",
            study_name="Study One",
            ingest_projects={"ingest-project": ingest},
        )
        center = CenterMetadata(
            adcid=3,
            active=True,
            studies={"study-1": study},
        )

        center.apply(visitor)

        assert visitor.redcap_pids == []

    def test_skips_distribution_projects(self, visitor: REDCapDisableVisitor) -> None:
        """Test visitor skips DistributionProjectMetadata.

        Validates: Requirements 3.2
        """
        dist = DistributionProjectMetadata(
            study_id="study-1",
            project_id="proj-dist",
            project_label="dist-project",
            datatype="form",
        )
        study = CenterStudyMetadata(
            study_id="study-1",
            study_name="Study One",
            distribution_projects={"dist-project": dist},
        )
        center = CenterMetadata(
            adcid=4,
            active=True,
            studies={"study-1": study},
        )

        center.apply(visitor)

        assert visitor.redcap_pids == []

    def test_collects_pids_across_multiple_studies_and_projects(
        self, visitor: REDCapDisableVisitor
    ) -> None:
        """Test visitor collects PIDs across multiple studies and multiple form
        ingest projects.

        Validates: Requirements 3.1, 3.2
        """
        # Study 1 with two form ingest projects, each with REDCap projects
        redcap_a = REDCapFormProjectMetadata(redcap_pid=10, label="mod-a")
        redcap_b = REDCapFormProjectMetadata(redcap_pid=20, label="mod-b")
        form_ingest_1 = FormIngestProjectMetadata(
            study_id="study-1",
            project_id="proj-1",
            project_label="form-ingest-1",
            pipeline_adcid=1,
            datatype="form",
            redcap_projects={"mod-a": redcap_a},
        )
        form_ingest_2 = FormIngestProjectMetadata(
            study_id="study-1",
            project_id="proj-2",
            project_label="form-ingest-2",
            pipeline_adcid=1,
            datatype="form",
            redcap_projects={"mod-b": redcap_b},
        )
        study_1 = CenterStudyMetadata(
            study_id="study-1",
            study_name="Study One",
            ingest_projects={
                "form-ingest-1": form_ingest_1,
                "form-ingest-2": form_ingest_2,
            },
        )

        # Study 2 with one form ingest project with multiple REDCap projects
        redcap_c = REDCapFormProjectMetadata(redcap_pid=30, label="mod-c")
        redcap_d = REDCapFormProjectMetadata(redcap_pid=40, label="mod-d")
        form_ingest_3 = FormIngestProjectMetadata(
            study_id="study-2",
            project_id="proj-3",
            project_label="form-ingest-3",
            pipeline_adcid=2,
            datatype="form",
            redcap_projects={"mod-c": redcap_c, "mod-d": redcap_d},
        )
        study_2 = CenterStudyMetadata(
            study_id="study-2",
            study_name="Study Two",
            ingest_projects={"form-ingest-3": form_ingest_3},
        )

        center = CenterMetadata(
            adcid=5,
            active=True,
            studies={"study-1": study_1, "study-2": study_2},
        )

        center.apply(visitor)

        assert sorted(visitor.redcap_pids) == [10, 20, 30, 40]

    def test_mixed_ingest_types_only_collects_form_ingest_pids(
        self, visitor: REDCapDisableVisitor
    ) -> None:
        """Test visitor collects PIDs only from FormIngestProjectMetadata when
        mixed with plain IngestProjectMetadata in the same study.

        Validates: Requirements 3.1, 3.2
        """
        redcap_proj = REDCapFormProjectMetadata(redcap_pid=55, label="mod-x")
        form_ingest = FormIngestProjectMetadata(
            study_id="study-1",
            project_id="proj-form",
            project_label="form-ingest",
            pipeline_adcid=1,
            datatype="form",
            redcap_projects={"mod-x": redcap_proj},
        )
        plain_ingest = IngestProjectMetadata(
            study_id="study-1",
            project_id="proj-plain",
            project_label="plain-ingest",
            pipeline_adcid=1,
            datatype="dicom",
        )
        study = CenterStudyMetadata(
            study_id="study-1",
            study_name="Study One",
            ingest_projects={
                "form-ingest": form_ingest,
                "plain-ingest": plain_ingest,
            },
        )
        center = CenterMetadata(
            adcid=6,
            active=True,
            studies={"study-1": study},
        )

        center.apply(visitor)

        assert visitor.redcap_pids == [55]
