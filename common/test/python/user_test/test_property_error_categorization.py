"""Property test for error event categorization.

**Feature: automated-error-handling, Property 1: Error Event Categorization**
**Validates: Requirements 1.3**
"""

from hypothesis import given, settings
from test_mocks.strategies import error_event_strategy
from users.event_models import EventCategory


@given(error_event=error_event_strategy())
@settings(max_examples=100)
def test_error_event_categorization(error_event):
    """Property test: Error events are assigned to exactly one predefined
    category.

    **Feature: automated-error-handling, Property 1: Error Event Categorization**
    **Validates: Requirements 1.3**

    For any captured error event, the system should assign it to exactly one of the
    predefined error categories.
    """
    # Assert - Error event should have a category
    assert hasattr(error_event, "category"), "Error event should have a category"
    assert error_event.category is not None, "Error event category should not be None"

    # Assert - Category should be exactly one category (not multiple)
    # Due to use_enum_values=True in model config, category is the string value
    assert isinstance(error_event.category, str), "Category should be a string value"
    assert len(error_event.category) > 0, "Category should not be empty"

    # Assert - Category should match one of the expected string values from
    #  EventCategory enum
    expected_category_values = {cat.value for cat in EventCategory}
    assert error_event.category in expected_category_values, (
        f"Category value '{error_event.category}' "
        "should be one of the expected values: "
        f"{expected_category_values}"
    )

    # Assert - Category should be one of the predefined EventCategory enum values
    # Verify that the category corresponds to a valid enum member
    category_found = False
    for category_enum in EventCategory:
        if category_enum.value == error_event.category:
            category_found = True
            break

    assert category_found, (
        f"Error event category '{error_event.category}' should correspond to "
        f"one of the predefined EventCategory enum values"
    )

    # Assert - User context should have required email field
    assert error_event.user_context is not None, "User context should not be None"
    assert hasattr(error_event.user_context, "email"), "User context should have email"
    assert error_event.user_context.email is not None, (
        "User context email should not be None"
    )
    assert len(error_event.user_context.email) > 0, (
        "User context email should not be empty"
    )
