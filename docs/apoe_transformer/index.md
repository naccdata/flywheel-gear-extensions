# APOE Transformer

Transforms APOE data from NCRAD to NACC encoding.

The gear takes an APOE genotype file from NCRAD as the input file, which is expected to have the following columns:

* `adcid`
* `ptid`
* `naccid`
* `a1`
* `a2`

The IDs are assumed to match. `a1` and `a2` are alleles for the two APOE loci, which are then used to calculate the NACC value `apoe` which is determined by the following:

```
if a1 == "E3" and a2 == "E3":
   apoe = 1
elif a1 =="E3" and a2 == "E4":
   apoe = 2
elif a1 =="E4" and a2 == "E3":
    apoe = 2
elif a1 =="E3" and a2 == "E2":
    apoe = 3
elif a1 =="E2" and a2 == "E3":
    apoe = 3
elif a1 =="E4" and a2 == "E4":
    apoe = 4
elif a1 =="E4" and a2 == "E2":
    apoe = 5
elif a1 =="E2" and a2 == "E4":
    apoe = 5
elif a1 =="E2" and a2 == "E2":
    apoe = 6
else:
    apoe = 9
```

It then outputs a CSV to the same project (or another project if specified in the config file) with the same IDs and newly calculated `apoe` value.

## Config

The only required input is the APOE genotype file from NCRAD, but the gear also takes in the following optional parameters:

```yaml
output_filename: <output filename; defaults to the input filename with '_apoe_transformed' postfixed>
target_project_id: <target output project ID; defaults to the same project the input file was uploaded to if not specified>
delimiter: <the input CSV delimiter; defaults to ','>
local_run: <whether or not this is a local run; if True, then target_project_id must be provided>
```
