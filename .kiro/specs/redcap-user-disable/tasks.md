# Implementation Plan: REDCap User Disable

## Overview

Add REDCap user role removal to the `InactiveUserProcess` disable flow and reorder the steps so that COmanage suspension happens last. The new step order is: (1) Flywheel disable, (2) COmanage lookup (resolve auth_email), (3) REDCap role removal with admin notification, (4) COmanage suspend.

Implementation proceeds bottom-up: helper function → visitor → event category → core disable logic → gear wiring → tests.

## Tasks

- [x] 1. Create `unassign_user_role` helper function
  - [x] 1.1 Create `common/src/python/users/redcap_user_operations.py` with `unassign_user_role(redcap_project, username)` function
    - Import `REDCapProject` from `redcap_api.redcap_project`
    - Call `redcap_project.assign_user_role(username, "")` and return the result
    - Let `REDCapConnectionError` propagate to the caller
    - Add a `BUILD` entry or confirm the existing `BUILD` file in `common/src/python/users/` covers new source files
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Create `REDCapDisableVisitor`
  - [x] 2.1 Create `common/src/python/users/redcap_disable_visitor.py` implementing `AbstractCenterMetadataVisitor`
    - Import visitor base class and metadata types from `centers.center_group`
    - Implement `visit_center` → iterate studies, `visit_study` → iterate ingest projects, `visit_form_ingest_project` → collect `redcap_pid` from each `REDCapFormProjectMetadata` in `redcap_projects`
    - All other visit methods (`visit_project`, `visit_ingest_project`, `visit_redcap_form_project`, `visit_distribution_project`, `visit_dashboard_project`, `visit_page_project`) are no-ops
    - Expose collected PIDs via a `redcap_pids` property returning `list[int]`
    - _Requirements: 3.1, 3.2_

- [x] 3. Add `REDCAP_USER_DISABLED` event category
  - [x] 3.1 Modify `common/src/python/users/event_models.py` to add `REDCAP_USER_DISABLED = "REDCap User Disabled"` to the `EventCategory` enum
    - Place it in the "Disable/re-enable categories" section alongside `USER_DISABLED` and `USER_RE_ENABLED`
    - _Requirements: 4.1_

- [x] 4. Implement REDCap disable logic in `InactiveUserProcess`
  - [x] 4.1 Add `email_client` and `support_emails` constructor parameters to `InactiveUserProcess`
    - Add `email_client: Optional[EmailClient] = None` and `support_emails: Optional[list[str]] = None` parameters
    - Store as private instance attributes `self.__email_client` and `self.__support_emails`
    - Import `EmailClient` from `notifications.email` and `EmailSendError` from `notifications.email`
    - _Requirements: 6.2, 6.3_

  - [x] 4.2 Add private `__disable_in_redcap` method to `InactiveUserProcess`
    - Method signature: `__disable_in_redcap(self, entry: UserEntry, user_context: UserContext, auth_email: Optional[str]) -> None`
    - **Username resolution**: if `entry.auth_email` is set use it; else if `auth_email` parameter is provided use it; else fall back to `entry.email`
    - **Center iteration**: get center map from `self.__env.admin_group.get_center_map()`, iterate ADCIDs, call `self.__env.admin_group.get_center(adcid)` for each
    - If center cannot be retrieved, log warning and continue
    - Get `CenterMetadata` via `center_group.get_project_info()`, apply `REDCapDisableVisitor` to collect PIDs
    - For each PID, get `REDCapProject` via `center_group.get_redcap_project(pid)`, if unavailable log and collect error event with `REDCAP_USER_DISABLED` category, continue
    - **Dry-run check**: if `self.__env.proxy.dry_run`, log intended action and collect success event with dry-run note, skip API call
    - Otherwise call `unassign_user_role(redcap_project, username)`, collect success event on success or error event on `REDCapConnectionError`
    - Track list of successfully unassigned projects (title and PID) for notification
    - After iteration, if any successes and `self.__email_client` is available, send notification email via `email_client.send_raw` with subject `[REDCap] inactive users to suspend`, body containing directory email, REDCap username, and list of affected projects
    - Catch `EmailSendError` from notification send, log and continue
    - Import `unassign_user_role` from `users.redcap_user_operations` and `REDCapDisableVisitor` from `users.redcap_disable_visitor`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 7.1, 7.2, 7.3, 7.4_

  - [x] 4.3 Restructure `InactiveUserProcess.visit()` into four steps
    - **Step 1 — Flywheel disable**: keep existing Flywheel disable logic unchanged
    - **Step 2 — COmanage lookup**: call `self.__env.user_registry.get(email=entry.email)` to get `person_list`, extract `auth_email` from first person's `email_address.mail` if found, store `person_list` for Step 4
    - **Step 3 — REDCap role removal**: call `self.__disable_in_redcap(entry, user_context, auth_email)`
    - **Step 4 — COmanage suspend**: move existing COmanage suspend logic here, use `person_list` from Step 2 (skip if no persons found)
    - Each step is independent — wrap each in its own try/except so failure of one does not block others
    - _Requirements: 3.6, 6.1_

- [x] 5. Wire `EmailClient` and support emails into `InactiveUserProcess` in `run.py`
  - [x] 5.1 Modify `gear/user_management/src/python/user_app/run.py` to pass `email_client` and `support_emails` to `InactiveUserProcess`
    - In the `UserProcess` construction area, create an `EmailClient` instance (reuse `create_ses_client()` and `self.__email_source`) and pass it along with `self.__support_emails` to `InactiveUserProcess`
    - This requires `InactiveUserProcess` to be constructed separately from `UserProcess`, or `UserProcess` to forward these parameters — follow the existing pattern where `UserProcess` creates `InactiveUserProcess` internally in its `execute()` method
    - Update `UserProcess.__init__` to accept and store `email_client` and `support_emails`, then pass them when constructing `InactiveUserProcess` in `execute()`
    - Update the `UserProcess(...)` call in `run.py` to pass the new parameters
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 6. Write unit tests for `unassign_user_role` helper
  - [x] 6.1 Create `common/test/python/user_test/test_redcap_user_operations.py`
    - Test that `unassign_user_role` calls `redcap_project.assign_user_role(username, "")` with correct arguments
    - Test that it returns the count from `assign_user_role`
    - Test that `REDCapConnectionError` propagates to the caller
    - Use `unittest.mock.Mock` for `REDCapProject`
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 7. Write unit tests for `REDCapDisableVisitor`
  - [x] 7.1 Create `common/test/python/user_test/test_redcap_disable_visitor.py`
    - Test visitor collects PIDs from `FormIngestProjectMetadata` with `redcap_projects`
    - Test visitor returns empty list when no form ingest projects exist
    - Test visitor skips non-form ingest projects (plain `IngestProjectMetadata`, `DistributionProjectMetadata`)
    - Test visitor collects PIDs across multiple studies and multiple form ingest projects
    - Build test `CenterMetadata` / `CenterStudyMetadata` / `FormIngestProjectMetadata` / `REDCapFormProjectMetadata` objects directly
    - _Requirements: 3.1, 3.2_

- [x] 8. Write unit tests for REDCap disable step in `InactiveUserProcess`
  - [x] 8.1 Create `common/test/python/user_test/test_inactive_user_process_redcap.py`
    - Test auth email resolution: entry with `auth_email` uses it directly, COmanage lookup result used when entry has no `auth_email`, fallback to directory email when no registry match
    - Test center iteration: skips centers with no form ingest projects, skips projects with unavailable credentials, continues after unassignment failure
    - Test dry-run mode: logs intended action, does not call `unassign_user_role`
    - Test event collection: success events have `REDCAP_USER_DISABLED` category with project title and PID, error events have `REDCAP_USER_DISABLED` category with error details
    - Test notification: sent when unassignments succeed, not sent when no unassignments, notification failure does not raise
    - Test step independence: REDCap step runs even if Flywheel disable fails, COmanage suspend runs even if REDCap step fails
    - Test four-step ordering: COmanage lookup happens before REDCap step, COmanage suspend happens after REDCap step
    - Mock `UserProcessEnvironment`, `NACCGroup`, `CenterGroup`, `REDCapProject`, `EmailClient`, `UserRegistry`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.2, 3.4, 3.5, 3.6, 3.7, 4.2, 4.3, 4.4, 5.1, 5.3, 5.5, 5.6, 7.1, 7.2, 7.3_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- The implementation language is Python, matching the existing codebase
- Each task references specific requirements for traceability
- The design has a Correctness Properties section but property-based tests are omitted per user request (skip optional tasks)
- All checkpoint tasks beyond the final one are omitted per user request
- Tasks build incrementally: helper → visitor → event category → core logic → wiring → tests
