"""Shared resource ID construction for the Authorization API.

Provides a single implementation of the ADR-016 resource ID format used
by both the translator (user_management gear) and the hierarchy seeder
(project_management gear).

Format:
- Center-scoped: "{center}_{label}-{study_id}"
- Non-center: "{label}-{study_id}"
- Without study: "{label}" or "{center}_{label}"

The study_id is always explicit when available.
The underscore separator is safe because center names never contain
underscores.
"""


def build_resource_id(
    label: str,
    *,
    center_id: str | None = None,
    study_id: str | None = None,
) -> str:
    """Build a resource ID using the Authorization API format (ADR-016).

    Args:
        label: The base label for the resource (e.g., "ingest-form",
            "dashboard-reports", "page-enrollment", "accepted").
        center_id: The center identifier for center-scoped resources,
            or None for non-center resources.
        study_id: The study identifier, or None if unavailable.

    Returns:
        The formatted resource ID.
    """
    # Append study_id (always explicit per ADR-016)
    if study_id:
        label = f"{label}-{study_id}"

    # Add center prefix for center-scoped resources
    if center_id is not None:
        return f"{center_id}_{label}"

    return label


# Maps resource prefix to its label prefix in the authorization API.
_PREFIX_LABELS: dict[str, str] = {
    "datatype": "ingest",
    "dashboard": "dashboard",
    "page": "page",
}


def build_label_for_resource_prefix(
    resource_prefix: str,
    resource_name: str,
) -> str:
    """Build the label portion of a resource ID from a resource prefix.

    Maps the gear's resource prefix to the authorization API label
    convention:
    - "datatype" -> "ingest-{name}"
    - "dashboard" -> "dashboard-{name}"
    - "page" -> "page-{name}"
    - other -> "{name}"

    Args:
        resource_prefix: The resource type prefix from the gear
            ("datatype", "dashboard", "page").
        resource_name: The resource name from the authorization activity.

    Returns:
        The label for the resource.
    """
    prefix_label = _PREFIX_LABELS.get(resource_prefix)
    if prefix_label:
        return f"{prefix_label}-{resource_name}"
    return resource_name
