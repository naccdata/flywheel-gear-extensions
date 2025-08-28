import csv
from collections import defaultdict
from io import StringIO
from typing import Any, DefaultDict, Dict, List, Optional, Tuple

import pytest
from csv_app.main import CSVSplitVisitor
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from inputs.csv_reader import read_csv
from outputs.error_writer import StreamErrorWriter
from uploads.provenance import FileProvenance
from uploads.uploader import JSONUploader


def write_to_stream(data: List[List[Any]], stream: StringIO) -> None:
    """Writes data to the StringIO object for use in a test.

    Resets stream pointer to beginning.

    Args:
      data: tabular data
      stream: the output stream
    """
    writer = csv.writer(
        stream,
        delimiter=",",
        quotechar='"',
        quoting=csv.QUOTE_NONNUMERIC,
        lineterminator="\n",
    )
    writer.writerows(data)
    stream.seek(0)


def empty(stream) -> bool:
    """Checks that the stream is empty.

    Returns   True if no data is read from the stream, False otherwise
    """
    stream.seek(0)
    return not bool(stream.readline())


@pytest.fixture(scope="module")
def missing_columns_table():
    yield [["dummy1", "dummy2", "dummy3"], [1, 1, 8], [1, 2, 99]]


@pytest.fixture(scope="function")
def missing_columns_stream(missing_columns_table):
    """Create data stream missing expected column headers."""
    data = missing_columns_table
    stream = StringIO()
    write_to_stream(data, stream)
    yield stream


@pytest.fixture(scope="module")
def valid_visit_table():
    yield [
        ["module", "formver", "naccid", "visitnum", "dummy-var"],
        ["UDS", "4", "NACC000000", "1", "888"],
    ]


@pytest.fixture(scope="function")
def visit_data_stream(valid_visit_table):
    """Create mock data stream."""
    data = valid_visit_table
    stream = StringIO()
    write_to_stream(data, stream)
    yield stream


@pytest.fixture(scope="function")
def visit_data_stream_duplicates(valid_visit_table):
    """Create mock data stream with duplicates."""
    data = valid_visit_table
    for _ in range(3):
        data.append(data[-1])

    stream = StringIO()
    write_to_stream(data, stream)
    yield stream


@pytest.fixture(scope="module")
def valid_non_visit_table():
    yield [
        ["module", "formver", "naccid", "visitdate", "dummy-var"],
        ["NP", "11", "NACC0000000", "2003-10-2", "888"],
    ]


@pytest.fixture(scope="function")
def non_visit_data_stream(valid_non_visit_table):
    """Data stream for valid non-visit.

    Non-visit has date instead of visit number
    """
    data = valid_non_visit_table
    stream = StringIO()
    write_to_stream(data, stream)
    yield stream


class MockFile(FileEntry):
    def __init__(self, record: Dict[str, Any]):
        self.__record = record
        self.__info: Dict[str, Any] = {}

    def update_info(self, info: Dict[str, Any]) -> None:
        self.__info.update(info)


class MockUploader(JSONUploader):
    def __init__(self, skip_duplicates: bool = True):
        self.__records: DefaultDict[str, List[MockFile]] = defaultdict(list)
        self.__skip_duplicates = skip_duplicates

    def upload_record(
        self,
        subject_label: str,
        record: Dict[str, Any],
    ) -> Optional[MockFile]:
        if self.__skip_duplicates and record in self.__records[subject_label]:
            return None

        file = MockFile(record)
        self.__records[subject_label].append(file)
        return file

    @property
    def records(self):
        return self.__records


class MockSubject(SubjectAdaptor):
    def __init__(self, label: str):
        self.__id = label

    @property
    def id(self):
        return self.__id


class MockProject(ProjectAdaptor):
    def __init__(self):
        pass

    def add_subject(self, label: str) -> MockSubject:
        return MockSubject(label)


class TestCSVSplitVisitor:
    """Tests csv-subject transformation."""

    def __create_dummy_visitor(
        self, uploader: Optional[MockUploader] = None
    ) -> Tuple[CSVSplitVisitor, StringIO, StreamErrorWriter]:
        """Create dummy visitor and error writer for testing."""
        err_stream = StringIO()
        error_writer = StreamErrorWriter(
            stream=err_stream, container_id="dummy", fw_path="dummy/dummy"
        )

        provenance = FileProvenance(
            file_id="123456789",
            file_name="dummy_file.csv",
            flywheel_path="fw://dummy-container/dummy_file.csv",
        )

        visitor = CSVSplitVisitor(
            provenance=provenance,
            req_fields=["naccid"],
            uploader=MockUploader() if uploader is None else uploader,
            project=MockProject(),
            error_writer=error_writer,
        )

        return visitor, err_stream, error_writer

    def test_missing_column_headers(self, missing_columns_stream):
        """test missing expected column headers."""
        visitor, err_stream, error_writer = self.__create_dummy_visitor()

        no_errors = read_csv(
            input_file=missing_columns_stream,
            error_writer=error_writer,
            visitor=visitor,
        )
        assert not no_errors, "expect error for missing columns"
        assert not empty(err_stream), "expect error message in output"

    def test_valid_visit(self, visit_data_stream):
        """Test case where data corresponds to form completed at visit."""
        visitor, err_stream, error_writer = self.__create_dummy_visitor()
        no_errors = read_csv(
            input_file=visit_data_stream, error_writer=error_writer, visitor=visitor
        )
        assert no_errors, "expect no errors"
        assert empty(err_stream), "expect error stream to be empty"

    def test_valid_non_visit(self, non_visit_data_stream):
        """Test case where data does not correspond to visit."""
        visitor, err_stream, error_writer = self.__create_dummy_visitor()
        no_errors = read_csv(
            input_file=non_visit_data_stream, error_writer=error_writer, visitor=visitor
        )

        assert no_errors, "expect no errors"
        assert empty(err_stream), "expect error stream to be empty"

    def test_duplicates(self, visit_data_stream_duplicates):
        """Test uploading duplicate visits only results in 1 record."""
        uploader = MockUploader()
        visitor, err_stream, error_writer = self.__create_dummy_visitor(
            uploader=uploader
        )

        no_errors = read_csv(
            input_file=visit_data_stream_duplicates,
            error_writer=error_writer,
            visitor=visitor,
        )

        assert no_errors, "expect no errors"
        assert empty(err_stream), "expect error stream to be empty"
        assert len(uploader.records) == 1
