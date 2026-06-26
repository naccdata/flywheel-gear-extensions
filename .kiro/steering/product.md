# Product Overview

NACC Flywheel Extensions is a monorepo containing Python-based tools and gears for managing the NACC (National Alzheimer's Coordinating Center) Data Platform on Flywheel.

## Core Functionality

- **Project Management**: Creates and manages NACC projects as Flywheel groups and projects
- **User Management**: Attaches users to centers in roles identified in NACC directory
- **Data Pipelines**: Processes and curates data through various pipelines (CSV, enrollment, forms, SCAN metadata)
- **Center Management**: Manages research centers and their data
- **Identifier Management**: Provisions and looks up identifiers for participants
- **Form Processing**: Schedules, screens, transforms, and QC checks forms
- **Data Curation**: Aggregates and curates data with attribute curators

## Key Components

- **Gears**: 26+ specialized Flywheel gears for specific data processing tasks
- **nacc-common**: Shared Python package with utilities for accessing the NACC Data Platform
- **Common Libraries**: Shared code for centers, identifiers, data processing, and Flywheel integration

## Target Users

Research centers and administrators working with Alzheimer's disease data through the NACC Data Platform.
