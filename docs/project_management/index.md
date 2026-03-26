# Study management

The project-management app builds containers within Flywheel for a coordinating center supported study.

A *coordinating center supported study* is a research activity for which data is being collected at the coordinating center.
For NACC this is primarily the ADRC program for which data is captured at Alzheimer's Disease Research Centers (ADRCs), and then transferred to NACC for harmonization and release.

## A note on the app name
The name "project-management" is historical and comes from a conversation with the NACC PI, Bud Kukull. 
He had legitimate reasons not to use "study", so we started with "project".
However, "project" is used in both Flywheel and REDCap to mean particular things, and having three things called projects started to make communication difficult.
And, naively, "study" makes sense.

So, we are using "study" now, but keeping the gear name for continuity.

## Usage

The gear can be run either via the Flywheel user interface or using a script.

You will need an input file uploaded to Flywheel.
The format is described below.

For NACC, access to the gear is restricted to the `fw://nacc/project-admin` project.
There is a file `adrc-program.yaml` attached to that project, and a gear rule that will run the gear when the file is updated.
For other scenarios, attach a file to the project, and run the gear as usual.

### Input Format

This app takes a YAML file describing the study and creates containers within Flywheel to support the ingest and curation of the collected data.

The file format is

```yaml
---
study: <study-name>
study-id: <string-identifier>
study_type: <'primary' or 'affiliated'>
centers: <list of center details>
datatypes: <list of datatype identifiers>
dashboards: <optional list of dashboard names>
mode: <whether data should be aggregated or distributed>
published: <whether the data is published>
```

"Center details" may either be a center identifier or a center-study object.
Center identifiers are Flywheel group IDs created by the [center management](../center_management/index.md) gear.
A center-study object has a center identifier labeled as `center-id`, an `enrollment-pattern` that may be `co-enrollment` or `separate`, and a `pipeline_adcid` that is an optional `int`.
The `pipeline_adcid` is an ADCID assigned for the study data pipeline and is required when the enrollment pattern is `separate` and otherwise should not be given.
In the `centers` list, a center identifier is assumed to represent a center-study object with the co-enrollment pattern.

The mode is a string that is either `aggregation` or `distribution`.
The mode may be omitted for aggregating studies to support older project formats.

The `dashboards` field is an optional list of dashboard names. When provided, dashboard projects will be created for each active center in the study. Dashboard projects are used as placeholders for managing access to dashboard pages within the ADRC portal. The portal uses Flywheel project roles to determine what content is shown to users.

Running on the file will create a group for each center that does not already exist, which includes

* a `metadata` project where center-specific metadata can be stored using the project info object.
* a `center-portal` project where center-level UI extensions for the ADRC portal can be attached.
  
Additional projects will be added if the study is either primary or it is affiliated and the center has separate enrollments:

1. pipeline projects for each datatype.
   For aggregating studies, a project will have a name of the form `<pipeline>-<datatype>-<study-id>` where `<pipeline>` is `ingest`, `sandbox` or `retrospective`.
   For distributing studies, the pipeline will be named `distribution`.
   For instance, `ingest-form-leads`.
   For the primary study, the study-id is dropped like `ingest-form`.
2. An `accepted` pipeline project for an aggregating study, where data that has passed QC is accessible.
3. Dashboard projects (if `dashboards` field is provided) for each dashboard name in the list.
   Dashboard projects will have a name of the form `dashboard-<dashboard-name>-<study-id>`.
   For the primary study, the study-id is dropped like `dashboard-enrollment`.
   Dashboard projects are only created for active centers and are used to manage access to portal dashboard pages.


Notes:
1. Only one study should have `primary` set to `True`.

2. Like with any YAML file, you can include several study definitions separated by a line with `---`.
   However, it is more pragmatic to have one file per study for large studies.

3. The `tags` are strings that will be permissible as tags within the group for the center. 
   Each tag will also be added to ingest projects within the center's pipeline(s).

4. Datatypes are strings used for creating ingest containers, and matching to sets of gear rules needed for handling ingest.

5. Each project added under a center group will have `project.info.adcid` set to the ADCID of the center.


### Example

```yaml
---
study: "Project Tau"
study-id: tau
study-type: affiliated
centers:
  - alpha
  - beta-inactive
datatypes:
  - form
  - dicom
dashboards:
  - enrollment
  - qc-status
mode: aggregation  
published: True
---
study: "Project Zeta"
study-id: zeta
study-type: affiliated
centers:
  - alpha
  - center-id: gamma-adrc
    enrollment-pattern: separate
datatypes:
  - form
mode: aggregation
published: False
```

## Running the App

For testing, see the gear wrangling directions in the development documentation.