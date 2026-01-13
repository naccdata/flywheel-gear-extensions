from s3.s3_bucket import S3BucketInterface

from event_capture.visit_events import VisitEvent


class VisitEventCapture:
    """Captures VisitEvent objects to transaction log.

    Manages transaction log as S3 bucket with flat structure:

    <transaction-log-bucket>
    ├── prod
    │   ├── log-submit-20240115-100000-42-ingest-form-alpha-110001-01.json
    │   ├── log-pass-qc-20240115-102000-42-ingest-form-alpha-110001-01.json
    │   └── log-not-pass-qc-20240116-143000-43-ingest-dicom-beta-220002-02.json
    └── dev
        └── log-submit-20240115-100000-42-ingest-form-alpha-110001-01.json

    Filename format: log-{action}-{timestamp}-{adcid}-{project}-{ptid}-{visitnum}.json
    """

    def __init__(self, s3_bucket: S3BucketInterface, environment: str = "prod") -> None:
        """Initialize the event capture.

        Args:
            s3_bucket: S3 bucket interface for writing events
            environment: Environment prefix (prod/dev), defaults to prod
        """
        self.__bucket = s3_bucket
        self.__environment = environment

    def create_event_filename(self, event: VisitEvent) -> str:
        """Create event filename with flat structure.

        Args:
            event: The visit event

        Returns:
            Filename in format:
            {env}/log-{action}-{timestamp}-{adcid}-{project}-{ptid}-{visitnum}.json
        """
        timestamp = event.timestamp.strftime("%Y%m%d-%H%M%S")

        # Sanitize project label (replace invalid chars with hyphens)
        project = event.project_label.replace("/", "-").replace("\\", "-")

        filename = (
            f"{self.__environment}/"
            f"log-{event.action}-{timestamp}-"
            f"{event.pipeline_adcid}-{project}-"
            f"{event.ptid}-{event.visit_number}.json"
        )
        return filename

    def capture_event(self, event: VisitEvent) -> None:
        """Captures the event.

        Args:
          event: the visit event
        """
        event_json = event.model_dump_json(exclude_none=True)
        filename = self.create_event_filename(event)
        self.__bucket.put_file_object(filename=filename, contents=event_json)
