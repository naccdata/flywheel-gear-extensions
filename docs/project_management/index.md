# Study management

The project-management app builds containers within Flywheel for a coordinating center supported study.

A *coordinating center supported study* is a research activity for which data is being collected at the coordinating center.
For NACC is this primarily the ADRC program for which data is captured at Alzheimer's Disease Research Centers (ADRCs), and then transferred to NACC for harmonization and release.

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
centers: <list of center information>
datatypes: <list of datatype identifiers>
published: <whether the data is published>
```

A center is described using the following fields

```yaml
name: <center name>
center-id: <string identifier>
adcid: <int>
is-active: <whether the center is active>
tags: <list of strings for tagging study>
```

Running on the file will create a group for each center that does not already exist, and add new projects:

1. pipeline projects for each datatype.
   A project will have a name of the form `<pipeline>-<datatype>-<study-id>` where `<pipeline>` is `ingest`, `sandbox` or `retrospective`.
   For instance, `ingest-form-leads`.
   For the primary study, the study-id is dropped like `ingest-form`.
2. An `accepted` pipeline project, where data that has passed QC is accessible.
2. a `metadata` project where center-specific metadata can be stored using the project info object.
3. a `center-portal` project where center-level UI extensions for the ADRC portal can be attached.

Notes:
1. Only one study should have `primary` set to `True`.

2. Like with any YAML file, you can include several study definitions separated by a line with `---`.
   However, it is more pragmatic to have one file per study for large studys.

2. The `tags` are strings that will be permissible as tags within the group for the center. 
   Each tag will also be added to ingest studys within the center's pipeline(s).

3. Choose `center-id` values to be mnemonic for the coordinating center staff.
   The choice will be visible to centers, but they will not need to type the value in regular interactions. 
   Staff, on the other hand, will need to use the strings in filters.

4. The `adcid` is an assigned code used to identify the center within submited data.
   Each center has a unique ADC ID.

5. Datatypes are strings used for creating ingest containers, and matching to sets of gear rules needed for handling ingest.


### Example

```yaml
---
study: "Project Tau"
study-id: tau
centers:
  - name: "Alpha Center"
    center-id: alpha
    adcid: 1
    is-active: True
    tags:
      - 'center-code-1006'
  - name: "Beta Center"
    center-id: beta-inactive
    adcid: 2
    is-active: False
    tags:
      - 'center-code-2006'
datatypes:
  - form
  - dicom
published: True
---
study: "Project Zeta"
study-id: zeta
centers:
  - name: "Alpha Center"
    center-id: alpha
    adcid: 1
    is-active: True
    tags:
      - 'center-code-1006'
  - name: "Gamma ADRC"
    center-id: gamma-adrc
    adcid: 3
    is-active: True
    tags:
      - 'center-code-5006'
datatypes:
  - form
published: False
```

## Running the App

For testing, see the gear wrangling directions in the development documentation.