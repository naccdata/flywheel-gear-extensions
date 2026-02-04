# Requirements Document: Visit Metadata Architecture Refactoring

## Introduction

This document specifies requirements for refactoring the visit metadata architecture in the nacc-common and common packages. The current inheritance hierarchy between `VisitKeys` and `VisitMetadata` creates confusion because it mixes concerns: QC logging parameters, event capture fields, and datatype-specific metadata. This refactoring will separate these concerns while maintaining backward compatibility with existing form processing code.

## Glossary

- **VisitKeys**: Base model containing visit identification fields common to all datatypes (adcid, ptid, visitnum, module, date, naccid)
- **VisitMetadata**: Extended model for form datatypes that adds packet field
- **ImageVisitMetadata**: Extended model for image datatypes that adds modality field
- **QCStatusLogManager**: Manager class that creates and updates QC status log files using visit identification
- **ErrorLogTemplate**: Template for generating QC status log filenames from visit data
- **VisitEvent**: Event model for capturing visit-related actions (submit, delete, pass-qc, not-pass-qc)
- **FileVisitAnnotator**: Class that adds visit metadata to QC log files
- **Datatype**: Category of data being processed (form, image, genomic, biospecimen)
- **Module**: For forms, the form module name (e.g., "A1", "B1"); for images, the modality (e.g., "MR", "CT")
- **Packet**: Form-specific field indicating the packet type (e.g., "I", "F")
- **Modality**: Image-specific field indicating the imaging modality (e.g., "MR", "CT", "PET")

## Requirements

### Requirement 1: Base Visit Identification Model

**User Story:** As a developer, I want a base model for visit identification fields, so that I can use it consistently across QC logging, event capture, and datatype-specific contexts.

#### Acceptance Criteria

1. THE VisitKeys model SHALL contain the following optional fields: adcid, ptid, visitnum, module, date, naccid
2. THE VisitKeys model SHALL provide a create_from class method that accepts a record dictionary and optional date_field parameter
3. WHEN create_from is called, THE VisitKeys model SHALL extract field values using FieldNames constants
4. THE VisitKeys model SHALL serve as the base class for all datatype-specific metadata models

### Requirement 2: Form-Specific Visit Metadata

**User Story:** As a form processing developer, I want a visit metadata model with form-specific fields, so that I can capture packet information for form events.

#### Acceptance Criteria

1. THE VisitMetadata model SHALL extend VisitKeys
2. THE VisitMetadata model SHALL add an optional packet field
3. THE VisitMetadata model SHALL provide a custom serializer that maps field names for VisitEvent creation
4. WHEN serializing for VisitEvent, THE VisitMetadata model SHALL map "date" to "visit_date" and "visitnum" to "visit_number"
5. THE VisitMetadata model SHALL provide a create class method that accepts a FileEntry and returns Optional[VisitMetadata]
6. WHEN create is called with a FileEntry containing visit info, THE VisitMetadata model SHALL validate and return a VisitMetadata instance
7. WHEN create is called with a FileEntry without visit info, THE VisitMetadata model SHALL return None

### Requirement 3: Image-Specific Visit Metadata

**User Story:** As an image processing developer, I want a visit metadata model with image-specific fields, so that I can capture modality information for image events.

#### Acceptance Criteria

1. THE ImageVisitMetadata model SHALL extend VisitKeys
2. THE ImageVisitMetadata model SHALL add a required modality field
3. WHEN ImageVisitMetadata is created, THE module field SHALL be set to the modality value
4. THE ImageVisitMetadata model SHALL provide a custom serializer that maps field names for VisitEvent creation
5. WHEN serializing for VisitEvent, THE ImageVisitMetadata model SHALL map "date" to "visit_date" and "visitnum" to "visit_number"
6. THE ImageVisitMetadata model SHALL be defined in nacc_common.error_models module

### Requirement 4: QC Logging Compatibility

**User Story:** As a QC logging developer, I want QCStatusLogManager to work with any VisitKeys subclass, so that I can log QC status for any datatype.

#### Acceptance Criteria

1. WHEN QCStatusLogManager.update_qc_log is called with any VisitKeys subclass, THE system SHALL accept it as the visit_keys parameter
2. WHEN preparing template records, THE QCStatusLogManager SHALL use model_dump to extract visit data from any VisitKeys subclass
3. WHEN generating QC log filenames, THE ErrorLogTemplate SHALL use the module field from any VisitKeys subclass
4. WHEN annotating QC log files, THE FileVisitAnnotator SHALL accept VisitMetadata instances
5. WHEN a VisitKeys instance (not VisitMetadata) is provided for annotation, THE QCStatusLogManager SHALL convert it to VisitMetadata with packet=None

### Requirement 5: Event Capture Compatibility

**User Story:** As an event capture developer, I want to create VisitEvent objects from any visit metadata subclass, so that I can capture events for any datatype.

#### Acceptance Criteria

1. WHEN VisitMetadata is serialized with exclude_none=True, THE system SHALL produce a dictionary suitable for VisitEvent creation
2. WHEN ImageVisitMetadata is serialized with exclude_none=True, THE system SHALL produce a dictionary suitable for VisitEvent creation
3. THE VisitEvent model SHALL accept module field from form metadata (form module names)
4. THE VisitEvent model SHALL accept module field from image metadata (modality values)
5. WHEN creating a VisitEvent for forms, THE packet field SHALL be included if present
6. WHEN creating a VisitEvent for images, THE packet field SHALL be None or omitted

### Requirement 6: Backward Compatibility

**User Story:** As a maintainer, I want existing form processing code to continue working unchanged, so that I can deploy the refactoring without breaking existing gears.

#### Acceptance Criteria

1. THE VisitKeys model SHALL maintain its current field names and types
2. THE VisitMetadata model SHALL maintain its current field names, types, and behavior
3. WHEN existing code uses VisitMetadata for forms, THE system SHALL continue to work without modification
4. WHEN existing code uses VisitKeys as a parameter type, THE system SHALL accept any VisitKeys subclass
5. THE VisitMetadata.create_from class method SHALL remain available and functional
6. THE VisitMetadata.create class method SHALL remain available and functional

### Requirement 7: Module Field Semantics

**User Story:** As a developer, I want clear semantics for the module field across datatypes, so that I can use it correctly in templates and event capture.

#### Acceptance Criteria

1. WHEN processing forms, THE module field SHALL contain the form module name (e.g., "A1", "B1", "C1")
2. WHEN processing images, THE module field SHALL contain the modality value (e.g., "MR", "CT", "PET")
3. THE ErrorLogTemplate SHALL use the module field to generate visit labels regardless of datatype
4. THE VisitEvent model SHALL normalize the module field to uppercase for canonical storage
5. WHEN VisitEvent validates a form event, THE system SHALL require module to be non-None
6. WHEN VisitEvent validates an image event, THE system SHALL require module to be non-None

### Requirement 8: Extensibility for Future Datatypes

**User Story:** As a platform architect, I want the visit metadata architecture to support future datatypes, so that I can add genomic, biospecimen, and other datatypes without major refactoring.

#### Acceptance Criteria

1. THE VisitKeys base class SHALL provide a foundation for all datatype-specific metadata models
2. WHEN adding a new datatype, THE system SHALL allow creating a new subclass of VisitKeys
3. WHEN adding a new datatype, THE QCStatusLogManager SHALL work with the new subclass without modification
4. WHEN adding a new datatype, THE ErrorLogTemplate SHALL work with the new subclass without modification
5. THE architecture SHALL support datatype-specific fields through inheritance from VisitKeys

### Requirement 9: Type Safety and Validation

**User Story:** As a developer, I want type-safe visit metadata models, so that I can catch errors at development time rather than runtime.

#### Acceptance Criteria

1. THE VisitKeys model SHALL use Pydantic BaseModel for validation
2. THE VisitMetadata model SHALL use Pydantic BaseModel for validation
3. THE ImageVisitMetadata model SHALL use Pydantic BaseModel for validation
4. WHEN ImageVisitMetadata is created without a modality field, THE system SHALL raise a validation error
5. WHEN any visit metadata model is created with invalid field types, THE system SHALL raise a validation error

### Requirement 10: Documentation and Migration Guide

**User Story:** As a developer adopting the refactored architecture, I want clear documentation on when to use each class, so that I can choose the correct model for my use case.

#### Acceptance Criteria

1. THE VisitKeys docstring SHALL explain it is the base class for visit identification
2. THE VisitMetadata docstring SHALL explain it is for form datatypes and includes packet field
3. THE ImageVisitMetadata docstring SHALL explain it is for image datatypes and includes modality field
4. THE documentation SHALL provide examples of when to use each class
5. THE documentation SHALL explain how module field semantics differ by datatype
6. THE documentation SHALL provide a migration guide for adding new datatypes
