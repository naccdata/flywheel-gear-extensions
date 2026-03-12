# Implementation Plan: Study Model Flexible Configuration

## Overview

This implementation refactors the StudyModel to support datatype-level mode configuration and per-dashboard level configuration, enabling mixed-mode studies while maintaining backward compatibility. The implementation follows a phased approach: first creating the new data models, then updating validation and migration logic, then modifying the project management integration, and finally adding comprehensive tests.

## Development Environment

**CRITICAL**: This project uses the `kiro-pants-power` for all Pants build system commands and devcontainer management. All quality checks, tests, and builds MUST be executed using the power tools, not manual bash commands.

### Required Tools

- Use `pants_fix` tool for code formatting and auto-fixes
- Use `pants_lint` tool for linting
- Use `pants_check` tool for type checking
- Use `pants_test` tool for running tests
- Use `full_quality_check` tool for complete validation workflow

The power automatically manages the devcontainer lifecycle - no manual container management needed.

### Troubleshooting

If you encounter any issues using the kiro-pants-power tools:
1. Document the issue in a file named `.kiro/specs/study-model-flexible-configuration/power-issues.md`
2. Include: the tool used, parameters provided, error message, and context
3. Notify the user about the issue
4. Attempt fallback to manual scripts only if absolutely necessary

## Tasks

- [ ] 1. Create new configuration models
  - [ ] 1.1 Create DatatypeConfig model in common/src/python/projects/study.py
    - Define DatatypeConfig with name and mode fields
    - Add Pydantic configuration with kebab-case aliases
    - Add docstring explaining the model purpose
    - _Requirements: 1.1, 1.2_

  - [ ] 1.2 Create DashboardConfig model in common/src/python/projects/study.py
    - Define DashboardConfig with name and level fields
    - Set default level to "center"
    - Add Pydantic configuration with kebab-case aliases
    - Add docstring explaining the model purpose
    - _Requirements: 2.1, 2.2_

- [ ] 2. Update StudyModel with new fields and helper methods
  - [ ] 2.1 Add new fields to StudyModel
    - Modify datatypes field to accept List[str] | List[DatatypeConfig]
    - Modify dashboards field to accept Optional[List[str] | List[DashboardConfig]]
    - Add funding_organization as Optional[str]
    - Mark mode field as Optional (deprecated)
    - _Requirements: 1.1, 2.1, 3.1_

  - [ ] 2.2 Implement helper methods for datatype access
    - Implement get_datatype_mode(datatype: str) method
    - Implement get_datatype_configs() method
    - Implement get_datatypes_by_mode(mode) method
    - _Requirements: 1.5_

  - [ ] 2.3 Implement helper methods for dashboard access
    - Implement get_dashboard_level(dashboard: str) method
    - Implement get_dashboard_configs() method
    - Implement get_dashboards_by_level(level) method
    - _Requirements: 2.6, 2.7_

- [ ] 3. Implement validation and migration logic
  - [ ] 3.1 Implement normalize_datatypes field validator
    - Handle List[str] format with study-level mode migration
    - Handle List[DatatypeConfig] format
    - Validate mode values are "aggregation" or "distribution"
    - Log deprecation warning when using study-level mode
    - _Requirements: 1.2, 1.3, 7.1, 8.7_

  - [ ] 3.2 Implement normalize_dashboards field validator
    - Handle List[str] format with default level "center"
    - Handle List[DashboardConfig] format
    - Handle None value
    - Validate level values are "center" or "study"
    - _Requirements: 2.2, 8.8_

  - [ ] 3.3 Implement validate_configuration model validator
    - Validate primary studies have aggregation-only datatypes
    - Validate all datatypes have mode configuration
    - Validate all dashboard levels are valid
    - Raise clear validation errors for invalid configurations
    - _Requirements: 1.4, 9.1, 9.3, 9.4_

  - [ ] 3.4 Write unit tests for StudyModel validation
    - Test migration from old format to new format
    - Test primary study validation (aggregation-only)
    - Test affiliated study with mixed modes
    - Test validation error messages
    - Test edge cases (empty lists, single items)
    - _Requirements: 1.2, 1.4, 7.1, 9.1, 9.2_

  - [ ] 3.5 Write property test for datatype mode storage and retrieval
    - **Property 1: Datatype Mode Storage and Retrieval**
    - **Validates: Requirements 1.1, 1.5**

  - [ ] 3.6 Write property test for backward compatible mode field
    - **Property 3: Backward Compatible Mode Field**
    - **Validates: Requirements 1.3, 7.1**

  - [ ]* 3.7 Write property test for primary study validation
    - **Property 4: Primary Study Aggregation-Only Validation**
    - **Validates: Requirements 1.4, 9.1**

  - [ ]* 3.8 Write property test for dashboard level storage and retrieval
    - **Property 6: Dashboard Level Storage and Retrieval**
    - **Validates: Requirements 2.1, 2.6**

- [ ] 4. Implement serialization support
  - [ ] 4.1 Verify DatatypeConfig serialization
    - Test serialization to dict/JSON format
    - Test deserialization from dict/JSON format
    - Verify kebab-case aliases work correctly
    - _Requirements: 8.1, 8.2_

  - [ ] 4.2 Verify DashboardConfig serialization
    - Test serialization to dict/JSON format
    - Test deserialization from dict/JSON format
    - Verify default level "center" is applied
    - _Requirements: 8.3, 8.4_

  - [ ] 4.3 Verify funding_organization serialization
    - Test serialization when field is present
    - Test deserialization when field is present
    - Test handling when field is absent
    - _Requirements: 8.5, 8.6_

  - [ ]* 4.4 Write property test for datatype configuration round trip
    - **Property 19: Datatype Configuration Serialization Round Trip**
    - **Validates: Requirements 8.1, 8.2**

  - [ ]* 4.5 Write property test for dashboard configuration round trip
    - **Property 20: Dashboard Configuration Serialization Round Trip**
    - **Validates: Requirements 8.3, 8.4**

  - [ ]* 4.6 Write property test for funding organization round trip
    - **Property 8: Funding Organization Round Trip**
    - **Validates: Requirements 3.1, 3.2, 8.5, 8.6**

- [ ] 5. Update StudyMappingVisitor for mixed-mode support
  - [ ] 5.1 Modify visit_study method to group datatypes by mode
    - Use get_datatypes_by_mode() to separate aggregation and distribution datatypes
    - Create AggregationMapper only if aggregation datatypes exist
    - Create DistributionMapper only if distribution datatypes exist
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ] 5.2 Update mapper invocations to pass datatype lists
    - Pass aggregation datatypes list to AggregationMapper methods
    - Pass distribution datatypes list to DistributionMapper methods
    - Ensure both mappers can operate on the same study
    - _Requirements: 5.3, 10.3_

  - [ ] 5.3 Update dashboard creation to use per-dashboard levels
    - Use get_dashboards_by_level("center") for center-level dashboards
    - Log and skip study-level dashboards (not implemented yet)
    - Maintain backward compatibility for old dashboard format
    - _Requirements: 2.4, 2.5, 6.1, 6.2, 6.3, 6.4_

  - [ ] 5.4 Write unit tests for mixed-mode study mapping
    - Test study with only aggregation datatypes
    - Test study with only distribution datatypes
    - Test study with mixed modes
    - Test dashboard creation at different levels
    - _Requirements: 4.1, 4.2, 5.1, 5.2, 6.1, 10.1, 10.2_

- [ ] 6. Update mapper methods to accept datatype lists
  - [ ] 6.1 Modify AggregationMapper.map_center_pipelines signature
    - Add datatypes parameter to method signature
    - Use datatypes parameter instead of study.datatypes
    - Update all calls to this method
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ] 6.2 Modify DistributionMapper methods to accept datatype lists
    - Add datatypes parameter to relevant methods
    - Use datatypes parameter instead of study.datatypes
    - Update all calls to these methods
    - _Requirements: 5.1, 5.2_

  - [ ] 6.3 Write unit tests for mapper datatype filtering
    - Test AggregationMapper with subset of datatypes
    - Test DistributionMapper with subset of datatypes
    - Verify correct projects are created for specified datatypes only
    - _Requirements: 4.1, 4.2, 5.1, 5.2_

- [ ] 7. Add comprehensive integration tests
  - [ ]* 7.1 Write property test for aggregation mode project creation
    - **Property 9: Aggregation Mode Ingest Projects**
    - **Property 10: Aggregation Mode Sandbox Projects**
    - **Validates: Requirements 4.1, 4.2**

  - [ ]* 7.2 Write property test for aggregation mode retrospective projects
    - **Property 11: Aggregation Mode Retrospective Projects**
    - **Validates: Requirements 4.3**

  - [ ]* 7.3 Write property test for aggregation mode accepted project
    - **Property 12: Aggregation Mode Accepted Project**
    - **Validates: Requirements 4.4**

  - [ ]* 7.4 Write property test for published study release infrastructure
    - **Property 13: Published Study Release Infrastructure**
    - **Validates: Requirements 4.5**

  - [ ]* 7.5 Write property test for distribution mode projects
    - **Property 14: Distribution Mode Center Projects**
    - **Property 15: Distribution Mode Study Projects**
    - **Validates: Requirements 5.1, 5.2**

  - [ ] 7.6 Write property test for mixed mode independence
    - **Property 16: Mixed Mode Independence**
    - **Validates: Requirements 5.3**

  - [ ]* 7.7 Write property test for dashboard creation at center level
    - **Property 7: Dashboard Creation at Center Level**
    - **Validates: Requirements 2.4, 6.1**

- [ ] 8. Add backward compatibility tests
  - [ ]* 8.1 Write property test for primary study validation preservation
    - **Property 17: Primary Study Validation Preservation**
    - **Validates: Requirements 7.3**

  - [ ] 8.2 Write property test for backward compatible project structure
    - **Property 18: Backward Compatible Project Structure**
    - **Validates: Requirements 7.4**

  - [ ]* 8.3 Write property test for single mode aggregation compatibility
    - **Property 28: Single Mode Aggregation Backward Compatibility**
    - **Validates: Requirements 10.4**

  - [ ]* 8.4 Write property test for single mode distribution compatibility
    - **Property 29: Single Mode Distribution Backward Compatibility**
    - **Validates: Requirements 10.5**

  - [ ] 8.5 Write unit tests with real study configurations
    - Test with actual NACC study configurations
    - Verify old format configurations still work
    - Verify project structure matches expected output
    - _Requirements: 7.1, 7.3, 7.4_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties across many inputs
- Unit tests validate specific examples, edge cases, and error conditions
- The implementation maintains backward compatibility throughout
- All code changes are in the common package (common/src/python/projects/)
