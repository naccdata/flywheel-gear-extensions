"""Activity-to-relation mapping for the Authorization API.

Maps the gear's internal Activity (action + Resource) to the
Authorization API's grant vocabulary (resource_type, relation, and the
structured resource label plus parent fields) and produces a set of
DesiredGrant objects for a user's authorizations.
"""

import logging

from authorization.models import AuthorizationModelMetadata
from users.authorizations import Authorizations, StudyAuthorizations

from authorization_sync.models import DesiredGrant
from authorization_sync.resource_ids import build_label_for_resource_prefix

log = logging.getLogger(__name__)

# The well-known community organization id under which general (non-center)
# resources are scoped. General page grants (e.g. the "community-resources"
# portal page) carry this as their ``community`` parent. The value must match
# the community id the hierarchy seeder attaches page parents to
# (``projects/hierarchy_seeder.py``: ``_community_scoped_parents``,
# ``parent_id="nacc"``); a grant pointing at a different id would reference a
# non-existent parent.
NACC_COMMUNITY_ID = "nacc"

# Resource types that require a parent per the Authorization API's per-type
# combination table. A grant of one of these types with no study/center/
# community parent is rejected by the API. General-scope grants of these types
# are scoped to the NACC community (the only parentless-looking scope the
# general path supports); any other resource type reaching the general path
# without a parent is unmapped and skipped rather than sent and rejected.
_COMMUNITY_SCOPED_GENERAL_TYPES: frozenset[str] = frozenset({"page"})

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

    Each grant carries the Structured Identity of the resource: the
    resource label from build_label_for_resource_prefix (e.g.,
    "ingest-form" for a data_pipeline resource) plus the applicable
    parent fields. The center parent is the center group id (None for
    general scope) and the study parent comes from StudyAuthorizations
    (else None). No flat resource id is built here; the client assembles
    identity from these structured fields.

    General (non-center) scope: the Authorization API requires a parent
    for resource types such as ``page``, so a parentless general grant
    would be rejected. General grants of a community-scoped resource type
    (:data:`_COMMUNITY_SCOPED_GENERAL_TYPES`) are therefore scoped to the
    NACC community (``community=NACC_COMMUNITY_ID``). A general grant of
    any other resource type has no parent the general path can supply; it
    is skipped with a warning rather than emitted and rejected by the API.
    Center-scoped grants (``center_group_id`` set) are unaffected and
    carry no community.

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
    # Extract study_id from StudyAuthorizations if available
    study_id: str | None = None
    if isinstance(authorizations, StudyAuthorizations):
        study_id = authorizations.study_id

    grants: set[DesiredGrant] = set()

    for resource, activity in authorizations.activities.items():
        action = activity.action
        resource_prefix = resource.prefix()
        resource_name = resource.name

        mapping_key = (action, resource_prefix)
        mapped_pairs = ACTIVITY_RELATION_MAP.get(mapping_key)

        if mapped_pairs is None:
            log.warning(
                "Unmapped activity: action=%s, resource_prefix=%s, "
                "resource_name=%s — skipping",
                action,
                resource_prefix,
                resource_name,
            )
            continue

        label = build_label_for_resource_prefix(resource_prefix, resource_name)

        # A grant needs a parent only when neither a center nor a study is
        # available; with a center or study present, the (center)/(study)
        # combinations already satisfy the API's per-type requirement.
        needs_general_parent = center_group_id is None and study_id is None

        for api_resource_type, relation in mapped_pairs:
            community: str | None = None
            if needs_general_parent:
                if api_resource_type in _COMMUNITY_SCOPED_GENERAL_TYPES:
                    # No center and no study: the API requires a parent for
                    # this resource type, so scope it to the NACC community.
                    community = NACC_COMMUNITY_ID
                else:
                    # No center, no study, and not a community-scoped type:
                    # there is no parent the general path can supply, and the
                    # API rejects a parentless grant of this type. Skip it
                    # rather than emit an unbuildable grant.
                    log.warning(
                        "Skipping general-scope grant with no parent: "
                        "resource_type=%s, relation=%s, label=%s — the "
                        "Authorization API requires a parent for this type",
                        api_resource_type,
                        relation,
                        label,
                    )
                    continue

            grants.add(
                DesiredGrant(
                    user_id=registry_id,
                    resource_type=api_resource_type,
                    relation=relation,
                    resource_label=label,
                    center=center_group_id,
                    study=study_id,
                    community=community,
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
            reason = check_assignable(model, api_resource_type, relation)
            if reason:
                warnings.append(
                    f"ACTIVITY_RELATION_MAP ({action}, {resource_prefix}) "
                    f"-> ({api_resource_type}, {relation}): {reason}"
                )

    return warnings


def check_assignable(
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
