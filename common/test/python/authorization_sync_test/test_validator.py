"""Tests for validate_activity_relation_map and _check_assignable."""

from authorization.models import (
    AuthorizationModelMetadata,
    RelationMetadata,
    TypeMetadata,
)
from authorization_sync.translator import (
    _check_assignable,
    validate_activity_relation_map,
)


def _build_model(types: dict[str, TypeMetadata]) -> AuthorizationModelMetadata:
    """Helper to build a minimal model."""
    return AuthorizationModelMetadata(version="1.0.0", types=types)


def _type_with_relations(
    name: str,
    category: str,
    relations: dict[str, bool],
) -> TypeMetadata:
    """Helper to build TypeMetadata with relations as {name: assignable}."""
    return TypeMetadata(
        name=name,
        category=category,
        relations={
            rel_name: RelationMetadata(name=rel_name, assignable=assignable)
            for rel_name, assignable in relations.items()
        },
    )


class TestCheckAssignable:
    """Tests for the _check_assignable helper."""

    def test_returns_none_for_valid_assignable_relation(self) -> None:
        """Valid type + assignable relation returns None."""
        model = _build_model(
            {
                "data_pipeline": _type_with_relations(
                    "data_pipeline", "resource", {"viewer": True, "submitter": True}
                ),
            }
        )

        assert _check_assignable(model, "data_pipeline", "viewer") is None

    def test_returns_reason_for_unknown_type(self) -> None:
        """Unknown type returns a reason string."""
        model = _build_model({})

        result = _check_assignable(model, "nonexistent", "viewer")

        assert result is not None
        assert "unknown type" in result
        assert "nonexistent" in result

    def test_returns_reason_for_unknown_relation(self) -> None:
        """Known type but unknown relation returns a reason string."""
        model = _build_model(
            {
                "data_pipeline": _type_with_relations(
                    "data_pipeline", "resource", {"viewer": True}
                ),
            }
        )

        result = _check_assignable(model, "data_pipeline", "nonexistent")

        assert result is not None
        assert "unknown relation" in result
        assert "nonexistent" in result

    def test_returns_reason_for_non_assignable_relation(self) -> None:
        """Known type and relation but not assignable returns a reason."""
        model = _build_model(
            {
                "data_pipeline": _type_with_relations(
                    "data_pipeline",
                    "resource",
                    {"study_admin_access": False},
                ),
            }
        )

        result = _check_assignable(model, "data_pipeline", "study_admin_access")

        assert result is not None
        assert "not assignable" in result


class TestValidateActivityRelationMap:
    """Tests for validate_activity_relation_map against
    ACTIVITY_RELATION_MAP."""

    def test_returns_empty_when_model_matches(self) -> None:
        """No warnings when model contains all mapped types and relations."""
        model = _build_model(
            {
                "data_pipeline": _type_with_relations(
                    "data_pipeline",
                    "resource",
                    {"viewer": True, "submitter": True},
                ),
                "dashboard": _type_with_relations(
                    "dashboard", "resource", {"viewer": True}
                ),
                "page": _type_with_relations("page", "resource", {"viewer": True}),
            }
        )

        warnings = validate_activity_relation_map(model)

        assert warnings == []

    def test_returns_warnings_for_missing_type(self) -> None:
        """Warns when a mapped type is missing from the model."""
        # Model has dashboard and page but NOT data_pipeline
        model = _build_model(
            {
                "dashboard": _type_with_relations(
                    "dashboard", "resource", {"viewer": True}
                ),
                "page": _type_with_relations("page", "resource", {"viewer": True}),
            }
        )

        warnings = validate_activity_relation_map(model)

        # data_pipeline is referenced by 3 map entries (submit-audit->2, view->1)
        assert len(warnings) == 3
        assert all("data_pipeline" in w for w in warnings)

    def test_returns_warnings_for_non_assignable(self) -> None:
        """Warns when a mapped relation exists but is not assignable."""
        model = _build_model(
            {
                "data_pipeline": _type_with_relations(
                    "data_pipeline",
                    "resource",
                    {"viewer": False, "submitter": False},
                ),
                "dashboard": _type_with_relations(
                    "dashboard", "resource", {"viewer": True}
                ),
                "page": _type_with_relations("page", "resource", {"viewer": True}),
            }
        )

        warnings = validate_activity_relation_map(model)

        # viewer is used in 3 map entries for data_pipeline, submitter in 1
        assert len(warnings) > 0
        assert all("not assignable" in w for w in warnings)
