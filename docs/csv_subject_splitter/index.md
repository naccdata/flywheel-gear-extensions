# CSV Subject Splitter

Gear reads a tabular (CSV) file where each row has a NACCID and creates a JSON file for each row

The JSON file will be added to a subject/session/acquisition for the participant determined by the NACCID. 

The labels for session and the file name are determined by the config input `hierarchy_labels` (represented as a JSON string), which is an an object with template strings for each:

```json
{
    "session": {
        "template": "<template-text>",
        "transform": "<transform-name>",
        "delimiter": "<delimiter>"
    },
    "acquisition": {
        "template": "<template-text>",
        "transform": "<transform-name>",
        "delimiter": "<delimiter>"
    },
    "filename": {
        "template": "<template-text>",
        "transform": "<transform-name>",
        "delimiter": "<delimiter>"
    }
}
```

In JSON string form:

```json
"{\"session\": {\"template\": \"<template-text>\",\"transform\": \"<transform-name>\"},\"acquisition\": {\"template\": \"<template-text>\",\"transform\": \"<transform-name>\"},\"filename\": {\"template\": \"<template-text>\",\"transform\": \"<transform-name>\"}"
```

templates must be given for each of `session`, `acquisition`, and `filename`.

A template can reference the fields in the file by preceding the field name with a dollar sign.
For instance, the NACCID in the row could be included as `$naccid`
Reference the base of the original file name with `$filename` (e.g., for a file `base.csv` the value would be `base`).

Supported transforms are converting the whole label to upper or lower case.
So, the allowed values are `upper` and `lower`.

A delimiter is also supported; if provided, will replace all spaces in the hierarchy label with the specified string.

As an example, suppose we are splitting biomarker data from a data release designated `2024-12`.
Also, the data was collected with an assay designated `assay-01`, and we want to use the original filename except in lower case.

```json
{
    "session": {
        "template": "biomarker-release-2024-12"
    },
    "acquisition": {
        "template": "assay-01"
    },
    "filename": {
        "template": "$filename",
        "transform": "lower"
    }
}
```

In JSON string form:

```json
"{\"session\": {\"template\": \"biomarker-release-2024-12\"},\"acquisition\": {\"template\": \"assay-01\"},\"filename\": {\"template\": \"$filename\",\"transform\": \"lower\"}}"
```

Here the first two don't have variables, and the last uses the filename.


### Inputs

This takes a CSV file as input.
The file must have a NACCID column.

### Configs
Gear configs are defined in [manifest.json](../../gear/csv_subject_splitter/src/docker/manifest.json).