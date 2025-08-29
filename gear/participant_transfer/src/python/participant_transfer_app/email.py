"""Module for sending email notifications."""

from typing import List

from notifications.email import EmailClient, create_ses_client


def send_failure_email(
    sender_email: str,
    target_emails: List[str],
    project_path: str,
    ptid: str,
    error: str,
) -> None:
    """Send a raw email notifying target emails of the gear failure.

    Args:
        sender_email: The sender email
        target_emails: The target email(s)
        project_path: Flywheel lookup path for enrollment project
        ptid: PTID of transfer request
        error: error message
    """
    client = EmailClient(client=create_ses_client(), source=sender_email)

    subject = f"ERROR: Participant Transfer gear failed for project {project_path}"
    body = (
        f"\n\nparticipant-transfer gear failed for PTID {ptid}"
        f"in enrollment project {project_path}.\n"
        f"Error message: {error}\n."
        "Please check the job log for more details.\n\n"
    )

    client.send_raw(destinations=target_emails, subject=subject, body=body)
