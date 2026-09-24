"""Contract-conformance tests for the Authorization client.

These tests demonstrate that the client honors the Authorization API's
resource-identity contract, using a mock whose behavior is derived from the
API's own published model metadata (``contract_model.json``) rather than from
the client's assumptions. See ``contract.py`` for why that makes the mock an
independent authority.

Two layers:

- Request/response conformance through the real ``AuthorizationClient``: every
  parent combination the model permits is accepted and round-trips; a
  combination the model forbids is rejected by the contract (HTTP 400) exactly
  as the real API would reject it.
- End-to-end sync conformance through the real ``AuthorizationSyncService``:
  translated grants are built, sent, persisted, and read back — all without a
  single contract violation — proving the client's produced identities match
  what the contract accepts.

A final drift guard pins the client's own ``ResourceObject.check_parent_fields``
table against the model's ``validParentCombinations`` so the two cannot silently
diverge.
"""

import itertools

import pytest
from authorization.client import AuthorizationClient
from authorization.exceptions import ValidationError
from authorization.models import _ORGANIZATION_TYPES, ResourceObject
from authorization_sync.sync_service import AuthorizationSyncService
from authorization_sync.translator import NACC_COMMUNITY_ID
from pydantic import ValidationError as PydanticValidationError
from users.authorizations import (
    Activities,
    Activity,
    Authorizations,
    DatatypeResource,
    PageResource,
    StudyAuthorizations,
)
from users.event_models import UserEventCollector

from .conftest import no_sleep
from .contract import (
    ContractEnforcingTransport,
    ContractViolation,
    load_contract_model,
    permitted_parent_field_sets,
)

# Field-name sets used to enumerate parent combinations.
_PARENT_FIELDS = ("study", "center", "community")


def model_types_by_category() -> dict[str, str]:
    """Map each type name in the model to its category (from the fixture)."""
    model = load_contract_model()
    return {name: meta.category for name, meta in model.types.items()}


# Organization type names declared by the model, used to parametrize the
# organization-type conformance test so all five are covered.
_MODEL_ORGANIZATION_TYPES = sorted(
    name
    for name, category in model_types_by_category().items()
    if category == "organization"
)


def _make_client() -> tuple[AuthorizationClient, ContractEnforcingTransport]:
    transport = ContractEnforcingTransport(model=load_contract_model())
    client = AuthorizationClient(transport=transport, sleep=no_sleep)  # type: ignore[arg-type]
    return client, transport


def _fields_to_kwargs(fields: frozenset[str]) -> dict[str, str]:
    """Turn a set of present parent-field names into grant kwargs."""
    values = {"study": "study-1", "center": "center-1", "community": NACC_COMMUNITY_ID}
    return {name: values[name] for name in fields}


class TestModelFixtureLoads:
    """The captured model fixture parses and exposes the expected types."""

    def test_fixture_parses_and_has_constrained_types(self) -> None:
        model = load_contract_model()
        assert model.version == "1.0.0"
        # The resource types the sync gear grants against are all present and
        # carry parent-combination constraints.
        for resource_type in ("data_pipeline", "dashboard", "page"):
            assert model.types[resource_type].valid_parent_combinations


class TestContractMockHasTeeth:
    """The contract mock rejects invalid identities on its own authority.

    A mock that never rejects anything would make every conformance test
    pass vacuously. These assertions confirm the mock's enforcement is
    real and independent of the client: it rejects combinations the
    model forbids, including the exact parentless-page shape of the
    original bug — proving that if the client regressed to producing
    such a request, the conformance tests above would fail rather than
    silently pass.
    """

    def test_rejects_forbidden_combination(self) -> None:
        transport = ContractEnforcingTransport(model=load_contract_model())
        # data_pipeline permits (study+center) or (study); community-alone is
        # forbidden by the model.
        with pytest.raises(ContractViolation):
            transport._validate_resource(  # noqa: SLF001 - exercising enforcement
                {"type": "data_pipeline", "label": "ingest-form", "community": "nacc"}
            )

    def test_rejects_parentless_resource_type(self) -> None:
        transport = ContractEnforcingTransport(model=load_contract_model())
        # The original bug: a page with no parent. The model requires a parent
        # for page, so the contract rejects it.
        with pytest.raises(ContractViolation):
            transport._validate_resource(  # noqa: SLF001 - exercising enforcement
                {"type": "page", "label": "page-x"}
            )

    def test_rejects_flat_id_on_request(self) -> None:
        transport = ContractEnforcingTransport(model=load_contract_model())
        with pytest.raises(ContractViolation):
            transport._validate_resource(  # noqa: SLF001 - exercising enforcement
                {"type": "page", "label": "page-x", "community": "nacc", "flatId": "x"}
            )

    def test_accepts_a_permitted_combination(self) -> None:
        transport = ContractEnforcingTransport(model=load_contract_model())
        # Sanity: a permitted combination does not raise.
        transport._validate_resource(  # noqa: SLF001 - exercising enforcement
            {"type": "page", "label": "page-x", "community": "nacc"}
        )


class TestGrantConformanceAcrossPermittedCombinations:
    """Every model-permitted parent combination is accepted and round-trips.

    Drives the real client's ``grant`` for each
    ``validParentCombination`` the model declares for the constrained
    resource types, and asserts the contract mock accepts it (no
    violation) and returns a parseable, structured response with a
    server-owned flat id.
    """

    @pytest.mark.parametrize("resource_type", ["data_pipeline", "dashboard", "page"])
    def test_all_permitted_combinations_round_trip(self, resource_type: str) -> None:
        model = load_contract_model()
        client, transport = _make_client()

        permitted = permitted_parent_field_sets(model, resource_type)
        # The constrained resource types always require at least one parent.
        assert permitted and all(combo for combo in permitted)

        for fields in permitted:
            kwargs = _fields_to_kwargs(fields)
            result = client.grant(
                user_id="user@institution.edu",
                resource_type=resource_type,
                resource_label=f"{resource_type}-x",
                relation="viewer",
                **kwargs,
            )
            # The response is structured and carries a server-owned flat id
            # the client never sent.
            assert result.resource is not None
            assert result.resource.type == resource_type
            assert result.resource.flat_id is not None
            assert result.resource.flat_id.startswith("srv::")

        # No request violated the contract.
        assert transport.violations == []


class TestInvalidCombinationsAreContractRejected:
    """Combinations the model forbids are rejected as the real API would.

    For each constrained resource type, every parent-field combination
    the model does NOT list is driven through the client. Because the
    client's own validator also enforces the same table, such a request
    raises a client-side ``ValidationError`` before any HTTP call — but
    the intent here is to prove that the contract (the mock) agrees the
    combination is invalid, i.e. the client is not more permissive than
    the API. Any combination that somehow reached the transport is
    recorded as a violation, and we assert the contract flagged it.
    """

    @pytest.mark.parametrize("resource_type", ["data_pipeline", "dashboard", "page"])
    def test_forbidden_combinations_never_accepted(self, resource_type: str) -> None:
        model = load_contract_model()
        permitted = set(permitted_parent_field_sets(model, resource_type))

        # Enumerate all 8 subsets of the three parent fields.
        all_combinations = [
            frozenset(combo)
            for r in range(len(_PARENT_FIELDS) + 1)
            for combo in itertools.combinations(_PARENT_FIELDS, r)
        ]
        forbidden = [combo for combo in all_combinations if combo not in permitted]
        assert forbidden  # sanity: there are forbidden combinations

        for fields in forbidden:
            client, transport = _make_client()
            kwargs = _fields_to_kwargs(fields)
            # The client rejects an invalid identity before sending (its
            # validator mirrors the contract). Either it raises client-side,
            # or — if it ever sent the request — the contract must reject it.
            try:
                client.grant(
                    user_id="user@institution.edu",
                    resource_type=resource_type,
                    resource_label=f"{resource_type}-x",
                    relation="viewer",
                    **kwargs,
                )
            except ValidationError:
                # Rejected before any HTTP call: the client agrees with the
                # contract that this combination is invalid. Nothing reached
                # the transport.
                assert transport.violations == []
                assert transport.seen_resources == []
            else:
                # If the client did send it, the contract must have rejected
                # it (proving the client is not more permissive than the API).
                assert transport.violations, (
                    f"contract accepted a forbidden combination "
                    f"{sorted(fields)} for {resource_type!r}"
                )


class TestRevokeConformance:
    """Revoke sends a contract-valid resource and removes the stored grant."""

    def test_revoke_round_trips(self) -> None:
        client, transport = _make_client()
        # Seed a stored grant via a grant call.
        client.grant(
            user_id="user@institution.edu",
            resource_type="page",
            resource_label="page-community-resources",
            relation="viewer",
            community=NACC_COMMUNITY_ID,
        )
        assert any(k[1] == "page" for k in transport.grants)

        client.revoke(
            user_id="user@institution.edu",
            resource_type="page",
            resource_label="page-community-resources",
            relation="viewer",
            community=NACC_COMMUNITY_ID,
        )
        assert not any(k[1] == "page" for k in transport.grants)
        assert transport.violations == []


class TestSyncEndToEndThroughContract:
    """The sync service round-trips through the contract with no violations.

    Drives the real ``AuthorizationSyncService`` (translate -> diff ->
    batch, and the per-type permissions read) against the contract mock.
    This is the strongest demonstration: the identities the
    translator/client produce are exactly the identities the contract
    accepts and echoes back, so a repeated sync is idempotent (no churn)
    and no request is ever rejected.
    """

    def _center_auth(self, study_id: str, datatype: str) -> StudyAuthorizations:
        activities = Activities()
        resource = DatatypeResource(datatype=datatype)
        activities.add(resource, Activity(resource=resource, action="submit-audit"))
        return StudyAuthorizations(study_id=study_id, activities=activities)

    def _general_page_auth(self, page: str) -> Authorizations:
        activities = Activities()
        resource = PageResource(page=page)
        activities.add(resource, Activity(resource=resource, action="view"))
        return Authorizations(activities=activities)

    def test_center_sync_applies_and_is_idempotent(self) -> None:
        client, transport = _make_client()
        collector = UserEventCollector()
        service = AuthorizationSyncService(client=client, collector=collector)

        # First sync: creates the center-scoped data_pipeline grants.
        service.sync_users(
            registry_id="user@institution.edu",
            authorizations=[self._center_auth("study-1", "form")],
            center_group_id="center-1",
        )
        assert transport.violations == []
        assert collector.error_count() == 0
        first_state = set(transport.grants)
        assert first_state  # something was granted

        # Second sync with the same desired state: the contract echoes the
        # same structured identities the translator produces, so the diff is
        # empty — no adds, no revokes, no churn.
        before = set(transport.grants)
        service.sync_users(
            registry_id="user@institution.edu",
            authorizations=[self._center_auth("study-1", "form")],
            center_group_id="center-1",
        )
        assert transport.grants == before
        assert transport.violations == []
        assert collector.error_count() == 0

    def test_general_page_sync_is_community_scoped_and_accepted(self) -> None:
        client, transport = _make_client()
        collector = UserEventCollector()
        service = AuthorizationSyncService(client=client, collector=collector)

        service.sync_user(
            registry_id="user@institution.edu",
            authorizations=self._general_page_auth("community-resources"),
        )
        # The general page grant was accepted by the contract (community-scoped)
        # and persisted; no violation, no error.
        assert transport.violations == []
        assert collector.error_count() == 0
        page_grants = [k for k in transport.grants if k[1] == "page"]
        assert len(page_grants) == 1
        # community parent is set to nacc; no center/study.
        (_uid, _type, _label, _relation, study, center, community) = page_grants[0]
        assert community == NACC_COMMUNITY_ID
        assert study is None
        assert center is None

        # Idempotent on re-sync.
        before = set(transport.grants)
        service.sync_user(
            registry_id="user@institution.edu",
            authorizations=self._general_page_auth("community-resources"),
        )
        assert transport.grants == before
        assert transport.violations == []


class TestClientValidatorMatchesContract:
    """The client's parent-field validator agrees with the model contract.

    Pins ``ResourceObject.check_parent_fields`` against the model's
    ``validParentCombinations`` for the constrained resource types, so
    the client's hand-maintained table cannot silently drift from the
    API's published contract. For every one of the 8 possible parent-
    field combinations, the client accepts a combination iff the model
    permits it.
    """

    @pytest.mark.parametrize("resource_type", ["data_pipeline", "dashboard", "page"])
    def test_validator_accepts_exactly_permitted_combinations(
        self, resource_type: str
    ) -> None:
        model = load_contract_model()
        permitted = set(permitted_parent_field_sets(model, resource_type))

        all_combinations = [
            frozenset(combo)
            for r in range(len(_PARENT_FIELDS) + 1)
            for combo in itertools.combinations(_PARENT_FIELDS, r)
        ]

        for fields in all_combinations:
            kwargs = _fields_to_kwargs(fields)
            client_accepts: bool
            try:
                ResourceObject(type=resource_type, label=f"{resource_type}-x", **kwargs)
                client_accepts = True
            except PydanticValidationError:
                client_accepts = False

            contract_permits = fields in permitted
            assert client_accepts == contract_permits, (
                f"client/contract disagree on {resource_type!r} with parents "
                f"{sorted(fields)}: client_accepts={client_accepts}, "
                f"contract_permits={contract_permits}"
            )

    @pytest.mark.parametrize("org_type", _MODEL_ORGANIZATION_TYPES)
    def test_organization_types_reject_all_parents(self, org_type: str) -> None:
        """Every organization type in the model carries no parents.

        The model marks these ``category: organization`` with no
        ``validParentCombinations``; the client's validator must reject
        any parent on them. Parametrized from the model so all five
        organization types are covered (including ``funding_agency`` and
        ``associated_organization``), not just the three the seed path
        happens to use.
        """
        model = load_contract_model()
        assert model.types[org_type].valid_parent_combinations is None

        # No parents: accepted by both.
        ResourceObject(type=org_type, label=f"{org_type}-x")

        # Any parent: rejected by the client.
        with pytest.raises(PydanticValidationError):
            ResourceObject(type=org_type, label=f"{org_type}-x", study="study-1")

    def test_client_organization_type_set_matches_model(self) -> None:
        """The client's organization-type set equals the model's exactly.

        ``ResourceObject`` treats a type not in ``_ORGANIZATION_TYPES``
        and not in the per-type combination table as a forward-
        compatible resource type (unconstrained parents). If the model
        declares an organization type the client omits, the client would
        wrongly accept parents on it. Pin the set against the model so
        the two cannot drift.
        """
        model_org_types = {
            name
            for name, meta in model_types_by_category().items()
            if meta == "organization"
        }
        assert model_org_types == _ORGANIZATION_TYPES
