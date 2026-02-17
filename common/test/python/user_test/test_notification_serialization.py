from users.event_notifications import ConsolidatedNotificationData


class TestNotificationSerialization:
    def test_serializes_to_expected_template_structure(self):
        """Test ConsolidatedNotificationData serializes to expected SES
        template structure.

        The AWS SES template expects:
        - Top-level fields: gear_name, execution_timestamp, total_errors, etc.
        - Individual category fields: unclaimed_records, bad_orcid_claims, etc.
        - Each error object must be FLAT (no nested user_context)
        """
        # Create notification data directly
        notification_data = ConsolidatedNotificationData(
            gear_name="test_gear",
            execution_timestamp="2024-01-27T10:30:00",
            total_events=2,
            events_by_category={"dummy": 2},
            event_summaries=["dummy summary 1", "dummy summary 2"],
            affected_users=["user1@example.com", "user2@example.com"],
            affected_users_count=2,
            category_details={
                "unclaimed_records": [
                    {
                        "email": "user1@example.com",
                        "name": "User One",
                        "message": "Test message",
                        "timestamp": "2024-01-27T10:25:00",
                    }
                ],
                "bad_orcid_claims": [
                    {
                        "email": "user2@example.com",
                        "name": "User Two",
                        "message": "Another test message",
                        "timestamp": "2024-01-27T10:26:00",
                    }
                ],
            },
        )

        # Serialize to dict as it would be sent to SES
        template_dict = notification_data.model_dump(exclude_none=True)

        # Verify top-level structure
        assert template_dict["gear_name"] == "test_gear"
        assert template_dict["execution_timestamp"] == "2024-01-27T10:30:00"
        assert template_dict["total_events"] == 2

        # Verify category fields exist with snake_case names
        assert "unclaimed_records" in template_dict
        assert "bad_orcid_claims" in template_dict

        # Verify error objects are flat (not nested)
        unclaimed_errors = template_dict["unclaimed_records"]
        assert len(unclaimed_errors) == 1
        assert unclaimed_errors[0]["email"] == "user1@example.com"
        assert unclaimed_errors[0]["name"] == "User One"
        assert unclaimed_errors[0]["message"] == "Test message"
        assert unclaimed_errors[0]["timestamp"] == "2024-01-27T10:25:00"
        assert "user_context" not in unclaimed_errors[0]  # Must be flat!

        bad_orcid_errors = template_dict["bad_orcid_claims"]
        assert len(bad_orcid_errors) == 1
        assert bad_orcid_errors[0]["email"] == "user2@example.com"
        assert bad_orcid_errors[0]["name"] == "User Two"
        assert bad_orcid_errors[0]["message"] == "Another test message"
        assert "user_context" not in bad_orcid_errors[0]  # Must be flat!
