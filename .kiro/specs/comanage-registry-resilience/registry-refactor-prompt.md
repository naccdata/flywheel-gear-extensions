# Refactor: Improve UserRegistry resilience to email variation and incomplete claims

## Background

### How enrollment works today

The user enrollment flow is driven by a directory of users maintained by NACC. Each directory entry has two email addresses: a contact email (`email`) and an authentication email (`auth_email`, sourced from the `fw_email` field in the directory). The authentication email is the one used to create and look up CoPerson skeleton records in the COManage registry.

The flow in `ActiveUserProcess.visit()` (in `user_processes.py`) works like this:

1. Look up the user's `auth_email` in `UserRegistry.get(email)` — this is an exact string match against all email addresses on all CoPerson records.
2. If no match is found, check `UserRegistry.get_bad_claim(full_name)` for incomplete claims (claimed records with no email).
3. If still no match, create a new skeleton CoPerson record with the `auth_email` as a single official email, and send a claim invitation.
4. If a match is found, check whether any matching record is claimed (has `oidcsub` identifier + verified email). Route to claimed or unclaimed processing accordingly.

When a user claims their account, they log in through an identity provider (IdP) via CILogon. The IdP returns an email address in the token. COManage matches this to the skeleton's email to complete the claim. If the IdP-returned email doesn't match any email on the skeleton, the claim fails or a new record is created.

### What goes wrong

Analysis of ~800 production CoPerson records identified systematic patterns where the enrollment flow creates duplicate skeletons or fails to match users to existing records. The root cause is that institutional IdPs frequently return email addresses that differ from what was used to create the skeleton.

Out of the unclaimed skeleton records analyzed:
- **743** were never attempted (no matching pending claim record found)
- **17** were superseded (a different skeleton for the same person was successfully claimed)
- **15** had empty tokens (the IdP returned no email at all)

Of the 17 superseded records, the original skeleton could have been detected as a duplicate at creation time if the system had domain-aware matching or name-based lookup.

### Observed email transformation patterns

These patterns were identified by comparing skeleton emails against the emails on successfully claimed records and pending claim records. All examples below use fictional names and email usernames; the institutional domains are real because the domain relationships are the point.

#### Pattern 1: Child domain dropped (most common)

The skeleton is created with a departmental subdomain, but the institutional IdP asserts the parent domain. The username typically stays the same.

| Name | Skeleton Email | Claimed/IdP Email | Institution |
|------|---------------|-------------------|-------------|
| Alice Torres | atorres@**med**.umich.edu | atorres@umich.edu | University of Michigan |
| Brian Novak | bnovak@**med**.umich.edu | bnovak@umich.edu | University of Michigan |
| Carmen Reyes | creyesg@**med**.umich.edu | creyesg@umich.edu | University of Michigan |
| David Huang | dhuang@**health**.ucdavis.edu | dhuang@ucdavis.edu | UC Davis |
| Elena Marsh | em4521@**cumc**.columbia.edu | em4521@columbia.edu | Columbia University |
| Frank Osei | fo2087@**cumc**.columbia.edu | frank.osei@columbia.edu | Columbia University |

Affected subdomains: `med.umich.edu`, `health.ucdavis.edu`, `cumc.columbia.edu`, `loni.usc.edu`

#### Pattern 2: Child domain added (reverse)

The skeleton uses the parent domain, but the IdP returns a departmental subdomain.

| Name | Skeleton Email | Claimed Email | Institution |
|------|---------------|---------------|-------------|
| Grace Kim | grace.kim@upenn.edu | grace.kim@**pennmedicine**.upenn.edu | UPenn |
| Henry Patel | hpatel@upenn.edu | henry.patel@**pennmedicine**.upenn.edu | UPenn |
| Irene Zhao | izhao5@wisc.edu | izhao@**medicine**.wisc.edu | UW-Madison |

Affected subdomains: `pennmedicine.upenn.edu`, `medicine.wisc.edu`

#### Pattern 3: Username format variation (same domain)

The domain matches exactly, but the IdP returns a different username alias.

| Name | Skeleton Email | IdP Email | Institution |
|------|---------------|-----------|-------------|
| James Okafor | jokafor@emory.edu | james.okafor@emory.edu | Emory University |
| Karen Walsh | kwalsh@emory.edu | karen.walsh@emory.edu | Emory University |
| Leo Fernandez | lfern@emory.edu | leofernandez@emory.edu | Emory University |
| Maria Santos | msantos1@jhmi.edu | msantos@jhmi.edu | Johns Hopkins |

Emory assigns users multiple email aliases; the IdP returns a `firstname.lastname` form while the directory uses a short alias.

#### Pattern 4: Affiliated but separate domains

| Name | Skeleton Email | Claimed Email | Institution |
|------|---------------|---------------|-------------|
| Nina Volkov | nvolkov@upmc.edu | nvolk3@pitt.edu | University of Pittsburgh |

UPMC and Pitt are affiliated institutions. Users may have accounts at both.

#### Pattern 5: Student vs main domain

| Name | Skeleton Email | Claimed Email | Institution |
|------|---------------|---------------|-------------|
| Oscar Diaz | oscar.diaz@northwestern.edu | oscardiaz2024@u.northwestern.edu | Northwestern |

#### Pattern 6: Completely different domain

| Name | Skeleton Email | Claimed Email | Institution |
|------|---------------|---------------|-------------|
| Paul Jennings | paulj.science@gmail.com | pjenn@msu.edu | Michigan State |

Personal email vs institutional. These are not catchable by domain matching alone — only name matching would find them.

### False positive risk in name matching

Name-based matching has real false positive risk. The analysis found cases where different people with the same last name at the same institution were incorrectly associated:

| Skeleton Name | Skeleton Email | Claimed Name | Claimed Email | Institution |
|--------------|---------------|--------------|---------------|-------------|
| Rachel Park | rpark42@kumc.edu | Robin Park | rkpark@kumc.edu | Univ. of Kansas Medical Center |
| Sandra Liu | sandra.liu@ucsf.edu | Stephanie Liu | stephanie.liu3@ucsf.edu | UC San Francisco |
| Amy Liu | amy.liu@ucsf.edu | Stephanie Liu | stephanie.liu3@ucsf.edu | UC San Francisco |

Two skeletons (Sandra Liu, Amy Liu) both mapped to the same claimed record (Stephanie Liu). These are false positives — different people with the same last name at the same institution.

### Incomplete claims (empty tokens)

Some IdPs — ORCID in particular, but also some institutional IdPs — return no email in the authentication token. The user has genuinely logged in (the CoPerson record has an `oidcsub` identifier), but the record has no email address. This is an incomplete state: at least one downstream system (Flywheel) uses email for OIDC-based user identification, so a record without email cannot be treated as fully claimed.

The current code handles this through a `__bad_claims` side-channel in `UserRegistry`, indexed by primary name. The `FailureAnalyzer` class detects ORCID-specific cases and emits appropriate events. But the registry itself doesn't represent "incomplete claim" as a distinct state — `is_claimed()` returns `False` for these records because it requires a verified email.

### Wrong IdP selection (ORCID when institutional IdP is available)

Users choose their identity provider during the claim flow. Some users with institutional email addresses (e.g., `umich.edu`, `columbia.edu`) mistakenly select ORCID as their IdP instead of their institution's IdP. ORCID typically does not return an institutional email, so the claim either fails (empty token) or succeeds with incomplete data.

This is a detectable mistake. The system knows the user's email domain from the skeleton record, and we can build a mapping from email domains to expected IdPs based on the CILogon IdP registry and observed claim data. The claimed-org-domains data from production shows which email domains have been successfully claimed through which IdPs. For example:

- `umich.edu` → University of Michigan (institutional IdP)
- `columbia.edu` → Columbia University (institutional IdP)
- `cumc.columbia.edu` → Columbia University (institutional IdP)
- `emory.edu` → Emory University (institutional IdP)

Some domains legitimately only have ORCID as an option because the institution doesn't participate in CILogon's federated identity:

- `advocatehealth.org` → ORCID only
- `bannerhealth.com` → ORCID only
- `ccf.org` → ORCID only
- `vumc.org` → ORCID only

When a user with an institutional-IdP-eligible domain claims via ORCID, the system should be able to detect this mismatch and flag it — either at claim time (if the system can inspect the pending claim) or after the fact when the incomplete claim is discovered. The appropriate remediation is to delete the bad record and have the user reclaim using their institutional IdP.

### Known CILogon IdP domains

The system interacts with ~62 distinct email domains. Of these, 36 map directly to a CILogon identity provider (e.g., `umich.edu` → University of Michigan). The remaining 26 are subdomains or affiliated domains that don't have their own IdP entry (e.g., `med.umich.edu`, `cumc.columbia.edu`, `pennmedicine.upenn.edu`, `upmc.edu`).

The unmatched domains that appear in skeleton records but have no direct CILogon IdP include:
`cumc.columbia.edu`, `hs.uci.edu`, `jh.edu`, `jhmi.edu`, `jhu.edu`, `loni.usc.edu`, `med.unc.edu`, `med.usc.edu`, `medicine.wisc.edu`, `mednet.ucla.edu`, `mgh.harvard.edu`, `neurology.ufl.edu`, `neurology.unc.edu`, `pennmedicine.upenn.edu`, `phhp.ufl.edu`, `u.northwestern.edu`, `upmc.edu`, and others.

This data could be used to build a domain-relationship map for matching purposes.

---

## Goals

- Reduce duplicate skeleton creation by improving how the registry matches incoming users to existing records when emails don't match exactly.
- Make the registry aware of records in incomplete states (claimed but missing email) as a distinct, queryable condition rather than handling them only through the `bad_claims` side channel.
- Support creating CoPerson records with multiple email addresses when more than one is known, since the COManage data model supports this and it increases the chance of matching the IdP-returned email.
- Surface diagnostic information when near-matches are found but not auto-matched, so operators can investigate potential duplicates.
- Preserve the invariant that a record without email is not in a complete/usable state for downstream OIDC-dependent systems.
- Detect when a user with an institutional-IdP-eligible email domain claims via ORCID instead, and surface this as a specific diagnostic event so operators can remediate.

## Scope

The refactor primarily touches two files:

- `user_registry.py` — the `RegistryPerson` and `UserRegistry` classes
- `user_processes.py` — the enrollment flow that uses `UserRegistry`

Supporting files like `failure_analyzer.py`, `user_entry.py`, and `event_models.py` may need changes to accommodate new event categories or entry attributes.

## Key areas to address

### 1. Domain-aware lookup in UserRegistry

`UserRegistry.get(email)` currently does exact-match lookup only. When this returns empty, `ActiveUserProcess` creates a new skeleton.

Add a fallback matching capability that can identify candidate records where the email domain is related to the query email's domain. The most common relationship is parent/child domain: `med.umich.edu` and `umich.edu` share the parent domain `umich.edu`. This covers Patterns 1, 2, and 5 above.

This should be a separate step from exact match — not a replacement — so that exact matches remain fast and unambiguous. When fallback matching produces candidates, the caller should have enough context (which records matched, what the domain relationship is) to decide how to proceed.

A useful approach is to extract the parent domain (last two segments of the domain, e.g., `umich.edu` from `med.umich.edu`) and maintain a secondary index by parent domain. This is a simple heuristic that covers the majority of observed cases.

### 2. Index records by registry ID regardless of email presence

Currently, `UserRegistry.__add_person()` only adds a person to `__registry_map_by_id` inside the branch where `person.email_addresses` is truthy. Records that have a registry ID but no email (the incomplete-claim case) are not findable via `find_by_registry_id()`. This forces `FailureAnalyzer.analyze_missing_claimed_user()` to compensate.

Fix the indexing so that any record with a registry ID is findable by that ID, independent of whether it has email addresses.

### 3. Represent incomplete claims as a first-class state

The current model is binary: `is_claimed()` returns true (active + verified email + oidcsub) or false. Records that have an `oidcsub` identifier but no email are genuinely claimed from the IdP's perspective, but incomplete from the system's perspective because downstream OIDC systems require email for user identification.

Make this state queryable on `RegistryPerson` so that callers can distinguish between:
- **Unclaimed**: no `oidcsub` identifier — user has never logged in
- **Incomplete claim**: has `oidcsub` but missing email — IdP didn't return complete data
- **Claimed**: has `oidcsub` and verified email — fully usable

The existing `is_claimed()` semantics (requiring email) should remain correct for downstream consumers that need a fully-usable record. The new state distinction should be additive — new methods or properties, not changes to `is_claimed()` behavior.

### 4. Support multiple emails when creating skeleton records

`RegistryPerson.create()` currently accepts a single `email` parameter and creates one `EmailAddress` with `type="official"`. The COManage data model supports multiple email addresses per CoPerson record.

The NACC directory provides two email addresses per user: a contact email (`email`) and an authentication email (`auth_email`). Currently only `auth_email` is used when creating the skeleton. Extend `create()` to accept multiple email addresses so the caller can pass both. This increases the chance that the skeleton's email set will overlap with whatever the IdP returns during claim, reducing email-mismatch failures.

### 5. Add a name-based index to UserRegistry

Currently, name-based lookup only exists in the `__bad_claims` dict (and only for records with no email). The analysis showed that name matching detected 12 of 21 superseded cases that exact email matching missed.

Add a name-based index that covers all records (or at least unclaimed records without a registry ID match). This is a secondary signal for detecting potential duplicates before creating a new skeleton. Name matches alone are ambiguous (common names, name variations — see the false positive examples above), so this should surface candidates for review rather than auto-match.

### 6. Improve ActiveUserProcess decision logic

`ActiveUserProcess.visit()` currently follows: exact email match → bad claim check → create new skeleton. With the new matching capabilities, the logic should become:

1. Exact email match → proceed as today (fast path)
2. No exact match → check domain-aware candidates and name-based candidates
3. If strong candidates exist (e.g., same parent domain + same full name), flag for review or attempt to associate rather than creating a new skeleton
4. If no candidates → create new skeleton as today

The specific thresholds for auto-matching vs flagging should err heavily toward flagging. False positives (incorrectly merging two different people) are significantly worse than false negatives (creating a duplicate that can be cleaned up later).

### 7. Diagnostic events for near-misses

When the system finds domain-aware or name-based candidates but doesn't auto-match, it should emit events through the existing `UserEventCollector` / `UserProcessEvent` infrastructure. This gives operators visibility into potential duplicates and replaces the current behavior of silently creating a new skeleton with no indication that a near-match existed.

Consider adding event categories for:
- Domain-related near-miss (same parent domain, different exact email)
- Name-based near-miss (same name, different email domain)
- Combined signal (same parent domain + same name — strongest indicator)

### 8. Detect wrong IdP selection (ORCID vs institutional)

When an incomplete claim is detected (has `oidcsub` but no email), the system should check whether the user's skeleton email domain maps to an institutional IdP. If it does, the user likely chose ORCID by mistake when they should have used their institution's IdP.

This requires a mapping from email domains to expected IdPs. The mapping can be built from:

- The CILogon IdP registry (which institutions participate in federated identity)
- Observed production data (which email domains have been successfully claimed through which IdPs)

The mapping should account for subdomains — if `umich.edu` maps to University of Michigan, then `med.umich.edu` should too (using the same parent-domain logic from area 1).

When a wrong-IdP claim is detected, the system should emit a specific diagnostic event (distinct from a generic incomplete claim) with an actionable message: the bad record needs to be deleted and the user needs to reclaim using their institutional IdP. The `FailureAnalyzer` already has a `detect_incomplete_claim` method that distinguishes ORCID claims; this should be extended to also check whether the user's domain had an institutional IdP available.

Domains that legitimately only have ORCID (e.g., `advocatehealth.org`, `bannerhealth.com`, `ccf.org`, `vumc.org`) should not trigger this detection — those users correctly chose ORCID because it's their only option.

## Constraints

- A record without email is not fully usable. Downstream OIDC systems depend on email for user identification. This invariant must be preserved.
- Exact email matching must remain the primary and fastest lookup path. Domain-aware matching is a fallback, not a replacement.
- False-positive matches (incorrectly merging two different people) are significantly worse than false negatives (creating a duplicate). Err on the side of flagging for review.
- The `is_claimed()` method's current return value semantics must not change in a way that breaks existing callers. New state distinctions should be additive.
- The `UserRegistry` class is used in production Flywheel gears. Changes should be backward-compatible or coordinated with callers.
