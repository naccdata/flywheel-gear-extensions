# Attribute Curator

Curates subject- and file-level attributes with values derived from file attributes.

Uses the [nacc-attribute-deriver](https://github.com/naccdata/nacc-attribute-deriver) package.

## Workflow

At a high-level, this gear does the following:

1. Iterate over all subjects in the project
2. For each subject
    1. Execute a data view to pull all acquisition files and relevant metadata
    2. Process the acquisition files based in a specific curation order (see below), and run the Attribute Deriver on each file
    3. Run a back-propogation pass on the subject to compute cross-module variables (e.g. reliant on multiple scopes and their chronological order) and update cross-sectional values for all files
    4. Push final curated metadata back to Flywheel


### Curation Order

The curation order is determined by:

1. The visit pass
2. The file scope
3. The file date

Currently there are 4 visit passes, which determine the order in which file scopes are processed. Which pass a file scope belongs to is dependent on its its reliance on other scopes. See `common/../curator/scheduling_models.py` to see the currently implemented passes.

1. `pass3`: Historic/legacy scopes
2. `pass2`: All other scopes
3. `pass1`: UDS
4. `pass0`: Scopes reliant on UDS

The file scope is determined by the filename. Typically the scopes refer to different modules (e.g. UDS, NP, etc.) or different data sources (imaging, genetic, etc.). All files within a given scope are processed together, in chronological order.

The file date is typically determined by a known date field specific to the scope (e.g. `visitdate` for forms). Some scopes are not dated (e.g. genetics data), in which case the `modified_date` of the FW container is used as the default.

### Metadata Access

The curation works by loading all relevant metadata, at both the file and subject level, into a single `SymbolTable` that the Attribute Deriver processes to compute both derived and missingness variables.

In general, the raw metadata is expected to come from one of the following locations:

* `file.info.forms.json` (form data)
* `file.info.raw` (all other data)
* `subject.info.*` (any already-curated data stored globally at the subject level)

Data then gets written to:

| Container | Metadata location | Description |
| - | - | - |
| File | `file.info.derived` | Derived variables specific to the file's scope. Note cross-sectional derived variables may get updated in the back-propagation pass. |
| File | `file.info.resolved` | Resolved missingness variables specific to that scope. |
| Subject | `subject.info.derived` | Superset of all `file.info.derived` for all scopes, updated as of the last curated file |
| Subject | `subject.info.derived.cross-sectional` | Cross-sectional derived variables for all scopes |
| Subject | `subject.info.derived.longitudinal` | Longitudinal derived variables for all scopes. Dated by the (UDS) form date. |
| Subject | `subject.info.working` | Temporary/working metadata for attribute curation |
| Subject | `subject.info.*` | Anything else is either for MQT or unrelated metadata |

Note that data is globally written to `subject.info`, and once written can be accessed by future file curations. As such, it is extremely important the files are curated in the correct curation order.
