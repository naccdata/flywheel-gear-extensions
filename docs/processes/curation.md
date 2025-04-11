# Data Aggregation and Curation

```mermaid
flowchart LR
    ingest/distribution -- copy --> accepted
    accepted -- curator --> accepted
    accepted -- copy --> master
```