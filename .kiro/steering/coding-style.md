# Coding Style Guidelines

## Python Import Organization

**CRITICAL**: All imports must be at the top of Python files, immediately after the module docstring (if present).

```python
# ✅ Correct
"""Module docstring."""

import os
from typing import List

import flywheel
from pydantic import BaseModel

def my_function():
    pass
```

```python
# ❌ Incorrect - imports scattered throughout file
def my_function():
    import os  # Don't do this
    pass

import flywheel  # Don't do this after function definitions
```

## Gear Architecture

### File Organization

Gears should follow this structure:
- `run.py` - Gear interface and Flywheel context management
- `main.py` - Core business logic and execution
- `processor.py` - (Optional) Complex business logic if needed for organization

### run.py Responsibilities

**Keep the gear context object in run.py**

```python
# run.py
import flywheel

from main import execute_gear

def main():
    context = flywheel.GearContext()
    
    # Open files here
    input_file = context.get_input_path('input_csv')
    
    # Load data or pass stream to main
    with open(input_file, 'r') as f:
        # Option 1: Load and pass data
        data = f.read()
        result = execute_gear(data, context.config)
        
        # Option 2: Pass stream
        result = execute_gear(f, context.config)
    
    # Handle outputs
    context.log.info(f"Result: {result}")
```

### main.py Responsibilities

**Core business logic without Flywheel dependencies**

```python
# main.py
from typing import TextIO, Dict, Any

def execute_gear(data_stream: TextIO, config: Dict[str, Any]) -> Any:
    """Execute the gear logic.
    
    Args:
        data_stream: Open file stream (not file path)
        config: Configuration dictionary (not individual simple types)
    
    Returns:
        Processing result
    """
    # Business logic here
    pass
```

### Code Smells to Avoid

**❌ Don't pass file paths and names to main.py**

```python
# Bad - passing file paths
def execute_gear(input_path: str, output_path: str):
    with open(input_path) as f:  # File handling in wrong place
        pass
```

**❌ Don't pass many simple type arguments**

```python
# Bad - too many simple arguments
def execute_gear(
    center_id: str,
    project_id: str, 
    user_name: str,
    is_active: bool,
    max_count: int
):
    pass
```

**✅ Do pass structured data**

```python
# Good - structured configuration
from pydantic import BaseModel

class GearConfig(BaseModel):
    center_id: str
    project_id: str
    user_name: str
    is_active: bool
    max_count: int

def execute_gear(config: GearConfig, data_stream: TextIO):
    pass
```

### processor.py (Optional)

Use `processor.py` only when business logic is complex enough to warrant separation from `main.py`. This is optional and should be used judiciously.

```python
# processor.py (when needed)
class DataProcessor:
    """Complex processing logic."""
    
    def process(self, data):
        # Complex business logic
        pass
```

## Design Principles

### Dependency Injection over Flag Parameters

**Prefer dependency injection over boolean flags for configurable behavior.**

When designing classes that need configurable behavior, use dependency injection with strategy patterns rather than boolean flag parameters.

**❌ Avoid:**

```python
class MyProcessor:
    def __init__(self, data: List[str], use_fast_mode: bool = False):
        self.data = data
        self.use_fast_mode = use_fast_mode
    
    def process(self):
        if self.use_fast_mode:
            return self._fast_process()
        else:
            return self._slow_process()
```

**✅ Prefer:**

```python
ProcessingStrategy = Callable[[List[str]], Any]

def fast_strategy(data: List[str]) -> Any:
    # Fast processing implementation
    pass

def thorough_strategy(data: List[str]) -> Any:
    # Thorough processing implementation
    pass

class MyProcessor:
    def __init__(self, data: List[str], strategy: ProcessingStrategy = thorough_strategy):
        self.data = data
        self.strategy = strategy
    
    def process(self):
        return self.strategy(self.data)
```

**Benefits:**

- **Extensibility**: Easy to add new strategies without modifying existing code
- **Testability**: Each strategy can be tested independently
- **Single Responsibility**: Each strategy focuses on one approach
- **Open/Closed Principle**: Open for extension, closed for modification
- **Clear Intent**: Strategy names are more descriptive than boolean flags

**Example in Codebase:**
See `AggregateCSVVisitor` in `common/src/python/inputs/csv_reader.py` which uses `strategy_builder` parameter with `short_circuit_strategy` and `visit_all_strategy` functions instead of a `short_circuit: bool` flag.

## Key Principles

1. **Separation of Concerns**: Keep Flywheel-specific code in `run.py`, business logic in `main.py`
2. **Testability**: `main.py` should be testable without Flywheel context
3. **Type Safety**: Use structured types (Pydantic models, dataclasses) over simple types
4. **Resource Management**: Handle file I/O in `run.py`, pass streams or loaded data to `main.py`
5. **Import Discipline**: All imports at the top, no scattered imports throughout the file
6. **Dependency Injection**: Use strategy patterns over boolean flags for configurable behavior

## Testing Guidelines

### Test Against Public Interfaces

**CRITICAL**: Tests should be robust to implementation changes within fixed interfaces.

**❌ Don't test private members**

```python
# Bad - fragile test tied to implementation
def test_processor_internal_state():
    processor = DataProcessor()
    processor.process(data)
    assert processor._internal_cache == expected  # Testing private member
    assert processor._step_count == 3  # Fragile
```

**✅ Do test public behavior**

```python
# Good - tests observable behavior through public interface
def test_processor_output():
    processor = DataProcessor()
    result = processor.process(data)
    assert result == expected_output  # Tests what matters
    assert processor.is_complete()  # Public interface
```

### Principles for Robust Tests

1. **Test behavior, not implementation**: Focus on what the code does, not how it does it
2. **Test through public APIs**: Only call public methods and check public attributes
3. **Avoid testing internal state**: Private members (prefixed with `_`) should not be tested directly
4. **Test contracts, not details**: Verify inputs produce expected outputs, not intermediate steps

### Mock Strategy

**Mocks should be generalized and reusable across tests.**

**❌ Don't create one-off mocks in each test**

```python
# Bad - duplicated mock setup in every test
def test_feature_a():
    mock_client = Mock()
    mock_client.get_project.return_value = Mock(id='123', label='test')
    mock_client.get_user.return_value = Mock(id='user1', email='test@example.com')
    # test code...

def test_feature_b():
    mock_client = Mock()
    mock_client.get_project.return_value = Mock(id='123', label='test')  # Duplicated
    mock_client.get_user.return_value = Mock(id='user1', email='test@example.com')  # Duplicated
    # test code...
```

**✅ Do create reusable mock fixtures**

```python
# Good - centralized, reusable mocks
# conftest.py or test utilities module
import pytest
from typing import Optional

@pytest.fixture
def mock_flywheel_client():
    """Reusable Flywheel client mock with sensible defaults."""
    client = Mock()
    client.get_project.return_value = create_mock_project()
    client.get_user.return_value = create_mock_user()
    return client

def create_mock_project(
    project_id: str = '123',
    label: str = 'test-project',
    **kwargs
) -> Mock:
    """Factory for creating mock projects with defaults."""
    project = Mock()
    project.id = project_id
    project.label = label
    for key, value in kwargs.items():
        setattr(project, key, value)
    return project

def create_mock_user(
    user_id: str = 'user1',
    email: str = 'test@example.com',
    **kwargs
) -> Mock:
    """Factory for creating mock users with defaults."""
    user = Mock()
    user.id = user_id
    user.email = email
    for key, value in kwargs.items():
        setattr(user, key, value)
    return user

# In tests
def test_feature_a(mock_flywheel_client):
    result = my_function(mock_flywheel_client)
    assert result.success

def test_feature_b_with_custom_project(mock_flywheel_client):
    # Override defaults when needed
    mock_flywheel_client.get_project.return_value = create_mock_project(
        project_id='custom-id',
        label='custom-label'
    )
    result = my_function(mock_flywheel_client)
    assert result.project_id == 'custom-id'
```

### Mock Organization Strategies

1. **Centralize mock factories**: Create factory functions for common mock objects
2. **Use pytest fixtures**: Share mock setup across tests with fixtures
3. **Provide sensible defaults**: Mocks should work out-of-the-box for common cases
4. **Allow customization**: Factory functions should accept kwargs for test-specific needs
5. **Keep mocks simple**: Only mock what's necessary for the test

### Refactoring-Resistant Test Patterns

**Strategy 1: Test at higher abstraction levels**

```python
# Instead of testing each step
def test_data_processing_steps():  # Fragile
    processor = DataProcessor()
    processor._validate_input(data)  # Private method
    processor._transform_data(data)  # Private method
    processor._save_results(data)  # Private method

# Test the complete operation
def test_data_processing_end_to_end():  # Robust
    processor = DataProcessor()
    result = processor.process(data)
    assert result.is_valid
    assert result.output_path.exists()
```

**Strategy 2: Use test data builders**

```python
# Create reusable builders for test data
class ProjectBuilder:
    def __init__(self):
        self._id = 'default-id'
        self._label = 'default-label'
        self._users = []
    
    def with_id(self, project_id: str):
        self._id = project_id
        return self
    
    def with_label(self, label: str):
        self._label = label
        return self
    
    def with_users(self, users: list):
        self._users = users
        return self
    
    def build(self):
        return create_mock_project(
            project_id=self._id,
            label=self._label,
            users=self._users
        )

# Usage in tests
def test_with_custom_project():
    project = ProjectBuilder().with_id('custom').with_label('test').build()
    result = process_project(project)
    assert result.success
```

**Strategy 3: Focus on integration points**

```python
# Test the boundaries between components
def test_gear_integration():
    """Test that run.py correctly calls main.py with proper data."""
    # Mock only external dependencies (Flywheel)
    mock_context = create_mock_gear_context()
    
    # Test the integration, not internal details
    result = run_gear(mock_context)
    
    # Verify observable outcomes
    assert result.exit_code == 0
    assert mock_context.log.info.called
```

### When Tests Break During Refactoring

If tests frequently break during refactoring, ask:

1. **Am I testing implementation details?** → Test behavior instead
2. **Are my mocks too specific?** → Use factories with defaults
3. **Am I testing private methods?** → Test through public interface
4. **Are tests coupled to structure?** → Test at higher abstraction level
5. **Do I have duplicate mock setup?** → Centralize in fixtures/factories

### Additional Strategies

**Use property-based testing for complex logic**

```python
from hypothesis import given, strategies as st

@given(st.lists(st.integers()))
def test_sorting_properties(input_list):
    """Test properties that should always hold, regardless of implementation."""
    result = my_sort_function(input_list)
    
    # Properties that should always be true
    assert len(result) == len(input_list)
    assert set(result) == set(input_list)
    assert all(result[i] <= result[i+1] for i in range(len(result)-1))
```

**Separate unit tests from integration tests**

```python
# Unit tests: Fast, isolated, test single components
# test/unit/test_processor.py
def test_processor_logic():
    processor = DataProcessor()
    result = processor.process(simple_data)
    assert result == expected

# Integration tests: Test components working together
# test/integration/test_gear_workflow.py
def test_complete_gear_workflow(flywheel_client):
    result = run_complete_workflow(flywheel_client, test_data)
    assert result.success
```
