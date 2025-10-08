from s3.s3_bucket import S3BucketInterface

from event_logging.visit_events import VisitEvent


class VisitEventLogger:
    """Writes VisitEvent objects to transaction log.

    Manages transaction log as S3 bucket with this structure

    <transaction-log-bucket>
    └── adcid-0
        ├── ingest-dicom
        │   └── log
        │       └── log-submit-20251007-160112.json
        └── ingest-form
            └── log
                └── log-submit-20251003-120100.json
    """

    def __init__(self, s3_bucket: S3BucketInterface) -> None:
        self.__bucket = s3_bucket

    def log_event(self, event: VisitEvent) -> None:
        """Logs the event.

        Args:
          event: the visit event
        """
        event_json = event.model_dump_json(exclude_none=True)
        timestamp = event.timestamp.strftime("%Y%m%d-%H%M%S")
        filename = (
            f"adcid-{event.pipeline_adcid}/"
            f"{event.project_label}/"
            f"log/"
            f"log-{event.action}-{timestamp}.json"
        )
        self.__bucket.put_file_object(filename=filename, contents=event_json)
