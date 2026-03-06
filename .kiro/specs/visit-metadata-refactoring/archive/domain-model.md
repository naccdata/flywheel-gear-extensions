# Domain Model: NACC Data Platform

## Purpose

This document describes the core domain concepts for data collected in the NACC Data Platform. It focuses on understanding the real-world entities and their relationships, independent of implementation details.

## Core Entities

### Participant

The individual about which data is being collected in the NACC research program.

**Identifiers:**
- `ptid` - Participant identifier assigned by the center
- `naccid` - Participant identifier assigned by NACC (corresponds to an adcid-ptid pair)

### Center

The research center where participants have visits to collect data. Also known as ADC (Alzheimer's Disease Center).

**Identifier:**
- `adcid` - Center identifier assigned by NACC

### Visit

A formal annual event where a participant goes to a center for observation and collection of a canonical set of data.

**Identifiers:**
- `visitnum` - Center-assigned sequence number for the visit (not necessarily numeric)
- `date` - The date of the first day of the visit

**Important:** Visit is a structured concept in NACC's data model. Not all data collected about a participant is associated with a visit.

## Data Categories

### Visit-Associated Data

Data collected during a formal visit event.

**Characteristics:**
- Associated with a specific visit (has visitnum)
- Has a visit date (the date of the visit)
- Part of the canonical annual data collection

**Primary Type:**
- **Visit Forms** - Clinical assessment forms collected during annual visits
  - Each form has a name (A1, B1, C1, D1, D2, etc.)
  - Forms have a packet indicating visit type:
    - I = Initial visit
    - F = Followup visit
    - T = Telephone visit

### Non-Visit Data

Data collected about a participant but not associated with a specific formal visit.

**Characteristics:**
- Associated with a participant and center
- Has a collection date (when the data was collected)
- No visitnum (not part of a formal visit)

**Types:**
- **One-time Forms** - Forms collected once
  - Example: NP form (post-mortem pathology exam data)
- **Sporadic Forms** - Forms collected as needed
  - Example: Milestone form (life events, participation changes)
- **Imaging Data** - Medical imaging studies
  - MR, CT, PET scans
  - May be collected near or during a visit, but not formally associated with it
  - Identified by modality (MR, CT, PET, etc.)
- **Other Research Data** - Other kinds of research data not currently collected

## Data Identification

All data in the platform needs to be identified by a combination of fields:

**Participant & Center (always present):**
- `adcid` - Center identifier
- `ptid` - Participant identifier (assigned by center)
- `naccid` - Participant identifier (assigned by NACC)

**Temporal (always present):**
- `date` - For visit data: visit date; for non-visit data: collection date

**Visit Association (only for visit data):**
- `visitnum` - Visit sequence number

**Data Type Identification:**
- **Forms:** Form name (A1, B1, NP, Milestone, etc.)
- **Forms:** Packet (I, F, T) - indicates visit type for visit forms
- **Images:** Modality (MR, CT, PET, etc.)
- **Other data types:** Will have their own identifying attributes

## Domain Relationships

```
Center (adcid)
  └─> has many Participants (ptid)
        └─> identified by NACC as (naccid)
        └─> has many Visits (visitnum, date)
              └─> collects Visit-Associated Data
                    └─> primarily Visit Forms (form name, packet)
        └─> has Non-Visit Data (collection date)
              └─> Non-Visit Forms (form name, optional packet)
              └─> Imaging Data (modality, collection date)
              └─> Other Research Data
```

## Key Domain Rules

1. **Visit Uniqueness:** A visit is uniquely identified by (adcid, ptid, visitnum)
2. **Participant Identification:** A participant can be identified by either (adcid, ptid) or (naccid)
3. **Visit vs Non-Visit:** Data is either associated with a visit (has visitnum) or not (no visitnum)
4. **Date Semantics:** 
   - For visit data: date is the visit date
   - For non-visit data: date is the collection date
5. **Form Packets:** Packets (I/F/T) are meaningful for visit forms, may be optional or have different meaning for non-visit forms
6. **Imaging Independence:** Imaging data is not formally associated with visits, even if collected during the same time period

## Domain Concepts Not Covered

This domain model focuses on data identification. It does not cover:
- Quality control processes
- Event tracking and audit
- Data storage and retrieval mechanisms
- Processing pipelines
- User permissions and access control

These are implementation concerns that use the domain model but are not part of the core domain itself.
