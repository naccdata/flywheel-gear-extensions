# Web Access Authorization - TODO

## Current Status

As of the REDCap directory format update, we now parse two new access level fields from the `web_report_access` checkbox field:

1. **`web_access_level`** - For general webinars/presentations access (no study scope)
2. **`adrc_reports_access_level`** - For ADRC-specific reports and dashboards access

### Implementation Details

- **Location**: `common/src/python/users/nacc_directory.py` - `DirectoryAuthorizations` class
- **Source Field**: Both fields parse from the same REDCap `web_report_access` checkbox field
- **Values**: 
  - Empty string → `NoAccess` for both
  - `"Web"` → `ViewAccess` for web, `NoAccess` for adrc_reports
  - `"RepDash"` → `NoAccess` for web, `ViewAccess` for adrc_reports
  - `"Web,RepDash"` → `ViewAccess` for both

### Current Behavior

These fields are:
- ✅ Validated and parsed correctly from REDCap directory reports
- ✅ Stored in the `DirectoryAuthorizations` model
- ❌ **NOT converted to Flywheel authorizations** (intentionally)

The `__parse_fields()` method in `DirectoryAuthorizations` ignores both fields because:
- `web_access_level` splits into 3 parts (not the required 4: study_datatype_access_level)
- `adrc_reports_access_level` splits into 4 parts, but "reports" is not a valid `DatatypeNameType`

## TODO: After `feature/add-dashboard-projects` Merges

The `feature/add-dashboard-projects` branch adds infrastructure for dashboard projects as a new project type (alongside ingest, distribution, accepted). This is the right place to map the `adrc_reports_access_level` field.

### Required Changes

1. **Update `DirectoryAuthorizations.__parse_fields()`** to handle dashboard access:
   - Add special case for `adrc_reports_access_level` field
   - Map it to dashboard project access (not a datatype)
   - This may require a new authorization type or extending the existing authorization model

2. **Update `CenterAuthorizationVisitor`** to apply dashboard authorizations:
   - The dashboard branch already has `visit_dashboard_project()` method
   - Ensure users with `adrc_reports_access_level == "ViewAccess"` get appropriate roles on dashboard projects

3. **Consider `web_access_level` mapping**:
   - Determine if webinars/presentations should map to any Flywheel projects
   - This might be a separate community/public project type, or might not map to Flywheel at all
   - Document the decision

4. **Update tests**:
   - `common/test/python/user_test/test_web_access_to_user_entry.py` currently documents that these fields don't create authorizations
   - Update tests to verify dashboard project access is granted correctly

### Questions to Answer

- Should `web_access_level` grant access to any Flywheel projects, or is it purely for external systems?
- What specific role should users with `adrc_reports_access_level == "ViewAccess"` get on dashboard projects?
- Are there multiple dashboard projects per study, or one per center?
- Should dashboard access be study-specific (e.g., separate dashboards for ADRC, LEADS, CLARiTI)?

## References

- **REDCap Codebook Entry**:
  ```
  [web_report_access]
  Webinars and Reports access: checkbox
  Web - Webinars/Presentations (View access)
  RepDash - ADRC Program Reports and Dashboards (ADRC members only)
  ```

- **Dashboard Branch**: `feature/add-dashboard-projects`
  - Adds `DashboardProjectMetadata` class
  - Adds `dashboard_projects` to `CenterStudyMetadata`
  - Adds `visit_dashboard_project()` to authorization visitor

- **Related Files**:
  - `common/src/python/users/nacc_directory.py` - Field definitions and parsing
  - `common/src/python/users/authorization_visitor.py` - Authorization application
  - `common/src/python/centers/center_group.py` - Project metadata
  - `common/src/python/keys/types.py` - Datatype definitions
  - `common/test/python/user_test/test_web_access_*.py` - Tests

## Migration Notes

When implementing this:
1. The field names and parsing logic are already correct and don't need to change
2. Only the authorization mapping logic needs to be added
3. Existing tests document the current "no authorization" behavior and should be updated
4. No changes needed to REDCap integration or directory pulling
