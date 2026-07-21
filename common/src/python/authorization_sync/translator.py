"""Activity-to-relation mapping for the Authorization API.

Maps the gear's internal Activity (action + Resource) to the
Authorization API's grant vocabulary (resource_type, relation,
resource_id) and produces a set of DesiredGrant objects for a user's
authorizations.
"""

import logging

from authorization.models import AuthorizationModelMetadata
from users.authorizations import Authorizations

from authorization_sync.models import DesiredGrant

log = logging.getLogger(__name__)

# Maps (action, resource_prefix) to list of (api_resource_type, relation) pairs.
# Only combinations listed here are valid; all others are unmapped and skipped.
ACTIVITY_RELATION_MAP: dict[
    tuple[str, str],  # (action, resource_prefix)
    list[tuple[str, str]],  # [(api_resource_type, relation), ...]
] = {
    ("submit-audit", "datatype"): [
        ("data_pipeline", "submitter"),
        ("data_pipeline", "viewer"),
    ],
    ("view", "datatype"): [("data_pipeline", "viewer")],
    ("view", "dashboard"): [("dashboard", "viewer")],
    ("view", "page"): [("page", "viewer")],
}


def translate(
    registry_id: str,
    authorizations: Authorizations,
    center_group_id: str | None = None,
) -> set[DesiredGrant]:
    """Translate authorizations to desired grants.

    Iterates activities in the authorizations and maps each to grants
    using ACTIVITY_RELATION_MAP.

    Resource ID scoping depends on center_group_id:
    - When provided: resource_id = "{center_group_id}/{project_label}"
    - When None: resource_id = "{project_label}" (no prefix)

    Works with both Authorizations (general) and StudyAuthorizations
    (center-scoped) since StudyAuthorizations extends Authorizations.

    Args:
        registry_id: The user's registry ID (ePPN).
        authorizations: The authorizations to translate (Authorizations
            or StudyAuthorizations).
        center_group_id: The Flywheel group ID for the center, or None
            for general (non-center) authorizations.

    Returns:
        Set of DesiredGrant objects.
    """
    grants: set[DesiredGrant] = set()

    for resource, activity in authorizations.activities.items():
        action = activity.action
        resource_prefix = resource.prefix()
        project_label = resource.name

        mapping_key = (action, resource_prefix)
        mapped_pairs = ACTIVITY_RELATION_MAP.get(mapping_key)

        if mapped_pairs is None:
            log.warning(
                "Unmapped activity: action=%s, resource_prefix=%s, "
                "resource_name=%s — skipping",
                action,
                resource_prefix,
                project_label,
            )
            continue

        # Construct resource_id based on scoping
        if center_group_id is not None:
            resource_id = f"{center_group_id}/{project_label}"
        else:
            resource_id = project_label

        for api_resource_type, relation in mapped_pairs:
            grants.add(
                DesiredGrant(
                    user_id=registry_id,
                    resource_type=api_resource_type,
                    resource_id=resource_id,
                    relation=relation,
                )
            )

    return grants


def validate_activity_relation_map(
    model: AuthorizationModelMetadata,
) -> list[str]:
    """Validate ACTIVITY_RELATION_MAP against the live authorization model.

    Checks that every (resource_type, relation) pair referenced in the
    map is a known, assignable relation in the model.

    Args:
        model: The authorization model metadata from the API.

    Returns:
        List of warning messages for invalid mappings. Empty if all
        mappings are valid.
    """
    warnings: list[str] = []

    for (action, resource_prefix), mapped_pairs in ACTIVITY_RELATION_MAP.items():
        for api_resource_type, relation in mapped_pairs:
            reason = _check_assignable(model, api_resource_type, relation)
            if reason:
                warnings.append(
                    f"ACTIVITY_RELATION_MAP ({action}, {resource_prefix}) "
                    f"-> ({api_resource_type}, {relation}): {reason}"
                )

    return warnings


def _check_assignable(
    model: AuthorizationModelMetadata,
    resource_type: str,
    relation: str,
) -> str | None:
    """Return a reason string if the relation is not assignable, else None.

    Args:
        model: The authorization model metadata.
        resource_type: The type to check.
        relation: The relation to check.

    Returns:
        A reason string if invalid, or None if valid.
    """
    type_meta = model.types.get(resource_type)
    if type_meta is None:
        return f"unknown type '{resource_type}'"

    relation_meta = type_meta.relations.get(relation)
    if relation_meta is None:
        return f"unknown relation '{relation}' on type '{resource_type}'"

    if not relation_meta.assignable:
        return f"relation '{relation}' on type '{resource_type}' is not assignable"

    return None
