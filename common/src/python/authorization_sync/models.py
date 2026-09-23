"""Data models for the authorization sync module."""

from dataclasses import dataclass
from typing import Literal

from authorization.models import BatchOperation, ResourceObject


@dataclass(frozen=True)
class DesiredGrant:
    """A grant the user should hold in the Authorization API.

    A frozen dataclass providing ``__hash__`` and ``__eq__`` for set
    operations. Carries the Structured Identity of the resource rather
    than a flat ``resource_id``: the ``resource_type``,
    ``resource_label``, and the applicable parent fields (``center``,
    ``study``, ``community``). Because the fields are exactly the
    Structured Identity Tuple components (plus ``user_id``), set
    difference over ``DesiredGrant`` keys on that tuple automatically;
    the server-owned ``flat_id`` handle is never a field and cannot
    affect equality.
    """

    user_id: str
    resource_type: str
    relation: str
    resource_label: str
    center: str | None = None
    study: str | None = None
    community: str | None = None

    def __post_init__(self) -> None:
        """Reject construction without a resource type or label.

        Raises:
            ValueError: If ``resource_type`` or ``resource_label`` is
                missing or empty.
        """
        if not self.resource_type or not self.resource_label:
            raise ValueError("DesiredGrant requires resource_type and resource_label")

    def identity(
        self,
    ) -> tuple[str, str, str, str | None, str | None, str | None]:
        """Return the Structured Identity Tuple used as the diff key.

        Returns:
            The tuple ``(resource_type, relation, resource_label, center,
            study, community)``.
        """
        return (
            self.resource_type,
            self.relation,
            self.resource_label,
            self.center,
            self.study,
            self.community,
        )

    def to_resource(self) -> ResourceObject:
        """Build a structured :class:`ResourceObject` for this grant.

        Returns:
            A ``ResourceObject`` carrying this grant's type, label, and
            parent fields. No ``flat_id`` is set.
        """
        return ResourceObject(
            type=self.resource_type,
            label=self.resource_label,
            center=self.center,
            study=self.study,
            community=self.community,
        )

    def to_batch_op(self, action: Literal["grant", "revoke"]) -> BatchOperation:
        """Convert this grant to a structured BatchOperation.

        Args:
            action: The batch action, either "grant" or "revoke".

        Returns:
            A BatchOperation carrying this grant's structured identity and
            the specified action.
        """
        return BatchOperation(
            action=action,
            user_id=self.user_id,
            resource_type=self.resource_type,
            resource_label=self.resource_label,
            relation=self.relation,
            center=self.center,
            study=self.study,
            community=self.community,
        )
