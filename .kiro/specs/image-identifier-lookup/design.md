# Design Document: Image Identifier Lookup Gear

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
│  └──────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 5. QC Status Logging                                     │  │
│  │    - Create/update project-level QC status log          │  │
│  │    - Add visit metadata to log file                      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 6. Event Capture                                          │  │
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
│                    ImageVisitMetadata                            │
│                    (extends VisitKeys)                           │
├─────────────────────────────────────────────────────────────────┤
│  + ptid: str                                                     │
│  + date: str                                                     │
│  + modality: str                                                 │
│  + adcid: Optional[int]                                         │
│  + naccid: Optional[str]                                        │
│  + module: str = "image"  # Fixed value for images              │
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
└─────────────────────────────────────────────────────────────────┘
```

## 3. Data Models

### 3.1 ImageVisitMetadata

A new datatype-specific metadata class extending the base `VisitKeys` model:

```python
class ImageVisitMetadata(VisitKeys):
    """Visit metadata specific to image datatypes.
    
    Extends VisitKeys with image-specific fields while maintaining
    compatibility with the generalized metadata architecture.
    
    For images, modality serves the same role as module does for forms:
    - Forms use module: "uds", "ivp", "tvp", etc.
    - Images use modality: "MR", "CT", "PET", etc.
    """
    modality: str  # DICOM Modality tag (0008,0060) - e.g., "MR", "CT", "PET"
    
    # Inherited from VisitKeys:
    # - ptid: Optional[str]
    # - date: Optional[str]  # From AcquisitionDate or StudyDate
    # - adcid: Optional[int]
    # - naccid: Optional[str]
    # - module: Optional[str]  # Set to modality value for images
    # - visitnum: Optional[str]  # Not used for images
```

**Design Rationale:**

- Extends `VisitKeys` to maintain compatibility with existing utilities
- For images, `module` field is set to the `modality` value (MR, CT, PET, etc.)
  - This parallels how forms use module (uds, ivp, tvp)
  - Modality is the natural categorization for imaging data
- Adds explicit `modality` field for clarity and type safety
- Does NOT include form-specific fields like `packet`
- Allows future extension for other datatypes (e.g., `GenomicVisitMetadata`, `BiospecimenVisitMetadata`)

### 3.2 ProcessResult

Internal result object for tracking processing outcomes:

```python
@dataclass
class ProcessResult:
    """Result of image identifier lookup processing."""
    success: bool
    ptid: str
    naccid: Optional[str]
    visit_metadata: ImageVisitMetadata
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
           - Visit metadata from DICOM (date, modality)
        3. Check idempotency: if NACCID already exists, skip to step 6
        4. Perform NACCID lookup using IdentifiersLambdaRepository
        5. Update subject metadata with NACCID
        6. Update QC status log
        7. Capture submission event
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
        
        Uses SubjectAdaptor.update_info()
        
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
    
    Args:
        project: Project adaptor
        
    Returns:
        Pipeline ADCID as integer
        
    Raises:
        ValueError: If ADCID missing or invalid format
    """
    adcid = project.get_metadata_value("pipeline_adcid")
    if not adcid:
        raise ValueError("Pipeline ADCID not found in project metadata")
    
    try:
        return int(adcid)
    except (ValueError, TypeError) as error:
        raise ValueError(f"Invalid pipeline ADCID format: {adcid}") from error


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
    return subject.get_info_value(naccid_field_name)


def extract_visit_metadata(
    file_path: Path,
    ptid: str,
    adcid: int,
    naccid: Optional[str],
    default_modality: str
) -> ImageVisitMetadata:
    """Extract visit metadata from DICOM file.
    
    Args:
        file_path: Path to DICOM file
        ptid: Pre-extracted PTID
        adcid: Pre-extracted pipeline ADCID
        naccid: Pre-extracted or looked-up NACCID
        default_modality: Default modality if DICOM tag missing
        
    Returns:
        ImageVisitMetadata instance
        
    Raises:
        ValueError: If required fields (date) are missing
        InvalidDicomError: If file is not valid DICOM
    """
    # Extract date (required)
    date = read_dicom_tag(file_path, (0x0008, 0x0022))  # AcquisitionDate
    if not date:
        date = read_dicom_tag(file_path, (0x0008, 0x0020))  # StudyDate fallback
    
    if not date:
        raise ValueError(
            "Visit date not found: both AcquisitionDate and StudyDate are missing"
        )
    
    # Extract modality (use default if missing)
    modality = read_dicom_tag(file_path, (0x0008, 0x0060))
    if not modality:
        modality = default_modality
    
    return ImageVisitMetadata(
        ptid=ptid,
        date=format_dicom_date(date),  # Convert YYYYMMDD to YYYY-MM-DD
        modality=modality,
        module=modality,  # For images, module = modality
        adcid=adcid,
        naccid=naccid
    )
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

- `(0010,0020)` - PatientID: Patient identifier
- `(0008,0022)` - AcquisitionDate: Date image was acquired (YYYYMMDD)
- `(0008,0020)` - StudyDate: Date of study (YYYYMMDD) - fallback for date
- `(0008,0060)` - Modality: Type of equipment (MR, CT, PET, etc.)

### 4.5 QC Status Logging

**Integration with Existing Infrastructure:**

The gear reuses the existing QC status logging infrastructure from `common/src/python/error_logging/`:

```python
# Initialization (in create method)
error_log_template = ErrorLogTemplate()
visit_annotator = FileVisitAnnotator(project=project)
qc_log_manager = QCStatusLogManager(
    error_log_template=error_log_template,
    visit_annotator=visit_annotator
)

# Usage (after processing)
visit_keys = ImageVisitMetadata(
    ptid=result.ptid,
    date=result.visit_metadata.date,
    modality=result.visit_metadata.modality,
    module=result.visit_metadata.modality,  # module = modality for images
    adcid=pipeline_adcid,
    naccid=result.naccid
)

status = QC_STATUS_PASS if result.success else QC_STATUS_FAIL

qc_log_manager.update_qc_log(
    visit_keys=visit_keys,
    project=project,
    gear_name=gear_name,
    status=status,
    errors=FileErrorList(root=result.errors),
    add_visit_metadata=True  # Add metadata on initial creation
)
```

**QC Log Filename Format:**

The `ErrorLogTemplate` generates filenames based on the visit keys using the pattern:

- Pattern: `{ptid}_{date}_{module}_qc-status.log`
- For images: `module` is set to the modality value (MR, CT, PET, etc.)
- Example: `110001_2024-01-15_MR_qc-status.log`
- For comparison, form QC logs use: `110001_2024-01-15_uds_qc-status.log`

**Note on Module Field:** For images, modality serves the same role as module does for forms:
- Forms categorize by module: "uds", "ivp", "tvp", etc.
- Images categorize by modality: "MR", "CT", "PET", etc.
- This provides natural categorization and makes QC log filenames descriptive

### 4.6 Event Capture

**Integration with Existing Infrastructure:**

The gear reuses the existing event capture infrastructure from `common/src/python/event_capture/`. Event capture is required for all image processing.

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
visit_event = VisitEvent(
    action=ACTION_SUBMIT,
    study="adrc",
    pipeline_adcid=pipeline_adcid,
    project_label=project.label,
    center_label=project.center_label,
    gear_name=gear_name,
    ptid=result.ptid,
    visit_date=result.visit_metadata.date,  # From AcquisitionDate/StudyDate
    visit_number=None,  # Not applicable for images
    datatype="image",
    module=None,  # Images don't have form modules
    packet=None,  # Not applicable for images
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

**Key Differences from Form Events:**

- `datatype="image"` instead of `"form"`
- `module=None` (no form module for images)
- `packet=None` (not applicable to images)
- `visit_number=None` (typically not used for imaging visits)

## 5. Error Handling

### 5.1 Error Categories

**1. Input Validation Errors (Fail Early):**

- Missing or invalid input file
- File is not a valid DICOM file
- Pipeline ADCID missing from project metadata
- Pipeline ADCID invalid format
- PTID missing from both subject.label and DICOM PatientID tag
- Visit date missing from both AcquisitionDate and StudyDate tags

**2. Configuration Errors (Fail Early):**

- Invalid database mode configuration
- Missing event capture configuration (event_environment or event_bucket)
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
        
    def handle_ptid_extraction_error(self, error: Exception) -> FileError:
        """Handle errors during PTID extraction."""
        return FileError(
            error_type="error",
            error_code="PTID_EXTRACTION_FAILED",
            message=f"Failed to extract PTID: {str(error)}",
            timestamp=datetime.now().isoformat()
        )
        
    def handle_lookup_error(self, ptid: str, adcid: int, error: Exception) -> FileError:
        """Handle identifier lookup errors."""
        return FileError(
            error_type="error",
            error_code="NACCID_LOOKUP_FAILED",
            message=f"Failed to lookup NACCID for PTID={ptid}, ADCID={adcid}: {str(error)}",
            ptid=ptid,
            timestamp=datetime.now().isoformat()
        )
        
    def handle_metadata_conflict(self, ptid: str, existing: str, new: str) -> FileError:
        """Handle NACCID conflict in subject metadata."""
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
- Visit date missing (both DICOM tags empty)
- Event capture not configured (missing event_environment or event_bucket)
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

2. **error_logging/** - QC status logging
   - `QCStatusLogManager`: Manage QC status logs
   - `FileVisitAnnotator`: Add visit metadata to log files
   - `ErrorLogTemplate`: Generate QC log filenames
   - `error_logger.py`: Update error logs and QC metadata

3. **event_capture/** - Event logging
   - `VisitEventCapture`: Capture events to S3
   - `visit_events.py`: VisitEvent model

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

**From `nacc-common/src/python/nacc_common/`:**

1. **error_models.py**
   - `VisitKeys`: Base visit identification model
   - `FileError`, `FileErrorList`: Error models
   - `QCStatus`: QC status literals
   - `GearTags`: Gear tagging utilities

### 7.2 New Components to Create

**In `gear/image_identifier_lookup/src/python/image_identifier_lookup_app/`:**

1. **models.py**
   - `ImageVisitMetadata`: Image-specific visit metadata (extends VisitKeys)
   - `ProcessResult`: Internal result object (may be simplified or removed)

2. **extraction.py**
   - `extract_pipeline_adcid()`: Extract ADCID from project metadata
   - `extract_ptid()`: Extract PTID from subject or DICOM
   - `extract_existing_naccid()`: Extract existing NACCID from subject.info
   - `extract_visit_metadata()`: Extract visit metadata from DICOM
   - `format_dicom_date()`: Convert DICOM date to ISO format

3. **dicom_utils.py**
   - `read_dicom_tag()`: Read DICOM tag value from file
   - `InvalidDicomError`: Custom exception for DICOM errors

4. **processor.py**
   - `ImageIdentifierLookupProcessor`: Simplified business logic
   - Receives pre-extracted data, performs lookup and update

5. **run.py**
   - `ImageIdentifierLookupVisitor`: Gear execution visitor
   - Main entry point and orchestration
   - Performs early extraction and fail-fast validation

6. **main.py**
   - `run()`: Main execution function
   - High-level workflow coordination

### 7.3 Potential Refactoring Opportunities

**1. Generalize VisitMetadata Architecture**

Current state: `VisitMetadata` in nacc-common includes `packet` field (form-specific)

Proposed refactoring:

```python
# In nacc-common/src/python/nacc_common/error_models.py

class VisitKeys(BaseModel):
    """Base visit identification fields common to all datatypes."""
    adcid: Optional[int] = None
    ptid: Optional[str] = None
    visitnum: Optional[str] = None
    module: Optional[str] = None
    date: Optional[str] = None
    naccid: Optional[str] = None

class VisitMetadata(VisitKeys):
    """Extended visit metadata for form datatypes.
    
    Includes packet field specific to forms.
    """
    packet: Optional[str] = None

class ImageVisitMetadata(VisitKeys):
    """Extended visit metadata for image datatypes.
    
    Includes modality field specific to images.
    """
    modality: str
    module: str = "image"  # Fixed value for images
```

**Benefits:**

- Cleaner separation of datatype-specific fields
- Easier to add new datatypes (genomic, biospecimen, etc.)
- Maintains backward compatibility with existing form-based code

**Impact:**

- No changes needed to existing form processing code
- `VisitMetadata` remains unchanged for forms
- New `ImageVisitMetadata` for images

**2. Enhance ErrorLogTemplate for Multiple Datatypes**

Current state: `ErrorLogTemplate` expects form-specific fields

Potential enhancement:

- Make template more flexible to handle different datatypes
- Use datatype-specific filename patterns
- Example: `{ptid}_{date}_{datatype}_{module}_qc.json`

**Decision:** Keep existing template for now, use `module="image"` as workaround. Consider enhancement in future if more datatypes are added.

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
   - Extract from AcquisitionDate (primary)
   - Fallback to StudyDate
   - Extract modality from DICOM tag
   - Use default modality when tag missing
   - Format DICOM date (YYYYMMDD) to ISO format (YYYY-MM-DD)

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

7. **Fail Fast - Missing Visit Date**
   - DICOM AcquisitionDate tag is missing
   - DICOM StudyDate tag is missing
   - Gear fails immediately during extraction
   - No lookup attempted

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

### 13.1 Batch Processing

**Current:** One file per gear execution

**Future:** Process multiple images in a single execution

- Accept directory or multiple file inputs
- Parallel processing for efficiency
- Aggregate QC reporting

### 13.2 Additional DICOM Metadata

**Current:** Extract PatientID, AcquisitionDate, StudyDate, Modality

**Future:** Extract and store additional metadata

- StudyDescription
- SeriesDescription
- ProtocolName
- Scanner manufacturer and model
- Image dimensions and resolution

### 13.3 Image Quality Checks

**Current:** Only identifier lookup

**Future:** Add image quality validation

- Check for required DICOM tags
- Validate image dimensions
- Check for corruption
- Verify modality-specific requirements

### 13.4 Multi-Center Support

**Current:** Single center per project (pipeline ADCID)

**Future:** Support multiple centers in one project

- Extract center from DICOM metadata
- Map to ADCID dynamically
- Support center-specific configurations

### 13.5 Generalized Metadata Architecture

**Current:** ImageVisitMetadata extends VisitKeys

**Future:** Formalize datatype-specific metadata hierarchy

- Base VisitMetadata with common fields
- FormVisitMetadata with packet
- ImageVisitMetadata with modality
- GenomicVisitMetadata with assay type
- BiospecimenVisitMetadata with sample type

**Benefits:**

- Consistent metadata structure across datatypes
- Easier to add new datatypes
- Shared utilities work polymorphically

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

| Tag | Name | Description | Usage |
|-----|------|-------------|-------|
| (0010,0020) | PatientID | Patient identifier | PTID extraction (fallback) |
| (0008,0022) | AcquisitionDate | Date image acquired | Visit date (primary) |
| (0008,0020) | StudyDate | Date of study | Visit date (fallback) |
| (0008,0060) | Modality | Equipment type | Visit metadata |

### 16.2 Error Codes

| Code | Description | Severity | Action |
|------|-------------|----------|--------|
| PTID_EXTRACTION_FAILED | Failed to extract PTID from subject or DICOM | ERROR | Check subject.label and DICOM PatientID tag |
| ADCID_MISSING | Pipeline ADCID not found in project metadata | ERROR | Add pipeline ADCID to project metadata |
| NACCID_LOOKUP_FAILED | Identifier lookup failed | ERROR | Verify PTID/ADCID combination exists in database |
| NACCID_CONFLICT | NACCID mismatch in subject metadata | ERROR | Investigate data inconsistency |
| METADATA_UPDATE_FAILED | Failed to update subject metadata | ERROR | Check Flywheel API permissions |
| INVALID_DICOM | File is not a valid DICOM file | ERROR | Verify input file format |
| MISSING_DATE | AcquisitionDate and StudyDate both missing | ERROR | Check DICOM file completeness |

### 16.3 Glossary

- **ADCID**: Alzheimer's Disease Research Center Identifier
- **DICOM**: Digital Imaging and Communications in Medicine
- **NACCID**: National Alzheimer's Coordinating Center Identifier
- **PTID**: Participant Identifier
- **QC**: Quality Control
- **Modality**: Type of imaging equipment (MR, CT, PET, etc.)
- **AcquisitionDate**: Date when the image was acquired
- **StudyDate**: Date of the imaging study
- **PatientID**: DICOM tag containing patient identifier

### 16.4 References

- [DICOM Standard](https://www.dicomstandard.org/)
- [pydicom Documentation](https://pydicom.github.io/)
- [Flywheel SDK Documentation](https://flywheel-io.gitlab.io/product/backend/sdk/branches/master/python/)
- [NACC Data Platform Documentation](https://naccdata.github.io/flywheel-gear-extensions/)
