"""Defines Regression Curator."""

import csv
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Tuple

from botocore.response import StreamingBody
from curator.scheduling import ProjectCurationScheduler
from fw_gear import GearContext
from gear_execution.gear_execution import GearExecutionError
from outputs.error_writer import ManagerListErrorWriter
from outputs.errors import unexpected_value_error
from s3.s3_bucket import S3BucketInterface

from .regression_curator import RegressionCurator

log = logging.getLogger(__name__)


class BaselineLocalizer(ABC):
    """Abstract method to handle localizing baselines from S3."""

    def __init__(
        self,
        s3_file: str,
        error_writer: ManagerListErrorWriter,
        subjects: List[str],
    ) -> None:
        self.s3_file = s3_file
        self.error_writer = error_writer
        self.subjects = subjects

    def localize_s3_file(self) -> StreamingBody:
        """Localizess the S3 file and returns the StreamingBody."""
        log.info(f"Localizing file from {self.s3_file}")

        s3_bucket, key = S3BucketInterface.parse_bucket_and_key(self.s3_file)
        s3_client = S3BucketInterface.create_from_environment(s3_bucket)
        if not s3_client or not key:
            raise GearExecutionError(f"Unable to access S3 file {self.s3_file}")

        # return body
        return s3_client.get_file_object(key)["Body"]

    def process_header(self, header: List[str]) -> List[str]:
        """Process the header line. Assumes no case-sensitivity and converts
        all to lowercase.

        Args:
            header: Header line to process
        Returns:
            Processed header
        """
        return [x.strip().lower() for x in header]

    def localize(self) -> Dict[str, str]:
        """Localize the file and generate the baseline.

        Returns:
            Localized baseline as a dict
        """
        body = self.localize_s3_file()
        header = None
        baseline: Dict[str, Any] = {}

        # the baselines are extremely large, so stream and process by line
        for line in body.iter_lines():
            raw_row = line.decode("utf-8")

            if not header:
                row = next(csv.reader([raw_row]))
                header = self.process_header(row)
                continue

            row = next(csv.DictReader([raw_row], fieldnames=header, strict=True))  # type: ignore

            # we always assume NACCID is in the row. skip NACCIDs irrelevant
            # to this regression test
            if row.get("naccid", None) not in self.subjects:  # type: ignore
                continue

            key, data = self.process_row(row)  # type: ignore

            if key in baseline:
                msg = f"Duplicate key found in {self.s3_file}, dropping: {key}"
                log.warning(msg)
                self.error_writer.write(
                    unexpected_value_error(
                        field="naccid", value=key, expected="unique key", message=msg
                    )
                )
                baseline.pop(key)
                continue

            baseline[key] = data

            # this is kind of a hack to handle cross-sectional data like NP and
            # genetics; just key on the most recent visit, which should also have
            # the most recent cross-sectional information
            baseline[row["naccid"]] = data  # type: ignore

        if not baseline:
            raise GearExecutionError(f"No usable records found in {self.s3_file}")

        log.info(f"Loaded {len(baseline)} records from QAF baseline")
        return baseline

    @abstractmethod
    def process_row(self, row: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
        """Process the given row.

        Args:
            row: Row to process
        Returns:
            Tuple containing processed key and row data
        """
        pass


class QAFBaselineLocalizer(BaselineLocalizer):
    """Class to handle localizing the QAF."""

    def __init__(
        self,
        s3_file: str,
        error_writer: ManagerListErrorWriter,
        subjects: List[str],
        variable_blacklist: Optional[Set[str]] = None,
    ) -> None:
        super().__init__(s3_file, error_writer, subjects)
        self.__variable_blacklist = (
            variable_blacklist if variable_blacklist is not None else []
        )

    def process_row(self, row: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
        """Process each row from the QAF.

        Args:
            row: Row to process
        Returns:
            Tuple containing processed key and row data
        """
        # create visitdate to make unique keys
        if "visityr" in row:
            visitdate = (
                f"{int(row['visityr']):04d}-"
                + f"{int(row['visitmo']):02d}-"
                + f"{int(row['visitday']):02d}"
            )
        elif "mriyr" in row:
            visitdate = (
                f"{int(row['mriyr']):04d}-"
                + f"{int(row['mrimo']):02d}-"
                + f"{int(row['mridy']):02d}"
            )

        record = {k: v for k, v in row.items() if k not in self.__variable_blacklist}
        record["visitdate"] = visitdate
        key = f"{row['naccid']}_{visitdate}"

        return key, record


class MQTBaselineLocalizer(BaselineLocalizer):
    """Class to handle localizing the MQT."""

    def process_row(self, row: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
        """Process each row from the MQT baseline.

        Args:
            row: Row to process
        Returns:
            Tuple containing processed key and row data
        """
        # need to convert string booleans to string 0/1s
        for k, v in row.items():
            if v.lower() == "true":
                row[k] = "1"
            elif v.lower() == "false":
                row[k] = "0"

        return row["naccid"], row


def run(
    context: GearContext,
    subjects: List[str],
    s3_qaf_file: str,
    scheduler: ProjectCurationScheduler,
    error_writer: ManagerListErrorWriter,
    s3_mqt_file: Optional[str] = None,
    variable_blacklist: Optional[Set[str]] = None,
) -> None:
    """Runs the Attribute Curator process.

    Args:
        context: gear context
        subjects: List of subjects to run regression test over
        s3_qaf_file: S3 QAF file to pull baseline from
        scheduler: Schedules the files to be curated
        error_writer: Multi-processing error writer
        s3_mqt_file: S3 MQT file to pull baseline from (optional)
        variable_blacklist: Set of variables to blacklist/ignore from QAF
    """
    qaf_baseline = QAFBaselineLocalizer(
        s3_file=s3_qaf_file,
        error_writer=error_writer,
        subjects=subjects,
        variable_blacklist=variable_blacklist,
    ).localize()

    mqt_baseline = None
    if s3_mqt_file:
        mqt_baseline = MQTBaselineLocalizer(
            s3_file=s3_mqt_file,
            error_writer=error_writer,
            subjects=subjects,
        ).localize()

    curator = RegressionCurator(
        qaf_baseline=qaf_baseline,
        error_writer=error_writer,
        mqt_baseline=mqt_baseline,
    )

    scheduler.apply(curator=curator, context=context)
