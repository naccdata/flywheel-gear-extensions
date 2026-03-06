"""Tests for projects.study_mapping module."""

from unittest.mock import Mock

from projects.study import StudyModel
from projects.study_mapping import AggregationMapper, DistributionMapper


class TestStudyMapperPageLabel:
    """Tests for StudyMapper.page_label() method."""

    def test_page_label_primary_study(self):
        """Test page_label() for primary study returns 'page-{page_name}'."""
        study = StudyModel(
            name="Primary Study",  # pyright: ignore[reportCallIssue]
            study_id="primary-study",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment", "data-entry"],
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        assert mapper.page_label("enrollment") == "page-enrollment"
        assert mapper.page_label("data-entry") == "page-data-entry"
        assert mapper.page_label("qc-status") == "page-qc-status"

    def test_page_label_affiliated_study(self):
        """Test page_label() for affiliated study returns 'page-{page_name}-

        {study_id}'.
        """
        study = StudyModel(
            name="Affiliated Study",  # pyright: ignore[reportCallIssue]
            study_id="nacc-ftld",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment", "data-entry"],
            mode="aggregation",
            study_type="affiliated",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        assert mapper.page_label("enrollment") == "page-enrollment-nacc-ftld"
        assert mapper.page_label("data-entry") == "page-data-entry-nacc-ftld"
        assert mapper.page_label("qc-status") == "page-qc-status-nacc-ftld"

    def test_page_label_distribution_mapper(self):
        """Test page_label() works with DistributionMapper."""
        study = StudyModel(
            name="Distribution Study",  # pyright: ignore[reportCallIssue]
            study_id="dist-study",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment"],
            mode="distribution",
            study_type="affiliated",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = DistributionMapper(study=study, proxy=mock_proxy)

        assert mapper.page_label("enrollment") == "page-enrollment-dist-study"
