# Legacy Identifier Transfer

This gear transfers legacy NACC IDs from the identifiers database into Flywheel by creating subjects and enrollment records.

## Environment

This gear uses the AWS SSM parameter store, and expects that AWS credentials are available in environment variables within the Flywheel runtime.
The variables used are `AWS_SECRET_ACCESS_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_DEFAULT_REGION`.
The gear needs to be added to the allow list for these variables to be shared.

## Configuration

The gear can be configured with the following options:

- `dry_run` -- whether to run the script without updating Flywheel or the files
  Default: `false`.
- `admin_group` -- name of the admin group.
  Default: `nacc`.
- `identifier_mode` -- whether to create identifiers in dev or prod database.
  Default: `prod`.
- `apikey_path_prefix` -- the instance specific AWS parameter path prefix for apikey.
  Default: `/prod/flywheel/gearbot`.

## Processing

The following diagrams describe the processing of legacy identifiers.

First, the gear retrieves all identifiers for a center's ADCID and validates each one before creating enrollment records.

```mermaid
graph TB
    start((*)) --> getids{Get Center\nIdentifiers} -- success --> validate{Validate\nIdentifiers}
    getids -- fail --> error1((error))
    validate -- valid --> process{Process\nEnrollments}
    validate -- invalid --> error2((error))
    process -- success --> createSubjects(Create Subjects)
    process -- existing --> skip(Skip Creation)
    createSubjects --> stop((done))
    skip --> stop
style start fill:#000, stroke:#000
```

## Enrollment Processing

Each identifier is validated and used to create enrollment records. The gear checks for existing subjects to avoid duplicates.

```mermaid
graph TB
    start((*)) --> validateId{Validate\nIdentifier} 
    validateId -- invalid --> error1((error))
    validateId -- valid --> checkNaccid{Check NACCID\nExists}
    checkNaccid -- exists --> skip((skip))
    checkNaccid -- new --> createSubject(Create Subject)
    createSubject --> addEnrollment(Add Enrollment)
    addEnrollment --> stop((done))
style start fill:#000, stroke:#000
```

```mermaid
sequenceDiagram
    Gear->>IdentifiersDB: get identifiers(ADCID)
    IdentifiersDB->>Gear: identifier list
    loop Each Identifier
        Gear->>Flywheel: find_subject(NACCID)
        alt subject exists
            Flywheel->>Gear: subject
            Note over Gear: Skip creation
        else no subject
            Flywheel->>Gear: none
            Gear->>Flywheel: create_subject(NACCID)
            Gear->>Flywheel: add_enrollment(record)
        end
    end
```