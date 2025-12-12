# Submission Logger Gear Design

## Overview

The submission-logger gear implements a Flywheel gear that captures "submit" events when files are uploaded to NACC projects. It uses a dynamic dispatch pattern to support multiple file formats, extracts visit information from uploaded data, logs submit events to S3, and creates initial QC status logs for downstream pipeline processing.

The design follows established gear patterns from the identifier-lookup gear while integrating with the existing event logging infrastructure.

## Architecture

### High-Level Architecture

```mermaid
graph TD
    A[File Upload] --> B[Submission Logger Gear]
    B --> C[File Type Dispatcher]
    C --> D[CSV Processor]
    C --> E[Future: JSON Processor]
    C --> F[Future: Other Processors]
    
    D --> G[Visit Extractor]
    G --> H[Event Logger]
    G --> I[QC Log Creator]
    G --> J[Metadata Enhancer]
    
    H --> K[S3 Event Storage]
    I --> L[Project QC Logs]
    J --> M[File Metadata]
    
    style B fill:#e1f5ff,stroke:#0066cc,stroke-width:2px
    style C fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    style K fill:#e8f5e8,stroke:#4caf50,stroke-width:2px
```

### Component Architecture

The gear leverages existing infrastructure with minimal new components:

1. **SubmissionLoggerVisitor**: Main execution environment extending `GearExecutionEnvironment`
2. **CSVLoggingVisitor**: Existing component from `common.event_logging` for CSV processing and event creation
3. **QCStatusLogCreator**: Creates initial QC status logs using `ErrorLogTemplate`
4. **File Type Detection**: Uses existing `InputFileWrapper.validate_file_extension()` for CSV detection

**Key Design Decision**: Instead of creating new file processors and visit extractors, directly use the existing `CSVLoggingVisitor` which already handles CSV parsing, visit extraction, and VisitEvent creation.

## Components and Interfaces

### Core Components

```python
# Use existing infrastructure instead of creating new interfaces
from event_logging.csv_logging_visitor import CSVLoggingVisitor
from event_logging.event_logging import VisitEventLogger
from nacc_common.error_models import VisitKeys
from configs.ingest_configs import ErrorLogTemplate

# Minimal new components needed:
class QCStatusLogCreator:
    """Creates initial QC status logs using ErrorLogTemplate."""
    
    def __init__(self, error_log_template: ErrorLogTemplate):
        self.__template = error_log_template
    
    def create_qc_log(self, visit_keys: VisitKeys, project: ProjectAdaptor) -> bool:
        """Creates QC status log file at project level."""
        pass
```

### Main Execution Component

```python
class SubmissionLoggerVisitor(GearExecutionEnvironment):
    """Main gear execution visitor for submission logging."""
    
    def __init__(
        self,
        *,
        client: ClientWrapper,
        file_input: InputFileWrapper,
        gear_name: str,
        event_logger: VisitEventLogger,
        processor_dispatcher: FileProcessorDispatcher,
    ):
        super().__init__(client=client)
        self.__file_input = file_input
        self.__gear_name = gear_name
        self.__event_logger = event_logger
        self.__processor_dispatcher = processor_dispatcher
    
    def run(self, context: GearToolkitContext):
        """Main execution method following identifier-lookup pattern."""
        # Process file using dynamic dispatch
        # Extract visits
        # Log submit events
        # Create QC status logs
        # Enhance file metadata
```

### Simplified Processing Logic

```python
class SubmissionLoggerVisitor(GearExecutionEnvironment):
    """Main gear execution visitor - simplified to use existing infrastructure."""
    
    def run(self, context: GearToolkitContext):
        """Main execution method using existing CSVLoggingVisitor."""
        
        # 1. Check if file is CSV using existing pattern
        if not self.__file_input.validate_file_extension(["csv"]):
            log.warning(f"Unsupported file type: {self.__file_input.filename}")
            return
        
        # 2. Use existing CSVLoggingVisitor for processing
        csv_visitor = CSVLoggingVisitor(
            center_label=project.group,
            project_label=project.label,
            gear_name=self.__gear_name,
            event_logger=self.__event_logger,
            module_configs=module_configs,
            error_writer=error_writer,
            timestamp=self.__file_input.file_entry(context).created,
            action="submit",  # Key difference from other uses
            datatype="form"
        )
        
        # 3. Process CSV file (creates submit events automatically)
        success = run_csv_processing(
            input_file=open(self.__file_input.filepath),
            csv_visitor=csv_visitor,
            error_writer=error_writer
        )
        
        # 4. Create QC status logs for each visit found
        # 5. Add visit metadata to file.info.visit
```

## Data Models

### Visit Information Model

```python
# Use existing VisitKeys from nacc_common.error_models instead of creating new model
from nacc_common.error_models import VisitKeys

# VisitKeys already provides the core visit identification:
# - ptid: Optional[str] 
# - date: Optional[str] (visit date)
# - module: Optional[str] 
# - visitnum: Optional[str] (visit number)
# - adcid: Optional[int]

# Additional context will be provided by project/gear context
```

### Processing Result Model

```python
class ProcessingResult(BaseModel):
    """Result of file processing operation."""
    visits_found: int
    events_logged: int
    qc_logs_created: int
    errors: List[FileError]
    success: bool
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Analysis

Based on the requirements analysis, the following properties ensure correctness:

**Property 1: Visit Event Creation Completeness**
*For any* uploaded file containing visit data, the number of submit events logged should equal the number of valid visits extracted from the file
**Validates: Requirements 1.2, 2.5**

**Property 2: QC Status Log Creation Consistency**  
*For any* visit identified in an uploaded file, a corresponding QC status log file should be created at the project level using the ErrorLogTemplate naming pattern
**Validates: Requirements 3.1, 3.2**

**Property 3: Event Timestamp Accuracy**
*For any* submit event created, the event timestamp should match the file upload timestamp within acceptable precision bounds
**Validates: Requirements 1.4**

**Property 4: File Metadata Enhancement Preservation**
*For any* uploaded file processed successfully, the original file content should remain unchanged while visit metadata is added to file.info.visit
**Validates: Requirements 4.1, 4.2**

**Property 5: Error Handling Robustness**
*For any* processing error encountered, the gear should log detailed error information and continue processing remaining visits without failing execution
**Validates: Requirements 6.1, 6.3, 6.4**

**Property 6: Dynamic Dispatch Correctness**
*For any* supported file type, the dispatcher should select exactly one appropriate processor that can handle that file type
**Validates: Technical Architecture Constraint 1**

## Error Handling

### Error Categories

1. **File Access Errors**: File not readable, permissions issues
2. **Format Errors**: Malformed CSV, missing required columns
3. **Data Validation Errors**: Invalid PTID, date formats, missing required fields
4. **Infrastructure Errors**: S3 connectivity, Flywheel API failures
5. **Processing Errors**: Visit extraction failures, event logging failures

### Error Handling Strategy

Following the identifier-lookup pattern:

```python
class SubmissionErrorHandler:
    """Handles errors during submission processing."""
    
    def __init__(self, error_writer: ListErrorWriter):
        self.__error_writer = error_writer
    
    def handle_file_error(self, error: Exception, file_path: Path):
        """Handles file-level errors."""
        # Log error but don't fail gear execution
        # Add to error writer for reporting
    
    def handle_visit_error(self, error: Exception, visit_data: Dict[str, Any]):
        """Handles visit-level errors."""
        # Continue processing other visits
        # Record specific visit error
```

## Testing Strategy

### Unit Testing Approach

- **File Processor Tests**: Test each processor type independently
- **Visit Extraction Tests**: Verify correct parsing of visit data
- **Event Creation Tests**: Validate VisitEvent object creation
- **Error Handling Tests**: Ensure robust error recovery

### Property-Based Testing Approach

Using **Hypothesis** for Python property-based testing:

- **Minimum 100 iterations** per property test
- **Property tags**: Each test tagged with format `**Feature: submission-logger, Property {number}: {property_text}**`
- **Generator strategies**: Smart generators for CSV data, visit information, file paths

**Property Test Examples:**

```python
@given(csv_data=csv_visit_generator())
def test_visit_event_creation_completeness(csv_data):
    """**Feature: submission-logger, Property 1: Visit Event Creation Completeness**"""
    # Generate CSV with known visit count
    # Process through submission logger
    # Assert events_logged == visits_extracted

@given(visit_info=visit_info_generator())
def test_qc_status_log_creation_consistency(visit_info):
    """**Feature: submission-logger, Property 2: QC Status Log Creation Consistency**"""
    # Generate visit information
    # Create QC status log
    # Assert file exists with correct ErrorLogTemplate naming
```

### Integration Testing

- **End-to-End Processing**: Full file upload to event logging pipeline
- **Flywheel Integration**: Test with actual Flywheel project context
- **S3 Integration**: Verify event storage in S3 bucket

## Implementation Plan

### Phase 1: Basic Gear Setup
1. Set up gear execution framework following identifier-lookup pattern
2. Create SubmissionLoggerVisitor extending GearExecutionEnvironment
3. Add file type detection using existing InputFileWrapper.validate_file_extension()

### Phase 2: CSV Processing Integration  
1. Integrate existing CSVLoggingVisitor from common.event_logging
2. Configure CSVLoggingVisitor with action="submit" for submission events
3. Handle ModuleConfigs loading for field validation

### Phase 3: QC Status Log Creation
1. Implement QCStatusLogCreator using ErrorLogTemplate
2. Extract visit information from CSVLoggingVisitor processing
3. Create initial QC status logs at project level

### Phase 4: File Metadata and Testing
1. Add visit metadata to file.info.visit structure  
2. Add property-based tests for correctness validation
3. Integration testing with existing event logging infrastructure

**Key Advantage**: By reusing CSVLoggingVisitor, we eliminate the need to implement CSV parsing, visit extraction, and VisitEvent creation - significantly reducing implementation complexity.
2. Add property-based tests for correctness validation
3. Integration testing with Flywheel and S3 infrastructure

## Configuration

### Gear Configuration Schema

```yaml
config:
  # Event logging configuration
  event_bucket: "nacc-event-logs"
  environment: "prod"  # or "dev"
  
  # Processing configuration  
  supported_formats: ["csv"]
  required_columns: ["ptid", "visitdate"]
  optional_columns: ["visitnum", "packet", "module"]
  
  # Error handling configuration
  continue_on_error: true
  max_errors_per_file: 100
```

### Environment Integration

- **Parameter Store**: AWS credentials and configuration
- **Flywheel Context**: Project and center information
- **S3 Bucket**: Event storage configuration

## Leveraging Existing Infrastructure

### Existing Components to Reuse

1. **CSVLoggingVisitor** (`common.event_logging.csv_logging_visitor`):
   - Already handles CSV parsing and VisitEvent creation
   - Includes proper error handling and field validation
   - Uses ModuleConfigs for required field checking
   - Perfect for submission event logging

2. **VisitKeys Model** (`nacc_common.error_models`):
   - Standard model for visit identification across the system
   - Used by form-scheduler and other gears
   - Provides consistent visit metadata structure

3. **Visit Extraction Functions** (`nacc_common.qc_report`):
   - `extract_visit_keys()` function for parsing visit information
   - Used by form-scheduler for QC log processing
   - Could be enhanced for CSV data extraction

### Potential Code Movement

Consider moving these components from `gear/form_scheduler` to `common`:

1. **Visit Event Creation Functions**:
   - `create_visit_event_from_error()`
   - `create_visit_event_from_status()`
   - `create_visit_event()` - Generic factory function

2. **Event Transformers**:
   - `event_status_transformer()`
   - Could be generalized for different event types

This would allow both submission-logger and form-scheduler to share common event creation logic.

## Dependencies

### External Dependencies
- `flywheel-gear-toolkit`: Gear execution framework
- `common.event_logging`: Event logging infrastructure and CSVLoggingVisitor
- `common.configs.ingest_configs`: ErrorLogTemplate for QC log naming
- `nacc_common.error_models`: VisitKeys model for visit identification
- `gear_execution.gear_execution`: Base execution classes

### Internal Components
- Reuse CSVLoggingVisitor for CSV processing instead of creating new logic
- Leverage existing VisitKeys model instead of creating new visit data structures
- Use established Flywheel adaptor patterns for project interaction

## Deployment Considerations

### Flywheel Integration
- Gear rules configuration for automatic triggering on file uploads
- Project-level permissions for QC log creation
- Integration with existing form processing pipeline

### Monitoring and Observability
- Gear execution logging following established patterns
- Metrics collection for processing statistics
- Error reporting integration with existing monitoring systems