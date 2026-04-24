# File Distribution

Gear that distributes files to target projects.

The ADCIDs are mapped to the Flywheel group ID using the custom info found in the NACC admin `metadata` project.

### Associated File Regex

Ideally we only distribute to centers for which the file is applicable. To figure out which are applicable, we have to associate the distributed file with another one, usually a CSV run through `csv-center-splitter`, to pull an associated ADCID list.

The `associated_csv_regex` basically defines a capture regex that runs on the input filename, and searches for another CSV file in the project that matches the capture. If found, the gear will then attempt to read that CSV file for ADCIDs.

For example, say our `associated_csv_regex` is `^(.*?)-reference\.csv`.

If our input file to be distributed is called `my-special-file-reference.csv`, the regex will capture the string `my-special-file` and search for a CSV file whose name **matches that string exactly**.

In other words, it will grab

```
my-special-file.csv
```

but not

```
my-special-file-other.csv
0-my-special-file.csv
```

If not found, an error will be thrown. Otherwise, the gear will open `my-special-file.csv` and look for a column with `adcid` (or field provided with the `adcid_key` config) and determine the ADCID list from there. It will then only write to projects in this found ADCID list.

Note this configuration is ignored if `staging_project_id` is provided, as there is only one definitive project we are writing to in that scenario.
