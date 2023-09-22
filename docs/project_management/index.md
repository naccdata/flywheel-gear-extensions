# Project management

The project management app builds containers within Flywheel for a coordinating center supported project.

A *coordinating center supported project* is a research activity for which data is being collected at the coordinating center.
For NACC is this primarily the ADRC program for which data is captured at Alzheimer's Disease Research Centers (ADRCs), and then transferred to NACC for harmonization and release.

## Input 

This app takes a YAML file describing the project and creates containers within Flywheel to support the ingest and curation of the collected data.

The file format is

```yaml
---
project: <project-name>
project-id: <string-identifier>
primary: <whether is primary project>
centers: <list of center information>
datatypes: <list of datatype identifiers>
published: <whether the data is published>
```

A center is described using the following fields

```yaml
name: <center name>
center-id: <string identifier>
is-active: <whether the center is active>
tags: <list of strings for tagging project>
```

Notes:
1. Only one project should have `primary` set to `True`.

2. Like with any YAML file, you can include several project definitions separated by a line with `---`.
   However, it is more pragmatic to have one file per project for large projects.

2. The `tags` are strings that will be permissible as tags within the group for the center. 
   Each tag will also be added to ingest projects within the center's pipeline(s).

3. Choose `center-id` values to be mnemonic for the coordinating center staff.
   The choice will be visible to centers, but they will not need to type the value in regular interactions. 
   Staff, on the other hand, will need to use the strings in filters.

3. Datatypes are strings used for creating ingest containers, and matching to sets of gear rules needed for handling ingest.


## Example

```yaml
---
project: "Project Tau"
project-id: tau
centers:
  - name: "Alpha Center"
    center-id: alpha
    is-active: True
    tags:
      - 'center-code-1006'
  - name: "Beta Center"
    center-id: beta-inactive
    is-active: False
    tags:
      - 'center-code-2006'
datatypes:
  - form
  - dicom
published: True
---
project: "Project Zeta"
project-id: zeta
centers:
  - name: "Alpha Center"
    center-id: alpha
    is-active: True
    tags:
      - 'center-code-1006'
  - name: "Gamma ADRC"
    center-id: gamma-adrc
    is-active: True
    tags:
      - 'center-code-5006'
datatypes:
  - form
published: False
```

## Running the App

To run from the command-line, first set the API key by running

```bash
export FW_API_KEY=XXXXXX
``` 
using your FW key instead of the `XXXXXX`. This key is available on your FW profile page.

```bash
pants run project_management/src/python/project_app:bin --  --no-gear project_management/data/project-definition.yaml
```

you can also specify the name of your admin group using `--admin_group` (default is `nacc`).
And, do a dry run using `--dry_run`

See the developers guide for information on deploying the app as a Docker container or Gear.