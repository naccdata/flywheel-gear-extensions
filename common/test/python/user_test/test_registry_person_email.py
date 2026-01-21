"""Unit tests for RegistryPerson email functionality.

Tests focus on email selection priority logic, email filtering, and
email search.
"""

from users.user_registry import RegistryPerson


class TestEmailAddressPropertyPriorityLogic:
    """Tests for email_address property priority logic.

    Tests Requirements 1.1, 1.2, 1.3, 1.4, 1.5:
    - Organizational email takes priority over all other emails
    - Official email takes priority when no org email
    - Verified email takes priority when no org or official email
    - Any email is used when no org, official, or verified email
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

    def test_official_email_priority_when_no_org_email(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that official email takes priority when no org email exists.

        When a person has no organizational email but has official
        emails, the email_address property should return the first
        official email.
        """
        # Create emails with official type first
        official_email = build_email_address(
            mail="official@example.com", email_type="official", verified=False
        )
        personal_email = build_email_address(
            mail="personal@example.com", email_type="personal", verified=True
        )
        work_email = build_email_address(
            mail="work@example.com", email_type="work", verified=True
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[personal_email, official_email, work_email],
            org_identities=None,
        )

        person = RegistryPerson(coperson_msg)

        # Should return official email even though it's not first in list
        assert person.email_address == official_email
        assert person.email_address.mail == "official@example.com"

    def test_verified_email_priority_when_no_org_or_official(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that verified email takes priority when no org or official
        email exists.

        When a person has no organizational or official email but has
        verified emails, the email_address property should return the
        first verified email.
        """
        # Create emails with verified but not official
        unverified_email = build_email_address(
            mail="unverified@example.com", email_type="personal", verified=False
        )
        verified_email = build_email_address(
            mail="verified@example.com", email_type="work", verified=True
        )
        another_unverified = build_email_address(
            mail="another@example.com", email_type="personal", verified=False
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[unverified_email, verified_email, another_unverified],
            org_identities=None,
        )

        person = RegistryPerson(coperson_msg)

        # Should return verified email even though it's not first in list
        assert person.email_address == verified_email
        assert person.email_address.mail == "verified@example.com"

    def test_any_email_when_no_org_official_or_verified(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that any email is used when no org, official, or verified email
        exists.

        When a person has only unverified, non-official emails, the
        email_address property should return the first email in the
        list.
        """
        # Create only unverified, non-official emails
        email1 = build_email_address(
            mail="first@example.com", email_type="personal", verified=False
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

    def test_priority_chain_with_all_types(
        self,
        build_email_address,
        build_identifier,
        build_org_identity,
        build_co_person,
        build_coperson_message,
    ):
        """Test complete priority chain with all email types present.

        When a person has org, official, verified, and unverified
        emails, should return org email (highest priority).
        """
        # Create org email
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

        # Create other email types
        official_email = build_email_address(
            mail="official@example.com", email_type="official", verified=False
        )
        verified_email = build_email_address(
            mail="verified@example.com", email_type="personal", verified=True
        )
        unverified_email = build_email_address(
            mail="unverified@example.com", email_type="work", verified=False
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[unverified_email, verified_email, official_email],
            org_identities=[org_identity],
        )

        person = RegistryPerson(coperson_msg)

        # Should return org email (highest priority)
        assert person.email_address == org_email
        assert person.email_address.mail == "org@example.com"

    def test_official_priority_over_verified(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that official email takes priority over verified email.

        When a person has both official (unverified) and verified (non-
        official) emails, official should take priority.
        """
        # Create verified but not official email
        verified_email = build_email_address(
            mail="verified@example.com", email_type="personal", verified=True
        )
        # Create official but not verified email
        official_email = build_email_address(
            mail="official@example.com", email_type="official", verified=False
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[verified_email, official_email],
            org_identities=None,
        )

        person = RegistryPerson(coperson_msg)

        # Should return official email (higher priority than verified)
        assert person.email_address == official_email
        assert person.email_address.mail == "official@example.com"

    def test_multiple_official_emails_returns_first(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that first official email is returned when multiple exist.

        When a person has multiple official emails, should return the
        first one in the list.
        """
        official1 = build_email_address(
            mail="official1@example.com", email_type="official", verified=True
        )
        official2 = build_email_address(
            mail="official2@example.com", email_type="official", verified=False
        )
        official3 = build_email_address(
            mail="official3@example.com", email_type="official", verified=True
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[official1, official2, official3],
            org_identities=None,
        )

        person = RegistryPerson(coperson_msg)

        # Should return first official email
        assert person.email_address == official1
        assert person.email_address.mail == "official1@example.com"

    def test_multiple_verified_emails_returns_first(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that first verified email is returned when multiple exist.

        When a person has multiple verified emails (no official), should
        return the first verified one.
        """
        unverified = build_email_address(
            mail="unverified@example.com", email_type="personal", verified=False
        )
        verified1 = build_email_address(
            mail="verified1@example.com", email_type="work", verified=True
        )
        verified2 = build_email_address(
            mail="verified2@example.com", email_type="personal", verified=True
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[unverified, verified1, verified2],
            org_identities=None,
        )

        person = RegistryPerson(coperson_msg)

        # Should return first verified email
        assert person.email_address == verified1
        assert person.email_address.mail == "verified1@example.com"

    def test_official_and_verified_email_returns_official(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that official+verified email is returned via official priority.

        When a person has an email that is both official and verified,
        it should be returned through the official priority level.
        """
        # Email that is both official and verified
        official_verified = build_email_address(
            mail="both@example.com", email_type="official", verified=True
        )
        # Just verified
        just_verified = build_email_address(
            mail="verified@example.com", email_type="personal", verified=True
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[just_verified, official_verified],
            org_identities=None,
        )

        person = RegistryPerson(coperson_msg)

        # Should return the official+verified email
        assert person.email_address == official_verified
        assert person.email_address.mail == "both@example.com"


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


class TestOfficialEmailAddressesProperty:
    """Tests for official_email_addresses property.

    Tests Requirements 3.1, 3.4, 3.5:
    - Filters emails by type="official" correctly
    - Returns empty list if no official emails
    - Preserves order from COManage
    """

    def test_filters_by_official_type_correctly(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that official_email_addresses filters by type correctly.

        When a person has multiple emails of different types, only
        emails with type="official" should be returned.
        """
        official1 = build_email_address(
            mail="official1@example.com", email_type="official", verified=True
        )
        personal = build_email_address(
            mail="personal@example.com", email_type="personal", verified=True
        )
        official2 = build_email_address(
            mail="official2@example.com", email_type="official", verified=False
        )
        work = build_email_address(
            mail="work@example.com", email_type="work", verified=True
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[official1, personal, official2, work],
        )

        person = RegistryPerson(coperson_msg)
        official_emails = person.official_email_addresses

        # Should return only official emails
        assert len(official_emails) == 2
        assert official1 in official_emails
        assert official2 in official_emails
        assert personal not in official_emails
        assert work not in official_emails

    def test_returns_empty_list_when_no_official_emails(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that empty list is returned when no official emails exist.

        When a person has emails but none are official, should return
        empty list.
        """
        personal = build_email_address(
            mail="personal@example.com", email_type="personal", verified=True
        )
        work = build_email_address(
            mail="work@example.com", email_type="work", verified=True
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[personal, work],
        )

        person = RegistryPerson(coperson_msg)
        official_emails = person.official_email_addresses

        # Should return empty list
        assert official_emails == []
        assert len(official_emails) == 0

    def test_returns_empty_list_when_no_emails_exist(
        self, build_co_person, build_coperson_message
    ):
        """Test that empty list is returned when person has no emails.

        When a person has no emails at all, should return empty list.
        """
        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=None,
        )

        person = RegistryPerson(coperson_msg)
        official_emails = person.official_email_addresses

        # Should return empty list
        assert official_emails == []

    def test_preserves_order_from_comanage(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that order is preserved from original COManage list.

        The filtered list should maintain the same order as the original
        email_addresses list.
        """
        official1 = build_email_address(
            mail="first@example.com", email_type="official", verified=True
        )
        official2 = build_email_address(
            mail="second@example.com", email_type="official", verified=False
        )
        official3 = build_email_address(
            mail="third@example.com", email_type="official", verified=True
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[official1, official2, official3],
        )

        person = RegistryPerson(coperson_msg)
        official_emails = person.official_email_addresses

        # Should preserve order
        assert len(official_emails) == 3
        assert official_emails[0] == official1
        assert official_emails[1] == official2
        assert official_emails[2] == official3

    def test_filters_mixed_types_preserving_order(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test filtering with mixed types preserves order of official emails.

        When official emails are interspersed with other types, the
        filtered list should maintain the relative order of official
        emails.
        """
        official1 = build_email_address(
            mail="official1@example.com", email_type="official"
        )
        personal = build_email_address(
            mail="personal@example.com", email_type="personal"
        )
        official2 = build_email_address(
            mail="official2@example.com", email_type="official"
        )
        work = build_email_address(mail="work@example.com", email_type="work")
        official3 = build_email_address(
            mail="official3@example.com", email_type="official"
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[official1, personal, official2, work, official3],
        )

        person = RegistryPerson(coperson_msg)
        official_emails = person.official_email_addresses

        # Should have 3 official emails in order
        assert len(official_emails) == 3
        assert official_emails[0] == official1
        assert official_emails[1] == official2
        assert official_emails[2] == official3


class TestVerifiedEmailAddressesProperty:
    """Tests for verified_email_addresses property.

    Tests Requirements 3.2, 3.4, 3.5:
    - Filters emails by verified=True correctly
    - Returns empty list if no verified emails
    - Preserves order from COManage
    """

    def test_filters_by_verified_status_correctly(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that verified_email_addresses filters by verified status.

        When a person has multiple emails with different verification
        statuses, only verified emails should be returned.
        """
        verified1 = build_email_address(
            mail="verified1@example.com", email_type="official", verified=True
        )
        unverified1 = build_email_address(
            mail="unverified1@example.com", email_type="personal", verified=False
        )
        verified2 = build_email_address(
            mail="verified2@example.com", email_type="work", verified=True
        )
        unverified2 = build_email_address(
            mail="unverified2@example.com", email_type="official", verified=False
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[verified1, unverified1, verified2, unverified2],
        )

        person = RegistryPerson(coperson_msg)
        verified_emails = person.verified_email_addresses

        # Should return only verified emails
        assert len(verified_emails) == 2
        assert verified1 in verified_emails
        assert verified2 in verified_emails
        assert unverified1 not in verified_emails
        assert unverified2 not in verified_emails

    def test_returns_empty_list_when_no_verified_emails(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that empty list is returned when no verified emails exist.

        When a person has emails but none are verified, should return
        empty list.
        """
        unverified1 = build_email_address(
            mail="unverified1@example.com", email_type="official", verified=False
        )
        unverified2 = build_email_address(
            mail="unverified2@example.com", email_type="personal", verified=False
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[unverified1, unverified2],
        )

        person = RegistryPerson(coperson_msg)
        verified_emails = person.verified_email_addresses

        # Should return empty list
        assert verified_emails == []
        assert len(verified_emails) == 0

    def test_returns_empty_list_when_no_emails_exist(
        self, build_co_person, build_coperson_message
    ):
        """Test that empty list is returned when person has no emails.

        When a person has no emails at all, should return empty list.
        """
        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=None,
        )

        person = RegistryPerson(coperson_msg)
        verified_emails = person.verified_email_addresses

        # Should return empty list
        assert verified_emails == []

    def test_preserves_order_from_comanage(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that order is preserved from original COManage list.

        The filtered list should maintain the same order as the original
        email_addresses list.
        """
        verified1 = build_email_address(
            mail="first@example.com", email_type="official", verified=True
        )
        verified2 = build_email_address(
            mail="second@example.com", email_type="personal", verified=True
        )
        verified3 = build_email_address(
            mail="third@example.com", email_type="work", verified=True
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[verified1, verified2, verified3],
        )

        person = RegistryPerson(coperson_msg)
        verified_emails = person.verified_email_addresses

        # Should preserve order
        assert len(verified_emails) == 3
        assert verified_emails[0] == verified1
        assert verified_emails[1] == verified2
        assert verified_emails[2] == verified3

    def test_filters_mixed_verification_preserving_order(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test filtering with mixed verification preserves order.

        When verified emails are interspersed with unverified emails,
        the filtered list should maintain the relative order of verified
        emails.
        """
        verified1 = build_email_address(
            mail="verified1@example.com", email_type="official", verified=True
        )
        unverified1 = build_email_address(
            mail="unverified1@example.com", email_type="personal", verified=False
        )
        verified2 = build_email_address(
            mail="verified2@example.com", email_type="work", verified=True
        )
        unverified2 = build_email_address(
            mail="unverified2@example.com", email_type="official", verified=False
        )
        verified3 = build_email_address(
            mail="verified3@example.com", email_type="personal", verified=True
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[verified1, unverified1, verified2, unverified2, verified3],
        )

        person = RegistryPerson(coperson_msg)
        verified_emails = person.verified_email_addresses

        # Should have 3 verified emails in order
        assert len(verified_emails) == 3
        assert verified_emails[0] == verified1
        assert verified_emails[1] == verified2
        assert verified_emails[2] == verified3

    def test_verified_includes_all_types(
        self, build_email_address, build_co_person, build_coperson_message
    ):
        """Test that verified filter works across all email types.

        Verified emails should be returned regardless of their type
        (official, personal, work, etc.).
        """
        verified_official = build_email_address(
            mail="official@example.com", email_type="official", verified=True
        )
        verified_personal = build_email_address(
            mail="personal@example.com", email_type="personal", verified=True
        )
        verified_work = build_email_address(
            mail="work@example.com", email_type="work", verified=True
        )
        unverified_official = build_email_address(
            mail="unverified@example.com", email_type="official", verified=False
        )

        coperson_msg = build_coperson_message(
            co_person=build_co_person(),
            email_addresses=[
                verified_official,
                verified_personal,
                verified_work,
                unverified_official,
            ],
        )

        person = RegistryPerson(coperson_msg)
        verified_emails = person.verified_email_addresses

        # Should return all verified emails regardless of type
        assert len(verified_emails) == 3
        assert verified_official in verified_emails
        assert verified_personal in verified_emails
        assert verified_work in verified_emails
        assert unverified_official not in verified_emails
