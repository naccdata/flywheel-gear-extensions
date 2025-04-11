# Data Aggregation and Curation

## Processes

```mermaid
flowchart LR
    A@{ shape: rect, label: "&laquo;project&raquo;\ningest/\ndistribution" }
    B@{ shape: rect, label: "&laquo;project&raquo;\naccepted" }
    C@{ shape: processes, label: "soft-copy" }
    D@{ shape: processes, label: "curator" }
    E@{ shape: processes, label: "soft-copy" }
    F@{ shape: rect, label: "&laquo;project&raquo;\nmaster-project" }
    A --> C
    C --> B
    B --> D
    D --> B
    B --> E
    E --> F
```

## Gears:

- [soft-copy](https://gitlab.com/flywheel-io/scientific-solutions/gears/soft-copy)
- [attribute-curator](../attribute-curator/)