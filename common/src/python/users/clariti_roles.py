"""CLARiTI role mapping functionality.

This module provides functions to map CLARiTI (Clinical Research in Alzheimer's
and Related Dementias Imaging and Translational Informatics) roles from the
NACC directory REDCap report to Activity objects for authorization.

CLARiTI roles are categorized into:
- Payment roles: Grant access to payment tracker dashboard
- Organizational roles: Grant access to enrollment dashboard
- Admin core member: Grants access to both dashboards

The mapping ensures deduplication when multiple roles grant access to the same
dashboard.
"""

from typing import TYPE_CHECKING

from users.authorizations import Activity, DashboardResource

if TYPE_CHECKING:
    from users.nacc_directory import DirectoryAuthorizations


def map_clariti_roles_to_activities(
    directory_auth: "DirectoryAuthorizations",
) -> list[Activity]:
    """Map CLARiTI roles from DirectoryAuthorizations to Activity objects.

    Mapping rules:
    - Payment roles (7) → payment-tracker dashboard view access
    - All organizational roles (14) → enrollment dashboard view access
    - Admin core member → both payment-tracker and enrollment view access
    - cl_pay_access_level="ViewAccess" → payment-tracker view access

    Deduplicates activities when multiple roles map to the same permission.

    Args:
        directory_auth: DirectoryAuthorizations object with CLARiTI role fields

    Returns:
        List of Activity objects for CLARiTI dashboard access
    """
    # Use a set for automatic deduplication
    activities: set[Activity] = set()

    # Payment roles (7 fields)
    payment_role_fields = [
        "loc_clariti_role___u01copi",
        "loc_clariti_role___pi",
        "loc_clariti_role___piadmin",
        "loc_clariti_role___copi",
        "loc_clariti_role___subawardadmin",
        "loc_clariti_role___addlsubaward",
        "loc_clariti_role___studycoord",
    ]

    # Check if any payment role is set
    has_payment_role = any(
        getattr(directory_auth, field, None) is True for field in payment_role_fields
    )

    # Check cl_pay_access_level
    has_pay_access = (
        hasattr(directory_auth, "clariti_dashboard_pay_access_level")
        and directory_auth.clariti_dashboard_pay_access_level == "ViewAccess"
    )

    # Add payment tracker activity if any payment source grants access
    if has_payment_role or has_pay_access:
        activities.add(
            Activity(
                resource=DashboardResource(dashboard="payment-tracker"), action="view"
            )
        )

    # Organizational roles (14 fields)
    organizational_role_fields = [
        "loc_clariti_role___u01copi",
        "loc_clariti_role___pi",
        "loc_clariti_role___piadmin",
        "loc_clariti_role___copi",
        "loc_clariti_role___subawardadmin",
        "loc_clariti_role___addlsubaward",
        "loc_clariti_role___studycoord",
        "loc_clariti_role___mpi",
        "loc_clariti_role___orecore",
        "loc_clariti_role___crl",
        "loc_clariti_role___advancedmri",
        "loc_clariti_role___physicist",
        "loc_clariti_role___addlimaging",
        "loc_clariti_role___reg",
    ]

    # Check if any organizational role is set
    has_org_role = any(
        getattr(directory_auth, field, None) is True
        for field in organizational_role_fields
    )

    # Add enrollment activity if any organizational role is set
    if has_org_role:
        activities.add(
            Activity(resource=DashboardResource(dashboard="enrollment"), action="view")
        )

    # Admin core member role
    if getattr(directory_auth, "ind_clar_core_role___admin", None) is True:
        # Admin gets both dashboards
        activities.add(
            Activity(
                resource=DashboardResource(dashboard="payment-tracker"), action="view"
            )
        )
        activities.add(
            Activity(resource=DashboardResource(dashboard="enrollment"), action="view")
        )

    return list(activities)
