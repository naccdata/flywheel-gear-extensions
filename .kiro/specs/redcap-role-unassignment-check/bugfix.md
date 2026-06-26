# Bugfix Requirements Document

## Introduction

When disabling a user in REDCap, the `InactiveUserProcess.__disable_in_redcap` method iterates over all centers and all REDCap projects, calling `__unassign_redcap_project` for every project — even those where the user was never a member. This results in unnecessary REDCap API calls and misleading success events that suggest a role was unassigned when the user had no role in the project.

The fix should check whether the user exists in a REDCap project before attempting to unassign their role. If the user is not found in the project, the unassignment should be skipped and no success event should be generated.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user is being disabled and the user does NOT exist in a REDCap project THEN the system calls `unassign_user_role` for that project anyway, making an unnecessary API call to REDCap

1.2 WHEN a user is being disabled and the user does NOT exist in a REDCap project THEN the system emits a success event indicating the role was unassigned, even though the user had no role in that project

1.3 WHEN a user is being disabled across multiple centers THEN the system attempts to unassign the user's role from every REDCap project across all centers without checking membership, resulting in potentially many unnecessary API calls

### Expected Behavior (Correct)

2.1 WHEN a user is being disabled and the user does NOT exist in a REDCap project THEN the system SHALL skip the unassignment for that project without making an API call to `assign_user_role`

2.2 WHEN a user is being disabled and the user does NOT exist in a REDCap project THEN the system SHALL NOT emit a success event for that project

2.3 WHEN a user is being disabled and the user DOES exist in a REDCap project THEN the system SHALL unassign the user's role and emit a success event as before

2.4 WHEN checking whether a user has a role assignment in a REDCap project THEN the system SHALL query the project's user-role mappings (via the REDCap `userRoleMapping` export API) and check whether the username appears in the assignments

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user is being disabled and the user DOES exist in a REDCap project THEN the system SHALL CONTINUE TO call `unassign_user_role` and emit a success event with the project title and PID

3.2 WHEN a user is being disabled and REDCap project credentials are unavailable THEN the system SHALL CONTINUE TO skip that project and emit an error event indicating credentials are unavailable

3.3 WHEN a user is being disabled in dry-run mode THEN the system SHALL CONTINUE TO skip the actual `unassign_user_role` call and emit a dry-run success event

3.4 WHEN `unassign_user_role` raises a `REDCapConnectionError` THEN the system SHALL CONTINUE TO catch the error, emit an error event, and continue processing the next project

3.5 WHEN a center group cannot be retrieved THEN the system SHALL CONTINUE TO skip that center and continue processing remaining centers

3.6 WHEN the user-role mapping export API call fails with a `REDCapConnectionError` THEN the system SHALL treat the failure gracefully (e.g., log an error event and skip the project) without crashing the disable flow
