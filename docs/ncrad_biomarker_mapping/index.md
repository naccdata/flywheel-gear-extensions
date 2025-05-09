# NCRAD Biomarker Mapping

Maps NCRAD Biomarker files to their corresponding QC data and writes both to a specified target project.

Mapping is generally based on plates, and only QC rows corresponding to the input file's plates will be copied to the final destination. If the data was not run on plates/wells, the entire QC contents are copied to the final destination.
