# Center management

The center management gear builds Flywheel groups for each supported research center, independent of a research study.

## Input Format

This gear takes a YAML file listing the centers.
A center is described using the following fields

```yaml
name: <center name>
center-id: <string identifier>
adcid: <int>
is-active: <whether the center is active>
tags: <list of strings for tagging study>
```

Running on the file will create a group for each center that does not already exist.

Notes: 

1. `center-id` values should be chosen to be mnemonic for the coordinating center staff.
   The choice will be visible to centers, but they will not need to type the value in regular interactions. 
   Staff, on the other hand, will need to use the strings in filters.

2. The `adcid` is an assigned code used to identify the center within submitted data.
   Each center has a unique ADC ID.

### Example

```yaml
---
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
- name: "Gamma ADRC"
  center-id: gamma-adrc
  adcid: 3
  is-active: True
  tags:
    - 'center-code-5006'
```