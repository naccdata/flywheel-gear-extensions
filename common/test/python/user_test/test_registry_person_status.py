"""Unit tests for RegistryPerson status functionality.

Tests focus on is_active and is_claimed methods which check the status
of a person in the registry.
"""

from users.user_registry import RegistryPerson


class TestIsClaimedMethod:
    """Tests for is_claimed method (current behavior).

    Tests Requirement 2.6:
    - Returns True when active AND has email AND has oidcsub
    - Returns False without oidcsub identifier
    - Returns False when inactive
    - Returns False without email
    """

    def test_returns_true_when_active_with_email_and_oidcsub(
        self,
        build_email_address,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that is_claimed returns True when all conditions are met.

        When a person is active, has an email, and has an oidcsub
        identifier, is_claimed should return True.
        """
        # Create active person with email and oidcsub
        email = build_email_address(mail="user@example.com")
        oidcsub = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        coperson = build_co_person(status="A")

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=[email],
            identifiers=[oidcsub],
        )

        person = RegistryPerson(coperson_msg)

        # Should be claimed
        assert person.is_claimed() is True

    def test_returns_false_without_oidcsub_identifier(
        self,
        build_email_address,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that is_claimed returns False without oidcsub identifier.

        When a person is active and has an email but no oidcsub
        identifier, is_claimed should return False.
        """
        # Create active person with email but no oidcsub
        email = build_email_address(mail="user@example.com")
        naccid = build_identifier(
            identifier="NACC123456",
            identifier_type="naccid",
            status="A",
        )
        coperson = build_co_person(status="A")

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=[email],
            identifiers=[naccid],  # Only naccid, no oidcsub
        )

        person = RegistryPerson(coperson_msg)

        # Should not be claimed without oidcsub
        assert person.is_claimed() is False

    def test_returns_false_when_inactive(
        self,
        build_email_address,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that is_claimed returns False when person is inactive.

        When a person has an email and oidcsub but is not active,
        is_claimed should return False.
        """
        # Create inactive person with email and oidcsub
        email = build_email_address(mail="user@example.com")
        oidcsub = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        coperson = build_co_person(status="D")  # Inactive status

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=[email],
            identifiers=[oidcsub],
        )

        person = RegistryPerson(coperson_msg)

        # Should not be claimed when inactive
        assert person.is_claimed() is False

    def test_returns_false_without_email(
        self,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that is_claimed returns False without email.

        When a person is active and has oidcsub but no email, is_claimed
        should return False.
        """
        # Create active person with oidcsub but no email
        oidcsub = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        coperson = build_co_person(status="A")

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=None,  # No email
            identifiers=[oidcsub],
        )

        person = RegistryPerson(coperson_msg)

        # Should not be claimed without email
        assert person.is_claimed() is False

    def test_returns_false_with_empty_email_list(
        self,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that is_claimed returns False with empty email list.

        When a person has an empty email list (not None, but []),
        is_claimed should return False.
        """
        # Create active person with oidcsub but empty email list
        oidcsub = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        coperson = build_co_person(status="A")

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=[],  # Empty list
            identifiers=[oidcsub],
        )

        person = RegistryPerson(coperson_msg)

        # Should not be claimed with empty email list
        assert person.is_claimed() is False

    def test_requires_cilogon_oidcsub(
        self,
        build_email_address,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that is_claimed requires oidcsub from cilogon.org.

        When a person has an oidcsub identifier that doesn't start with
        http://cilogon.org, is_claimed should return False.
        """
        # Create active person with email and non-cilogon oidcsub
        email = build_email_address(mail="user@example.com")
        oidcsub = build_identifier(
            identifier="http://other.org/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        coperson = build_co_person(status="A")

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=[email],
            identifiers=[oidcsub],
        )

        person = RegistryPerson(coperson_msg)

        # Should not be claimed without cilogon.org oidcsub
        assert person.is_claimed() is False

    def test_multiple_identifiers_with_valid_oidcsub(
        self,
        build_email_address,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that is_claimed works with multiple identifiers.

        When a person has multiple identifiers including a valid
        oidcsub, is_claimed should return True.
        """
        # Create active person with email and multiple identifiers
        email = build_email_address(mail="user@example.com")
        naccid = build_identifier(
            identifier="NACC123456",
            identifier_type="naccid",
            status="A",
        )
        oidcsub = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        eppn = build_identifier(
            identifier="user@institution.edu",
            identifier_type="eppn",
            status="A",
        )
        coperson = build_co_person(status="A")

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=[email],
            identifiers=[naccid, oidcsub, eppn],
        )

        person = RegistryPerson(coperson_msg)

        # Should be claimed with valid oidcsub among other identifiers
        assert person.is_claimed() is True

    def test_suspended_status_is_not_claimed(
        self,
        build_email_address,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that suspended status is not considered claimed.

        When a person has status "S" (suspended), is_claimed should
        return False even with email and oidcsub.
        """
        # Create suspended person with email and oidcsub
        email = build_email_address(mail="user@example.com")
        oidcsub = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        coperson = build_co_person(status="S")  # Suspended

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=[email],
            identifiers=[oidcsub],
        )

        person = RegistryPerson(coperson_msg)

        # Should not be claimed when suspended
        assert person.is_claimed() is False

    def test_no_coperson_is_not_claimed(
        self,
        build_email_address,
        build_identifier,
        build_coperson_message,
    ):
        """Test that missing CoPerson means not claimed.

        When a CoPersonMessage has no CoPerson object, is_claimed should
        return False.
        """
        # Create message with email and oidcsub but no CoPerson
        email = build_email_address(mail="user@example.com")
        oidcsub = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )

        coperson_msg = build_coperson_message(
            co_person=None,  # No CoPerson
            email_addresses=[email],
            identifiers=[oidcsub],
        )

        person = RegistryPerson(coperson_msg)

        # Should not be claimed without CoPerson
        assert person.is_claimed() is False

    def test_multiple_emails_with_valid_oidcsub(
        self,
        build_email_address,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that is_claimed works with multiple emails.

        When a person has multiple emails and a valid oidcsub,
        is_claimed should return True.
        """
        # Create active person with multiple emails and oidcsub
        email1 = build_email_address(mail="user1@example.com")
        email2 = build_email_address(mail="user2@example.com")
        email3 = build_email_address(mail="user3@example.com")
        oidcsub = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        coperson = build_co_person(status="A")

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=[email1, email2, email3],
            identifiers=[oidcsub],
        )

        person = RegistryPerson(coperson_msg)

        # Should be claimed with any email present
        assert person.is_claimed() is True


class TestIsClaimedWithVerifiedEmailRequirement:
    """Tests for updated is_claimed method requiring verified email.

    Tests Requirement 1.10:
    - Returns False without verified email (even with unverified email)
    - Returns True with verified email AND oidcsub AND active
    - Tests all combinations of conditions
    """

    def test_returns_false_with_unverified_email(
        self,
        build_email_address,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that is_claimed returns False with only unverified email.

        When a person is active and has oidcsub but only unverified
        emails, is_claimed should return False.
        """
        # Create active person with unverified email and oidcsub
        email = build_email_address(mail="user@example.com", verified=False)
        oidcsub = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        coperson = build_co_person(status="A")

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=[email],
            identifiers=[oidcsub],
        )

        person = RegistryPerson(coperson_msg)

        # Should not be claimed without verified email
        assert person.is_claimed() is False

    def test_returns_true_with_verified_email_and_oidcsub_and_active(
        self,
        build_email_address,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that is_claimed returns True with all conditions met.

        When a person is active, has verified email, and has oidcsub,
        is_claimed should return True.
        """
        # Create active person with verified email and oidcsub
        email = build_email_address(mail="user@example.com", verified=True)
        oidcsub = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        coperson = build_co_person(status="A")

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=[email],
            identifiers=[oidcsub],
        )

        person = RegistryPerson(coperson_msg)

        # Should be claimed with all conditions met
        assert person.is_claimed() is True

    def test_returns_false_with_mixed_emails_all_unverified(
        self,
        build_email_address,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that is_claimed returns False with multiple unverified emails.

        When a person has multiple emails but none are verified,
        is_claimed should return False.
        """
        # Create active person with multiple unverified emails and oidcsub
        email1 = build_email_address(mail="user1@example.com", verified=False)
        email2 = build_email_address(mail="user2@example.com", verified=False)
        email3 = build_email_address(mail="user3@example.com", verified=False)
        oidcsub = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        coperson = build_co_person(status="A")

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=[email1, email2, email3],
            identifiers=[oidcsub],
        )

        person = RegistryPerson(coperson_msg)

        # Should not be claimed without any verified email
        assert person.is_claimed() is False

    def test_returns_true_with_one_verified_among_unverified(
        self,
        build_email_address,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that is_claimed returns True with at least one verified email.

        When a person has multiple emails and at least one is verified,
        is_claimed should return True.
        """
        # Create active person with mixed verified/unverified emails and oidcsub
        email1 = build_email_address(mail="user1@example.com", verified=False)
        email2 = build_email_address(mail="user2@example.com", verified=True)
        email3 = build_email_address(mail="user3@example.com", verified=False)
        oidcsub = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        coperson = build_co_person(status="A")

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=[email1, email2, email3],
            identifiers=[oidcsub],
        )

        person = RegistryPerson(coperson_msg)

        # Should be claimed with at least one verified email
        assert person.is_claimed() is True

    def test_all_condition_combinations(
        self,
        build_email_address,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test all combinations of active, verified email, and oidcsub.

        This test verifies the truth table for is_claimed:
        - Active=True, VerifiedEmail=True, Oidcsub=True -> True
        - All other combinations -> False
        """
        # Test case 1: All conditions True -> claimed
        email_verified = build_email_address(mail="user@example.com", verified=True)
        oidcsub = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        coperson_active = build_co_person(status="A")

        msg1 = build_coperson_message(
            co_person=coperson_active,
            email_addresses=[email_verified],
            identifiers=[oidcsub],
        )
        assert RegistryPerson(msg1).is_claimed() is True

        # Test case 2: Active=False, VerifiedEmail=True, Oidcsub=True -> not claimed
        coperson_inactive = build_co_person(status="D")
        msg2 = build_coperson_message(
            co_person=coperson_inactive,
            email_addresses=[email_verified],
            identifiers=[oidcsub],
        )
        assert RegistryPerson(msg2).is_claimed() is False

        # Test case 3: Active=True, VerifiedEmail=False, Oidcsub=True -> not claimed
        email_unverified = build_email_address(mail="user@example.com", verified=False)
        msg3 = build_coperson_message(
            co_person=coperson_active,
            email_addresses=[email_unverified],
            identifiers=[oidcsub],
        )
        assert RegistryPerson(msg3).is_claimed() is False

        # Test case 4: Active=True, VerifiedEmail=True, Oidcsub=False -> not claimed
        naccid = build_identifier(
            identifier="NACC123456",
            identifier_type="naccid",
            status="A",
        )
        msg4 = build_coperson_message(
            co_person=coperson_active,
            email_addresses=[email_verified],
            identifiers=[naccid],  # No oidcsub
        )
        assert RegistryPerson(msg4).is_claimed() is False

        # Test case 5: Active=False, VerifiedEmail=False, Oidcsub=True -> not claimed
        msg5 = build_coperson_message(
            co_person=coperson_inactive,
            email_addresses=[email_unverified],
            identifiers=[oidcsub],
        )
        assert RegistryPerson(msg5).is_claimed() is False

        # Test case 6: Active=False, VerifiedEmail=True, Oidcsub=False -> not claimed
        msg6 = build_coperson_message(
            co_person=coperson_inactive,
            email_addresses=[email_verified],
            identifiers=[naccid],
        )
        assert RegistryPerson(msg6).is_claimed() is False

        # Test case 7: Active=True, VerifiedEmail=False, Oidcsub=False -> not claimed
        msg7 = build_coperson_message(
            co_person=coperson_active,
            email_addresses=[email_unverified],
            identifiers=[naccid],
        )
        assert RegistryPerson(msg7).is_claimed() is False

        # Test case 8: Active=False, VerifiedEmail=False, Oidcsub=False -> not claimed
        msg8 = build_coperson_message(
            co_person=coperson_inactive,
            email_addresses=[email_unverified],
            identifiers=[naccid],
        )
        assert RegistryPerson(msg8).is_claimed() is False

    def test_returns_false_with_empty_verified_email_list(
        self,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that is_claimed returns False when verified_email_addresses is
        empty.

        When a person has no verified emails (empty list), is_claimed
        should return False.
        """
        # Create active person with oidcsub but no emails
        oidcsub = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        coperson = build_co_person(status="A")

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=[],  # Empty list
            identifiers=[oidcsub],
        )

        person = RegistryPerson(coperson_msg)

        # Should not be claimed without verified emails
        assert person.is_claimed() is False

    def test_verified_email_with_multiple_oidcsub_identifiers(
        self,
        build_email_address,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that is_claimed works with multiple oidcsub identifiers.

        When a person has verified email and multiple oidcsub
        identifiers, is_claimed should return True.
        """
        # Create active person with verified email and multiple oidcsub
        email = build_email_address(mail="user@example.com", verified=True)
        oidcsub1 = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        oidcsub2 = build_identifier(
            identifier="http://cilogon.org/serverB/users/5678",
            identifier_type="oidcsub",
            status="A",
        )
        coperson = build_co_person(status="A")

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=[email],
            identifiers=[oidcsub1, oidcsub2],
        )

        person = RegistryPerson(coperson_msg)

        # Should be claimed with verified email and valid oidcsub
        assert person.is_claimed() is True

    def test_multiple_verified_emails_with_oidcsub(
        self,
        build_email_address,
        build_identifier,
        build_co_person,
        build_coperson_message,
    ):
        """Test that is_claimed works with multiple verified emails.

        When a person has multiple verified emails and oidcsub,
        is_claimed should return True.
        """
        # Create active person with multiple verified emails and oidcsub
        email1 = build_email_address(mail="user1@example.com", verified=True)
        email2 = build_email_address(mail="user2@example.com", verified=True)
        email3 = build_email_address(mail="user3@example.com", verified=True)
        oidcsub = build_identifier(
            identifier="http://cilogon.org/serverA/users/1234",
            identifier_type="oidcsub",
            status="A",
        )
        coperson = build_co_person(status="A")

        coperson_msg = build_coperson_message(
            co_person=coperson,
            email_addresses=[email1, email2, email3],
            identifiers=[oidcsub],
        )

        person = RegistryPerson(coperson_msg)

        # Should be claimed with verified emails
        assert person.is_claimed() is True
