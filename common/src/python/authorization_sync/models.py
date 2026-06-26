"""Data models for the authorization sync module."""

from dataclasses import dataclass
from typing import Literal

from authorization.models import BatchOperation


@dataclass(frozen=True)
class DesiredGrant:
    """A grant the user should hold in the Authorization API.

    A frozen dataclass providing __hash__ and __eq__ for set operations.
    Two DesiredGrant instances are equal when all four fields match
    (case-sensitive).
    """

    user_id: str
    resource_type: str
    resource_id: str
    relation: str

    def to_batch_op(self, action: Literal["grant", "revoke"]) -> BatchOperation:
        """Convert this grant to a BatchOperation.

        Args:
            action: The batch action, either "grant" or "revoke".

        Returns:
            A BatchOperation with this grant's fields and the specified
            action.
        """
        return BatchOperation(
            action=action,
            user_id=self.user_id,
            resource_type=self.resource_type,
            resource_id=self.resource_id,
            relation=self.relation,
        )
