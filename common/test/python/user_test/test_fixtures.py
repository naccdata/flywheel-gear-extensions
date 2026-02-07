"""Tests to verify the test fixtures work correctly."""


class TestHelperFunctions:
    """Tests for helper functions that build test objects."""

    def test_build_email_address_defaults(self, build_email_address):
        """Test building an EmailAddress with default values."""
        email = build_email_address()
        assert email.mail == "test@example.com"
        assert email.type == "official"
        assert email.verified is True

    def test_build_email_address_custom(self, build_email_address):
        """Test building an EmailAddress with custom values."""
        email = build_email_address(
            mail="custom@test.com",
            email_type="personal",
            verified=False,
        )
        assert email.mail == "custom@test.com"
        assert email.type == "personal"
        assert email.verified is False

    def test_build_name_defaults(self, build_name):
        """Test building a Name with default values."""
        name = build_name()
        assert name.given == "John"
        assert name.family == "Doe"
        assert name.type == "official"
        assert name.primary_name is True

    def test_build_identifier_defaults(self, build_identifier):
        """Test building an Identifier with default values."""
        identifier = build_identifier()
        assert identifier.identifier == "test-id-123"
        assert identifier.type == "naccid"
        assert identifier.status == "A"
        assert identifier.login is None

    def test_build_co_person_defaults(self, build_co_person):
        """Test building a CoPerson with default values."""
        coperson = build_co_person()
        assert coperson.co_id == 1
        assert coperson.status == "A"
        assert coperson.meta is None

    def test_build_org_identity_empty(self, build_org_identity):
        """Test building an OrgIdentity with no data."""
        org = build_org_identity()
        assert org.email_address is None
        assert org.identifier is None

    def test_build_coperson_message_minimal(self, build_coperson_message):
        """Test building a minimal CoPersonMessage."""
        msg = build_coperson_message()
        assert msg.co_person is None
        assert msg.email_address is None
        assert msg.name is None
        assert msg.identifier is None
        assert msg.org_identity is None
        assert msg.co_person_role is None

    def test_build_coperson_message_complete(
        self,
        build_coperson_message,
        build_co_person,
        build_email_address,
        build_name,
        build_identifier,
        build_org_identity,
    ):
        """Test building a complete CoPersonMessage."""
        coperson = build_co_person()
        emails = [build_email_address()]
        names = [build_name()]
        identifiers = [build_identifier()]
        org_identities = [build_org_identity()]

        msg = build_coperson_message(
            co_person=coperson,
            email_addresses=emails,
            names=names,
            identifiers=identifiers,
            org_identities=org_identities,
        )

        assert msg.co_person == coperson
        assert msg.email_address == emails
        assert msg.name == names
        assert msg.identifier == identifiers
        assert msg.org_identity == org_identities
