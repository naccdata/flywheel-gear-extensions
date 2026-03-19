# Requirements Document

## Introduction

The COManage UserRegistry enrollment flow creates duplicate skeleton CoPerson records and fails to match users to existing records when institutional identity providers (IdPs) return email addresses that differ from the skeleton email. Analysis of ~800 production records identified systematic email transformation patterns (subdomain variation, username aliasing, affiliated domains) that cause match failures. Additionally, records claimed via IdPs that return no email (notably fallback IdPs that lack institutional email data) are not represented as a distinct queryable state, and users who select the wrong IdP are not detected. This refactor improves the registry's resilience to email variation, surfaces incomplete claims as a first-class state, and adds diagnostic events for near-miss matches and wrong-IdP selection.

## Glossary

- **UserRegistry**: The repository class that wraps the COManage API, maintaining in-memory indexes of CoPerson records by email, registry ID, and name. Defined in `user_registry.py`.
- **RegistryPerson**: A wrapper around a COManage CoPersonMessage providing access to person attributes (emails, names, identifiers, status). Defined in `user_registry.py`.
- **ActiveUserProcess**: The process class that handles active user entries by looking them up in the UserRegistry, creating new skeletons when no match is found, and routing to claimed/unclaimed queues. Defined in `user_processes.py`.
- **Skeleton_Record**: A CoPerson record created in COManage with a name and email but not yet claimed by the user.
- **Claimed_Record**: A CoPerson record where the user has logged in via an IdP, resulting in an `oidcsub` identifier and a verified email address.
- **Incomplete_Claim_Record**: A CoPerson record that has an `oidcsub` identifier (user logged in) but no email address, because the IdP did not return one.
- **Parent_Domain**: The last two segments of an email domain (e.g., `umich.edu` from `med.umich.edu`). Used for domain-aware fallback matching.
- **Domain_Relationship_Config**: A configuration parameter that maps child domains to their parent domains and affiliated domains for fallback matching purposes.
- **IdP_Domain_Config**: A configuration parameter that maps email domains to their expected identity providers, distinguishing domains with institutional IdPs from domains that use the Fallback_IdP.
- **Fallback_IdP**: The identity provider used when a user's email domain does not have a dedicated institutional IdP in CILogon. This is a configurable value in the IdP_Domain_Config (currently ORCID in production). The fallback IdP typically does not return institutional email addresses in authentication tokens.
- **UserEventCollector**: The event collection infrastructure that accumulates UserProcessEvent objects during gear execution for reporting. Defined in `event_models.py`.
- **FailureAnalyzer**: The class that analyzes complex failure scenarios and produces diagnostic events. Defined in `failure_analyzer.py`.
- **Near_Miss_Match**: A candidate record found through domain-aware or name-based lookup that is not an exact email match, requiring operator review before association.

## Requirements

### Requirement 1: Domain-Aware Fallback Lookup

**User Story:** As an operator, I want the UserRegistry to find candidate records when the exact email does not match but the email domains are related, so that duplicate skeletons are not created for users whose IdP returns a parent or child domain variant.

#### Acceptance Criteria

1. WHEN an exact email lookup returns no results, THE UserRegistry SHALL provide a method to retrieve candidate RegistryPerson records whose email addresses share the same Parent_Domain as the query email.
2. THE UserRegistry SHALL maintain a secondary index keyed by Parent_Domain that maps to the set of RegistryPerson records with email addresses in that Parent_Domain.
3. WHEN the domain-aware lookup returns candidates, THE UserRegistry SHALL include the matched email address and the domain relationship for each candidate so the caller can assess match quality.
4. THE UserRegistry SHALL accept a Domain_Relationship_Config parameter that defines parent-child and affiliated domain relationships, rather than hardcoding specific domain mappings.
5. THE UserRegistry SHALL preserve exact email lookup as the primary path; domain-aware lookup SHALL operate as a separate fallback method that does not affect the performance of exact matching.
6. THE domain resolution strategy (how Parent_Domain is extracted, what constitutes a domain relationship) SHALL be determined by the Domain_Relationship_Config, not by hardcoded heuristics such as "last two segments of the domain." The config SHALL support explicit parent-child mappings and affiliated-domain groupings so that institutions with non-standard domain hierarchies (e.g., `upmc.edu` affiliated with `pitt.edu`) can be represented.

### Requirement 2: Index Records by Registry ID Regardless of Email

**User Story:** As a developer, I want all CoPerson records with a registry ID to be findable via `find_by_registry_id()`, so that Incomplete_Claim_Records are not invisible to the registry.

#### Acceptance Criteria

1. WHEN a CoPerson record has a registry ID, THE UserRegistry SHALL add the record to the registry-ID index regardless of whether the record has email addresses.
2. WHEN `find_by_registry_id()` is called with a registry ID belonging to an Incomplete_Claim_Record, THE UserRegistry SHALL return the corresponding RegistryPerson object.
3. THE UserRegistry SHALL continue to index records with email addresses in the email-based index as it does today.

### Requirement 3: Incomplete Claim as First-Class State

**User Story:** As a developer, I want to distinguish between unclaimed, incomplete-claim, and fully-claimed records on RegistryPerson, so that callers can query the claim state without relying on the `__bad_claims` side channel.

#### Acceptance Criteria

1. THE RegistryPerson SHALL provide a method to indicate whether the record is an Incomplete_Claim_Record (has `oidcsub` identifier but no verified email address).
2. THE RegistryPerson SHALL provide a method to indicate whether the record is unclaimed (no `oidcsub` identifier).
3. THE RegistryPerson `is_claimed()` method SHALL continue to return True only when the record is active, has a verified email, and has an `oidcsub` identifier from cilogon.org.
4. WHEN a record transitions from unclaimed to incomplete-claim (gains `oidcsub` but no email), THE RegistryPerson incomplete-claim method SHALL return True and `is_claimed()` SHALL return False.

### Requirement 4: Support Multiple Emails on Skeleton Creation

**User Story:** As an operator, I want skeleton records to be created with both the contact email and the authentication email when both are available, so that the chance of matching the IdP-returned email during claim is increased.

#### Acceptance Criteria

1. THE `RegistryPerson.create()` method SHALL accept a list of email addresses instead of a single email address.
2. WHEN multiple email addresses are provided, THE `RegistryPerson.create()` method SHALL create an EmailAddress entry for each provided address with type "official".
3. WHEN a single email address is provided, THE `RegistryPerson.create()` method SHALL behave identically to the current implementation (backward compatible).
4. THE ActiveUserProcess SHALL pass both the contact email and the authentication email to `RegistryPerson.create()` when both are available and distinct.

### Requirement 5: Name-Based Index for Duplicate Detection

**User Story:** As an operator, I want the UserRegistry to detect potential duplicate records by name before creating a new skeleton, so that operators are alerted when a near-match exists.

#### Acceptance Criteria

1. THE UserRegistry SHALL maintain a name-based index that maps normalized full names to RegistryPerson records.
2. THE UserRegistry SHALL provide a method to retrieve candidate RegistryPerson records by full name from the name-based index.
3. THE name-based index SHALL cover all records in the registry, not only Incomplete_Claim_Records.
4. WHEN the name-based lookup returns candidates, THE UserRegistry SHALL return the full list of candidates without filtering, so the caller can apply its own match-quality assessment.
5. THE name normalization strategy (e.g., case folding, whitespace handling, ordering of name components) SHALL be configurable or implemented as an injectable function, so that normalization rules can be adjusted without modifying the UserRegistry implementation.

### Requirement 6: Improved ActiveUserProcess Decision Logic

**User Story:** As an operator, I want the enrollment flow to check domain-aware and name-based candidates before creating a new skeleton, so that potential duplicates are flagged for review instead of silently created.

#### Acceptance Criteria

1. WHEN exact email lookup returns no results, THE ActiveUserProcess SHALL check domain-aware candidates and name-based candidates before creating a new Skeleton_Record.
2. WHEN domain-aware or name-based candidates are found, THE ActiveUserProcess SHALL emit a diagnostic event through the UserEventCollector and SHALL NOT automatically associate the user with a candidate record.
3. WHEN no exact match, no domain-aware candidates, and no name-based candidates are found, THE ActiveUserProcess SHALL create a new Skeleton_Record as it does today.
4. THE ActiveUserProcess SHALL preserve exact email matching as the first and fastest lookup step, with no change to the existing exact-match path.

### Requirement 7: Diagnostic Events for Near-Miss Matches

**User Story:** As an operator, I want the system to emit specific diagnostic events when near-miss matches are found, so that I can investigate potential duplicates and take corrective action.

#### Acceptance Criteria

1. WHEN a domain-related near-miss is found (same Parent_Domain, different exact email), THE ActiveUserProcess SHALL emit a UserProcessEvent with a category that identifies it as a domain-related near-miss.
2. WHEN a name-based near-miss is found (same full name, different email domain), THE ActiveUserProcess SHALL emit a UserProcessEvent with a category that identifies it as a name-based near-miss.
3. WHEN both domain-related and name-based signals match the same candidate (same Parent_Domain and same full name), THE ActiveUserProcess SHALL emit a UserProcessEvent with a category that identifies it as a combined-signal near-miss, indicating the strongest duplicate indicator.
4. THE near-miss diagnostic events SHALL include the user context from the directory entry and the candidate record details (email, name, registry ID) so operators can assess the match.

### Requirement 8: Detect Wrong IdP Selection

**User Story:** As an operator, I want the system to detect when a user with an institutional-IdP-eligible email domain claims via the Fallback_IdP instead, so that I can remediate by deleting the bad record and having the user reclaim with the correct IdP.

#### Acceptance Criteria

1. WHEN an Incomplete_Claim_Record is detected, THE FailureAnalyzer SHALL check whether the user's skeleton email domain maps to an institutional IdP using the IdP_Domain_Config, and whether the claim was made through a different IdP than the one configured for that domain.
2. WHEN the skeleton email domain maps to an institutional IdP and the user claimed via a different IdP (e.g., the Fallback_IdP), THE FailureAnalyzer SHALL emit a UserProcessEvent indicating wrong IdP selection, with an action message to delete the record and reclaim using the expected institutional IdP.
3. WHEN the skeleton email domain is configured in the IdP_Domain_Config as using the Fallback_IdP (i.e., the domain has no institutional IdP available), THE FailureAnalyzer SHALL NOT flag the claim as wrong IdP selection.
4. THE FailureAnalyzer SHALL use the same Parent_Domain logic from the domain-aware lookup to resolve subdomains to their parent domain's IdP mapping (e.g., `med.umich.edu` resolves to the `umich.edu` IdP mapping).
5. THE IdP_Domain_Config SHALL be a configuration parameter, not hardcoded domain-to-IdP mappings. The identity of the Fallback_IdP SHALL itself be a configurable value within the IdP_Domain_Config.

### Requirement 9: External Configuration of Domain-Specific Rules

**User Story:** As an operator, I want all domain-specific rules (domain relationships, IdP mappings, name normalization) to be loaded from external configuration files, so that the system can adapt to new institutions and domain changes without code modifications.

#### Acceptance Criteria

1. THE Domain_Relationship_Config and IdP_Domain_Config SHALL be defined as Pydantic models that can be loaded from external YAML files, following the same pattern used by the AuthMap configuration in the user management gear (file input declared in the gear manifest, loaded via `model_validate`, and injected into the process environment).
2. THE gear manifest SHALL declare the domain configuration as a file input so that operators can update domain rules independently of code deployments.
3. THE Domain_Relationship_Config SHALL support at minimum: explicit parent-child domain mappings (e.g., `med.umich.edu` → `umich.edu`), affiliated domain groupings (e.g., `upmc.edu` grouped with `pitt.edu`), and a default parent-domain extraction strategy for domains not explicitly listed.
4. THE IdP_Domain_Config SHALL support at minimum: mapping email domains to their expected institutional IdP, designating which domains use the Fallback_IdP (because the institution has no CILogon-federated IdP), specifying the identity of the Fallback_IdP itself, and resolving subdomains to their parent domain's IdP mapping via the Domain_Relationship_Config.
5. WHEN no external configuration file is provided, THE system SHALL fall back to a sensible default behavior (e.g., parent-domain extraction using the last two domain segments) so that the feature is functional without requiring configuration.
6. THE configuration models SHALL validate their contents on load and raise clear errors for malformed or contradictory entries (e.g., a domain listed as both institutional-IdP and fallback-only).
