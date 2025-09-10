# Identifier Provisioning

This gear provisions NACCIDs for data entered with Participant Enrollment and Transfer (ENROLL) forms.

## Processing

The following diagrams describe the processing of the ENROLL form data.

First, check that the module for the form is the right one, and then determine whether this is a new enrollment or transfer.

```mermaid
graph TB
    start((*)) -->module{module is\nENROLL} -- no --> moduleerror((error))
    module -- yes --> enrltype{Is new\nenrollment?}
    enrltype -- yes --> newenrollment(New Enrollment)    
    enrltype -- no --> transfer(Transfer)
    newenrollment --> stop((done))
    transfer --> stop
style start fill:#000, stroke:#000
```

### New Enrollment

A new enrollment involves a series of validations that result in errors if the identifying information is inconsistent.
The last step checks the demographics, and if any NACCIDs exists with matching demographics, an error is reported.
In this case, someone will need to manually check the match.
If there are no existing participants that could be matches, then a new NACCID is provisioned.

```mermaid
graph TB
    start((*)) --> naccidforptid{Does NACCID\n exist for\n ADCID,PTID?}
    naccidforptid -- yes --> errorptid((error))
    naccidforptid -- no --> naccidforguid{Does NACCID\n exist for\n GUID?}
    naccidforguid -- yes --> errorguid((error))
    naccidforguid -- no --> checkdemographics{Does NACCID\n exist for\n demographics?}
    checkdemographics -- yes --> errordemo((error))
    checkdemographics -- no --> provision(Provision new NACCID) --> stop((done))
style start fill:#000, stroke:#000
```


```mermaid
sequenceDiagram
    Gear->>Identifiers: get(ADCID,PTID)
    alt has NACCID
        Identifiers->>Gear: identifier record
        break when NACCID exists
            Gear->>File: exists error
        end
    else no match
        Identifiers->>Gear: no match error
        Gear->>Demographics: get(demographics)
        Demographics->>Gear: NACCID list
        alt has matches
          break when list not empty
              Gear->>File: demographic match error
          end
        else no match
            Gear->>Identifiers: add(ADCID,PTID,GUID)
            Identifiers->>Gear: NACCID
            Gear->>Demographics: add(NACCID,demographics)
        end

    end
```

### Transfer

A transfer is reported by the receiving center.
When a form represents a transfer into a center, the goal is to

* identify the participant by NACCID
* confirm that the participant has transferred
* link new identifiers to the NACCID
  
```mermaid
graph TB
    start((*)) --> 
    
    
    naccidprovided{Is NACCID\n provided?}
    naccidprovided -- yes --> hasparticipant{Is NACCID valid?}
    naccidprovided -- no --> prevenrolled{Was\n previously\n enrolled?}
    hasparticipant -- yes --> prevenrolled
    hasparticipant -- no --> noparticipant((error))
    prevenrolled -- no --> whattransfer((error))
    prevenrolled -- yes --> oldptidknown{Is old\n PTID known?}
    prevenrolled -- unknown --> recordtransfer(Create transfer record) --> pendingerror((error))
    oldptidknown -- no --> recordtransfer
    oldptidknown -- yes --> naccidforoldptid{Does NACCID\n exist for PTID\n of previous\n enrollment?}

    naccidforoldptid -- yes --> existingnaccid{Do\n NACCIDs\n match?}
    naccidforoldptid -- no --> nonaccid((error))
    existingnaccid -- yes --> recordtransfer
    existingnaccid -- no --> mismatch((error))
style start fill:#000, stroke:#000
```

