"""Unit tests for RegistryPerson email functionality.

Tests focus on email selection priority logic, email filtering, and
email search.
"""

from users.user_registry import RegistryPerson


class TestEmailAddressPropertyPriorityLogic:
    """Tests for email_address property priority logic.

    Tests Requirements 1.1, 1.5:
    - Organizational email takes priority over regular emails
    - Fallback to first email when no org email
    - None when no emails exist
    """

    def test_organizational_email_takes_priority(
        self,
        build_email_address,
        build_identifier,
        build_org_identity,
        build_co_person,
        build_coperson_message,
    ):
        """Test that organizational email takes priority over regular emails.

        When a person has both organizational emails and regular emails,
        the email_address property should return the first
        organizational email.
        """
        # Create organizational identity with email
        org_email = build_email_address(
            mail="org@example.com", email_type="official", verified=True
        )
        org_identifier = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
            login=True,
        )
        org_identity = build_org_identity(
            email_addresses=[org_email], identifiers=[org_identifier]
        )

        # Create regular emails
        regular_email1 = build_email_address(
            mail="regular1@example.com", email_type="personal", verified=True
        )
        regular_email2 = build_email_address(
            mail="regular2@example.com", email_type="work", verified=False
        )

        # Build person with both org and regular emails
        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[regular_email1, regular_email2],
            org_identities=[org_identity],
        )

        person = RegistryPerson(coperson_msg)

        # Should return organizational email, not regular emails
        assert person.email_address == org_email
        assert person.email_address.mail == "org@example.com"

    def test_fallback_to_first_email_when_no_org_email(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test fallback to first email when no organizational email exists.

        When a person has no organizational email, the email_address
        property should return the first email in the list.
        """
        # Create regular emails (no org identity)
        email1 = build_email_address(
            mail="first@example.com", email_type="personal", verified=True
        )
        email2 = build_email_address(
            mail="second@example.com", email_type="work", verified=False
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[email1, email2],
            org_identities=None,
        )

        person = RegistryPerson(coperson_msg)

        # Should return first email
        assert person.email_address == email1
        assert person.email_address.mail == "first@example.com"

    def test_none_when_no_emails_exist(self, build_co_person, build_coperson_message):
        """Test that None is returned when no emails exist.

        When a person has no emails at all, the email_address property
        should return None.
        """
        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=None,
            org_identities=None,
        )

        person = RegistryPerson(coperson_msg)

        # Should return None
        assert person.email_address is None

    def test_org_identity_without_email_falls_back_to_regular(
        self,
        build_identifier,
        build_org_identity,
        build_email_address,
        build_co_person,
        build_coperson_message,
    ):
        """Test fallback when org identity exists but has no email.

        When a person has an organizational identity but it has no
        email, should fall back to regular emails.
        """
        # Create org identity without email
        org_identifier = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
            login=True,
        )
        org_identity = build_org_identity(
            email_addresses=None, identifiers=[org_identifier]
        )

        # Create regular email
        regular_email = build_email_address(
            mail="regular@example.com", email_type="personal", verified=True
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[regular_email],
            org_identities=[org_identity],
        )

        person = RegistryPerson(coperson_msg)

        # Should fall back to regular email
        assert person.email_address == regular_email
        assert person.email_address.mail == "regular@example.com"

    def test_multiple_org_emails_returns_first(
        self,
        build_email_address,
        build_identifier,
        build_org_identity,
        build_co_person,
        build_coperson_message,
    ):
        """Test that first organizational email is returned when multiple
        exist.

        When an organizational identity has multiple emails, should
        return the first one.
        """
        # Create org identity with multiple emails
        org_email1 = build_email_address(
            mail="org1@example.com", email_type="official", verified=True
        )
        org_email2 = build_email_address(
            mail="org2@example.com", email_type="official", verified=True
        )
        org_identifier = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
            login=True,
        )
        org_identity = build_org_identity(
            email_addresses=[org_email1, org_email2], identifiers=[org_identifier]
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=None,
            org_identities=[org_identity],
        )

        person = RegistryPerson(coperson_msg)

        # Should return first org email
        assert person.email_address == org_email1
        assert person.email_address.mail == "org1@example.com"


class TestHasEmailMethod:
    """Tests for has_email method.

    Tests Requirement 1.9:
    - Finds email in list (search logic)
    - Returns False for missing email
    """

    def test_finds_email_in_list(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that has_email finds an email that exists in the list.

        When a person has multiple emails, has_email should return True
        for any email in the list.
        """
        email1 = build_email_address(mail="first@example.com")
        email2 = build_email_address(mail="second@example.com")
        email3 = build_email_address(mail="third@example.com")

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[email1, email2, email3],
        )

        person = RegistryPerson(coperson_msg)

        # Should find all three emails
        assert person.has_email("first@example.com") is True
        assert person.has_email("second@example.com") is True
        assert person.has_email("third@example.com") is True

    def test_returns_false_for_missing_email(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that has_email returns False for an email not in the list.

        When searching for an email that doesn't exist, has_email should
        return False.
        """
        email1 = build_email_address(mail="exists@example.com")

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[email1],
        )

        person = RegistryPerson(coperson_msg)

        # Should not find emails that don't exist
        assert person.has_email("notfound@example.com") is False
        assert person.has_email("missing@example.com") is False

    def test_returns_false_when_no_emails_exist(
        self, build_co_person, build_coperson_message
    ):
        """Test that has_email returns False when person has no emails.

        When a person has no emails at all, has_email should return
        False for any search.
        """
        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=None,
        )

        person = RegistryPerson(coperson_msg)

        # Should return False for any email when list is empty
        assert person.has_email("any@example.com") is False

    def test_case_sensitive_email_search(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that has_email is case-sensitive.

        Email addresses should be matched exactly, including case.
        """
        email = build_email_address(mail="Test@Example.com")

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[email],
        )

        person = RegistryPerson(coperson_msg)

        # Exact match should work
        assert person.has_email("Test@Example.com") is True

        # Different case should not match (if implementation is case-sensitive)
        # Note: This tests current behavior - may need adjustment if
        # implementation changes to be case-insensitive
        assert person.has_email("test@example.com") is False
        assert person.has_email("TEST@EXAMPLE.COM") is False

    def test_searches_across_all_email_types(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that has_email searches across all email types.

        The search should find emails regardless of their type
        (official, personal, work, etc.).
        """
        official_email = build_email_address(
            mail="official@example.com", email_type="official"
        )
        personal_email = build_email_address(
            mail="personal@example.com", email_type="personal"
        )
        work_email = build_email_address(mail="work@example.com", email_type="work")

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[official_email, personal_email, work_email],
        )

        person = RegistryPerson(coperson_msg)

        # Should find emails of all types
        assert person.has_email("official@example.com") is True
        assert person.has_email("personal@example.com") is True
        assert person.has_email("work@example.com") is True
