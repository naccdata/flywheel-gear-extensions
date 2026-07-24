"""Integration tests for the Center Form Export gear.

Tests CenterFormExportVisitor.run with mocked Flywheel SDK components
(group resolution, project resolution, subject iteration).

Validates: Requirements 8.1, 8.3
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
from center_form_export_app.run import CenterFormExportVisitor
from gear_execution.gear_execution import GearExecutionError


def create_visitor(
    mock_client: MagicMock,
    group_id: str = "test-group",
    project_name: str = "test-project",
    modules: set[str] | None = None,
    info_paths: list[str] | None = None,
    study_id: str = "adrc",
    formver_split: bool = False,
    run_id: str = "",
) -> CenterFormExportVisitor:
    """Factory to create a CenterFormExportVisitor with test defaults."""
    if modules is None:
        modules = {"UDS"}
    if info_paths is None:
        info_paths = ["forms.json"]

    return CenterFormExportVisitor(
        client=mock_client,
        group_id=group_id,
        project_name=project_name,
        info_paths=info_paths,
        modules=modules,
        study_id=study_id,
        formver_split=formver_split,
        run_id=run_id,
    )


def create_mock_subject(label: str, subject_id: str) -> MagicMock:
    """Factory to create a mock Flywheel subject."""
    subject = MagicMock()
    subject.label = label
    subject.id = subject_id
    return subject


def setup_single_subject_project(mock_proxy: MagicMock) -> None:
    """Wires proxy mocks so that a project with one subject resolves."""
    mock_group = MagicMock()
    mock_project = MagicMock()
    mock_project.id = "proj-123"
    mock_project.label = "test-project"
    mock_project.project.subjects.iter.return_value = iter(
        [create_mock_subject("NACC000001", "sub-001")]
    )
    mock_proxy.find_group.return_value = mock_group
    mock_group.find_project.return_value = mock_project


def create_mock_gatherer(
    module_name: str,
    content: str | None = None,
    content_by_formver: dict[str, str] | None = None,
) -> MagicMock:
    """Factory to create a mock ModuleDataGatherer that has already
    gathered."""
    gatherer = MagicMock()
    gatherer.module_name = module_name
    if content_by_formver is not None:
        gatherer.split_by_formver = True
        gatherer.content_by_formver = content_by_formver
    else:
        gatherer.split_by_formver = False
        gatherer.content = content
    return gatherer


class TestErrorHandling:
    """Tests for graceful handling of missing groups, projects, and subjects.

    Validates: Requirements 3.4, 3.5, 3.6
    """

    def test_group_not_found(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        """When proxy.find_group returns None, raise GearExecutionError."""
        mock_proxy.find_group.return_value = None

        visitor = create_visitor(mock_client, group_id="nonexistent-group")

        with pytest.raises(
            GearExecutionError, match="Group not found: nonexistent-group"
        ):
            visitor.run(mock_context)

        mock_context.open_output.assert_not_called()

    def test_project_not_found(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        """When group is found but project is not, raise GearExecutionError."""
        mock_group = MagicMock()
        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = None

        visitor = create_visitor(
            mock_client,
            group_id="test-group",
            project_name="nonexistent-project",
        )

        with pytest.raises(
            GearExecutionError, match="Project not found: nonexistent-project"
        ):
            visitor.run(mock_context)

        mock_context.open_output.assert_not_called()

    def test_empty_project(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """When project has no subjects, log warning and return."""
        mock_group = MagicMock()
        mock_project = MagicMock()
        mock_project.project.subjects.iter.return_value = iter([])
        mock_project.label = "test-project"

        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project

        visitor = create_visitor(mock_client)

        with caplog.at_level(logging.WARNING):
            visitor.run(mock_context)

        assert "No subjects found" in caplog.text
        mock_context.open_output.assert_not_called()

    def test_project_with_no_matching_files(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """When subjects exist but a module's batched query returns no files,
        skip output for that module and log a warning."""
        mock_group = MagicMock()
        mock_project = MagicMock()
        mock_project.id = "proj-with-subjects"
        mock_project.label = "test-project"
        mock_project.project.subjects.iter.return_value = iter(
            [create_mock_subject("NACC000001", "sub-001")]
        )

        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project
        mock_proxy.get_files.return_value = []

        visitor = create_visitor(mock_client)

        with caplog.at_level(logging.WARNING):
            visitor.run(mock_context)

        assert "skipping output for module UDS" in caplog.text
        mock_context.open_output.assert_not_called()


class TestBatchSizeAndReloadWorkersConfig:
    """batch_size/reload_workers are read from gear config (with defaults of
    100/10) and passed through to main.run()."""

    def _setup_project(self, mock_proxy: MagicMock) -> None:
        mock_group = MagicMock()
        mock_project = MagicMock()
        mock_project.project.subjects.iter.return_value = iter(
            [create_mock_subject("NACC000001", "sub-001")]
        )
        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project

    def test_defaults_used_when_not_configured(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        self._setup_project(mock_proxy)
        visitor = create_visitor(mock_client)

        with patch("center_form_export_app.run.run") as mock_run:
            visitor.run(mock_context)

        assert mock_run.call_args.kwargs["batch_size"] == 100
        assert mock_run.call_args.kwargs["reload_workers"] == 10

    def test_configured_values_passed_through(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        self._setup_project(mock_proxy)
        visitor = CenterFormExportVisitor(
            client=mock_client,
            group_id="test-group",
            project_name="test-project",
            info_paths=["forms.json"],
            modules={"UDS"},
            study_id="adrc",
            batch_size=250,
            reload_workers=5,
        )

        with patch("center_form_export_app.run.run") as mock_run:
            visitor.run(mock_context)

        assert mock_run.call_args.kwargs["batch_size"] == 250
        assert mock_run.call_args.kwargs["reload_workers"] == 5


class TestCreateValidation:
    """Non-positive batch_size/reload_workers are rejected by create() as gear-
    level configuration errors, rather than surfacing later as a raw ValueError
    from ThreadPoolExecutor or an empty query loop."""

    def _create(self, **config) -> CenterFormExportVisitor:
        options = {
            "group_id": "test-group",
            "project_name": "test-project",
            "modules": "UDS",
        }
        options.update(config)
        context = MagicMock()
        context.config.opts = options

        with patch("center_form_export_app.run.GearBotClient.create"):
            return CenterFormExportVisitor.create(
                context=context, parameter_store=MagicMock()
            )

    @pytest.mark.parametrize("batch_size", [0, -1])
    def test_non_positive_batch_size_rejected(self, batch_size: int):
        with pytest.raises(GearExecutionError, match="batch_size must be a positive"):
            self._create(batch_size=batch_size)

    @pytest.mark.parametrize("reload_workers", [0, -1])
    def test_non_positive_reload_workers_rejected(self, reload_workers: int):
        with pytest.raises(
            GearExecutionError, match="reload_workers must be a positive"
        ):
            self._create(reload_workers=reload_workers)

    def test_positive_values_accepted(self):
        visitor = self._create(batch_size=50, reload_workers=4)

        assert isinstance(visitor, CenterFormExportVisitor)

    @pytest.mark.parametrize(
        "run_id",
        [
            "2026-07-24T21:04:31",  # dashes and colons
            "20260724T210431.1",  # dot
            "run_1",  # underscore
            "run 1",  # space
            "run/1",  # path separator
        ],
    )
    def test_malformed_run_id_rejected(self, run_id: str):
        """A run_id outside [A-Za-z0-9] would make filename segments ambiguous
        for consumers, so it fails the job rather than silently falling back to
        a date-only name."""
        with pytest.raises(GearExecutionError, match="run_id must contain only"):
            self._create(run_id=run_id)

    def test_over_long_run_id_rejected(self):
        with pytest.raises(GearExecutionError, match="run_id must be at most"):
            self._create(run_id="a" * 33)

    def test_well_formed_run_id_accepted(self):
        visitor = self._create(run_id="20260724T210431")

        assert isinstance(visitor, CenterFormExportVisitor)

    def test_omitted_run_id_accepted(self):
        visitor = self._create()

        assert isinstance(visitor, CenterFormExportVisitor)

    def test_whitespace_only_run_id_treated_as_omitted(self):
        visitor = self._create(run_id="   ")

        assert isinstance(visitor, CenterFormExportVisitor)


class TestRunIdStamp:
    """A caller-supplied run_id is appended to output filenames after the run
    date, so that two exports of the same modules on the same day produce
    distinct files instead of the second overwriting the first."""

    def test_run_id_appended_to_default_filename(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        setup_single_subject_project(mock_proxy)
        visitor = create_visitor(mock_client, modules={"UDS"}, run_id="20260724T210431")

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer_cls.return_value = create_mock_gatherer(
                "UDS", content="header\ndata\n"
            )
            with patch("center_form_export_app.run.date") as mock_date:
                mock_date.today.return_value.isoformat.return_value = "2026-07-24"
                visitor.run(mock_context)

        assert list(mock_context.output_files) == [
            "adrc-UDS-2026-07-24-20260724T210431.csv"
        ]

    def test_run_id_appended_to_formver_split_filenames(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        setup_single_subject_project(mock_proxy)
        visitor = create_visitor(
            mock_client,
            modules={"UDS"},
            formver_split=True,
            run_id="20260724T210431",
        )

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer_cls.return_value = create_mock_gatherer(
                "UDS",
                content_by_formver={"v3": "naccid\nA\n", "v4": "naccid\nB\n"},
            )
            with patch("center_form_export_app.run.date") as mock_date:
                mock_date.today.return_value.isoformat.return_value = "2026-07-24"
                visitor.run(mock_context)

        assert sorted(mock_context.output_files) == [
            "adrc-UDS-v3-2026-07-24-20260724T210431.csv",
            "adrc-UDS-v4-2026-07-24-20260724T210431.csv",
        ]

    def test_omitted_run_id_reproduces_date_only_filenames(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        """Ad-hoc callers that send no run_id keep the previous filenames
        exactly, with no trailing separator."""
        setup_single_subject_project(mock_proxy)
        visitor = create_visitor(mock_client, modules={"UDS"})

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer_cls.return_value = create_mock_gatherer(
                "UDS", content="header\ndata\n"
            )
            with patch("center_form_export_app.run.date") as mock_date:
                mock_date.today.return_value.isoformat.return_value = "2026-07-24"
                visitor.run(mock_context)

        assert list(mock_context.output_files) == ["adrc-UDS-2026-07-24.csv"]

    def test_every_module_shares_one_date(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        """The date is read from the clock once per run, not once per output
        file.

        Output is written as each module finishes gathering, which on a
        long export can be minutes apart -- and across midnight, two
        different dates. Consumers group a run's files by their stamp,
        so a per-file clock read would split one run into several
        apparent runs. The stubbed clock returns a later date on any
        second call: both modules must still carry the first.
        """
        setup_single_subject_project(mock_proxy)
        visitor = create_visitor(mock_client, modules={"UDS", "FTLD"})

        gatherers = {
            "UDS": create_mock_gatherer("UDS", content="header\nuds\n"),
            "FTLD": create_mock_gatherer("FTLD", content="header\nftld\n"),
        }

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer_cls.side_effect = (
                lambda proxy, module_name, info_paths, **kwargs: gatherers[module_name]
            )
            with patch("center_form_export_app.run.date") as mock_date:
                before_midnight = MagicMock()
                before_midnight.isoformat.return_value = "2026-07-24"
                after_midnight = MagicMock()
                after_midnight.isoformat.return_value = "2026-07-25"
                mock_date.today.side_effect = [before_midnight, after_midnight]

                visitor.run(mock_context)

        assert sorted(mock_context.output_files) == [
            "adrc-FTLD-2026-07-24.csv",
            "adrc-UDS-2026-07-24.csv",
        ]

    def test_every_module_shares_one_run_id(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        setup_single_subject_project(mock_proxy)
        visitor = create_visitor(
            mock_client, modules={"UDS", "FTLD"}, run_id="20260724T210431"
        )

        gatherers = {
            "UDS": create_mock_gatherer("UDS", content="header\nuds\n"),
            "FTLD": create_mock_gatherer("FTLD", content="header\nftld\n"),
        }

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer_cls.side_effect = (
                lambda proxy, module_name, info_paths, **kwargs: gatherers[module_name]
            )
            visitor.run(mock_context)

        assert len(mock_context.output_files) == 2
        assert all(
            filename.endswith("-20260724T210431.csv")
            for filename in mock_context.output_files
        )


class TestOutputTagging:
    """Output files are tagged with the gear name so consumers can recognize
    export artifacts from typed file metadata instead of a filename pattern."""

    def test_each_output_file_is_tagged(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        """Tagging goes through the explicit container_type path, since an
        output file does not exist as a container at gear runtime."""
        setup_single_subject_project(mock_proxy)
        visitor = create_visitor(mock_client, modules={"UDS"}, formver_split=True)

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer_cls.return_value = create_mock_gatherer(
                "UDS",
                content_by_formver={"v3": "naccid\nA\n", "v4": "naccid\nB\n"},
            )
            visitor.run(mock_context)

        tagged = {
            call.args[0]: call.kwargs
            for call in mock_context.metadata.update_file_metadata.call_args_list
        }
        assert set(tagged) == set(mock_context.output_files)
        for kwargs in tagged.values():
            assert kwargs["container_type"] == "project"
            assert kwargs["tags"] == ["center-form-export"]

    def test_untagged_when_no_output_is_written(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        setup_single_subject_project(mock_proxy)
        visitor = create_visitor(mock_client, modules={"UDS"})

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer_cls.return_value = create_mock_gatherer("UDS", content="")
            visitor.run(mock_context)

        mock_context.metadata.update_file_metadata.assert_not_called()

    def test_tagging_failure_does_not_discard_output(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """Tagging is advisory: it must not fail a run whose data is already
        written."""
        setup_single_subject_project(mock_proxy)
        mock_context.metadata.update_file_metadata.side_effect = ValueError(
            "container type project is outside the hierarchy"
        )
        visitor = create_visitor(mock_client, modules={"UDS"})

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer_cls.return_value = create_mock_gatherer(
                "UDS", content="header\ndata\n"
            )
            with caplog.at_level(logging.WARNING):
                visitor.run(mock_context)

        assert len(mock_context.output_files) == 1
        assert "Unable to tag output file" in caplog.text


class TestOutput:
    """Tests for CSV output file production.

    Validates: Requirements 5.1, 5.2, 5.3
    """

    def test_produces_output(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        """When a gatherer has data, output files are written."""
        mock_group = MagicMock()
        mock_project = MagicMock()
        mock_project.id = "proj-123"
        mock_project.label = "test-project"
        mock_project.project.subjects.iter.return_value = iter(
            [create_mock_subject("NACC000001", "sub-001")]
        )

        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project

        visitor = create_visitor(mock_client, modules={"UDS"}, study_id="adrc")

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer = MagicMock()
            mock_gatherer.module_name = "UDS"
            mock_gatherer.content = "header1,header2\nval1,val2\n"
            mock_gatherer.split_by_formver = False
            mock_gatherer_cls.return_value = mock_gatherer

            visitor.run(mock_context)

        mock_context.open_output.assert_called_once()
        call_args = mock_context.open_output.call_args
        filename = call_args[0][0]
        assert filename.startswith("adrc-UDS-")
        assert filename.endswith(".csv")

    def test_output_filename_format(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        """Output filename follows {study_id}-{module}-{date}.csv pattern."""
        mock_group = MagicMock()
        mock_project = MagicMock()
        mock_project.id = "proj-123"
        mock_project.label = "test-project"
        mock_project.project.subjects.iter.return_value = iter(
            [create_mock_subject("NACC000001", "sub-001")]
        )

        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project

        visitor = create_visitor(mock_client, modules={"FTLD"}, study_id="mystudy")

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer = MagicMock()
            mock_gatherer.module_name = "FTLD"
            mock_gatherer.content = "col1\ndata1\n"
            mock_gatherer.split_by_formver = False
            mock_gatherer_cls.return_value = mock_gatherer

            with patch("center_form_export_app.run.date") as mock_date:
                mock_date.today.return_value.isoformat.return_value = "2024-01-15"
                visitor.run(mock_context)

        call_args = mock_context.open_output.call_args
        filename = call_args[0][0]
        assert filename == "mystudy-FTLD-2024-01-15.csv"

    def test_skips_empty_modules(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """Only modules with content produce output; empty ones are skipped."""
        mock_group = MagicMock()
        mock_project = MagicMock()
        mock_project.id = "proj-123"
        mock_project.label = "test-project"
        mock_project.project.subjects.iter.return_value = iter(
            [create_mock_subject("NACC000001", "sub-001")]
        )

        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project

        visitor = create_visitor(mock_client, modules={"UDS", "FTLD"}, study_id="adrc")

        mock_uds_gatherer = MagicMock()
        mock_uds_gatherer.module_name = "UDS"
        mock_uds_gatherer.content = "header\ndata\n"
        mock_uds_gatherer.split_by_formver = False

        mock_ftld_gatherer = MagicMock()
        mock_ftld_gatherer.module_name = "FTLD"
        mock_ftld_gatherer.content = ""  # Empty - no data
        mock_ftld_gatherer.split_by_formver = False

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:

            def create_gatherer(proxy, module_name, info_paths, **kwargs):
                if module_name == "UDS":
                    return mock_uds_gatherer
                return mock_ftld_gatherer

            mock_gatherer_cls.side_effect = create_gatherer

            with caplog.at_level(logging.WARNING):
                visitor.run(mock_context)

        # Only UDS should produce output (FTLD has no content)
        assert mock_context.open_output.call_count == 1
        call_args = mock_context.open_output.call_args
        filename = call_args[0][0]
        assert "UDS" in filename

        # Warning should be logged for the empty module
        assert "skipping output for module FTLD" in caplog.text


class TestFormverSplit:
    """Tests for formver_split=True output behavior.

    When formver_split is enabled, the gear produces one CSV per
    (module, formver) pair instead of one CSV per module.
    """

    def _build_visitor(self, mock_client: MagicMock):
        return CenterFormExportVisitor(
            client=mock_client,
            group_id="test-group",
            project_name="test-project",
            info_paths=["forms.json"],
            modules={"UDS"},
            study_id="adrc",
            formver_split=True,
        )

    def test_produces_one_file_per_formver_bucket(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        """A gatherer with two formver buckets produces two output files."""
        mock_group = MagicMock()
        mock_project = MagicMock()
        mock_project.id = "proj-123"
        mock_project.label = "test-project"
        mock_project.project.subjects.iter.return_value = iter(
            [create_mock_subject("NACC000001", "sub-001")]
        )
        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project

        visitor = self._build_visitor(mock_client)

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer = MagicMock()
            mock_gatherer.module_name = "UDS"
            mock_gatherer.split_by_formver = True
            mock_gatherer.content_by_formver = {
                "v3": "naccid\nNACC000001\n",
                "v4": "naccid,extra\nNACC000002,x\n",
            }
            mock_gatherer_cls.return_value = mock_gatherer

            with patch("center_form_export_app.run.date") as mock_date:
                mock_date.today.return_value.isoformat.return_value = "2024-01-15"
                visitor.run(mock_context)

        assert mock_context.open_output.call_count == 2
        filenames = sorted(mock_context.output_files.keys())
        assert filenames == [
            "adrc-UDS-v3-2024-01-15.csv",
            "adrc-UDS-v4-2024-01-15.csv",
        ]
        # Each output file contains its bucket's content
        assert mock_context.output_files["adrc-UDS-v3-2024-01-15.csv"] == (
            "naccid\nNACC000001\n"
        )
        assert mock_context.output_files["adrc-UDS-v4-2024-01-15.csv"] == (
            "naccid,extra\nNACC000002,x\n"
        )

    def test_empty_buckets_are_skipped(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
    ):
        """Buckets with empty content do not produce files."""
        mock_group = MagicMock()
        mock_project = MagicMock()
        mock_project.id = "proj-123"
        mock_project.label = "test-project"
        mock_project.project.subjects.iter.return_value = iter(
            [create_mock_subject("NACC000001", "sub-001")]
        )
        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project

        visitor = self._build_visitor(mock_client)

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer = MagicMock()
            mock_gatherer.module_name = "UDS"
            mock_gatherer.split_by_formver = True
            mock_gatherer.content_by_formver = {
                "v3": "naccid\nNACC000001\n",
                "v4": "",  # empty
            }
            mock_gatherer_cls.return_value = mock_gatherer

            visitor.run(mock_context)

        assert mock_context.open_output.call_count == 1
        filename = next(iter(mock_context.output_files.keys()))
        assert "v3" in filename and "v4" not in filename

    def test_gatherer_with_no_buckets_logs_warning(
        self,
        mock_client: MagicMock,
        mock_proxy: MagicMock,
        mock_context: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """A gatherer that gathered no rows produces no files and logs."""
        mock_group = MagicMock()
        mock_project = MagicMock()
        mock_project.id = "proj-123"
        mock_project.label = "test-project"
        mock_project.project.subjects.iter.return_value = iter(
            [create_mock_subject("NACC000001", "sub-001")]
        )
        mock_proxy.find_group.return_value = mock_group
        mock_group.find_project.return_value = mock_project

        visitor = self._build_visitor(mock_client)

        with patch(
            "center_form_export_app.run.ModuleDataGatherer"
        ) as mock_gatherer_cls:
            mock_gatherer = MagicMock()
            mock_gatherer.module_name = "UDS"
            mock_gatherer.split_by_formver = True
            mock_gatherer.content_by_formver = {}
            mock_gatherer_cls.return_value = mock_gatherer

            with caplog.at_level(logging.WARNING):
                visitor.run(mock_context)

        mock_context.open_output.assert_not_called()
        assert "skipping output for module UDS" in caplog.text
