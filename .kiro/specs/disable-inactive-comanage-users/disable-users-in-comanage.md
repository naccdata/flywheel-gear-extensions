# Disable Users in COmanage When Marked Inactive

## Context

When a user is marked inactive in the NACC directory, the system currently disables them in Flywheel (sets `disabled=True` and clears permissions via `InactiveUserProcess`). We need to also suspend them in the COmanage registry so that downstream OIDC authorization is revoked.

### COmanage API Details

- The COmanage Core API supports updating a CO Person record via `PUT /api/co/{coid}/core/v1/people?identifier={registry_id}` with a `CoPersonMessage` body
- **The update does NOT support patch semantics.** Both create (POST) and update (PUT) require sending the **entire JSON document** representing the full desired state of the CoPerson and all related models. The correct pattern is: read the record, make the minor change, send back the entire (slightly) modified record.
- **Critical**: If you strip out related models (e.g., only send `EmailAddress` without `Name`, `CoPersonRole`, `Identifier`, `OrgIdentity`, etc.), the API interprets that as a request to delete those missing models, which will throw a cryptic deletion error.
- Per guidance from CILogon support (Scott Koranda), the correct approach is to set the **CO Person status to `"S"` (Suspended)** on the CO Person record (not the CO Person Role, since we don't use COUs)
- Suspended status is reversible — the user can be re-enabled by setting status back to `"A"`
- Suspending removes the user from the `CO:members:active` group, which controls authorization for downstream OIDC clients
- Identifier associations are preserved when suspending

### Update Pattern (from CILogon support)

The generated SDK provides a `CoPersonMessage` object with a `co_person` property and list properties for related models (`EmailAddress`, `Name`, `CoPersonRole`, `Identifier`, `OrgIdentity`, etc.). To update a record:

1. **GET** the full `CoPersonMessage` for the person
2. Modify only the field you need (e.g., `co_person.status = "S"`)
3. **PUT** the entire `CoPersonMessage` back — all related models must remain intact

### Key Files

- `common/src/python/users/user_registry.py` — `UserRegistry` class, `RegistryPerson` class
- `common/src/python/users/user_processes.py` — `InactiveUserProcess` class
- `common/src/python/users/user_process_environment.py` — `UserProcessEnvironment`
- `comanage/coreapi.yaml` — COmanage Core API OpenAPI spec (PUT endpoint and `CoPerson.status` enum)
- `gear/user_management/src/python/user_app/run.py` — gear entry point that wires up the environment

## What Needs to Change

### 1. UserRegistry — add update/suspend capability

`UserRegistry` (`common/src/python/users/user_registry.py`) needs a new method to suspend a CO Person record via the COmanage Core API PUT endpoint. The `UserRegistry` currently has `add` and `get` methods but no `update` method.

The suspend flow must:
1. Retrieve the **full** `CoPersonMessage` from COmanage (using the existing `get` or `find_by_registry_id` method)
2. Modify **only** the `CoPerson.status` field to `"S"` (Suspended) — all other fields and related models (`Name`, `CoPersonRole`, `Identifier`, `OrgIdentity`, `EmailAddress`, etc.) must remain unchanged
3. Submit the **entire** modified `CoPersonMessage` back via PUT — omitting related models will cause the API to attempt to delete them

### 2. InactiveUserProcess — suspend in COmanage after disabling in Flywheel

`InactiveUserProcess` (`common/src/python/users/user_processes.py`) currently only disables users in Flywheel. It needs to also suspend the user in COmanage. The process should:

- Disable the user in Flywheel first (existing behavior)
- Then suspend the user in COmanage (new behavior)
- The two services should be independent — a failure in one should not prevent the other from proceeding
- Look up the user in COmanage by email to find their registry record
- Set the CO Person status to `"S"` (Suspended) via the API
- Handle COmanage API errors independently from Flywheel errors
- Collect events using the existing `USER_DISABLED` category for the aggregate action across both services

### 3. Re-enabling users

When processing an active user entry, if a user already exists in COmanage with the same email but has status `"S"` (Suspended), re-enable them by setting status back to `"A"` (Active) instead of creating a new record. This does not cover users who have moved to a new institution — that would be a new record.

### 4. Dry-run support

The Flywheel proxy already supports dry-run mode. The COmanage suspension/re-enable operations should also respect dry-run mode, logging the intended action without calling the API.

### 5. InactiveUserProcess already has access to UserRegistry

`InactiveUserProcess` receives a `UserProcessEnvironment` which already has a `user_registry` property, so no new wiring should be needed.

## Design Decisions

- **Event tracking**: Use the existing `USER_DISABLED` `EventCategory` to capture the aggregate disable action across both Flywheel and COmanage. Event messages should distinguish which service was affected.
- **Ordering**: Disable in Flywheel first, then suspend in COmanage. Failures are independent.
- **Full record update**: The COmanage PUT endpoint does **not** support patch semantics. The entire `CoPersonMessage` with all related models must be sent back. Omitting models causes the API to try to delete them. Always: read → modify → write back the full record.
- **Re-enable scope**: Only re-enable users with the same email. Users at new institutions get new records.
- **Dry-run**: Supported for all new COmanage operations.
