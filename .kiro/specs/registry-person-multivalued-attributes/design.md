# Design Document: Registry Person Multivalued Attributes

## Overview

This design improves the RegistryPerson class to provide clearer semantics for email selection, better support for multivalued attributes, and comprehensive test coverage. The key improvements are:

1. **Explicit email priority logic**: Organizational → Official → Verified → Any
2. **New filtering methods**: Get emails by type, verification status
3. **Enhanced is_claimed validation**: Requires verified email in addition to oidcsub identifier
4. **Comprehensive test suite**: Unit tests covering all functionality
5. **Backward compatibility**: All existing methods and properties preserved

The design maintains the existing API while adding new capabilities, ensuring existing code continues to work without modification.

## Architecture

The RegistryPerson class remains a wrapper around COManage's CoPersonMessage object. The architecture follows these principles:

1. **Encapsulation**: Internal CoPersonMessage is private, accessed only through public methods
2. **Lazy evaluation**: No caching or preprocessing - properties compute values on demand
3. **Immutability**: RegistryPerson is read-only after construction
4. **Single responsibility**: RegistryPerson focuses on convenient access to person attributes

### Email Priority Strategy

The email selection strategy implements a clear priority hierarchy:

```
1. Organizational emails (from claimed OrgIdentity)
   ↓
2. Official emails (type="official")
   ↓
3. Verified emails (verified=True)
   ↓
4. Any email (first available)
   ↓
5. None (no emails exist)
```

This priority ensures we prefer:
- Emails from claimed organizational identities (most authoritative)
- Official emails designated by administrators
- Verified emails confirmed by users
- Any available email as last resort

## Components and Interfaces

### RegistryPerson Class

The RegistryPerson class provides the following public interface:

#### Factory Methods

```python
@classmethod
def create(cls, *, firstname: str, lastname: str, email: str, coid: int) -> "RegistryPerson":
    """Creates a RegistryPerson with name and email for testing/provisioning."""
```

#### Properties

```python
@property
def email_address(self) -> Optional[EmailAddress]:
    """Returns primary email using priority: organizational → official → verified → any."""

@property
def email_addresses(self) -> List[EmailAddress]:
    """Returns all email addresses."""

@property
def organization_email_addresses(self) -> List[EmailAddress]:
    """Returns emails from claimed organizational identity."""

@property
def official_email_addresses(self) -> List[EmailAddress]:
    """Returns all emails with type='official'."""

@property
def verified_email_addresses(self) -> List[EmailAddress]:
    """Returns all emails with verified=True."""

@property
def primary_name(self) -> Optional[str]:
    """Returns primary name as 'Given Family'."""

@property
def creation_date(self) -> Optional[datetime]:
    """Returns creation date from metadata."""
```

#### Methods

```python
def has_email(self, email: str) -> bool:
    """Checks if person has specific email address."""

def is_active(self) -> bool:
    """Checks if CoPerson status is 'A' (active)."""

def is_claimed(self) -> bool:
    """Checks if account is claimed (has oidcsub identifier AND verified email)."""

def identifiers(self, predicate: Callable[[Identifier], bool] = lambda x: True) -> List[Identifier]:
    """Returns identifiers matching predicate."""

def registry_id(self) -> Optional[str]:
    """Returns NACC registry ID (naccid identifier)."""

def as_coperson_message(self) -> CoPersonMessage:
    """Returns underlying CoPersonMessage object."""
```

### Email Filtering Implementation

The email filtering methods use list comprehensions to filter the email_addresses list:

```python
@property
def official_email_addresses(self) -> List[EmailAddress]:
    """Returns all official emails."""
    return [addr for addr in self.email_addresses if addr.type == "official"]

@property
def verified_email_addresses(self) -> List[EmailAddress]:
    """Returns all verified emails."""
    return [addr for addr in self.email_addresses if addr.verified]
```

### Enhanced is_claimed Logic

The `is_claimed()` method now validates both oidcsub identifier AND verified email:

```python
def is_claimed(self) -> bool:
    """Indicates whether the CoPerson record is claimed.
    
    A record is claimed if:
    1. The person is active
    2. Has at least one verified email
    3. Has an oidcsub identifier from cilogon.org
    """
    if not self.is_active():
        return False
    
    if not self.verified_email_addresses:
        return False
    
    identifiers = self.identifiers(
        predicate=lambda identifier: identifier.type == "oidcsub"
        and identifier.identifier.startswith("http://cilogon.org")
    )
    return bool(identifiers)
```

## Data Models

The RegistryPerson class wraps COManage data models from the `coreapi_client` package:

### CoPersonMessage

The root object containing all person data:

```python
class CoPersonMessage:
    co_person: Optional[CoPerson]
    email_address: Optional[List[EmailAddress]]
    name: Optional[List[Name]]
    identifier: Optional[List[Identifier]]
    org_identity: Optional[List[OrgIdentity]]
    co_person_role: Optional[List[CoPersonRole]]
```

### EmailAddress

Represents an email with metadata:

```python
class EmailAddress:
    mail: str                    # The email address
    type: str                    # e.g., "official", "personal"
    verified: bool               # Whether email is verified
    co_person_id: Optional[int]  # Associated CoPerson ID
```

### Name

Represents a person's name:

```python
class Name:
    given: str              # First name
    family: str             # Last name
    type: str               # e.g., "official"
    primary_name: bool      # Whether this is the primary name
```

### Identifier

Represents various identifiers:

```python
class Identifier:
    identifier: str         # The identifier value
    type: str              # e.g., "naccid", "oidcsub"
    status: str            # e.g., "A" for active
    login: Optional[bool]  # Whether used for login
```

### OrgIdentity

Represents organizational affiliation:

```python
class OrgIdentity:
    identifier: Optional[List[Identifier]]
    email_address: Optional[List[EmailAddress]]
```

## Correctness Properties


A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.

### Property 1: Email Priority Selection

*For any* RegistryPerson instance, when accessing the email_address property, it should return the first email according to this priority: organizational emails first, then official emails, then verified emails, then any email, then None if no emails exist.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

### Property 2: Email Filtering Correctness

*For any* RegistryPerson instance, when filtering emails by type or verification status (official_email_addresses, verified_email_addresses, organization_email_addresses), all returned emails should match the filter criteria and preserve the original order from COManage.

**Validates: Requirements 1.7, 1.8, 3.1, 3.2, 3.3, 3.5**

### Property 3: Email Search Completeness

*For any* RegistryPerson instance and any email string, the has_email method should return True if and only if that email exists in the complete list of email addresses, regardless of type or verification status.

**Validates: Requirements 1.9, 3.6**

### Property 4: Claimed Account Validation

*For any* RegistryPerson instance, the is_claimed method should return True if and only if the person is active AND has at least one verified email AND has an oidcsub identifier starting with "http://cilogon.org".

**Validates: Requirements 1.10**

### Property 5: Primary Name Extraction

*For any* RegistryPerson instance with names, the primary_name property should return the name marked as primary_name=True formatted as "Given Family", or None if no primary name exists.

**Validates: Requirements 2.4**

### Property 6: Identifier Filtering

*For any* RegistryPerson instance and any predicate function, the identifiers method should return only identifiers that satisfy the predicate, preserving the original order.

**Validates: Requirements 2.5**

### Property 7: Registry ID Extraction

*For any* RegistryPerson instance, the registry_id method should return the identifier value where type="naccid" and status="A", or None if no such identifier exists.

**Validates: Requirements 2.7**

### Property 8: Active Status Check

*For any* RegistryPerson instance, the is_active method should return True if and only if the CoPerson status is "A".

**Validates: Requirements 2.8**

## Error Handling

The RegistryPerson class handles missing or malformed data gracefully:

1. **Missing emails**: Returns empty lists or None as appropriate
2. **Missing names**: Returns None for primary_name
3. **Missing identifiers**: Returns empty list or None as appropriate
4. **Missing metadata**: Returns None for creation_date
5. **None values in lists**: Filters are defensive against None values

All methods are designed to never raise exceptions for missing data - they return sensible defaults (None, empty list, False) instead.

### Error Scenarios

| Scenario | Behavior |
|----------|----------|
| No emails | email_address returns None, email_addresses returns [] |
| No primary name | primary_name returns None |
| No identifiers | identifiers returns [], registry_id returns None |
| No metadata | creation_date returns None |
| Inactive person | is_active returns False, is_claimed returns False |
| Unclaimed person | is_claimed returns False |

## Testing Strategy

The testing strategy uses both unit tests and property-based tests to ensure comprehensive coverage.

### Unit Tests

Unit tests focus on specific examples and edge cases:

1. **Email priority examples**: Test each level of the priority chain with specific email configurations
2. **Edge cases**: Empty lists, None values, missing attributes
3. **Filtering examples**: Specific cases of email filtering by type and verification
4. **Integration**: Test with realistic CoPersonMessage objects from COManage

Unit tests are organized by functionality:
- `test_email_selection.py`: Email priority and filtering
- `test_identifiers.py`: Identifier handling and registry ID
- `test_names.py`: Name extraction and formatting
- `test_status.py`: Active and claimed status checks
- `test_factory.py`: Factory method creation

### Property-Based Tests

Property-based tests verify universal properties across randomized inputs using the `hypothesis` library (Python's property-based testing framework).

**Configuration**:
- Minimum 100 iterations per property test
- Each test tagged with: `# Feature: registry-person-multivalued-attributes, Property N: [property text]`

**Test Generators**:

Custom Hypothesis strategies generate valid CoPersonMessage objects. The strategies are designed to avoid overzealous filtering by ensuring that when specific email types are requested, they are explicitly added to the generated data rather than relying on random generation to produce them.

```python
@st.composite
def email_address_strategy(draw, email_type=None, verified=None):
    """Generate EmailAddress with optional constraints.
    
    Args:
        draw: Hypothesis draw function
        email_type: If provided, use this type; otherwise randomly choose
        verified: If provided, use this value; otherwise randomly choose
    """
    return EmailAddress(
        mail=draw(st.emails()),
        type=email_type if email_type is not None else draw(st.sampled_from(["official", "personal", "work"])),
        verified=verified if verified is not None else draw(st.booleans())
    )

@st.composite
def coperson_message_strategy(draw, 
                               min_emails=0,
                               max_emails=5,
                               ensure_official=False,
                               ensure_verified=False,
                               ensure_org_email=False,
                               include_identifiers=True,
                               include_names=True):
    """Generate CoPersonMessage with configurable properties.
    
    This strategy avoids overzealous filtering by explicitly adding required
    email types when requested, rather than hoping random generation produces them.
    
    Args:
        draw: Hypothesis draw function
        min_emails: Minimum number of emails to generate
        max_emails: Maximum number of emails to generate
        ensure_official: If True, guarantee at least one official email
        ensure_verified: If True, guarantee at least one verified email
        ensure_org_email: If True, add organizational identity with email
        include_identifiers: If True, generate identifiers
        include_names: If True, generate names
    """
    # Generate base emails
    num_emails = draw(st.integers(min_value=min_emails, max_value=max_emails))
    emails = []
    
    # Add required email types first to avoid filtering issues
    if ensure_official and num_emails > 0:
        emails.append(draw(email_address_strategy(email_type="official")))
        num_emails -= 1
    
    if ensure_verified and num_emails > 0:
        # Add verified email (may or may not be official)
        emails.append(draw(email_address_strategy(verified=True)))
        num_emails -= 1
    
    # Fill remaining slots with random emails
    for _ in range(num_emails):
        emails.append(draw(email_address_strategy()))
    
    # Shuffle to avoid position bias
    if emails:
        draw(st.randoms()).shuffle(emails)
    
    # Generate organizational identity with email if requested
    org_identity = None
    if ensure_org_email:
        org_email = draw(email_address_strategy())
        org_identifier = Identifier(
            identifier=f"http://cilogon.org/serverA/users/{draw(st.integers(min_value=1000, max_value=9999))}",
            type="oidcsub",
            login=True,
            status="A"
        )
        org_identity = OrgIdentity(
            email_address=[org_email],
            identifier=[org_identifier]
        )
    
    # Generate identifiers
    identifiers = None
    if include_identifiers:
        num_identifiers = draw(st.integers(min_value=0, max_value=3))
        if num_identifiers > 0:
            identifiers = []
            for _ in range(num_identifiers):
                id_type = draw(st.sampled_from(["naccid", "oidcsub", "eppn"]))
                identifiers.append(Identifier(
                    identifier=f"{id_type}-{draw(st.integers(min_value=1000, max_value=9999))}",
                    type=id_type,
                    status=draw(st.sampled_from(["A", "D"])),
                    login=draw(st.booleans()) if id_type == "oidcsub" else None
                ))
    
    # Generate names
    names = None
    if include_names:
        num_names = draw(st.integers(min_value=0, max_value=2))
        if num_names > 0:
            names = []
            for i in range(num_names):
                names.append(Name(
                    given=draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll')))),
                    family=draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll')))),
                    type="official",
                    primary_name=(i == 0)  # First name is primary
                ))
    
    # Generate CoPerson with random status
    coperson = CoPerson(
        co_id=1,
        status=draw(st.sampled_from(["A", "D", "S"])),
        meta=None  # Can be extended if needed
    )
    
    return CoPersonMessage(
        CoPerson=coperson,
        EmailAddress=emails if emails else None,
        OrgIdentity=[org_identity] if org_identity else None,
        Identifier=identifiers,
        Name=names,
        CoPersonRole=None  # Can be extended if needed
    )
```

**Property Test Examples**:

```python
# Feature: registry-person-multivalued-attributes, Property 1: Email Priority Selection
@given(coperson_message_strategy(min_emails=0, max_emails=5))
def test_email_priority_property(coperson_msg):
    """Property: Email selection follows priority hierarchy.
    
    This test verifies that email_address always returns the highest priority
    email available according to the defined hierarchy.
    """
    person = RegistryPerson(coperson_msg)
    email = person.email_address
    
    # Check priority hierarchy
    if person.organization_email_addresses:
        assert email == person.organization_email_addresses[0]
    elif person.official_email_addresses:
        assert email == person.official_email_addresses[0]
    elif person.verified_email_addresses:
        assert email == person.verified_email_addresses[0]
    elif person.email_addresses:
        assert email == person.email_addresses[0]
    else:
        assert email is None

# Feature: registry-person-multivalued-attributes, Property 2: Email Filtering Correctness
@given(coperson_message_strategy(min_emails=0, max_emails=5))
def test_email_filtering_property(coperson_msg):
    """Property: Email filters return only matching emails in original order.
    
    This test verifies that filtering methods correctly filter emails and
    preserve the original order from COManage.
    """
    person = RegistryPerson(coperson_msg)
    all_emails = person.email_addresses
    
    # Test official email filtering
    official = person.official_email_addresses
    assert all(email.type == "official" for email in official)
    assert official == [e for e in all_emails if e.type == "official"]
    
    # Test verified email filtering
    verified = person.verified_email_addresses
    assert all(email.verified for email in verified)
    assert verified == [e for e in all_emails if e.verified]
    
    # Test organizational email filtering
    org_emails = person.organization_email_addresses
    # All org emails should be in the overall email list or org identity
    for email in org_emails:
        assert isinstance(email, EmailAddress)

# Feature: registry-person-multivalued-attributes, Property 3: Email Search Completeness
@given(
    coperson_message_strategy(min_emails=1, max_emails=5),
    st.integers(min_value=0, max_value=4)
)
def test_has_email_completeness(coperson_msg, email_index):
    """Property: has_email finds any email in the complete list.
    
    This test verifies that has_email returns True for any email that exists
    in the person's email list, regardless of type or verification status.
    """
    person = RegistryPerson(coperson_msg)
    
    # If we have emails and the index is valid, has_email should find it
    if person.email_addresses and email_index < len(person.email_addresses):
        target_email = person.email_addresses[email_index].mail
        assert person.has_email(target_email)
    
    # has_email should return False for emails not in the list
    fake_email = "definitely-not-in-list@example.com"
    if not any(e.mail == fake_email for e in person.email_addresses):
        assert not person.has_email(fake_email)

# Feature: registry-person-multivalued-attributes, Property 4: Claimed Account Validation
@given(coperson_message_strategy(min_emails=0, max_emails=3, include_identifiers=True))
def test_claimed_account_property(coperson_msg):
    """Property: is_claimed requires active status, verified email, and oidcsub.
    
    This test verifies that is_claimed returns True only when all three
    conditions are met: active status, verified email, and oidcsub identifier.
    """
    person = RegistryPerson(coperson_msg)
    is_claimed = person.is_claimed()
    
    if is_claimed:
        # If claimed, must be active
        assert person.is_active()
        # Must have at least one verified email
        assert len(person.verified_email_addresses) > 0
        # Must have oidcsub identifier
        oidcsub_ids = person.identifiers(
            lambda i: i.type == "oidcsub" and i.identifier.startswith("http://cilogon.org")
        )
        assert len(oidcsub_ids) > 0
    else:
        # If not claimed, at least one condition must be false
        has_verified = len(person.verified_email_addresses) > 0
        has_oidcsub = bool(person.identifiers(
            lambda i: i.type == "oidcsub" and i.identifier.startswith("http://cilogon.org")
        ))
        # At least one of these must be false
        assert not (person.is_active() and has_verified and has_oidcsub)
```

### Test Organization

Tests are located in `common/test/python/users/`:

```
common/test/python/users/
├── BUILD
├── test_registry_person_email.py       # Email selection and filtering
├── test_registry_person_identifiers.py # Identifier handling
├── test_registry_person_names.py       # Name extraction
├── test_registry_person_status.py      # Active and claimed status
├── test_registry_person_factory.py     # Factory method
└── test_registry_person_properties.py  # Property-based tests
```

### Running Tests

```bash
# Ensure dev container is running
./bin/start-devcontainer.sh

# Run all RegistryPerson tests
./bin/exec-in-devcontainer.sh pants test common/test/python/users::

# Run specific test file
./bin/exec-in-devcontainer.sh pants test common/test/python/users:test_registry_person_email

# Run property-based tests only
./bin/exec-in-devcontainer.sh pants test common/test/python/users:test_registry_person_properties
```

### Coverage Goals

- **Line coverage**: >95% for RegistryPerson class
- **Branch coverage**: 100% for all conditional logic
- **Property coverage**: All 8 correctness properties implemented as property-based tests
- **Edge case coverage**: All edge cases from requirements tested explicitly
