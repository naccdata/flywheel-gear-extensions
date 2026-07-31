# Data Identification Architecture

## Overview

The `DataIdentification` model (`nacc-common/src/python/nacc_common/data_identification.py`) provides a composable way to identify data artifacts across the NACC Data Platform. It uses nested sub-models to separate participant identity, visit context, and datatype-specific fields.

## Class Hierarchy

```
DataIdentification
├── participant: ParticipantIdentification (always required)
│   ├── adcid: Optional[int]
│   ├── ptid: str
│   └── naccid: Optional[str]
├── date: str (always required)
├── visit: Optional[VisitIdentification]
│   └── visitnum: str
└── data: FormIdentification | ImageIdentification (always required)
```

### Current Data Subclasses

- **FormIdentification** — identifies form data (module + optional packet)
- **ImageIdentification** — identifies imaging data (modality)

## Serialization Behavior

`DataIdentification` has a custom `@model_serializer` that **flattens** all nested sub-models into a single dict:

```python
# Internal structure:
DataIdentification(
    participant=ParticipantIdentification(adcid=42, ptid="ABC", naccid="NACC001"),
    date="2024-01-15",
    visit=VisitIdentification(visitnum="1"),
    data=FormIdentification(module="UDS", packet="I"),
)

# Serialized output (model_dump()):
{
    "adcid": 42,
    "ptid": "ABC",
    "naccid": "NACC001",
    "date": "2024-01-15",
    "visitnum": "1",
    "module": "UDS",
    "packet": "I",
}
```

When `visit` is `None`, the serialized output includes `"visitnum": None`.

### Serialization Modes

- **Default** (`model_dump()`): Flattened dict with all fields (including None values).
- **`exclude_none=True`**: Flattened dict omitting None fields. Used by `VisitEventCapture` for JSON output.
- **`mode="raw"`**: Preserves the nested structure (does NOT flatten). Used by `QCStatusLogCreator` when writing visit metadata to QC log `custom_info`.

## VisitEvent Serialization

`VisitEvent` wraps a `DataIdentification` and applies additional renaming when serializing for the event log:

| DataIdentification field | VisitEvent serialized key |
|--------------------------|---------------------------|
| `adcid`                  | `pipeline_adcid`          |
| `date`                   | `visit_date`              |
| `visitnum`               | `visit_number`            |
| All other fields         | Passed through as-is      |

The renaming is defined in `VisitEvent._RENAMED_FIELDS`. All fields from the flattened `DataIdentification` that are NOT in the rename map are forwarded directly. This means new fields added to future data subclasses will automatically appear in the serialized `VisitEvent` without updating the serializer.

## Extending with a New Datatype

When a new datatype needs event capture (e.g., `enrollment`, `biomarker`), follow these steps:

### Step 1: Define the data subclass

Add a new model in `data_identification.py`:

```python
class EnrollmentIdentification(BaseModel):
    """Identifies enrollment-specific data."""

    enrollment_type: str  # e.g., "initial", "transfer"

    def apply(self, visitor: AbstractIdentificationVisitor) -> None:
        """Apply visitor to this enrollment identification."""
        visitor.visit_enrollment(self)  # Add to visitor ABC too
```

### Step 2: Expand the union type

Update `DataIdentification.data`:

```python
data: FormIdentification | ImageIdentification | EnrollmentIdentification
```

### Step 3: Update the factory method

Add a branch to `DataIdentification.from_visit_metadata`:

```python
if modality is not None:
    data = ImageIdentification(modality=modality)
elif enrollment_type is not None:
    data = EnrollmentIdentification(enrollment_type=enrollment_type)
elif module is not None:
    data = FormIdentification(module=module, packet=packet)
else:
    raise ValueError("Either module, modality, or enrollment_type must be provided")
```

### Step 4: Update the VisitEvent validator

Add a branch to `VisitEvent.validate_datatype_consistency`:

```python
elif self.datatype == "enrollment":
    if not isinstance(data_obj, EnrollmentIdentification):
        raise ValueError(
            f"Visit event has datatype 'enrollment' but data_identification.data "
            f"is {type(data_obj).__name__}"
        )
```

### Step 5: Update the visitor ABC (if applicable)

Add a new `visit_*` method to `AbstractIdentificationVisitor` if the new subclass participates in the visitor pattern.

### What does NOT need updating

- **`DataIdentification.serialize_model`** — flattening already handles arbitrary fields from any data subclass generically.
- **`DataIdentification.__getattr__`** — attribute delegation already forwards to `self.data` regardless of type.
- **`VisitEvent.serialize_model`** — the passthrough loop already forwards all non-renamed fields from the flattened DataIdentification. New fields will appear automatically.
- **`VisitEvent.__getattr__`** — delegates to `data_identification.__getattr__`, which delegates to `self.data`.

### Checklist

| Step | File | Required? |
|------|------|-----------|
| Define subclass | `data_identification.py` | Yes |
| Expand union type | `data_identification.py` | Yes |
| Update factory method | `data_identification.py` | Yes, if using `from_visit_metadata` |
| Update VisitEvent validator | `visit_events.py` | Yes |
| Update visitor ABC | `data_identification.py` | Only if using visitor pattern |
| Update VisitEvent serializer | `visit_events.py` | No (automatic) |
| Update VisitEvent `__getattr__` | `visit_events.py` | No (automatic) |
| Update documentation | `docs/processes/` | Yes |

## Design Rationale

- **Composition over inheritance**: `DataIdentification` composes sub-models rather than using a deep class hierarchy. This keeps each concept (participant, visit, data-type-specifics) isolated and testable.
- **Flat serialization**: The custom serializer produces a flat dict that matches the legacy schema expected by downstream consumers (S3 event logs, Parquet tables).
- **Forward-compatible VisitEvent serializer**: By iterating over all fields rather than maintaining an explicit allowlist, new data subclass fields are surfaced automatically.
- **Validator as guardrail**: `validate_datatype_consistency` ensures you can't accidentally create mismatched events (e.g., a "form" event with `ImageIdentification` data). Each new datatype requires an explicit validator branch, making the addition a conscious design decision.
