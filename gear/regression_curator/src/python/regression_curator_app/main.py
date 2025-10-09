"""Defines Regression Curator."""

import csv
import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, List, Optional, Set, Tuple

from botocore.response import StreamingBody
from curator.regression_curator import RegressionCurator
from curator.scheduling import ProjectCurationScheduler
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError
from outputs.error_writer import ErrorWriter
from outputs.errors import unexpected_value_error
from s3.s3_client import S3BucketReader

log = logging.getLogger(__name__)


class BaselineLocalizer(ABC):
    """Abstract method to handle localizing baselines from S3."""

    def __init__(
        self,
        s3_file: str,
        error_writer: ErrorWriter,
        keep_fields: Optional[List[str]] = None,
    ) -> None:
        self.s3_file = s3_file
        self.error_writer = error_writer
        self.keep_fields = keep_fields if keep_fields else []

    def localize_s3_file(self) -> StreamingBody:
        """Localizess the S3 file and returns the StreamingBody."""
        log.info(f"Localizing file from {self.s3_file}")

        stripped_s3_file = self.s3_file.strip().replace("s3://", "")
        s3_parts = stripped_s3_file.split("/")

        if len(s3_parts) < 2:
            raise GearExecutionError(f"Invalid S3 key: {self.s3_file}")

        s3_bucket = s3_parts[0]
        key = "/".join(s3_parts[1:])

        s3_client = S3BucketReader.create_from_environment(s3_bucket)
        if not s3_client:
            raise GearExecutionError(f"Unable to access S3 bucket {s3_bucket}")

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
        header = [x.strip().lower() for x in header]
        missing = []
        for required in self.keep_fields:
            if required not in header:
                missing.append(required)

        if missing:
            raise GearExecutionError(
                f"Required field(s) not found in {self.s3_file} header: {missing}"
            )

        return header

    def localize(self) -> Dict[str, str]:
        """Localize the file and generate the baseline.

        Returns:
            Localized baseline as a dict
        """
        body = self.localize_s3_file()
        header = None
        baseline: Dict[str, Any] = {}
        duplicates: Set[str] = set()

        # the baselines are extremely large, so stream and process by line
        for line in body.iter_lines():
            raw_row = line.decode("utf-8")

            if not header:
                row = next(csv.reader([raw_row]))
                header = self.process_header(row)
                continue

            row = next(csv.DictReader([raw_row], fieldnames=header, strict=True))  # type: ignore
            key, data = self.process_row(row)  # type: ignore

            if key in baseline:
                duplicates.add(key)
                msg = f"Duplicate key found in {self.s3_file}, dropping: {key}"
                log.warning(msg)
                self.error_writer.write(
                    unexpected_value_error(
                        field="naccid", value=key, expected="unique key", message=msg
                    )
                )
                continue

            baseline[key] = data

        # remove duplicates from baseline
        for dup in duplicates:
            baseline.pop(dup)

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

    # these are derived variables that have NOT been defined yet
    # eventually should all be defined, but hardcode to ignore for now
    # mainly MP
    BLACKLIST: ClassVar = [
        "naccacsf",
        "naccapsa",
        "naccmrsa",
        "naccnapa",
        "naccnmri",
        "naccpcsf",
        "nacctcsf",
        "naccdico",
        "naccnift",
        "naccmria",
        "naccmrfi",
        "naccmnum",
        "naccmrdy",
        "naccvnum",
        "naccapta",
        "naccaptf",
        "naccapnm",
        "naccaptd",
        "naccabbp",
        "nacccore",
        "naccdadd",
        "naccfamh",
        "naccmomd",
        "naccdod",
        "naccadc",
    ]

    def process_row(self, row: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
        """Process each row from the QAF. Only retains NACC* and NGDS* derived
        variables, visitdate, and fields specified by the keep_fields
        parameter.

        Args:
            row: Row to process
        Returns:
            Tuple containing processed key and row data
        """
        # create visitdate to make unique keys
        naccid = row["naccid"]

        if 'visityr' in row:
            visitdate = (
                f"{int(row['visityr']):04d}-"
                + f"{int(row['visitmo']):02d}-"
                + f"{int(row['visitday']):02d}"
            )
        elif 'mriyr' in row:
            visitdate = (
                f"{int(row['mriyr']):04d}-"
                + f"{int(row['mrimo']):02d}-"
                + f"{int(row['mridy']):02d}"
            )

        row_data = {"visitdate": visitdate}
        row_data.update(
            {
                k: v
                for k, v in row.items()
                if (k in self.keep_fields)
                or (
                    (
                        k.startswith("nacc")
                        or k.startswith("ngds")
                        or k.startswith("ncds")
                    )
                    and k not in self.BLACKLIST
                )
            }
        )

        key = f"{naccid}_{visitdate}"
        return key, row_data


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
    context: GearToolkitContext,
    s3_qaf_file: str,
    keep_fields: List[str],
    scheduler: ProjectCurationScheduler,
    error_writer: ErrorWriter,
    s3_mqt_file: Optional[str] = None,
) -> None:
    """Runs the Attribute Curator process.

    Args:
        context: gear context
        s3_qaf_file: S3 QAF file to pull baseline from
        keep_fields: Additional fields to retain from the QAF
        scheduler: Schedules the files to be curated
        error_writer: Multi-processing error writer
        s3_mqt_file: S3 MQT file to pull baseline from (optional)
    """
    qaf_baseline = QAFBaselineLocalizer(
        s3_file=s3_qaf_file, error_writer=error_writer, keep_fields=keep_fields
    ).localize()

    mqt_baseline = None
    if s3_mqt_file:
        mqt_baseline = MQTBaselineLocalizer(
            s3_file=s3_mqt_file, error_writer=error_writer
        ).localize()

    curator = RegressionCurator(
        qaf_baseline=qaf_baseline, mqt_baseline=mqt_baseline, error_writer=error_writer
    )

    scheduler.apply(curator=curator, context=context)
