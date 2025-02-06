# Form Transformer

Reads a tabular (CSV) file containing form visit data, performs transformations on the data and creates a participant-visit specific JSON file for each row.

The JSON file is attached to a subject/session/acquisition for the participant determined by the NACCID.
The file must have a module column.

Current transformations filter columns based on the versions of forms.
Data from the NACC REDCap projects will contain rows for all versions of forms, and the transformations filter out the columns specific to the versions not used.

The transformation file should contain a JSON object with module names as the key values.
Each module is associated with a list of field filters, which determine the fields to be filtered for the module version.

Each field filter is used to determine the fields to be filtered based on the module version.
It consists of an object indicating how to determine the version of the module to exclude.

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

A field filter also includes the full lists of fields for each version of the module.
If `nofill` set to `true` exclude fields must be empty

This (partial) example shows field filters for the C2 forms of UDS and the version of the LBD module.

```json
{
    "UDS": [
        {
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
    "LBD": [
        {
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
```