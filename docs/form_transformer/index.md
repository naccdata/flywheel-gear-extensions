# Form Transformer

Reads a tabular (CSV) file containing form visit data, performs transformations on the data and creates a participant-visit specific JSON file for each row.

The JSON file is attached to a subject/session/acquisition for the participant determined by the NACCID.
The file must have a module column.

## File Metadata and Tagging

After processing, the gear updates the input CSV file with the following metadata. See the [QC Conventions](../nacc_common/qc-conventions.md) reference for details on the data models and conventions used.

1. **QC Result**: A validation QC result is added to the file's `file.info.qc` metadata with:
   - `name`: `"validation"`
   - `state`: `"PASS"` or `"FAIL"` depending on whether transformation succeeded
   - `data`: List of `FileError` objects with error details if any errors occurred during transformation

2. **File Tag**: The gear name (e.g., `"form-transformer"`) is added as a simple tag to the input file, indicating the file has been processed by this gear.

## Transformations

The transformation file contains a JSON object with module names as the keys.
Each module maps to an object that groups its transformations into two
categories:

- **`field_transformations`** — transformations that drop individual columns
  from a record (e.g. filtering out fields for the form versions not in use).
- **`form_transformations`** — transformations that remove an entire form from
  a record (e.g. dropping a form that has not yet been released for a visit).

Every transformation object carries a `transform_type` tag identifying its
type, which allows new transformation types to be added under either category
in the future.

```json
{
    "UDS": {
        "field_transformations": [ /* ... */ ],
        "form_transformations": [ /* ... */ ]
    }
}
```

If `nofill` is set to `true` on a transformation, the fields it would drop must
be empty; otherwise the record is rejected with an error.

### Field transformations

#### `version_map`

Data from the NACC REDCap projects contains rows with columns for all versions
of a form. A `version_map` transformation filters out the columns specific to
the versions not used.

It includes an object indicating how to determine the version of the module:

```json
{
    "fieldname": "indicator-field",
    "value_map": { "indicator-value": "version1" },
    "default": "version2"
}
```

This information is used to determine which fields to exclude:

- if the value of the `indicator-field` is `indicator-value`, exclude fields for `version1`
- otherwise, exclude fields for `version2`

The transformation also includes the full lists of fields for each version of
the module under `fields`.

### Form transformations

#### `release_date`

A `release_date` transformation removes an entire form from a record when the
form has not yet been released for that visit and was not submitted. When the
visit date is before the form's release date and the mode field value is not
one of `retain_modes`, the form's data fields, `header_fields`, and mode field
(derived as `mode` + `form_name`) are all removed.

The release date is looked up by `form_name` from the module's release date
configuration; a form with no configured release date is treated as already
released. When `nofill` is `true`, if any data field is non-empty the record is
rejected (header fields are exempt from this check).

### Example

This (partial) example shows a `version_map` field transformation and a
`release_date` form transformation for UDS, and a `version_map` for LBD.

```json
{
    "UDS": {
        "field_transformations": [
            {
                "transform_type": "version_map",
                "version_map": {
                    "fieldname": "rmmodec2c2t",
                    "value_map": { "1": "C2" },
                    "default": "C2T"
                },
                "fields": {
                    "C2": [],
                    "C2T": []
                },
                "nofill": true
            }
        ],
        "form_transformations": [
            {
                "transform_type": "release_date",
                "form_name": "d1c",
                "retain_modes": ["1"],
                "header_fields": ["frmdated1c", "initialsd1c", "langd1c", "d1cnot"],
                "fields": [],
                "nofill": true
            }
        ]
    },
    "LBD": {
        "field_transformations": [
            {
                "transform_type": "version_map",
                "version_map": {
                    "fieldname": "formver",
                    "value_map": { "3.1": "v3.0" },
                    "default": "v3.1"
                },
                "fields": {
                    "v3.0": [],
                    "v3.1": []
                },
                "nofill": true
            }
        ]
    }
}
```

