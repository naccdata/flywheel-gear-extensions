"""Tests for user directory."""

import yaml
from users.authorizations import Authorizations
from users.nacc_directory import ActiveUserEntry, PersonName, UserEntry, UserEntryList


# pylint: disable=(no-self-use,too-few-public-methods)
class TestUserEntry:
    """Tests for UserEntry."""

    def test_inactive(self):
        """Tests for creating inactive objects."""
        entry = UserEntry(
            name=PersonName(first_name="ooly", last_name="puppy"),
            email="ools@that.org",
            auth_email="ools@that.org",
            active=False,
        )
        entry2 = UserEntry.create_from_record(
            {
                "contact_company_name": "the center",
                "adresearchctr": "0",
                "firstname": "ooly",
                "lastname": "puppy",
                "email": "ools@that.org",
                "fw_email": "ools@that.org",
                "flywheel_access_activities": "a,c,d,e",
                "nacc_data_platform_access_information_complete": "2",
                "archive_contact": "1",
            }
        )
        assert entry == entry2
        entry_yaml = yaml.safe_dump(entry.as_dict())
        entry_object = yaml.safe_load(entry_yaml)
        print(entry_object)
        entry3 = UserEntry.create(entry_object)
        assert entry == entry3

    def test_active(self):
        """Tests around creating objects."""
        entry = ActiveUserEntry(
            org_name="the center",
            adcid=0,
            name=PersonName(first_name="chip", last_name="puppy"),
            email="chip@theorg.org",
            authorizations=Authorizations(
                study_id="adrc",
                submit=["form", "enrollment"],
                audit_data=True,
                approve_data=True,
                view_reports=True,
            ),
            active=True,
            auth_email="chip_auth@theorg.org",
        )

        assert entry.authorizations.audit_data

        # assumes study_id is adrc
        entry2 = UserEntry.create_from_record(
            {
                "contact_company_name": "the center",
                "adresearchctr": "0",
                "firstname": "chip",
                "lastname": "puppy",
                "email": "chip@theorg.org",
                "fw_email": "chip_auth@theorg.org",
                "flywheel_access_activities": "a,c,d,e",
                "nacc_data_platform_access_information_complete": "2",
                "archive_contact": "0",
            }
        )
        assert entry == entry2

        entry_yaml = yaml.safe_dump(entry.as_dict())
        entry_object = yaml.safe_load(entry_yaml)
        print(entry_object)
        entry3 = UserEntry.create(entry_object)
        assert entry == entry3

    def test_list_serialization(self):
        user_list = UserEntryList([])

        entry1 = UserEntry(
            name=PersonName(first_name="ooly", last_name="puppy"),
            email="ools@that.org",
            auth_email="ools@that.org",
            active=False,
        )
        user_list.append(entry1)
        entry2 = ActiveUserEntry(
            org_name="the center",
            adcid=0,
            name=PersonName(first_name="chip", last_name="puppy"),
            email="chip@theorg.org",
            authorizations=Authorizations(
                study_id="dummy",
                submit=["form", "enrollment"],
                audit_data=True,
                approve_data=True,
                view_reports=True,
            ),
            active=True,
            auth_email="chip_auth@theorg.org",
        )
        user_list.append(entry2)
        assert user_list.model_dump(serialize_as_any=True) == [
            entry1.model_dump(serialize_as_any=True),
            entry2.model_dump(serialize_as_any=True),
        ]
