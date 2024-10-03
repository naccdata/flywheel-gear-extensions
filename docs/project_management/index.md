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
primary: <whether is primary study>
centers: <list of center identifiers>
datatypes: <list of datatype identifiers>
mode: <whether data should be aggregated or distributed>
published: <whether the data is published>
```

Center identifiers are Flywheel group IDs created by the [center management](../center_management/index.md) gear.

The mode is a string that is either `aggregation` or `distribution`.
The mode may be omitted for aggregating studies to support older project formats.

Running on the file will create a group for each center that does not already exist, and add new projects:

1. pipeline projects for each datatype.
   For aggregating studies, a project will have a name of the form `<pipeline>-<datatype>-<study-id>` where `<pipeline>` is `ingest`, `sandbox` or `retrospective`.
   For distributing studies, the pipline will be named `distribution`.
   For instance, `ingest-form-leads`.
   For the primary study, the study-id is dropped like `ingest-form`.
2. An `accepted` pipeline project for an aggregating study, where data that has passed QC is accessible.
3. a `metadata` project where center-specific metadata can be stored using the project info object.
4. a `center-portal` project where center-level UI extensions for the ADRC portal can be attached.

Notes:
1. Only one study should have `primary` set to `True`.

2. Like with any YAML file, you can include several study definitions separated by a line with `---`.
   However, it is more pragmatic to have one file per study for large studies.

3. The `tags` are strings that will be permissible as tags within the group for the center. 
   Each tag will also be added to ingest studys within the center's pipeline(s).

4. Datatypes are strings used for creating ingest containers, and matching to sets of gear rules needed for handling ingest.


### Example

```yaml
---
study: "Project Tau"
study-id: tau
centers:
  - alpha
  - beta-inactive
datatypes:
  - form
  - dicom
mode: aggregation  
published: True
---
study: "Project Zeta"
study-id: zeta
centers:
  - alpha
  - gamma-adrc
datatypes:
  - form
mode: aggregation
published: False
```

## Running the App

For testing, see the gear wrangling directions in the development documentation.