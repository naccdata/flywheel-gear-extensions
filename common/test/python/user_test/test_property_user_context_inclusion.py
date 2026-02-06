"""Property test for user context inclusion.

**Feature: automated-error-handling, Property 2: User Context Inclusion**
**Validates: Requirements 1.4**
"""

from hypothesis import given, settings
from test_mocks.strategies import error_event_strategy, user_context_strategy
from users.event_models import UserContext


@given(error_event=error_event_strategy())
@settings(max_examples=100)
def test_user_context_inclusion_in_error_events(error_event):
    """Property test: Error events include all available user context
    information.

    **Feature: automated-error-handling, Property 2: User Context Inclusion**
    **Validates: Requirements 1.4**

    For any captured error event, the system should include all available user context
    information (email, name, center, registry ID) with each captured event.
    """
    # Assert - Error event should have user_context
    assert hasattr(error_event, "user_context"), "Error event should have user_context"
    assert error_event.user_context is not None, "User context should not be None"
    assert isinstance(error_event.user_context, UserContext), (
        "User context should be UserContext instance"
    )

    # Assert - User context should have email (required field)
    assert hasattr(error_event.user_context, "email"), (
        "User context should have email field"
    )
    assert error_event.user_context.email is not None, (
        "User context email should not be None"
    )
    assert isinstance(error_event.user_context.email, str), (
        "User context email should be a string"
    )
    assert len(error_event.user_context.email) > 0, (
        "User context email should not be empty"
    )
    assert "@" in error_event.user_context.email, (
        "User context email should be a valid email format"
    )

    # Assert - User context should have all optional fields defined (even if None)
    assert hasattr(error_event.user_context, "name"), (
        "User context should have name field"
    )
    assert hasattr(error_event.user_context, "center_id"), (
        "User context should have center_id field"
    )
    assert hasattr(error_event.user_context, "registry_id"), (
        "User context should have registry_id field"
    )
    assert hasattr(error_event.user_context, "auth_email"), (
        "User context should have auth_email field"
    )

    # Assert - When optional fields are present, they should have valid values
    if error_event.user_context.name is not None:
        assert isinstance(error_event.user_context.name, str), "Name should be a string"
        assert len(error_event.user_context.name) > 0, "Name should not be empty"
        assert (
            " " in error_event.user_context.name
            or error_event.user_context.name == "Unknown"
        ), "Name should contain first and last name separated by space"

    if error_event.user_context.center_id is not None:
        assert isinstance(error_event.user_context.center_id, int), (
            "Center ID should be integer"
        )
        assert error_event.user_context.center_id > 0, "Center ID should be positive"

    if error_event.user_context.registry_id is not None:
        assert isinstance(error_event.user_context.registry_id, str), (
            "Registry ID should be string"
        )
        assert len(error_event.user_context.registry_id) > 0, (
            "Registry ID should not be empty"
        )

    if error_event.user_context.auth_email is not None:
        assert isinstance(error_event.user_context.auth_email, str), (
            "Auth email should be string"
        )
        assert len(error_event.user_context.auth_email) > 0, (
            "Auth email should not be empty"
        )
        assert "@" in error_event.user_context.auth_email, (
            "Auth email should be valid email format"
        )

    # Assert - User context should be serializable (can be converted to dict)
    try:
        context_dict = error_event.user_context.model_dump()
        assert isinstance(context_dict, dict), (
            "User context should be serializable to dict"
        )
        assert "email" in context_dict, "Serialized context should contain email"
        assert context_dict["email"] == error_event.user_context.email, (
            "Serialized email should match"
        )
    except Exception as e:
        raise AssertionError(f"User context should be serializable: {e}") from e


@given(user_context=user_context_strategy())
@settings(max_examples=100)
def test_user_context_preserves_all_available_information(user_context):
    """Property test: UserContext preserves all available information when
    created.

    **Feature: automated-error-handling, Property 2: User Context Inclusion**
    **Validates: Requirements 1.4**

    For any UserContext created with available information, all provided fields
    should be preserved and accessible.
    """
    # Assert - Required email field is always present and valid
    assert hasattr(user_context, "email"), "UserContext should have email field"
    assert user_context.email is not None, "UserContext email should not be None"
    assert isinstance(user_context.email, str), "UserContext email should be string"
    assert len(user_context.email) > 0, "UserContext email should not be empty"
    assert "@" in user_context.email, "UserContext email should be valid email format"

    # Assert - All optional fields are accessible (even if None)
    assert hasattr(user_context, "name"), "UserContext should have name field"
    assert hasattr(user_context, "center_id"), "UserContext should have center_id field"
    assert hasattr(user_context, "registry_id"), (
        "UserContext should have registry_id field"
    )
    assert hasattr(user_context, "auth_email"), (
        "UserContext should have auth_email field"
    )

    # Assert - When fields are provided, they maintain their values and types
    if user_context.name is not None:
        assert isinstance(user_context.name, str), "Name should be a string"
        assert len(user_context.name) > 0, "Name should not be empty"

    if user_context.center_id is not None:
        assert isinstance(user_context.center_id, int), "Center ID should be integer"
        assert user_context.center_id > 0, "Center ID should be positive"

    if user_context.registry_id is not None:
        assert isinstance(user_context.registry_id, str), "Registry ID should be string"
        assert len(user_context.registry_id) > 0, "Registry ID should not be empty"

    if user_context.auth_email is not None:
        assert isinstance(user_context.auth_email, str), "Auth email should be string"
        assert len(user_context.auth_email) > 0, "Auth email should not be empty"
        assert "@" in user_context.auth_email, "Auth email should be valid email format"

    # Assert - UserContext can be serialized and deserialized without loss
    try:
        # Serialize to dict
        context_dict = user_context.model_dump()
        assert isinstance(context_dict, dict), "UserContext should serialize to dict"

        # Verify all fields are in serialized form
        assert "email" in context_dict, "Serialized context should contain email"
        assert "name" in context_dict, "Serialized context should contain name"
        assert "center_id" in context_dict, (
            "Serialized context should contain center_id"
        )
        assert "registry_id" in context_dict, (
            "Serialized context should contain registry_id"
        )
        assert "auth_email" in context_dict, (
            "Serialized context should contain auth_email"
        )

        # Verify values match
        assert context_dict["email"] == user_context.email, (
            "Serialized email should match"
        )

        # Deserialize back to UserContext
        reconstructed = UserContext(**context_dict)
        assert reconstructed.email == user_context.email, (
            "Reconstructed email should match"
        )
        assert reconstructed.center_id == user_context.center_id, (
            "Reconstructed center_id should match"
        )
        assert reconstructed.registry_id == user_context.registry_id, (
            "Reconstructed registry_id should match"
        )
        assert reconstructed.auth_email == user_context.auth_email, (
            "Reconstructed auth_email should match"
        )

        # Handle name comparison (now strings with default)
        assert reconstructed.name is not None, (
            "Reconstructed name should not be None (has default 'Unknown')"
        )
        assert reconstructed.name == user_context.name, (
            "Reconstructed name should match"
        )

    except Exception as e:
        raise AssertionError(
            f"UserContext should be serializable and deserializable: {e}"
        ) from e


@given(user_context=user_context_strategy())
@settings(max_examples=100)
def test_user_context_from_user_entry_preserves_information(user_context):
    """Property test: UserContext.from_user_entry preserves available
    information.

    **Feature: automated-error-handling, Property 2: User Context Inclusion**
    **Validates: Requirements 1.4**

    For any user entry, UserContext.from_user_entry should preserve all available
    user information from the entry.
    """
    from users.user_entry import ActiveUserEntry, PersonName

    # Create a mock user entry with the same information as user_context
    # Note: We're testing the preservation of information, so we create an entry
    # with known values and verify they're preserved in the UserContext

    # ActiveUserEntry requires a PersonName, so create one from user_context.name
    if user_context.name is not None:
        # Parse the string name back into first and last name
        name_parts = user_context.name.split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""
        entry_name = PersonName(first_name=first_name, last_name=last_name)
    else:
        entry_name = PersonName(first_name="Test", last_name="User")

    user_entry = ActiveUserEntry(
        name=entry_name,
        email=user_context.email,
        auth_email=user_context.auth_email,
        active=True,
        approved=True,
        org_name="Test Organization",
        adcid=user_context.center_id or 1,  # ActiveUserEntry requires adcid
        authorizations=[],
    )

    # Create UserContext from the user entry
    created_context = UserContext.from_user_entry(user_entry)

    # Assert - All available information is preserved
    assert created_context.email == user_entry.email, (
        "Email should be preserved from user entry"
    )
    assert created_context.auth_email == user_entry.auth_email, (
        "Auth email should be preserved from user entry"
    )

    # Name should be preserved - UserEntry always has a name
    assert created_context.name is not None, "Name should be preserved from user entry"
    expected_name = f"{user_entry.name.first_name} {user_entry.name.last_name}".strip()
    assert created_context.name == expected_name, (
        "Name should be preserved as full name string"
    )

    # If the original user_context had a name, it should match exactly
    if user_context.name is not None:
        assert created_context.name == user_context.name, (
            "Original name should be preserved"
        )

    # Assert - UserContext has all required fields
    assert hasattr(created_context, "email"), "Created context should have email field"
    assert hasattr(created_context, "name"), "Created context should have name field"
    assert hasattr(created_context, "center_id"), (
        "Created context should have center_id field"
    )
    assert hasattr(created_context, "registry_id"), (
        "Created context should have registry_id field"
    )
    assert hasattr(created_context, "auth_email"), (
        "Created context should have auth_email field"
    )

    # Assert - Required email is valid
    assert created_context.email is not None, "Created context email should not be None"
    assert isinstance(created_context.email, str), (
        "Created context email should be string"
    )
    assert len(created_context.email) > 0, "Created context email should not be empty"
    assert "@" in created_context.email, (
        "Created context email should be valid email format"
    )
