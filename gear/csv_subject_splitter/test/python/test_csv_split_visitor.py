import csv
from collections import defaultdict
from io import StringIO
from typing import Any, DefaultDict, Dict, List

import pytest
from csv_app.main import CSVSplitVisitor
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from inputs.csv_reader import read_csv
from outputs.errors import StreamErrorWriter
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


class MockUploader(JSONUploader):
    def __init__(self, skip_duplicates: bool = True):
        self.__records: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.__skip_duplicates = skip_duplicates

    def upload_record(
        self,
        subject_label: str,
        record: Dict[str, Any],
    ) -> None:
        if self.__skip_duplicates and record in self.__records[subject_label]:
            return

        self.__records[subject_label].append(record)

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

    def test_missing_column_headers(self, missing_columns_stream):
        """test missing expected column headers."""
        err_stream = StringIO()
        # records: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
        error_writer = StreamErrorWriter(
            stream=err_stream, container_id="dummy", fw_path="dummy/dummy"
        )
        visitor = CSVSplitVisitor(
            req_fields=["naccid"],
            uploader=MockUploader(),
            project=MockProject(),
            error_writer=error_writer,
        )

        no_errors = read_csv(
            input_file=missing_columns_stream,
            error_writer=error_writer,
            visitor=visitor,
        )
        assert not no_errors, "expect error for missing columns"
        assert not empty(err_stream), "expect error message in output"

    def test_valid_visit(self, visit_data_stream):
        """Test case where data corresponds to form completed at visit."""
        err_stream = StringIO()
        # records: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
        error_writer = StreamErrorWriter(
            stream=err_stream, container_id="dummy", fw_path="dummy/dummy"
        )
        visitor = CSVSplitVisitor(
            req_fields=["naccid"],
            uploader=MockUploader(),
            project=MockProject(),
            error_writer=error_writer,
        )
        no_errors = read_csv(
            input_file=visit_data_stream, error_writer=error_writer, visitor=visitor
        )
        assert no_errors, "expect no errors"
        assert empty(err_stream), "expect error stream to be empty"

    def test_valid_non_visit(self, non_visit_data_stream):
        """Test case where data does not correspond to visit."""
        err_stream = StringIO()
        # records: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
        error_writer = StreamErrorWriter(
            stream=err_stream, container_id="dummy", fw_path="dummy/dummy"
        )
        visitor = CSVSplitVisitor(
            req_fields=["naccid"],
            uploader=MockUploader(),
            project=MockProject(),
            error_writer=error_writer,
        )
        no_errors = read_csv(
            input_file=non_visit_data_stream, error_writer=error_writer, visitor=visitor
        )

        assert no_errors, "expect no errors"
        assert empty(err_stream), "expect error stream to be empty"

    def test_duplicates(self, visit_data_stream_duplicates):
        """Test uploading duplicate visits only results in 1 record."""
        err_stream = StringIO()
        # records: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
        error_writer = StreamErrorWriter(
            stream=err_stream, container_id="dummy", fw_path="dummy/dummy"
        )
        uploader = MockUploader()
        visitor = CSVSplitVisitor(
            req_fields=["naccid"],
            uploader=uploader,
            project=MockProject(),
            error_writer=error_writer,
        )

        no_errors = read_csv(
            input_file=visit_data_stream_duplicates,
            error_writer=error_writer,
            visitor=visitor,
        )

        assert no_errors, "expect no errors"
        assert empty(err_stream), "expect error stream to be empty"
        assert len(uploader.records) == 1
