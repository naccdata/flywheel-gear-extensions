"""CSV export functionality for user error events."""

from io import StringIO

from outputs.outputs import CSVWriter

from users.event_models import UserEventCollector


def export_errors_to_csv(collector: UserEventCollector) -> str:
    """Export errors from UserEventCollector to CSV format.

    Args:
        collector: The UserEventCollector containing errors

    Returns:
        CSV-formatted string with all error information

    Raises:
        ValueError: If collector is empty or has no errors
    """
    if not collector.has_errors():
        raise ValueError("Collector has no errors to export")

    errors = collector.get_errors()

    # Get field names from UserProcessEvent class
    from users.event_models import UserProcessEvent

    fieldnames = UserProcessEvent.csv_fieldnames()

    # Create CSV in memory using CSVWriter
    output = StringIO()
    writer = CSVWriter(stream=output, fieldnames=fieldnames, extrasaction="ignore")

    # Write error rows using the model's serializer
    for error in errors:
        row = error.model_dump()
        writer.write(row)

    return output.getvalue()
