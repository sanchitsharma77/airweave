"""Admin-only API endpoints for organization management."""

from typing import List, Optional
from uuid import UUID

from fastapi import Body, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from airweave import crud, schemas
from airweave.api import deps
from airweave.api.context import ApiContext
from airweave.api.router import TrailingSlashRouter
from airweave.billing.service import billing_service
from airweave.core.context_cache_service import context_cache
from airweave.core.exceptions import InvalidStateError, NotFoundException
from airweave.core.organization_service import organization_service
from airweave.core.shared_models import FeatureFlag as FeatureFlagEnum
from airweave.core.source_connection_service_helpers import source_connection_helpers
from airweave.core.sync_service import sync_service
from airweave.core.temporal_service import temporal_service
from airweave.crud.crud_organization_billing import organization_billing
from airweave.db.unit_of_work import UnitOfWork
from airweave.integrations.auth0_management import auth0_management_client
from airweave.integrations.stripe_client import stripe_client
from airweave.models.organization import Organization
from airweave.models.organization_billing import OrganizationBilling
from airweave.models.user_organization import UserOrganization
from airweave.platform.sync.config import SyncExecutionConfig
from airweave.schemas.organization_billing import BillingPlan, BillingStatus

router = TrailingSlashRouter()


@router.get("/feature-flags", response_model=List[dict])
async def list_available_feature_flags(
    ctx: ApiContext = Depends(deps.get_context),
) -> List[dict]:
    """Get all available feature flags in the system (admin only).

    Args:
        ctx: API context

    Returns:
        List of feature flag definitions with name and value

    Raises:
        HTTPException: If user is not an admin
    """
    _require_admin(ctx)

    # Return all feature flags from the enum
    return [{"name": flag.name, "value": flag.value} for flag in FeatureFlagEnum]


def _require_admin(ctx: ApiContext) -> None:
    """Validate that the user is an admin or superuser.

    Args:
        ctx: The API context

    Raises:
        HTTPException: If user is not an admin or superuser
    """
    # Allow both explicit admins AND superusers (for system operations and tests)
    if not ctx.has_user_context or not (ctx.user.is_admin or ctx.user.is_superuser):
        raise HTTPException(status_code=403, detail="Admin access required")


def _build_sort_subqueries(query, sort_by: str):
    """Build necessary subqueries for sorting and return updated query + subqueries.

    Returns:
        Tuple of (query, subqueries_dict) where subqueries_dict contains named subqueries.
    """
    from datetime import datetime

    from sqlalchemy import select as sa_select

    from airweave.models.billing_period import BillingPeriod
    from airweave.models.source_connection import SourceConnection
    from airweave.models.usage import Usage
    from airweave.models.user import User
    from airweave.schemas.billing_period import BillingPeriodStatus

    subqueries = {}

    # For usage-based sorting, join Usage and BillingPeriod
    if sort_by in ["entity_count", "query_count"]:
        now = datetime.utcnow()
        query = query.outerjoin(
            BillingPeriod,
            and_(
                BillingPeriod.organization_id == Organization.id,
                BillingPeriod.period_start <= now,
                BillingPeriod.period_end > now,
                BillingPeriod.status.in_(
                    [
                        BillingPeriodStatus.ACTIVE,
                        BillingPeriodStatus.TRIAL,
                        BillingPeriodStatus.GRACE,
                    ]
                ),
            ),
        ).outerjoin(Usage, Usage.billing_period_id == BillingPeriod.id)
        subqueries["Usage"] = Usage

    # For user_count sorting
    if sort_by == "user_count":
        user_count_subq = (
            sa_select(
                UserOrganization.organization_id,
                func.count(UserOrganization.user_id).label("user_count"),
            )
            .group_by(UserOrganization.organization_id)
            .subquery()
        )
        query = query.outerjoin(
            user_count_subq, Organization.id == user_count_subq.c.organization_id
        )
        subqueries["user_count_subq"] = user_count_subq

    # For source_connection_count sorting
    if sort_by == "source_connection_count":
        source_connection_count_subq = (
            sa_select(
                SourceConnection.organization_id,
                func.count(SourceConnection.id).label("source_connection_count"),
            )
            .group_by(SourceConnection.organization_id)
            .subquery()
        )
        query = query.outerjoin(
            source_connection_count_subq,
            Organization.id == source_connection_count_subq.c.organization_id,
        )
        subqueries["source_connection_count_subq"] = source_connection_count_subq

    # For last_active_at sorting
    if sort_by == "last_active_at":
        max_active_subq = (
            sa_select(
                UserOrganization.organization_id,
                func.max(User.last_active_at).label("max_last_active"),
            )
            .join(User, UserOrganization.user_id == User.id)
            .group_by(UserOrganization.organization_id)
            .subquery()
        )
        query = query.outerjoin(
            max_active_subq, Organization.id == max_active_subq.c.organization_id
        )
        subqueries["max_active_subq"] = max_active_subq

    return query, subqueries


def _get_sort_column(sort_by: str, subqueries: dict):
    """Get the SQLAlchemy column to sort by."""
    from airweave.models.usage import Usage

    # Map sort_by to column
    column_map = {
        "billing_plan": OrganizationBilling.billing_plan,
        "billing_status": OrganizationBilling.billing_status,
        "entity_count": Usage.entities,
        "query_count": Usage.queries,
        "is_member": Organization.created_at,  # Handled client-side
    }

    if sort_by in column_map:
        return column_map[sort_by]
    if sort_by == "user_count" and "user_count_subq" in subqueries:
        return subqueries["user_count_subq"].c.user_count
    if sort_by == "source_connection_count" and "source_connection_count_subq" in subqueries:
        return subqueries["source_connection_count_subq"].c.source_connection_count
    if sort_by == "last_active_at" and "max_active_subq" in subqueries:
        return subqueries["max_active_subq"].c.max_last_active
    if hasattr(Organization, sort_by):
        return getattr(Organization, sort_by)
    return Organization.created_at  # Default


async def _update_or_create_membership(
    db: AsyncSession, ctx: ApiContext, organization_id: UUID, role: str
) -> bool:
    """Update existing membership or create new one. Returns True if membership changed."""
    # Check if user is already a member
    existing_user_org = None
    for user_org in ctx.user.user_organizations:
        if user_org.organization.id == organization_id:
            existing_user_org = user_org
            break

    if existing_user_org:
        return await _update_membership_role(db, ctx, organization_id, role, existing_user_org)

    return await _create_new_membership(db, ctx, organization_id, role)


async def _update_membership_role(
    db: AsyncSession, ctx: ApiContext, organization_id: UUID, role: str, existing_user_org
) -> bool:
    """Update role if different, return True if changed."""
    if existing_user_org.role == role:
        ctx.logger.info(
            f"Admin {ctx.user.email} already member of org {organization_id} with role {role}"
        )
        return False

    from sqlalchemy import update

    stmt = (
        update(UserOrganization)
        .where(
            UserOrganization.user_id == ctx.user.id,
            UserOrganization.organization_id == organization_id,
        )
        .values(role=role)
    )
    await db.execute(stmt)
    await db.commit()
    ctx.logger.info(f"Admin {ctx.user.email} updated role in org {organization_id} to {role}")
    return True


async def _create_new_membership(
    db: AsyncSession, ctx: ApiContext, organization_id: UUID, role: str
) -> bool:
    """Create new membership, return True if successful."""
    try:
        user_org = UserOrganization(
            user_id=ctx.user.id,
            organization_id=organization_id,
            role=role,
            is_primary=False,
        )
        db.add(user_org)
        await db.commit()
        ctx.logger.info(
            f"Admin {ctx.user.email} added self to org {organization_id} with role {role}"
        )
        return True
    except Exception as e:
        ctx.logger.error(f"Failed to add admin to organization: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to add user to organization: {str(e)}")


@router.get("/organizations", response_model=List[schemas.OrganizationMetrics])
async def list_all_organizations(
    db: AsyncSession = Depends(deps.get_db),
    ctx: ApiContext = Depends(deps.get_context),
    skip: int = 0,
    limit: int = Query(1000, le=10000, description="Maximum number of organizations to return"),
    search: Optional[str] = Query(None, description="Search by organization name"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
) -> List[schemas.OrganizationMetrics]:
    """List all organizations with comprehensive metrics (admin only).

    This endpoint fetches all organizations with their billing info and usage metrics
    using optimized queries to minimize database round-trips.

    Args:
        db: Database session
        ctx: API context
        skip: Number of organizations to skip
        limit: Maximum number of organizations to return (default 1000, max 10000)
        search: Optional search term to filter by organization name
        sort_by: Field to sort by (name, created_at, billing_plan, user_count,
            source_connection_count, entity_count, query_count, last_active_at)
        sort_order: Sort order (asc or desc)

    Returns:
        List of all organizations with comprehensive metrics

    Raises:
        HTTPException: If user is not an admin
    """
    _require_admin(ctx)

    # Build the base query with billing join
    query = select(Organization).outerjoin(
        OrganizationBilling, Organization.id == OrganizationBilling.organization_id
    )

    # Build sort subqueries based on sort_by field
    query, subqueries = _build_sort_subqueries(query, sort_by)

    # Apply search filter
    if search:
        query = query.where(Organization.name.ilike(f"%{search}%"))

    # Apply sorting (is_member sorting handled client-side)
    sort_column = _get_sort_column(sort_by, subqueries)

    if sort_order.lower() == "asc":
        query = query.order_by(sort_column.asc().nullslast())
    else:
        query = query.order_by(sort_column.desc().nullslast())

    # Apply pagination
    query = query.offset(skip).limit(limit)

    # Execute query
    result = await db.execute(query)
    orgs = list(result.scalars().all())

    if not orgs:
        return []

    org_ids = [org.id for org in orgs]

    # Fetch all billing info in one query
    billing_query = select(OrganizationBilling).where(
        OrganizationBilling.organization_id.in_(org_ids)
    )
    billing_result = await db.execute(billing_query)
    billing_map = {b.organization_id: b for b in billing_result.scalars().all()}

    # Fetch user counts in one query
    user_count_query = (
        select(
            UserOrganization.organization_id,
            func.count(UserOrganization.user_id).label("count"),
        )
        .where(UserOrganization.organization_id.in_(org_ids))
        .group_by(UserOrganization.organization_id)
    )
    user_count_result = await db.execute(user_count_query)
    user_count_map = {row.organization_id: row.count for row in user_count_result}

    # Fetch admin's memberships in these organizations
    admin_membership_query = select(UserOrganization).where(
        UserOrganization.user_id == ctx.user.id,
        UserOrganization.organization_id.in_(org_ids),
    )
    admin_membership_result = await db.execute(admin_membership_query)
    admin_membership_map = {
        uo.organization_id: uo.role for uo in admin_membership_result.scalars().all()
    }

    # Fetch last active timestamp for each organization (most recent user activity)
    from airweave.models.user import User

    last_active_query = (
        select(
            UserOrganization.organization_id,
            func.max(User.last_active_at).label("last_active"),
        )
        .join(User, UserOrganization.user_id == User.id)
        .where(UserOrganization.organization_id.in_(org_ids))
        .group_by(UserOrganization.organization_id)
    )
    last_active_result = await db.execute(last_active_query)
    last_active_map = {row.organization_id: row.last_active for row in last_active_result}

    # Fetch current usage for all organizations using CRUD layer
    usage_map = await crud.usage.get_current_usage_for_orgs(db, organization_ids=org_ids)

    # Fetch source connection counts in one query (dynamically counted, not stored in usage)
    from airweave.models.source_connection import SourceConnection

    source_connection_count_query = (
        select(
            SourceConnection.organization_id,
            func.count(SourceConnection.id).label("count"),
        )
        .where(SourceConnection.organization_id.in_(org_ids))
        .group_by(SourceConnection.organization_id)
    )
    source_connection_result = await db.execute(source_connection_count_query)
    source_connection_map = {row.organization_id: row.count for row in source_connection_result}

    # Build response with all metrics
    org_metrics = []
    for org in orgs:
        billing = billing_map.get(org.id)
        usage_record = usage_map.get(org.id)
        admin_role = admin_membership_map.get(org.id)

        # Extract enabled features from the relationship
        enabled_features = [FeatureFlagEnum(ff.flag) for ff in org.feature_flags if ff.enabled]

        org_metrics.append(
            schemas.OrganizationMetrics(
                id=org.id,
                name=org.name,
                description=org.description,
                created_at=org.created_at,
                modified_at=org.modified_at,
                auth0_org_id=org.auth0_org_id,
                billing_plan=billing.billing_plan if billing else None,
                billing_status=billing.billing_status if billing else None,
                stripe_customer_id=billing.stripe_customer_id if billing else None,
                trial_ends_at=billing.trial_ends_at if billing else None,
                user_count=user_count_map.get(org.id, 0),
                source_connection_count=source_connection_map.get(org.id, 0),
                entity_count=usage_record.entities if usage_record else 0,
                query_count=usage_record.queries if usage_record else 0,
                last_active_at=last_active_map.get(org.id),
                is_member=admin_role is not None,
                member_role=admin_role,
                enabled_features=enabled_features,
            )
        )

    ctx.logger.info(
        f"Admin retrieved {len(org_metrics)} organizations "
        f"(search={search}, sort_by={sort_by}, sort_order={sort_order})"
    )

    return org_metrics


@router.post(
    "/organizations/{organization_id}/add-self",
    response_model=schemas.OrganizationWithRole,
)
async def add_self_to_organization(
    organization_id: UUID,
    role: str = "owner",  # Default to owner for admins
    db: AsyncSession = Depends(deps.get_db),
    ctx: ApiContext = Depends(deps.get_context),
) -> schemas.OrganizationWithRole:
    """Add the admin user to an organization (admin only).

    This allows admins to join any organization for support purposes.

    Args:
        organization_id: The organization to join
        role: Role to assign (owner, admin, or member)
        db: Database session
        ctx: API context

    Returns:
        The organization with the admin's new role

    Raises:
        HTTPException: If user is not an admin or organization doesn't exist
    """
    _require_admin(ctx)

    # Validate role
    if role not in ["owner", "admin", "member"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be owner, admin, or member")

    # Check if organization exists
    org = await crud.organization.get(db, organization_id, ctx)
    if not org:
        raise NotFoundException(f"Organization {organization_id} not found")

    # Capture org values before any commits to avoid detached instance issues
    org_data = {
        "id": org.id,
        "name": org.name,
        "description": org.description,
        "created_at": org.created_at,
        "modified_at": org.modified_at,
        "auth0_org_id": org.auth0_org_id,
        "org_metadata": org.org_metadata,
    }

    membership_changed = await _update_or_create_membership(db, ctx, organization_id, role)

    # Also add to Auth0 if available
    try:
        if org_data["auth0_org_id"] and ctx.user.auth0_id and auth0_management_client:
            await auth0_management_client.add_user_to_organization(
                org_id=org_data["auth0_org_id"],
                user_id=ctx.user.auth0_id,
            )
            ctx.logger.info(f"Added admin {ctx.user.email} to Auth0 org {org_data['auth0_org_id']}")
    except Exception as e:
        ctx.logger.warning(f"Failed to add admin to Auth0 organization: {e}")
        # Don't fail the request if Auth0 fails

    if membership_changed and ctx.user and ctx.user.email:
        await context_cache.invalidate_user(ctx.user.email)

    return schemas.OrganizationWithRole(
        id=org_data["id"],
        name=org_data["name"],
        description=org_data["description"],
        created_at=org_data["created_at"],
        modified_at=org_data["modified_at"],
        role=role,
        is_primary=False,
        auth0_org_id=org_data["auth0_org_id"],
        org_metadata=org_data["org_metadata"],
    )


@router.post("/organizations/{organization_id}/upgrade-to-enterprise")
async def upgrade_organization_to_enterprise(  # noqa: C901
    organization_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    ctx: ApiContext = Depends(deps.get_context),
) -> schemas.Organization:
    """Upgrade an organization to enterprise plan (admin only).

    Uses the existing billing service infrastructure to properly handle
    enterprise upgrades with Stripe customer and $0 subscription management.

    For new billing: Creates Stripe customer + $0 enterprise subscription
    For existing billing: Upgrades plan using billing service

    Args:
        organization_id: The organization to upgrade
        db: Database session
        ctx: API context

    Returns:
        The updated organization

    Raises:
        HTTPException: If user is not an admin or organization doesn't exist
    """
    _require_admin(ctx)

    # Get organization as ORM model (enrich=False) to allow mutations and db.refresh()
    org = await crud.organization.get(db, organization_id, ctx, enrich=False)
    if not org:
        raise NotFoundException(f"Organization {organization_id} not found")

    org_schema = schemas.Organization.model_validate(org, from_attributes=True)

    # Check if billing record exists
    billing = await organization_billing.get_by_organization(db, organization_id=organization_id)

    if not billing:
        # No billing record - create one using the billing service
        ctx.logger.info(f"Creating enterprise billing for org {organization_id}")

        # Get owner email
        owner_email = ctx.user.email if ctx.user else "admin@airweave.ai"
        stmt = select(UserOrganization).where(
            UserOrganization.organization_id == organization_id,
            UserOrganization.role == "owner",
        )
        result = await db.execute(stmt)
        owner_user_org = result.scalar_one_or_none()

        if owner_user_org:
            from airweave.models.user import User

            stmt = select(User).where(User.id == owner_user_org.user_id)
            result = await db.execute(stmt)
            owner_user = result.scalar_one_or_none()
            if owner_user:
                owner_email = owner_user.email

        # Set enterprise in org metadata for billing service
        if not org.org_metadata:
            org.org_metadata = {}
        org.org_metadata["plan"] = "enterprise"
        await db.flush()

        # Create system context for billing operations
        internal_ctx = billing_service._create_system_context(org_schema, "admin_upgrade")

        # Create Stripe customer
        if not stripe_client:
            raise InvalidStateError("Stripe is not enabled")

        customer = await stripe_client.create_customer(
            email=owner_email,
            name=org.name,
            metadata={
                "organization_id": str(organization_id),
                "plan": "enterprise",
            },
        )

        # Use billing service to create record (handles $0 subscription)
        async with UnitOfWork(db) as uow:
            await billing_service.create_billing_record(
                db=db,
                organization=org,
                stripe_customer_id=customer.id,
                billing_email=owner_email,
                ctx=internal_ctx,
                uow=uow,
                contextual_logger=ctx.logger,
            )
            await uow.commit()

        ctx.logger.info(f"Created enterprise billing for org {organization_id}")
    else:
        # Billing exists - cancel old subscription and create new enterprise one
        # The webhook will handle updating billing record and creating periods
        ctx.logger.info(f"Upgrading org {organization_id} to enterprise")

        # Cancel existing subscription if any
        if billing.stripe_subscription_id:
            try:
                await stripe_client.cancel_subscription(
                    billing.stripe_subscription_id, at_period_end=False
                )
                ctx.logger.info(f"Cancelled subscription {billing.stripe_subscription_id}")
            except Exception as e:
                ctx.logger.warning(f"Failed to cancel subscription: {e}")

        # Create new $0 enterprise subscription
        # Webhook will update billing record with subscription_id, plan, periods, etc.
        if stripe_client:
            price_id = stripe_client.get_price_for_plan(BillingPlan.ENTERPRISE)
            if price_id:
                sub = await stripe_client.create_subscription(
                    customer_id=billing.stripe_customer_id,
                    price_id=price_id,
                    metadata={
                        "organization_id": str(organization_id),
                        "plan": "enterprise",
                    },
                )
                ctx.logger.info(
                    f"Created $0 enterprise subscription {sub.id}, "
                    f"webhook will update billing record"
                )
            else:
                raise InvalidStateError("Enterprise price ID not configured")
        else:
            raise InvalidStateError("Stripe is not enabled")

        await db.commit()
        ctx.logger.info(f"Enterprise subscription created for org {organization_id}")

    # Refresh and return
    await db.refresh(org)
    await context_cache.invalidate_organization(organization_id)
    return schemas.Organization.model_validate(org)


@router.post("/organizations/create-enterprise", response_model=schemas.Organization)
async def create_enterprise_organization(
    organization_data: schemas.OrganizationCreate,
    owner_email: str,
    db: AsyncSession = Depends(deps.get_db),
    ctx: ApiContext = Depends(deps.get_context),
) -> schemas.Organization:
    """Create a new enterprise organization (admin only).

    This creates an organization directly on the enterprise plan.

    Args:
        organization_data: The organization data
        owner_email: Email of the user who will own this organization
        db: Database session
        ctx: API context

    Returns:
        The created organization

    Raises:
        HTTPException: If user is not an admin or owner user doesn't exist
    """
    _require_admin(ctx)

    # Find the owner user
    try:
        owner_user = await crud.user.get_by_email(db, email=owner_email)
    except NotFoundException:
        raise HTTPException(status_code=404, detail=f"User with email {owner_email} not found")

    # Create organization with enterprise billing
    async with UnitOfWork(db) as uow:
        # Create the organization (without Auth0/Stripe integration to avoid automatic trial setup)
        from airweave.core.datetime_utils import utc_now_naive
        from airweave.models.organization import Organization
        from airweave.models.organization_billing import OrganizationBilling

        org = Organization(
            name=organization_data.name,
            description=organization_data.description,
            created_by_email=ctx.user.email,
            modified_by_email=ctx.user.email,
        )
        uow.session.add(org)
        await uow.session.flush()

        # Add owner to organization
        user_org = UserOrganization(
            user_id=owner_user.id,
            organization_id=org.id,
            role="owner",
            is_primary=len(owner_user.user_organizations) == 0,  # Primary if first org
        )
        uow.session.add(user_org)

        # Create Stripe customer
        try:
            customer = await stripe_client.create_customer(
                email=owner_email,
                name=org.name,
                metadata={"organization_id": str(org.id), "plan": "enterprise"},
            )

            # Create enterprise billing record
            billing = OrganizationBilling(
                organization_id=org.id,
                stripe_customer_id=customer.id,
                stripe_subscription_id=None,
                billing_plan="enterprise",
                billing_status=BillingStatus.ACTIVE,
                billing_email=owner_email,
                payment_method_added=True,
                current_period_start=utc_now_naive(),
                current_period_end=None,
            )
            uow.session.add(billing)
        except Exception as e:
            ctx.logger.error(f"Failed to create Stripe customer for enterprise org: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create billing: {str(e)}")

        await uow.session.commit()
        await uow.session.refresh(org)

        ctx.logger.info(f"Created enterprise organization {org.id} for {owner_email}")

    # Try to create Auth0 organization (best effort)
    try:
        if owner_user.auth0_id and auth0_management_client:
            # Create Auth0 org name (lowercase, URL-safe)
            auth0_org_name = organization_service._create_org_name(
                schemas.OrganizationCreate(name=org.name, description=org.description)
            )

            auth0_org = await auth0_management_client.create_organization(
                name=auth0_org_name,
                display_name=org.name,
            )

            # Update org with Auth0 ID
            org.auth0_org_id = auth0_org["id"]
            await db.commit()
            await db.refresh(org)

            # Add owner to Auth0 org
            await auth0_management_client.add_user_to_organization(
                org_id=auth0_org["id"],
                user_id=owner_user.auth0_id,
            )

            ctx.logger.info(f"Created Auth0 organization for {org.id}")
    except Exception as e:
        ctx.logger.warning(f"Failed to create Auth0 organization: {e}")
        # Don't fail the request if Auth0 fails

    await context_cache.invalidate_user(owner_user.email)

    return schemas.Organization.model_validate(org)


@router.post("/organizations/{organization_id}/feature-flags/{flag}/enable")
async def enable_feature_flag(
    organization_id: UUID,
    flag: str,
    db: AsyncSession = Depends(deps.get_db),
    ctx: ApiContext = Depends(deps.get_context),
) -> dict:
    """Enable a feature flag for an organization (admin only).

    Args:
        organization_id: The organization ID
        flag: The feature flag name to enable
        db: Database session
        ctx: API context

    Returns:
        Success message with flag details

    Raises:
        HTTPException: If user is not an admin, organization doesn't exist, or invalid flag
    """
    _require_admin(ctx)

    # Verify organization exists
    org = await crud.organization.get(db, organization_id, ctx, skip_access_validation=True)
    if not org:
        raise NotFoundException(f"Organization {organization_id} not found")

    # Validate flag exists
    try:
        feature_flag = FeatureFlagEnum(flag)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid feature flag: {flag}")

    # Enable the feature
    await crud.organization.enable_feature(db, organization_id, feature_flag)

    # Invalidate organization cache so next request sees updated feature flags
    await context_cache.invalidate_organization(organization_id)

    ctx.logger.info(f"Admin enabled feature flag {flag} for org {organization_id}")

    return {"message": f"Feature flag '{flag}' enabled", "organization_id": str(organization_id)}


@router.post("/organizations/{organization_id}/feature-flags/{flag}/disable")
async def disable_feature_flag(
    organization_id: UUID,
    flag: str,
    db: AsyncSession = Depends(deps.get_db),
    ctx: ApiContext = Depends(deps.get_context),
) -> dict:
    """Disable a feature flag for an organization (admin only).

    Args:
        organization_id: The organization ID
        flag: The feature flag name to disable
        db: Database session
        ctx: API context

    Returns:
        Success message with flag details

    Raises:
        HTTPException: If user is not an admin, organization doesn't exist, or invalid flag
    """
    _require_admin(ctx)

    # Verify organization exists
    org = await crud.organization.get(db, organization_id, ctx, skip_access_validation=True)
    if not org:
        raise NotFoundException(f"Organization {organization_id} not found")

    # Validate flag exists
    try:
        feature_flag = FeatureFlagEnum(flag)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid feature flag: {flag}")

    # Disable the feature
    await crud.organization.disable_feature(db, organization_id, feature_flag)

    # Invalidate organization cache so next request sees updated feature flags
    await context_cache.invalidate_organization(organization_id)

    ctx.logger.info(f"Admin disabled feature flag {flag} for org {organization_id}")

    return {"message": f"Feature flag '{flag}' disabled", "organization_id": str(organization_id)}


@router.post("/resync/{sync_id}", response_model=schemas.SyncJob)
async def resync_with_execution_config(
    *,
    db: AsyncSession = Depends(deps.get_db),
    sync_id: UUID,
    ctx: ApiContext = Depends(deps.get_context),
    execution_config: Optional[SyncExecutionConfig] = Body(
        None,
        description="Optional execution config for sync behavior (handler toggles, etc.)",
        examples=[
            {
                "enable_vector_handlers": False,
                "enable_postgres_handler": False,
                "skip_cursor_load": True,
                "skip_cursor_updates": True,
            }
        ],
    ),
) -> schemas.SyncJob:
    """Admin-only: Trigger a sync with custom execution config via Temporal.

    This endpoint allows admins to trigger syncs with custom execution configurations
    for advanced use cases like ARF-only capture, destination-specific replays, or dry runs.

    The sync is dispatched to Temporal and runs asynchronously in workers, not in the backend pod.

    Args:
        db: Database session
        sync_id: ID of the sync to trigger
        ctx: API context
        execution_config: Optional dict with execution config parameters

    Returns:
        The created sync job

    Raises:
        HTTPException: If user is not admin or sync not found

    Example execution configs:
        - ARF capture only: {"enable_vector_handlers": false, "enable_postgres_handler": false}
        - Dry run: {"enable_vector_handlers": false, "enable_raw_data_handler": false,
          "enable_postgres_handler": false}
        - Target specific destination: {"target_destinations": ["<uuid>"]}
    """
    _require_admin(ctx)

    ctx.logger.info(
        f"Admin triggering resync for sync {sync_id} with execution config: {execution_config}"
    )

    # Get the sync to validate it exists
    sync_obj = await crud.sync.get(db, id=sync_id, ctx=ctx)
    if not sync_obj:
        raise NotFoundException(f"Sync {sync_id} not found")

    # Create sync job with execution config (convert Pydantic to dict for DB storage)
    sync, sync_job = await sync_service.trigger_sync_run(
        db=db,
        sync_id=sync_id,
        ctx=ctx,
        execution_config=execution_config.model_dump() if execution_config else None,
    )

    # Get source connection and collection for Temporal workflow
    source_conn = await crud.source_connection.get_by_sync_id(db=db, sync_id=sync.id, ctx=ctx)
    if not source_conn:
        raise NotFoundException(f"Source connection not found for sync {sync_id}")

    collection = await crud.collection.get_by_readable_id(
        db=db, readable_id=source_conn.readable_collection_id, ctx=ctx
    )
    if not collection:
        raise NotFoundException(f"Collection {source_conn.readable_collection_id} not found")

    collection_schema = schemas.Collection.model_validate(collection, from_attributes=True)

    # Get the Connection object (not SourceConnection) for Temporal
    connection_schema = await source_connection_helpers.get_connection_for_source_connection(
        db=db, source_connection=source_conn, ctx=ctx
    )

    # Dispatch to Temporal
    ctx.logger.info(f"Dispatching sync job {sync_job.id} to Temporal with execution config")
    await temporal_service.run_source_connection_workflow(
        sync=sync,
        sync_job=sync_job,
        collection=collection_schema,
        connection=connection_schema,
        ctx=ctx,
        force_full_sync=False,
    )

    ctx.logger.info(f"✅ Admin resync job {sync_job.id} dispatched to Temporal")

    return sync_job
