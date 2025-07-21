# User Enrollment Process

## Center member authorization

A center member is authorized as a user of the NACC Directory by the Center Administrator.
In this process, the administrator adds a center member to the NACC Directory in REDCap and authorizes their access to the NACC Data Platform.
Authorization initiates a Data Platform Access survey that prompts the user to provide the email to be used for authentication.

```mermaid
sequenceDiagram
    actor admin as Center<br/>Admin
    actor member as Center<br/>Member

    participant directory as NACC<br/>Directory
    admin ->> directory: authorize
    directory -) member: access survey email
    member ->> directory: auth email
```

## Pulling NACC Directory

The directory is pulled nightly to Flywheel using the [Directory Pull](../pull_directory/) gear.
This gear writes a file with user information in an admin project on Flywheel.

```mermaid
sequenceDiagram
    scheduler ->> puller: initiate
    note right of scheduler: nightly

    participant puller as Directory Pull
    participant directory as NACC<br/>Directory
    puller ->> directory: get user information
    puller ->> Flywheel: write directory user file
```

## User management

Updates to the NACC directory user file trigger a gear rule that runs the user management gear.

```mermaid
sequenceDiagram
    Rule ->> usermgmt: initiate
    note right of Rule: update to directory user file

    participant usermgmt as User<br/>Management
    usermgmt ->> Flywheel: pull directory users
    loop each authorized user
        usermgmt ->> CoManage: get by email
        actor member as Center<br/>Member   
        alt user not in registry
            usermgmt ->> CoManage: create
            usermgmt -) member: claim email
        else user is claimed in registry
            usermgmt ->> Flywheel: find by registry ID
            alt if user not in Flywheel
              usermgmt ->> Flywheel: create
              usermgmt -) member: notification email
            end
            usermgmt ->> Flywheel: set user roles
        else is unclaimed for more than a week
            usermgmt -) member: claim reminder email
        end
    end
```
