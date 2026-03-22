import uuid
from decimal import Decimal
from typing import Optional
from datetime import date, datetime, timezone
from dateutil.relativedelta import relativedelta

from fastapi import APIRouter, Depends, Path, Query, Body
from sqlalchemy import and_, func as sa_func

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.decorators import require_role_or_above, log_access
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    NOT_FOUND,
    VALIDATION_ERROR_CODE,
)
from users.models.distributor import (
    DistributorTerritory,
    DistributorPractitioner,
    DistributorCredits,
    CreditTransaction,
    CreditTransactionTypeEnum,
)
from users.models.practitioner import PractitionerCredits
from users.models.user import Users, UserProfile
from users.models.phase3 import CostRecord

distributor_routes = APIRouter(prefix="/distributor", tags=["Distributor"])


# ---------------------------------------------------------------------------
# 1. GET /distributor/territory — Territory info
# ---------------------------------------------------------------------------
@distributor_routes.get("/territory")
def get_territory(
    user_data: dict = Depends(require_role_or_above("distributor")),
):
    session = ScopedSession()
    try:
        log_access(user_data, "distributor/territory", "read")
        distributor_id = user_data.get("sub")

        territory = (
            session.query(DistributorTerritory)
            .filter(
                DistributorTerritory.distributor_id == distributor_id,
                DistributorTerritory.is_deleted == False,
            )
            .first()
        )

        if not territory:
            return create_response(
                message="Territory not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        # Count practitioners in this distributor's network
        practitioner_count = (
            session.query(sa_func.count(DistributorPractitioner.id))
            .filter(
                DistributorPractitioner.distributor_id == distributor_id,
                DistributorPractitioner.is_deleted == False,
            )
            .scalar()
        ) or 0

        active_count = (
            session.query(sa_func.count(DistributorPractitioner.id))
            .filter(
                DistributorPractitioner.distributor_id == distributor_id,
                DistributorPractitioner.status == "active",
                DistributorPractitioner.is_deleted == False,
            )
            .scalar()
        ) or 0

        return create_response(
            message="Territory info retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "territory": {
                    "id": str(territory.id),
                    "name": territory.name,
                    "region": territory.region,
                    "country": territory.country,
                    "description": territory.description,
                    "created_at": territory.created_at.isoformat() if territory.created_at else None,
                },
                "practitioner_counts": {
                    "total": practitioner_count,
                    "active": active_count,
                },
            },
        )
    except Exception as e:
        logger.error(f"Error retrieving territory info: {e}")
        return create_response(
            message="Failed to retrieve territory info",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 2. GET /distributor/practitioners — List practitioners in network
# ---------------------------------------------------------------------------
@distributor_routes.get("/practitioners")
def list_practitioners(
    user_data: dict = Depends(require_role_or_above("distributor")),
):
    session = ScopedSession()
    try:
        log_access(user_data, "distributor/practitioners", "list")
        distributor_id = user_data.get("sub")

        results = (
            session.query(
                DistributorPractitioner,
                Users.email,
                UserProfile.first_name,
                UserProfile.last_name,
                PractitionerCredits.total_credits,
                PractitionerCredits.used_credits,
                PractitionerCredits.reserved_credits,
            )
            .join(Users, Users.user_id == DistributorPractitioner.practitioner_id)
            .outerjoin(
                UserProfile,
                UserProfile.user_id == DistributorPractitioner.practitioner_id,
            )
            .outerjoin(
                PractitionerCredits,
                PractitionerCredits.practitioner_id == DistributorPractitioner.practitioner_id,
            )
            .filter(
                DistributorPractitioner.distributor_id == distributor_id,
                DistributorPractitioner.is_deleted == False,
            )
            .order_by(sa_func.coalesce(UserProfile.first_name, Users.email).asc())
            .all()
        )

        practitioners = []
        for dp, email, first_name, last_name, total_cr, used_cr, reserved_cr in results:
            total_val = float(total_cr) if total_cr else 0
            used_val = float(used_cr) if used_cr else 0
            reserved_val = float(reserved_cr) if reserved_cr else 0
            practitioners.append(
                {
                    "id": str(dp.id),
                    "practitioner_id": str(dp.practitioner_id),
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "status": dp.status,
                    "onboarded_at": dp.onboarded_at.isoformat() if dp.onboarded_at else None,
                    "credit_allocation": total_val,
                    "credits_used": used_val,
                    "credits_available": total_val - used_val - reserved_val,
                }
            )

        return create_response(
            message="Practitioners retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={"practitioners": practitioners, "total": len(practitioners)},
        )
    except Exception as e:
        logger.error(f"Error listing practitioners: {e}")
        return create_response(
            message="Failed to retrieve practitioners",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 3. GET /distributor/practitioners/{pract_id} — Practitioner detail
# ---------------------------------------------------------------------------
@distributor_routes.get("/practitioners/{pract_id}")
def get_practitioner_detail(
    pract_id: str = Path(...),
    user_data: dict = Depends(require_role_or_above("distributor")),
):
    session = ScopedSession()
    try:
        log_access(user_data, f"distributor/practitioners/{pract_id}", "read")
        distributor_id = user_data.get("sub")

        dp = (
            session.query(DistributorPractitioner)
            .filter(
                DistributorPractitioner.distributor_id == distributor_id,
                DistributorPractitioner.practitioner_id == pract_id,
                DistributorPractitioner.is_deleted == False,
            )
            .first()
        )
        if not dp:
            return create_response(
                message="Practitioner not found in your network",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        user = session.query(Users).filter(Users.user_id == pract_id).first()
        profile = (
            session.query(UserProfile).filter(UserProfile.user_id == pract_id).first()
        )
        credits = (
            session.query(PractitionerCredits)
            .filter(PractitionerCredits.practitioner_id == pract_id)
            .first()
        )

        return create_response(
            message="Practitioner detail retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "practitioner": {
                    "practitioner_id": str(dp.practitioner_id),
                    "email": user.email if user else None,
                    "first_name": profile.first_name if profile else None,
                    "last_name": profile.last_name if profile else None,
                    "status": dp.status,
                    "onboarded_at": dp.onboarded_at.isoformat() if dp.onboarded_at else None,
                },
                "credit_balance": {
                    "total": float(credits.total_credits) if credits else 0,
                    "used": float(credits.used_credits) if credits else 0,
                    "reserved": float(credits.reserved_credits) if credits else 0,
                    "available": float(credits.available_credits) if credits else 0,
                },
            },
        )
    except Exception as e:
        logger.error(f"Error getting practitioner detail: {e}")
        return create_response(
            message="Failed to retrieve practitioner detail",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 4. POST /distributor/credits/allocate — Allocate credits
# ---------------------------------------------------------------------------
@distributor_routes.post("/credits/allocate")
def allocate_credits(
    practitioner_id: str = Body(...),
    amount: float = Body(...),
    description: Optional[str] = Body(None),
    user_data: dict = Depends(require_role_or_above("distributor")),
):
    session = ScopedSession()
    try:
        log_access(user_data, "distributor/credits/allocate", "create")
        distributor_id = user_data.get("sub")
        amount_decimal = Decimal(str(amount))

        if amount_decimal <= 0:
            return create_response(
                message="Amount must be greater than zero",
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=400,
            )

        # Validate practitioner is in distributor's network
        dp = (
            session.query(DistributorPractitioner)
            .filter(
                DistributorPractitioner.distributor_id == distributor_id,
                DistributorPractitioner.practitioner_id == practitioner_id,
                DistributorPractitioner.is_deleted == False,
            )
            .first()
        )
        if not dp:
            return create_response(
                message="Practitioner not found in your network",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        # Check distributor has sufficient credits
        dist_credits = (
            session.query(DistributorCredits)
            .filter(DistributorCredits.distributor_id == distributor_id)
            .first()
        )
        if not dist_credits:
            return create_response(
                message="No credit account found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        available = (
            (dist_credits.total_purchased or 0)
            - (dist_credits.total_allocated or 0)
            - (dist_credits.total_used or 0)
        )
        if amount_decimal > available:
            return create_response(
                message=f"Insufficient credits. Available: {float(available)}",
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=400,
            )

        # Update distributor allocated total
        dist_credits.total_allocated = (dist_credits.total_allocated or 0) + amount_decimal

        # Update or create practitioner credits
        pract_credits = (
            session.query(PractitionerCredits)
            .filter(PractitionerCredits.practitioner_id == practitioner_id)
            .first()
        )
        if pract_credits:
            pract_credits.total_credits = (pract_credits.total_credits or 0) + amount_decimal
        else:
            pract_credits = PractitionerCredits(
                id=uuid.uuid4(),
                practitioner_id=practitioner_id,
                total_credits=amount_decimal,
                used_credits=Decimal("0"),
                reserved_credits=Decimal("0"),
            )
            session.add(pract_credits)

        # Create transaction record
        txn = CreditTransaction(
            id=uuid.uuid4(),
            distributor_id=distributor_id,
            practitioner_id=practitioner_id,
            transaction_type=CreditTransactionTypeEnum.ALLOCATION,
            amount=amount_decimal,
            description=description or f"Credit allocation to practitioner",
        )
        session.add(txn)
        session.commit()

        return create_response(
            message="Credits allocated successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "transaction_id": str(txn.id),
                "practitioner_id": practitioner_id,
                "amount_allocated": float(amount_decimal),
                "distributor_remaining": float(
                    (dist_credits.total_purchased or 0)
                    - (dist_credits.total_allocated or 0)
                    - (dist_credits.total_used or 0)
                ),
            },
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error allocating credits: {e}")
        return create_response(
            message="Failed to allocate credits",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 5. GET /distributor/credits — Credit inventory
# ---------------------------------------------------------------------------
@distributor_routes.get("/credits")
def get_credits(
    user_data: dict = Depends(require_role_or_above("distributor")),
):
    session = ScopedSession()
    try:
        log_access(user_data, "distributor/credits", "read")
        distributor_id = user_data.get("sub")

        dist_credits = (
            session.query(DistributorCredits)
            .filter(DistributorCredits.distributor_id == distributor_id)
            .first()
        )

        purchased = float(dist_credits.total_purchased) if dist_credits else 0
        allocated = float(dist_credits.total_allocated) if dist_credits else 0
        used = float(dist_credits.total_used) if dist_credits else 0
        remaining = purchased - allocated - used

        # Recent transactions summary
        recent_txns = (
            session.query(CreditTransaction)
            .filter(CreditTransaction.distributor_id == distributor_id)
            .order_by(CreditTransaction.created_at.desc())
            .limit(5)
            .all()
        )
        transaction_summary = [
            {
                "id": str(t.id),
                "type": t.transaction_type.value if t.transaction_type else None,
                "amount": float(t.amount) if t.amount else 0,
                "description": t.description,
                "practitioner_id": str(t.practitioner_id) if t.practitioner_id else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in recent_txns
        ]

        return create_response(
            message="Credit inventory retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "credits": {
                    "purchased": purchased,
                    "allocated": allocated,
                    "used": used,
                    "remaining": remaining,
                },
                "transaction_summary": transaction_summary,
            },
        )
    except Exception as e:
        logger.error(f"Error retrieving credit inventory: {e}")
        return create_response(
            message="Failed to retrieve credit inventory",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 6. GET /distributor/credits/transactions — Paginated transaction history
# ---------------------------------------------------------------------------
@distributor_routes.get("/credits/transactions")
def list_transactions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user_data: dict = Depends(require_role_or_above("distributor")),
):
    session = ScopedSession()
    try:
        log_access(user_data, "distributor/credits/transactions", "list")
        distributor_id = user_data.get("sub")

        query = (
            session.query(CreditTransaction)
            .filter(CreditTransaction.distributor_id == distributor_id)
            .order_by(CreditTransaction.created_at.desc())
        )

        total = query.count()
        offset = (page - 1) * limit
        rows = query.offset(offset).limit(limit).all()

        transactions = [
            {
                "id": str(t.id),
                "type": t.transaction_type.value if t.transaction_type else None,
                "amount": float(t.amount) if t.amount else 0,
                "description": t.description,
                "practitioner_id": str(t.practitioner_id) if t.practitioner_id else None,
                "reference_id": t.reference_id,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in rows
        ]

        return create_response(
            message="Transactions retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "transactions": transactions,
                "total": total,
                "page": page,
                "limit": limit,
            },
        )
    except Exception as e:
        logger.error(f"Error listing transactions: {e}")
        return create_response(
            message="Failed to retrieve transactions",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 7. GET /distributor/costs — Cost metrics
# ---------------------------------------------------------------------------
@distributor_routes.get("/costs")
def get_costs(
    user_data: dict = Depends(require_role_or_above("distributor")),
):
    session = ScopedSession()
    try:
        log_access(user_data, "distributor/costs", "read")
        distributor_id = user_data.get("sub")

        # Total credits purchased (sum of purchase transactions)
        credits_purchased = (
            session.query(sa_func.coalesce(sa_func.sum(CreditTransaction.amount), 0))
            .filter(
                CreditTransaction.distributor_id == distributor_id,
                CreditTransaction.transaction_type == CreditTransactionTypeEnum.PURCHASE,
            )
            .scalar()
        )

        # Total credits allocated (sum of allocation transactions)
        credits_allocated = (
            session.query(sa_func.coalesce(sa_func.sum(CreditTransaction.amount), 0))
            .filter(
                CreditTransaction.distributor_id == distributor_id,
                CreditTransaction.transaction_type == CreditTransactionTypeEnum.ALLOCATION,
            )
            .scalar()
        )

        return create_response(
            message="Cost metrics retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "credits_purchased_total": float(credits_purchased),
                "credits_allocated_total": float(credits_allocated),
                "revenue": {},  # placeholder
                "commission": {},  # placeholder
            },
        )
    except Exception as e:
        logger.error(f"Error retrieving cost metrics: {e}")
        return create_response(
            message="Failed to retrieve cost metrics",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 8. GET /distributor/revenue — Revenue / commission summary
# ---------------------------------------------------------------------------
@distributor_routes.get("/revenue")
def get_revenue(
    user_data: dict = Depends(require_role_or_above("distributor")),
):
    session = ScopedSession()
    try:
        log_access(user_data, "distributor/revenue", "read")
        distributor_id = user_data.get("sub")

        # Build time-series for last 6 months
        now = datetime.now(timezone.utc)
        time_series = []
        for i in range(5, -1, -1):
            month_start = (now - relativedelta(months=i)).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            if i > 0:
                month_end = (now - relativedelta(months=i - 1)).replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                )
            else:
                month_end = now

            allocated = (
                session.query(
                    sa_func.coalesce(sa_func.sum(CreditTransaction.amount), 0)
                )
                .filter(
                    CreditTransaction.distributor_id == distributor_id,
                    CreditTransaction.transaction_type == CreditTransactionTypeEnum.ALLOCATION,
                    CreditTransaction.created_at >= month_start,
                    CreditTransaction.created_at < month_end,
                )
                .scalar()
            )

            time_series.append(
                {
                    "month": month_start.strftime("%Y-%m"),
                    "credits_allocated": float(allocated),
                    "revenue_estimate": 0,  # placeholder
                }
            )

        # Overall summary
        dist_credits = (
            session.query(DistributorCredits)
            .filter(DistributorCredits.distributor_id == distributor_id)
            .first()
        )

        return create_response(
            message="Revenue summary retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "summary": {
                    "total_purchased": float(dist_credits.total_purchased) if dist_credits else 0,
                    "total_allocated": float(dist_credits.total_allocated) if dist_credits else 0,
                    "total_used": float(dist_credits.total_used) if dist_credits else 0,
                    "revenue_estimate": 0,  # placeholder
                    "commission_estimate": 0,  # placeholder
                },
                "time_series": time_series,
            },
        )
    except Exception as e:
        logger.error(f"Error retrieving revenue summary: {e}")
        return create_response(
            message="Failed to retrieve revenue summary",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()
