# Design Document: Image Identifier Lookup Gear

## Implementation Status: ✅ COMPLETE

**All design components have been implemented and tested.**

✅ **Infrastructure Ready:**
- `DataIdentification` with `ImageIdentification` for image metadata
- QCStatusLogManager, ErrorLogTemplate, FileVisitAnnotator updated for DataIdentification
- VisitEvent and VisitEventCapture support image datatypes
- Visitor pattern for datatype-agnostic QC log filename generation
- All shared utilities ready for image processing

✅ **Implementation Complete:**
- DICOM metadata extraction (PatientID, StudyDate, Modality, and comprehensive metadata fields)
- Identifier lookup orchestration with ImageIdentifierLookupProcessor
- Early data extraction and fail-fast validation in run.py
- Integration with existing QC logging and event capture (required)
- Idempotency checks for safe re-runs
- Comprehensive error handling and reporting

## 1. Overview

The Image Identifier Lookup gear performs NACCID lookups for DICOM images uploaded to the NACC Data Platform. The gear operates on a single image file as input, performing one lookup per file execution.

### Key Characteristics

- **Input**: Single DICOM image file
- **Unit of Data**: One file = one lookup operation
- **Primary Function**: Look up NACCID using PTID and ADCID, store result in subject metadata
- **Secondary Functions**: QC status logging, transactional event capture
- **Code Reuse**: Maximizes reuse from `common/` package and existing gears

### Related Gears

This gear shares architectural patterns and reuses components from the `identifier_lookup` gear, which performs similar identifier lookups for CSV files containing multiple participant records. The key difference is the unit of processing: this gear processes one image file per execution, while the CSV-based gear processes multiple rows in a single file.

## 2. Architecture

### 2.1 High-Level Design

```
┌─────────────────────────────────────────────────────────────────┐
│                    Image Identifier Lookup Gear                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 1. Input Processing & Early Extraction (Fail Early)      │  │
│  │    - Retrieve input DICOM file                           │  │
│  │    - Get parent subject and project                      │  │
│  │    - Extract pipeline ADCID from project metadata        │  │
│  │    - Extract PTID from subject.label or DICOM PatientID  │  │
│  │    - Extract existing NACCID from subject.info (if any)  │  │
│  │    - Extract visit metadata from DICOM (date, modality)  │  │
│  │    - Fail immediately if required data missing           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 2. Idempotency Check                                     │  │
│  │    - If NACCID already exists in subject.info:           │  │
│  │      → Skip to QC logging and event capture              │  │
│  │      → Mark as success (idempotent re-run)               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 3. NACCID Lookup                                         │  │
│  │    - Query IdentifiersLambdaRepository                   │  │
│  │    - Use PTID + ADCID for lookup                         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 4. Subject Metadata Update                               │  │
│  │    - Store NACCID in subject.info                        │  │
│  │    - Store extracted DICOM metadata in subject.info      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 5. QC Status Logging                                     │  │
│  │    - Create/update project-level QC status log          │  │
│  │    - Add visit metadata to log file                      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 6. Event Capture (Required)                              │  │
│  │    - Log submission event to S3 transaction log          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 7. File QC Metadata Update                               │  │
│  │    - Add QC metadata to input file                       │  │
│  │    - Add gear tag (PASS/FAIL)                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                  ImageIdentifierLookupVisitor                    │
│                  (GearExecutionEnvironment)                      │
├─────────────────────────────────────────────────────────────────┤
│  - client: ClientWrapper                                         │
│  - file_input: InputFileWrapper                                 │
│  - identifiers_repository: IdentifierRepository                 │
│  - qc_log_manager: QCStatusLogManager                           │
│  - event_capture: VisitEventCapture                             │
│  - gear_name: str                                               │
│  - naccid_field_name: str                                       │
│  - default_modality: str                                        │
│                                                                   │
│  Key Responsibilities:                                           │
│  - Extract all data from Flywheel objects early (fail fast)     │
│  - Check for existing NACCID (idempotency)                      │
│  - Orchestrate lookup and metadata updates                      │
│  - Handle QC logging and event capture                          │
└─────────────────────────────────────────────────────────────────┘
                           │
                           │ uses
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│              ImageIdentifierLookupProcessor                      │
│              (Pure business logic - no Flywheel access)          │
├─────────────────────────────────────────────────────────────────┤
│  Key Responsibilities:                                           │
│  - Perform NACCID lookup with provided PTID/ADCID              │
│  - Update subject metadata with NACCID                          │
│  - Return processing results                                     │
│                                                                   │
│  Note: Receives all extracted data as parameters                │
└─────────────────────────────────────────────────────────────────┘
                           │
                           │ uses
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                    DataIdentification                            │
│            (from nacc_common.data_identification)                │
├─────────────────────────────────────────────────────────────────┤
│  + participant: ParticipantIdentification                        │
│    - adcid: int                                                  │
│    - ptid: str                                                   │
│    - naccid: Optional[str]                                       │
│  + date: str                                                     │
│  + visit: Optional[VisitIdentification]                          │
│  + data: ImageIdentification                                     │
│    - modality: str                                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                  Shared Components (Reused)                      │
├─────────────────────────────────────────────────────────────────┤
│  - IdentifiersLambdaRepository (from identifiers/)              │
│  - QCStatusLogManager (from error_logging/)                     │
│  - FileVisitAnnotator (from error_logging/)                     │
│  - VisitEventCapture (from event_capture/)                      │
│  - ProjectAdaptor, SubjectAdaptor (from flywheel_adaptor/)      │
│  - ErrorLogTemplate (from error_logging/)                       │
│  - DataIdentification, ImageIdentification (from nacc_common/)  │
└─────────────────────────────────────────────────────────────────┘
```

## 3. Data Models

### 3.1 DataIdentification with ImageIdentification (✅ Implemented in refactor/visit-metadata)

The gear uses the refactored `DataIdentification` architecture from `nacc_common.data_identification`:

```python
# From nacc-common/src/python/nacc_common/data_identification.py

class ImageIdentification(BaseModel):
    """Identifies image-specific data."""
    modality: str  # Imaging modality (MR, CT, PET, etc.) - required

class DataIdentification(BaseModel):
    """Base class for all data identification using composition."""
    participant: ParticipantIdentification  # adcid, ptid, naccid
    date: str  # Visit date or acquisition date
    visit: Optional[VisitIdentification] = None  # visitnum (if applicable)
    data: FormIdentification | ImageIdentification  # Datatype-specific fields
```

**For images, create DataIdentification like this:**

```python
data_id = DataIdentification.from_visit_metadata(
    adcid=pipeline_adcid,
    ptid=ptid,
    naccid=naccid,
    date=acquisition_date,  # From DICOM AcquisitionDate/StudyDate
    modality=modality,  # From DICOM Modality tag
    visitnum=None  # Images typically don't have visit numbers
)
```

**Key Features:**
- Composition pattern separates participant, visit, and datatype-specific data
- `ImageIdentification` contains only image-specific fields (modality)
- Flat serialization for backward compatibility with existing storage
- Visitor pattern support for datatype-agnostic operations (QC log filenames, etc.)
- Works seamlessly with QCStatusLogManager, FileVisitAnnotator, VisitEventCapture

### 3.2 ProcessResult

Internal result object for tracking processing outcomes:

```python
@dataclass
class ProcessResult:
    """Result of image identifier lookup processing."""
    success: bool
    ptid: str
    naccid: Optional[str]
    data_identification: DataIdentification  # Uses refactored architecture
    errors: List[FileError]
    skipped: bool = False  # True if NACCID already exists with correct value
```

## 4. Detailed Component Design

### 4.1 ImageIdentifierLookupVisitor

**Responsibility:** Gear execution environment and orchestration

**Key Methods:**

```python
class ImageIdentifierLookupVisitor(GearExecutionEnvironment):
    """Visitor for the Image Identifier Lookup gear."""
    
    def __init__(
        self,
        *,
        client: ClientWrapper,
        file_input: InputFileWrapper,
        identifiers_repository: IdentifierRepository,
        qc_log_manager: QCStatusLogManager,
        gear_name: str,
        naccid_field_name: str = "naccid",
        default_modality: str = "UNKNOWN",
        event_capture: VisitEventCapture,
    ):
        """Initialize the visitor with dependencies."""
        
    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'ImageIdentifierLookupVisitor':
        """Factory method to create visitor from gear context.
        
        Extracts configuration:
        - database_mode: prod/dev for identifier repository
        - naccid_field_name: subject metadata field name (default: "naccid")
        - default_modality: fallback modality (default: "UNKNOWN")
        - event_environment: environment prefix for event capture (required)
        - event_bucket: S3 bucket for event storage (required)
        - admin_group: NACC admin group ID (default: "nacc")
        
        Initializes:
        - ClientWrapper (GearBotClient)
        - InputFileWrapper for input_file
        - IdentifiersLambdaRepository
        - QCStatusLogManager with ErrorLogTemplate and FileVisitAnnotator
        - VisitEventCapture (required - fails if event_environment or event_bucket missing)
        """
        
    def run(self, context: GearToolkitContext) -> None:
        """Main execution method.
        
        1. Retrieve input file, parent subject, and project
        2. Extract all required data early (fail fast):
           - Pipeline ADCID from project metadata
           - PTID from subject.label or DICOM PatientID tag
           - Existing NACCID from subject.info (if present)
           - Visit metadata from DICOM (StudyDate, modality)
           - Comprehensive DICOM metadata for storage
        3. Check idempotency: if NACCID already exists, skip to step 6
        4. Perform NACCID lookup using IdentifiersLambdaRepository
        5. Update subject metadata with NACCID and DICOM metadata
        6. Update QC status log
        7. Capture submission event (required)
        8. Update file QC metadata and tags
        """
```

### 4.2 ImageIdentifierLookupProcessor

**Responsibility:** Core business logic for identifier lookup (no Flywheel object access)

**Design Philosophy:** The processor receives all extracted data as parameters and focuses purely on business logic. It does not access Flywheel objects directly, making it easier to test and reason about.

**Key Methods:**

```python
class ImageIdentifierLookupProcessor:
    """Processes identifier lookup using pre-extracted data."""
    
    def __init__(
        self,
        *,
        identifiers_repository: IdentifierRepository,
        subject: SubjectAdaptor,
        naccid_field_name: str,
    ):
        """Initialize processor with minimal dependencies.
        
        Args:
            identifiers_repository: Repository for NACCID lookups
            subject: Subject adaptor for metadata updates
            naccid_field_name: Field name for NACCID in subject.info
        """
        
    def lookup_and_update(
        self,
        ptid: str,
        adcid: int,
        existing_naccid: Optional[str] = None
    ) -> str:
        """Look up NACCID and update subject metadata.
        
        Args:
            ptid: Pre-extracted participant identifier
            adcid: Pre-extracted pipeline ADCID
            existing_naccid: Pre-extracted existing NACCID (if any)
            
        Returns:
            The NACCID (either looked up or existing)
            
        Raises:
            ValueError: If existing_naccid differs from lookup result
            LookupError: If no matching record found
            RepositoryError: If lookup service unavailable
            UpdateError: If metadata update fails
        """
        
    def _lookup_naccid(self, ptid: str, adcid: int) -> str:
        """Look up NACCID using PTID and ADCID.
        
        Uses IdentifiersLambdaRepository.get_naccid().
        
        Raises:
            LookupError: If no matching record found
            RepositoryError: If lookup service unavailable
        """
        
    def _update_subject_metadata(self, naccid: str) -> None:
        """Store NACCID in subject.info using configured field name.
        
        Uses SubjectAdaptor.update() to update subject.info
        
        Raises:
            UpdateError: If metadata update fails
        """
```

### 4.3 Early Data Extraction (Visitor Utilities)

**Responsibility:** Extract all required data from Flywheel objects as early as possible

**Design Philosophy:** Fail fast by extracting and validating all required data upfront. This approach:
- Catches missing data immediately before any processing
- Simplifies the processor by providing pre-validated data
- Makes the code more testable by separating extraction from business logic
- Enables early idempotency checks

**Extraction Functions:**

```python
def extract_pipeline_adcid(project: ProjectAdaptor) -> int:
    """Extract pipeline ADCID from project metadata.
    
    Uses ProjectAdaptor.get_pipeline_adcid() which handles fallback
    from "pipeline_adcid" to "adcid" in project.info.
    
    Args:
        project: Project adaptor
        
    Returns:
        Pipeline ADCID as integer
        
    Raises:
        ProjectError: If ADCID missing from project metadata
    """
    return project.get_pipeline_adcid()


def extract_ptid(
    subject: SubjectAdaptor,
    file_path: Path
) -> str:
    """Extract PTID from subject.label or DICOM PatientID tag.
    
    Priority:
    1. subject.label (if not empty)
    2. DICOM PatientID tag (0010,0020)
    
    Args:
        subject: Subject adaptor
        file_path: Path to DICOM file
        
    Returns:
        PTID as string
        
    Raises:
        ValueError: If both sources are empty/missing
        InvalidDicomError: If file is not valid DICOM
    """
    # Try subject.label first
    ptid = subject.label
    if ptid and ptid.strip():
        return ptid.strip()
    
    # Fallback to DICOM PatientID tag
    ptid = read_dicom_tag(file_path, (0x0010, 0x0020))
    if ptid and ptid.strip():
        return ptid.strip()
    
    raise ValueError(
        "PTID not found: subject.label is empty and DICOM PatientID tag is missing"
    )


def extract_existing_naccid(
    subject: SubjectAdaptor,
    naccid_field_name: str
) -> Optional[str]:
    """Extract existing NACCID from subject metadata.
    
    Args:
        subject: Subject adaptor
        naccid_field_name: Field name for NACCID in subject.info
        
    Returns:
        Existing NACCID if present, None otherwise
    """
    return subject.info.get(naccid_field_name)


def extract_visit_metadata(
    file_path: Path,
    ptid: str,
    adcid: int,
    naccid: Optional[str],
    default_modality: str
) -> DataIdentification:
    """Extract visit metadata from DICOM file.
    
    Args:
        file_path: Path to DICOM file
        ptid: Pre-extracted PTID
        adcid: Pre-extracted pipeline ADCID
        naccid: Pre-extracted or looked-up NACCID
        default_modality: Default modality if DICOM tag missing
        
    Returns:
        DataIdentification instance with ImageIdentification
        
    Raises:
        ValueError: If required fields (StudyDate) are missing
        InvalidDicomError: If file is not valid DICOM
    """
    # Extract date (required) - StudyDate is canonical per DICOM standard
    date = read_dicom_tag(file_path, (0x0008, 0x0020))  # StudyDate (required field)
    
    if not date:
        raise ValueError(
            "Visit date not found: StudyDate (0008,0020) is missing (required DICOM field)"
        )
    
    # Extract modality (use default if missing)
    modality = read_dicom_tag(file_path, (0x0008, 0x0060))
    if not modality:
        modality = default_modality
    
    return DataIdentification.from_visit_metadata(
        ptid=ptid,
        date=format_dicom_date(date),  # Convert YYYYMMDD to YYYY-MM-DD
        modality=modality,
        adcid=adcid,
        naccid=naccid,
        visitnum=None  # Images typically don't have visit numbers
    )


def extract_dicom_metadata(file_path: Path) -> dict[str, Any]:
    """Extract comprehensive DICOM metadata for storage.
    
    Extracts identifier and descriptive fields for tracking and reference.
    
    Args:
        file_path: Path to DICOM file
        
    Returns:
        Dictionary of DICOM metadata fields (None for missing optional fields)
        
    Raises:
        InvalidDicomError: If file is not valid DICOM
    """
    metadata = {}
    
    # Identifier fields
    metadata['patient_id'] = read_dicom_tag(file_path, (0x0010, 0x0020))  # PatientID
    metadata['study_instance_uid'] = read_dicom_tag(file_path, (0x0020, 0x000D))  # StudyInstanceUID
    metadata['series_instance_uid'] = read_dicom_tag(file_path, (0x0020, 0x000E))  # SeriesInstanceUID
    metadata['series_number'] = read_dicom_tag(file_path, (0x0020, 0x0011))  # SeriesNumber
    
    # Date fields
    metadata['study_date'] = read_dicom_tag(file_path, (0x0008, 0x0020))  # StudyDate
    metadata['series_date'] = read_dicom_tag(file_path, (0x0008, 0x0021))  # SeriesDate
    
    # Descriptive fields
    metadata['modality'] = read_dicom_tag(file_path, (0x0008, 0x0060))  # Modality
    metadata['magnetic_field_strength'] = read_dicom_tag(file_path, (0x0018, 0x0087))  # MagneticFieldStrength
    metadata['manufacturer'] = read_dicom_tag(file_path, (0x0008, 0x0070))  # Manufacturer
    metadata['manufacturer_model_name'] = read_dicom_tag(file_path, (0x0008, 0x1090))  # ManufacturerModelName
    metadata['series_description'] = read_dicom_tag(file_path, (0x0008, 0x103E))  # SeriesDescription
    metadata['images_in_acquisition'] = read_dicom_tag(file_path, (0x0020, 0x1002))  # ImagesInAcquisition
    
    return metadata
```

**Helper Functions:**

```python
def format_dicom_date(dicom_date: str) -> str:
    """Convert DICOM date format (YYYYMMDD) to ISO format (YYYY-MM-DD).
    
    Args:
        dicom_date: Date in DICOM format (YYYYMMDD)
        
    Returns:
        Date in ISO format (YYYY-MM-DD)
        
    Raises:
        ValueError: If date format is invalid
    """
    if len(dicom_date) != 8:
        raise ValueError(f"Invalid DICOM date format: {dicom_date}")
    
    try:
        year = dicom_date[0:4]
        month = dicom_date[4:6]
        day = dicom_date[6:8]
        return f"{year}-{month}-{day}"
    except Exception as error:
        raise ValueError(f"Failed to parse DICOM date: {dicom_date}") from error
```

### 4.4 DICOM Metadata Extraction

**Implementation using pydicom:**

```python
import pydicom
from pathlib import Path

def read_dicom_tag(file_path: Path, tag: tuple[int, int]) -> Optional[str]:
    """Read a DICOM tag value from file.
    
    Args:
        file_path: Path to DICOM file
        tag: DICOM tag as tuple (group, element), e.g., (0x0010, 0x0020)
        
    Returns:
        Tag value as string, or None if tag not found
        
    Raises:
        InvalidDicomError: If file is not a valid DICOM file
    """
    try:
        dcm = pydicom.dcmread(str(file_path), stop_before_pixels=True)
        if tag in dcm:
            return str(dcm[tag].value)
        return None
    except Exception as error:
        raise InvalidDicomError(f"Failed to read DICOM file: {error}") from error

# Usage examples:
patient_id = read_dicom_tag(file_path, (0x0010, 0x0020))  # PatientID
acquisition_date = read_dicom_tag(file_path, (0x0008, 0x0022))  # AcquisitionDate
study_date = read_dicom_tag(file_path, (0x0008, 0x0020))  # StudyDate
modality = read_dicom_tag(file_path, (0x0008, 0x0060))  # Modality
```

**DICOM Tags Used:**

**Identifier Tags:**
- `(0010,0020)` - PatientID: Patient identifier (PTID source)
- `(0020,000D)` - StudyInstanceUID: Unique study identifier
- `(0020,000E)` - SeriesInstanceUID: Unique series identifier
- `(0020,0011)` - SeriesNumber: Series number within study

**Date Tags:**
- `(0008,0020)` - StudyDate: Date of study (YYYYMMDD) - **canonical date per DICOM standard (required field)**
- `(0008,0021)` - SeriesDate: Date of series (YYYYMMDD) - optional

**Descriptive Tags:**
- `(0008,0060)` - Modality: Type of equipment (MR, CT, PET, etc.)
- `(0018,0087)` - MagneticFieldStrength: Field strength for MR
- `(0008,0070)` - Manufacturer: Equipment manufacturer
- `(0008,1090)` - ManufacturerModelName: Equipment model
- `(0008,103E)` - SeriesDescription: Description of series
- `(0020,1002)` - ImagesInAcquisition: Number of images in acquisition

**Note:** StudyDate is used as the canonical date because it is a required field in the DICOM standard. All other date fields (like AcquisitionDate, SeriesDate) are optional and should not be used as the primary date source.

### 4.5 QC Status Logging

**Integration with Existing Infrastructure:**

The gear reuses the existing QC status logging infrastructure from `common/src/python/error_logging/`, which has been updated to work with `DataIdentification`:

```python
# Initialization (in create method)
error_log_template = ErrorLogTemplate()
visit_annotator = FileVisitAnnotator(project=project)
qc_log_manager = QCStatusLogManager(
    error_log_template=error_log_template,
    visit_annotator=visit_annotator
)

# Usage (after processing)
data_id = DataIdentification.from_visit_metadata(
    ptid=result.ptid,
    date=result.data_identification.date,
    modality=result.data_identification.data.modality,  # ImageIdentification.modality
    adcid=pipeline_adcid,
    naccid=result.naccid
)

status = QC_STATUS_PASS if result.success else QC_STATUS_FAIL

qc_log_manager.update_qc_log(
    visit_keys=data_id,  # Accepts DataIdentification
    project=project,
    gear_name=gear_name,
    status=status,
    errors=FileErrorList(root=result.errors),
    add_visit_metadata=True  # Add metadata on initial creation
)
```

**QC Log Filename Format:**

The `ErrorLogTemplate` uses the visitor pattern to generate filenames from `DataIdentification`:

- Pattern: `{ptid}[_{visitnum}]_{date}_{modality}_qc-status.log`
- For images (no visitnum): `{ptid}_{date}_{modality}_qc-status.log`
- Example: `110001_2024-01-15_mr_qc-status.log`
- For comparison, form QC logs: `110001_001_2024-01-15_a1_i_qc-status.log`

**Key Changes from Original Design:**
- Uses `DataIdentification` instead of `ImageVisitMetadata`
- Modality is accessed via `data_id.data.modality` (ImageIdentification component)
- Filename generation uses visitor pattern (datatype-agnostic)
- No need to set `module=modality` - handled by composition

### 4.6 Event Capture

**Integration with Existing Infrastructure:**

The gear reuses the existing event capture infrastructure from `common/src/python/event_capture/`, which has been updated to use `DataIdentification`. Event capture is required for all image processing.

```python
# Initialization (in create method - required)
event_environment = context.config.get("event_environment")
event_bucket = context.config.get("event_bucket")

if not event_environment or not event_bucket:
    raise GearExecutionError(
        "event_environment and event_bucket are required configuration parameters"
    )

try:
    s3_bucket = S3BucketInterface.create_from_environment(event_bucket)
    event_capture = VisitEventCapture(
        s3_bucket=s3_bucket,
        environment=event_environment
    )
except ClientError as error:
    raise GearExecutionError(
        f"Failed to initialize event capture: Unable to access S3 bucket "
        f"'{event_bucket}'. Error: {error}"
    ) from error

# Usage (after successful processing)

# Extract comprehensive DICOM metadata for storage
dicom_metadata = extract_dicom_metadata(file_path)

# Store DICOM metadata in subject.info
subject.update({
    'dicom_metadata': dicom_metadata,
    naccid_field_name: result.naccid
})

# Create DataIdentification for event capture
data_id = DataIdentification.from_visit_metadata(
    ptid=result.ptid,
    date=result.data_identification.date,
    modality=result.data_identification.data.modality,
    adcid=pipeline_adcid,
    naccid=result.naccid
)

visit_event = VisitEvent(
    action=ACTION_SUBMIT,
    study="adrc",
    project_label=project.label,
    center_label=project.center_label,
    gear_name=gear_name,
    data_identification=data_id,
    datatype="dicom",  # Use "dicom" for image datatypes
    timestamp=datetime.now()
)

try:
    event_capture.capture_event(visit_event)
    log.info(f"Captured submission event for {result.ptid}")
except Exception as error:
    log.error(f"Failed to capture event: {error}")
    # Don't fail the entire operation for event capture failure
```

**Event Filename Format:**

The `VisitEventCapture` generates filenames:

- Pattern: `{env}/log-{action}-{timestamp}-{adcid}-{project}-{ptid}-{visit_date}.json`
- Example: `prod/log-submit-20240115-100000-42-imaging-project-110001-2024-01-15.json`

**Key Changes from Original Design:**

- Uses `DataIdentification` with `ImageIdentification` component
- VisitEvent accepts `data_identification` parameter (composition pattern)
- Datatype is "dicom" for images (not "image")
- No need to manually set module/packet - handled by composition
- Event serialization flattens DataIdentification for backward compatibility

## 5. Error Handling

### 5.1 Error Categories

**1. Input Validation Errors (Fail Early):**

- Missing or invalid input file
- File is not a valid DICOM file
- Pipeline ADCID missing from project metadata
- Pipeline ADCID invalid format
- PTID missing from both subject.label and DICOM PatientID tag
- Visit date (StudyDate) missing from DICOM file

**2. Configuration Errors (Fail Early):**

- Invalid database mode configuration
- Missing event capture configuration (event_environment or event_bucket) - REQUIRED
- S3 bucket not accessible during initialization

**3. Lookup Errors:**

- No matching identifier record found
- Identifier repository service unavailable
- Network/connectivity issues

**4. Metadata Update Errors:**

- NACCID field exists with different value (conflict)
- Subject metadata update fails (API error)
- Insufficient permissions

**5. QC Logging Errors (Non-Critical):**

- Failed to create/update QC status log
- Failed to add visit metadata to log file

**6. Event Capture Errors (Non-Critical):**

- Failed to write event to S3

### 5.2 Error Handling Strategy

```python
class ErrorHandler:
    """Centralized error handling for image identifier lookup."""
    
    def __init__(self, error_writer: ListErrorWriter):
        self.__error_writer = error_writer
        
    def create_ptid_extraction_error(self, error: Exception) -> FileError:
        """Create FileError for PTID extraction failures."""
        return FileError(
            error_type="error",
            error_code="PTID_EXTRACTION_FAILED",
            message=f"Failed to extract PTID: {str(error)}",
            timestamp=datetime.now().isoformat()
        )
        
    def create_lookup_error(self, ptid: str, adcid: int, error: Exception) -> FileError:
        """Create FileError for identifier lookup failures."""
        return FileError(
            error_type="error",
            error_code="NACCID_LOOKUP_FAILED",
            message=f"Failed to lookup NACCID for PTID={ptid}, ADCID={adcid}: {str(error)}",
            ptid=ptid,
            timestamp=datetime.now().isoformat()
        )
        
    def create_metadata_conflict_error(self, ptid: str, existing: str, new: str) -> FileError:
        """Create FileError for NACCID conflicts in subject metadata."""
        return FileError(
            error_type="error",
            error_code="NACCID_CONFLICT",
            message=f"NACCID conflict for PTID={ptid}: existing={existing}, new={new}",
            ptid=ptid,
            expected=new,
            value=existing,
            timestamp=datetime.now().isoformat()
        )
```

### 5.3 Error Recovery and Resilience

**Fail Fast Strategy:**

The gear extracts all required data early and fails immediately if any critical data is missing:
- Pipeline ADCID from project metadata
- PTID from subject.label or DICOM PatientID
- Visit date from DICOM AcquisitionDate or StudyDate

This prevents wasted processing time and provides clear error messages upfront.

**Idempotency Check:**

After extracting existing NACCID from subject.info, the gear checks if processing is needed:
- If NACCID exists: Skip lookup and metadata update, proceed to QC logging and event capture
- This allows safe re-runs without errors or unnecessary API calls

**QC Logging Failures (Non-Critical):**

- Log error but don't fail the entire operation
- Continue with event capture and file metadata updates
- Rationale: QC log is for tracking, not critical to core functionality

**Event Capture Failures (Non-Critical):**

- Log error but don't fail the entire operation
- Continue with file metadata updates
- Rationale: Event capture is for auditing; the core identifier lookup has already succeeded

**Critical Failures (Fail the Gear):**

- Input file not found or invalid
- File is not a valid DICOM file
- Pipeline ADCID missing or invalid format
- PTID extraction fails (both sources empty)
- Visit date (StudyDate) missing from DICOM file (required DICOM field)
- Event capture not configured (missing event_environment or event_bucket) - REQUIRED
- S3 bucket not accessible during initialization
- Identifier lookup fails (no matching record)
- NACCID conflict (existing value differs from lookup result)
- Subject metadata update fails

## 6. Configuration

### 6.1 Gear Manifest Configuration

```json
{
    "config": {
        "database_mode": {
            "description": "Database mode for identifier repository (prod/dev)",
            "type": "string",
            "enum": ["prod", "dev"],
            "default": "prod"
        },
        "naccid_field_name": {
            "description": "Field name for NACCID in subject metadata",
            "type": "string",
            "default": "naccid"
        },
        "default_modality": {
            "description": "Default modality when DICOM tag is missing",
            "type": "string",
            "default": "UNKNOWN"
        },
        "event_environment": {
            "description": "Environment prefix for event capture (prod/dev) - REQUIRED",
            "type": "string"
        },
        "event_bucket": {
            "description": "S3 bucket name for event storage - REQUIRED",
            "type": "string"
        },
        "admin_group": {
            "description": "NACC admin group ID",
            "type": "string",
            "default": "nacc"
        },
        "apikey_path_prefix": {
            "description": "AWS parameter path prefix for API key",
            "type": "string",
            "default": "/prod/flywheel/gearbot"
        }
    },
    "inputs": {
        "api-key": {
            "base": "api-key"
        },
        "input_file": {
            "description": "DICOM image file for identifier lookup",
            "base": "file",
            "type": {
                "enum": ["dicom"]
            }
        }
    }
}
```

### 6.2 Configuration Validation

**Event Capture:**

- Both `event_environment` and `event_bucket` are required
- Gear fails during initialization if either is missing
- S3 bucket accessibility is verified during initialization

**Database Mode:**

- Must be either "prod" or "dev"
- Determines which identifier repository database to query

**Field Names:**

- `naccid_field_name` must be a valid Python identifier
- Used as key in subject.info dictionary

## 7. Code Reuse Strategy

### 7.1 Existing Components to Reuse

**From `common/src/python/`:**

1. **identifiers/** - Identifier lookup
   - `IdentifiersLambdaRepository`: Query identifier database
   - `IdentifierRepository`: Abstract interface
   - `model.py`: PTID patterns and validation

2. **error_logging/** - QC status logging (✅ Updated for DataIdentification)
   - `QCStatusLogManager`: Manage QC status logs
   - `FileVisitAnnotator`: Add visit metadata to log files
   - `ErrorLogTemplate`: Generate QC log filenames using visitor pattern
   - `error_logger.py`: Update error logs and QC metadata

3. **event_capture/** - Event logging (✅ Updated for DataIdentification)
   - `VisitEventCapture`: Capture events to S3
   - `visit_events.py`: VisitEvent model with DataIdentification support

4. **flywheel_adaptor/** - Flywheel API interactions
   - `ProjectAdaptor`: Project operations and metadata
   - `SubjectAdaptor`: Subject operations and metadata
   - `flywheel_proxy.py`: Proxy classes for Flywheel objects

5. **gear_execution/** - Gear framework
   - `GearExecutionEnvironment`: Base class for gear visitors
   - `ClientWrapper`, `GearBotClient`: Flywheel client management
   - `InputFileWrapper`: Input file handling

6. **s3/** - S3 operations
   - `S3BucketInterface`: S3 bucket operations for event storage

**From `nacc-common/src/python/nacc_common/` (✅ Refactored Architecture):**

1. **data_identification.py**
   - `DataIdentification`: Base class using composition pattern
   - `ParticipantIdentification`: Participant and center identification
   - `VisitIdentification`: Visit number identification
   - `ImageIdentification`: Image-specific data (modality)
   - `AbstractIdentificationVisitor`: Visitor pattern interface

2. **error_models.py**
   - `FileError`, `FileErrorList`: Error models
   - `QCStatus`: QC status literals
   - `GearTags`: Gear tagging utilities

### 7.2 New Components to Create

**In `gear/image_identifier_lookup/src/python/image_identifier_lookup_app/`:**

1. **extraction.py**
   - `extract_pipeline_adcid()`: Extract ADCID from project metadata
   - `extract_ptid()`: Extract PTID from subject or DICOM
   - `extract_existing_naccid()`: Extract existing NACCID from subject.info
   - `extract_visit_metadata()`: Extract visit metadata from DICOM and create DataIdentification
   - `format_dicom_date()`: Convert DICOM date to ISO format

2. **dicom_utils.py**
   - `read_dicom_tag()`: Read DICOM tag value from file
   - `InvalidDicomError`: Custom exception for DICOM errors

3. **processor.py**
   - `ImageIdentifierLookupProcessor`: Simplified business logic
   - Receives pre-extracted data, performs lookup and update

4. **run.py**
   - `ImageIdentifierLookupVisitor`: Gear execution visitor
   - Main entry point and orchestration
   - Performs early extraction and fail-fast validation

5. **main.py**
   - `run()`: Main execution function
   - High-level workflow coordination

6. **models.py** (optional)
   - `ProcessResult`: Internal result object if needed for complex state tracking

### 7.3 Refactoring Status (✅ COMPLETED)

**Visit Metadata Architecture Refactoring**

The visit metadata architecture has been successfully refactored in the merged refactor/visit-metadata branch:

✅ **Completed Changes:**

1. **DataIdentification with Composition Pattern**
   - Replaced flat `VisitKeys`/`VisitMetadata` with composition-based `DataIdentification`
   - Component classes: `ParticipantIdentification`, `VisitIdentification`, `FormIdentification`, `ImageIdentification`
   - Visitor pattern for datatype-agnostic operations

2. **Image Support**
   - `ImageIdentification` class with modality field
   - No form-specific fields (packet) in image metadata
   - Seamless integration with QCStatusLogManager, FileVisitAnnotator, VisitEventCapture

3. **Enhanced QC Log Filenames**
   - Visitor pattern generates filenames: `{ptid}[_{visitnum}]_{date}_{modality}_qc-status.log`
   - Backward compatible with legacy filenames
   - Works for any datatype through visitor pattern

4. **Event Capture Updates**
   - VisitEvent uses `data_identification: DataIdentification`
   - Supports "dicom" datatype for images
   - Flat serialization for backward compatibility

**Benefits Realized:**

- Clean separation of datatype-specific fields
- Easy to add new datatypes (genomic, biospecimen, etc.)
- Full backward compatibility with existing form processing code
- Datatype-agnostic utilities through visitor pattern
- No need for workarounds like `module="image"`

## 8. Testing Strategy

### 8.1 Unit Tests

**Test Coverage:**

1. **Early Data Extraction Tests** (`test_early_extraction.py`)
   - Extract pipeline ADCID from project metadata
   - Extract PTID from subject.label (primary)
   - Extract PTID from DICOM PatientID tag (fallback)
   - Extract existing NACCID from subject.info
   - Extract visit metadata from DICOM (date, modality)
   - Fail fast when ADCID missing
   - Fail fast when ADCID invalid format
   - Fail fast when PTID missing from both sources
   - Fail fast when visit date missing from both DICOM tags

2. **Idempotency Tests** (`test_idempotency.py`)
   - Skip lookup when NACCID already exists in subject.info
   - Still create QC log and capture event on skip
   - Detect NACCID conflict (existing differs from lookup)

3. **NACCID Lookup Tests** (`test_naccid_lookup.py`)
   - Successful lookup with valid PTID/ADCID
   - Error when no matching record
   - Error when repository unavailable

4. **Subject Metadata Update Tests** (`test_metadata_update.py`)
   - Store NACCID in subject.info
   - Error when update fails

5. **Visit Metadata Tests** (`test_visit_metadata.py`)
   - Extract StudyDate (canonical date per DICOM standard)
   - Extract modality from DICOM tag
   - Use default modality when tag missing
   - Format DICOM date (YYYYMMDD) to ISO format (YYYY-MM-DD)
   - Fail when StudyDate is missing (required field)

6. **DICOM Metadata Extraction Tests** (`test_dicom_metadata.py`)
   - Extract all identifier fields (PatientID, StudyInstanceUID, SeriesInstanceUID, SeriesNumber)
   - Extract all descriptive fields (MagneticFieldStrength, Manufacturer, etc.)
   - Handle missing optional tags gracefully (store None/null)
   - Store metadata in subject.info

6. **QC Status Logging Tests** (`test_qc_logging.py`)
   - Create QC status log on success
   - Create QC status log on failure
   - Add visit metadata to log file
   - Handle QC logging failures gracefully

7. **Event Capture Tests** (`test_event_capture.py`)
   - Capture submission event on success
   - Handle event capture failures gracefully
   - Verify event structure for images
   - Fail initialization when event capture not configured

8. **Error Handling Tests** (`test_error_handling.py`)
   - Collect and report all errors
   - Add QC metadata to input file
   - Add gear tags (PASS/FAIL)
   - Fail fast on missing required data

9. **DICOM Parsing Tests** (`test_dicom_parsing.py`)
   - Read DICOM tags successfully
   - Error on invalid DICOM file
   - Handle missing optional tags gracefully

### 8.2 Integration Tests

**Test Scenarios:**

1. **End-to-End Success Flow**
   - Input: Valid DICOM file with PatientID
   - Project has pipeline ADCID
   - Subject has no existing NACCID
   - All data extracted successfully
   - Identifier lookup succeeds
   - Subject metadata updated
   - QC log created with PASS status
   - Event captured
   - File tagged with gear-PASS

2. **End-to-End Failure Flow**
   - Input: Valid DICOM file
   - All data extracted successfully
   - Identifier lookup fails (no matching record)
   - QC log created with FAIL status
   - Event captured
   - File tagged with gear-FAIL

3. **Idempotent Re-run (NACCID Already Exists)**
   - First run: successful lookup and update
   - Second run: NACCID detected early, skip lookup
   - Both runs create QC log and capture event
   - Both runs succeed

4. **NACCID Conflict**
   - Subject already has NACCID in metadata
   - Lookup returns different NACCID value
   - Gear fails with conflict error
   - QC log created with FAIL status

5. **Fail Fast - Missing ADCID**
   - Project metadata missing pipeline ADCID
   - Gear fails immediately during extraction
   - No lookup attempted
   - Clear error message provided

6. **Fail Fast - Missing PTID**
   - Subject.label is empty
   - DICOM PatientID tag is missing
   - Gear fails immediately during extraction
   - No lookup attempted

7. **Fail Fast - Missing Visit Date (StudyDate)**
   - DICOM StudyDate tag is missing (required DICOM field)
   - Gear fails immediately during extraction
   - No lookup attempted
   - Clear error message provided

### 8.3 Property-Based Tests

Following the pattern from identifier_lookup gear, implement property-based tests for:

1. **Early Extraction Determinism**
   - Property: Extracting data from same Flywheel objects always returns same values
   - Given same project/subject/file, extraction is deterministic

2. **PTID Extraction Consistency**
   - Property: PTID extraction follows priority order consistently
   - subject.label takes precedence over DICOM PatientID

3. **Visit Metadata Completeness**
   - Property: Visit metadata always has required fields (ptid, date, module)
   - Generated for any valid DICOM file with required tags

4. **Date Format Conversion**
   - Property: DICOM date (YYYYMMDD) always converts to valid ISO date (YYYY-MM-DD)
   - Conversion is reversible and preserves date value

5. **QC Status Determination**
   - Property: QC status is PASS if and only if no errors occurred
   - QC status is FAIL if any error occurred

6. **Event Structure Validity**
   - Property: All captured events have valid structure
   - Required fields are always present
   - Datatype is always "image"

7. **Idempotency**
   - Property: Running gear twice with same input produces same final state
   - Second run detects existing NACCID and skips lookup
   - Both runs succeed and produce same metadata

8. **Fail Fast Consistency**
   - Property: Missing required data always fails before any processing
   - No partial state changes when extraction fails

## 9. Dependencies

### 9.1 Python Packages

**Required:**

- `flywheel-sdk>=20.0.0` - Flywheel platform SDK
- `flywheel-gear-toolkit>=0.2` - Gear development toolkit
- `pydantic>=2.5.2` - Data validation
- `pydicom>=2.4.0` - DICOM file parsing
- `boto3>=1.28.53` - AWS SDK (for S3 and Lambda)

**From Internal Packages:**

- `nacc-common` - Error models, field names
- `common` - All shared utilities

### 9.2 AWS Services

- **Lambda**: Identifier lookup service
- **S3**: Event storage (transaction log)
- **SSM Parameter Store**: API key storage

### 9.3 Flywheel Resources

- **Subject**: Parent container for image
- **Project**: Parent container for subject, stores pipeline ADCID
- **File**: Input DICOM file and QC status logs

## 10. Deployment

### 10.1 Docker Image

**Base Image:** Python 3.11

**Additional Requirements:**

- pydicom for DICOM parsing
- All dependencies from requirements.txt

**Build Configuration:**

```dockerfile
FROM python:3.11-slim

# Install system dependencies if needed
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy gear code
COPY src/python/image_identifier_lookup_app /flywheel/v0/app

# Set entrypoint
ENTRYPOINT ["/flywheel/v0/app/run.py"]
```

### 10.2 Gear Registration

**Gear Metadata:**

- Name: `image-identifier-lookup`
- Label: `Image Identifier Lookup`
- Category: `utility`
- Suite: `Utility`
- Version: `0.1.0`

**Permissions Required:**

- Read access to input file
- Read/write access to subject metadata
- Read access to project metadata
- Write access to project files (for QC logs)
- Write access to S3 bucket (for event capture)

### 10.3 Environment Variables

**Required:**

- `FLYWHEEL`: Flywheel environment path (default: `/flywheel/v0`)

**Optional (from configuration):**

- AWS credentials (for Lambda and S3 access)
- Configured via IAM role or environment variables

## 11. Monitoring and Observability

### 11.1 Logging

**Log Levels:**

- `INFO`: Normal operation (successful lookups, QC log creation, event capture)
- `WARNING`: Non-critical issues (QC logging failures, event capture failures)
- `ERROR`: Critical failures (lookup failures, metadata conflicts, missing configuration)

**Key Log Messages:**

```python
log.info(f"Processing image file: {file_path}")
log.info(f"Extracted PTID: {ptid} from subject.label")
log.info(f"Extracted PTID: {ptid} from DICOM PatientID tag")
log.info(f"Pipeline ADCID: {adcid}")
log.info(f"NACCID lookup successful: {naccid}")
log.info(f"Subject metadata updated with NACCID: {naccid}")
log.info(f"Skipping update - NACCID already set correctly: {naccid}")
log.info(f"QC status log created: {qc_log_filename}")
log.info(f"Submission event captured for {ptid}")

log.warning(f"Failed to create QC status log: {error}")
log.warning(f"Failed to capture event: {error}")

log.error(f"Failed to extract PTID: {error}")
log.error(f"Pipeline ADCID missing from project metadata")
log.error(f"NACCID lookup failed for PTID={ptid}, ADCID={adcid}: {error}")
log.error(f"NACCID conflict: existing={existing}, new={new}")
log.error(f"Failed to update subject metadata: {error}")
```

### 11.2 Metrics

**Success Metrics:**

- Number of successful lookups
- Number of skipped updates (idempotent re-runs)
- QC logs created
- Events captured

**Failure Metrics:**

- Number of failed lookups
- Number of NACCID conflicts
- Number of metadata update failures
- Number of QC logging failures
- Number of event capture failures

**Performance Metrics:**

- Gear execution time
- Identifier lookup latency
- DICOM parsing time

### 11.3 Alerting

**Critical Alerts:**

- High rate of lookup failures (> 10% in 1 hour)
- High rate of NACCID conflicts (> 5% in 1 hour)
- Identifier repository unavailable
- S3 bucket inaccessible

**Warning Alerts:**

- High rate of QC logging failures (> 20% in 1 hour)
- High rate of event capture failures (> 20% in 1 hour)

## 12. Security Considerations

### 12.1 Data Protection

**PHI/PII Handling:**

- PTID, NACCID are identifiers (PHI)
- DICOM files may contain PHI in metadata
- All data remains within Flywheel platform
- No PHI logged to external systems

**Access Control:**

- Gear runs with GearBot credentials
- Requires appropriate Flywheel permissions
- AWS credentials for Lambda and S3 access

### 12.2 API Key Management

- API keys stored in AWS SSM Parameter Store
- Retrieved at runtime via ParameterStore utility
- Never logged or exposed in error messages

### 12.3 Input Validation

- Validate DICOM file format before processing
- Validate PTID format (matches PTID_PATTERN)
- Validate ADCID is positive integer
- Validate date format (YYYY-MM-DD)

## 13. Future Enhancements

### 13.1 DICOM PatientID Replacement (Out of Scope for This Gear)

**Status:** OUT OF SCOPE for this gear - should be handled later in the pipeline

**Rationale:**
- This gear focuses on identifier lookup and metadata storage
- PatientID replacement is a data transformation that should occur after validation
- Separating concerns allows for better control over when de-identification occurs
- A dedicated de-identification gear can handle this along with other PHI removal tasks

**Future Implementation Notes:**
- Consider creating a separate DICOM de-identification gear
- Should run after QC validation and before data acceptance
- Should preserve original files and create de-identified copies
- Should maintain audit trail of transformations
- Should handle all PHI fields, not just PatientID

### 13.2 Batch Processing

**Current:** One file per gear execution

**Future:** Process multiple images in a single execution

- Accept directory or multiple file inputs
- Parallel processing for efficiency
- Aggregate QC reporting

### 13.3 Additional DICOM Metadata

**Current:** Extract PatientID, StudyDate, Modality, plus comprehensive metadata (StudyInstanceUID, SeriesInstanceUID, SeriesNumber, MagneticFieldStrength, Manufacturer, ManufacturerModelName, SeriesDescription, ImagesInAcquisition)

**Future:** Extract and store additional metadata for advanced use cases

- StudyDescription
- ProtocolName
- Image dimensions and resolution
- Additional scanner-specific parameters

### 13.4 Image Quality Checks

**Current:** Only identifier lookup

**Future:** Add image quality validation

- Check for required DICOM tags
- Validate image dimensions
- Check for corruption
- Verify modality-specific requirements

### 13.5 Multi-Center Support

**Current:** Single center per project (pipeline ADCID)

**Future:** Support multiple centers in one project

- Extract center from DICOM metadata
- Map to ADCID dynamically
- Support center-specific configurations

### 13.6 Generalized Metadata Architecture (✅ COMPLETED)

**Status:** This has been completed in the refactor/visit-metadata branch (merged)

**Implementation:**
- `DataIdentification` with composition pattern (replaces VisitKeys/VisitMetadata)
- Component classes: `ParticipantIdentification`, `VisitIdentification`
- Datatype-specific components: `FormIdentification` (packet), `ImageIdentification` (modality)
- Visitor pattern for datatype-agnostic operations
- Full backward compatibility with existing code

**Benefits Realized:**
- Consistent metadata structure across datatypes
- Easy to add new datatypes (genomic, biospecimen, etc.)
- Shared utilities work polymorphically via visitor pattern
- Clean separation of concerns

## 14. Implementation Plan

### Phase 1: Core Functionality (MVP)

1. Create ImageVisitMetadata model
2. Implement DicomMetadataExtractor
3. Implement ImageIdentifierLookupProcessor
4. Implement ImageIdentifierLookupVisitor
5. Update manifest.json with configuration
6. Basic unit tests

### Phase 2: QC and Event Integration

1. Integrate QCStatusLogManager
2. Integrate VisitEventCapture
3. Add file QC metadata updates
4. Add gear tagging
5. Integration tests

### Phase 3: Error Handling and Resilience

1. Implement comprehensive error handling
2. Add idempotency logic
3. Add conflict detection
4. Error handling tests

### Phase 4: Testing and Documentation

1. Complete unit test coverage
2. Add property-based tests
3. Integration tests
4. Update gear documentation
5. Add usage examples

### Phase 5: Deployment and Monitoring

1. Build Docker image
2. Register gear in Flywheel
3. Set up monitoring and alerting
4. Deploy to test environment
5. User acceptance testing
6. Deploy to production

## 15. Acceptance Criteria

The implementation will be considered complete when:

1. ✅ Gear successfully extracts PTID from subject.label or DICOM PatientID tag
2. ✅ Gear successfully extracts pipeline ADCID from project metadata
3. ✅ Gear successfully looks up NACCID using IdentifiersLambdaRepository
4. ✅ Gear successfully stores NACCID in subject metadata
5. ✅ Gear creates QC status log at project level with visit metadata
6. ✅ Gear captures submission event to S3 transaction log (when enabled)
7. ✅ Gear adds QC metadata and tags to input file
8. ✅ Gear handles idempotent re-runs correctly (skip update if NACCID already correct)
9. ✅ Gear detects and reports NACCID conflicts
10. ✅ Gear handles errors gracefully with appropriate error messages
11. ✅ All unit tests pass
12. ✅ All integration tests pass
13. ✅ All property-based tests pass
14. ✅ Code follows project style guidelines (passes `pants fix`, `pants lint`, `pants check`)
15. ✅ Documentation is complete and accurate

## 16. Appendix

### 16.1 DICOM Tag Reference

**Identifier Tags:**

| Tag | Name | Description | Usage |
|-----|------|-------------|-------|
| (0010,0020) | PatientID | Patient identifier | PTID extraction (fallback) |
| (0020,000D) | StudyInstanceUID | Unique study identifier | Metadata storage |
| (0020,000E) | SeriesInstanceUID | Unique series identifier | Metadata storage |
| (0020,0011) | SeriesNumber | Series number within study | Metadata storage |

**Date Tags:**

| Tag | Name | Description | Usage |
|-----|------|-------------|-------|
| (0008,0020) | StudyDate | Date of study (YYYYMMDD) | Visit date (canonical - required DICOM field) |
| (0008,0021) | SeriesDate | Date of series (YYYYMMDD) | Metadata storage (optional) |

**Descriptive Tags:**

| Tag | Name | Description | Usage |
|-----|------|-------------|-------|
| (0008,0060) | Modality | Equipment type (MR, CT, PET, etc.) | Visit metadata |
| (0018,0087) | MagneticFieldStrength | Field strength for MR | Metadata storage |
| (0008,0070) | Manufacturer | Equipment manufacturer | Metadata storage |
| (0008,1090) | ManufacturerModelName | Equipment model | Metadata storage |
| (0008,103E) | SeriesDescription | Description of series | Metadata storage |
| (0020,1002) | ImagesInAcquisition | Number of images | Metadata storage |

### 16.2 Error Codes

| Code | Description | Severity | Action |
|------|-------------|----------|--------|
| PTID_EXTRACTION_FAILED | Failed to extract PTID from subject or DICOM | ERROR | Check subject.label and DICOM PatientID tag |
| ADCID_MISSING | Pipeline ADCID not found in project metadata | ERROR | Add pipeline ADCID to project metadata |
| NACCID_LOOKUP_FAILED | Identifier lookup failed | ERROR | Verify PTID/ADCID combination exists in database |
| NACCID_CONFLICT | NACCID mismatch in subject metadata | ERROR | Investigate data inconsistency |
| METADATA_UPDATE_FAILED | Failed to update subject metadata | ERROR | Check Flywheel API permissions |
| INVALID_DICOM | File is not a valid DICOM file | ERROR | Verify input file format |
| MISSING_DATE | StudyDate is missing (required DICOM field) | ERROR | Check DICOM file completeness |

### 16.3 Glossary

- **ADCID**: Alzheimer's Disease Research Center Identifier
- **DICOM**: Digital Imaging and Communications in Medicine
- **NACCID**: National Alzheimer's Coordinating Center Identifier
- **PTID**: Participant Identifier
- **QC**: Quality Control
- **Modality**: Type of imaging equipment (MR, CT, PET, etc.)
- **StudyDate**: Date of the imaging study (DICOM tag 0008,0020) - canonical date field, required in DICOM standard
- **PatientID**: DICOM tag (0010,0020) containing patient identifier
- **StudyInstanceUID**: Unique identifier for a DICOM study
- **SeriesInstanceUID**: Unique identifier for a DICOM series
- **SeriesNumber**: Series number within a study

### 16.4 References

- [DICOM Standard](https://www.dicomstandard.org/)
- [pydicom Documentation](https://pydicom.github.io/)
- [Flywheel SDK Documentation](https://flywheel-io.gitlab.io/product/backend/sdk/branches/master/python/)
- [NACC Data Platform Documentation](https://naccdata.github.io/flywheel-gear-extensions/)
