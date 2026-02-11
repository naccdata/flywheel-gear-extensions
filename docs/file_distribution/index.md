# File Distribution

Gear that distributes files to target projects.

The ADCIDs are mapped to the Flywheel group ID using the custom info found in the NACC admin `metadata` project.

### Associated File Regex

Oftentimes the file we are distributing is associated with another file being run through the `csv-center-splitter` gear. If the `associated_csv_regex` config is provided, this gear will search for a CSV file containing the string returned from running the regex on the input file's filename. It will then attempt to read that CSV file and pull an ADCID list from that associated file.

For example, say our `associated_csv_regex` is `^(.*?)-reference\.csv`.

If our input file to be distributed is called `my-special-file-reference.csv`, the regex will pull out the string `my-special-file`and search for a CSV file whose name **matches that string exactly**.

In other words, it will grab

```
my-special-file.csv
```

but not

```
my-special-file-other.csv
```

If not found, an error will be thrown. Otherwise, the gear will open `my-special-file.csv` and look for a column with `adcid` (or field provided with the `adcid_key` config) and determine the ADCID list from there. It will then only write to projects in this found ADCID list.

Note this configuration is ignored if `staging_project_id` is provided, as there is only one definitive project we are writing to in that scenario.
