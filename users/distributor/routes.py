"""
Distributor API endpoints (2.4)

All endpoints require the 'distributor' role (or super-admin).
Prefix: /v1/distributors
"""
import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, Path, Query, Body
from typing import Optional

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.decorators import require_role
from users.response import (
    create_response, SUCCESS_CODE, SOMETHING_WENT_WRONG,
    VALIDATION_ERROR_CODE, NOT_FOUND,
)
from users.models.user import Users, UserProfile
from users.models.distributor import (
    DistributorTerritory, DistributorPractitioner,
    DistributorCredit, CreditTransaction, TransactionTypeEnum,
)
from users.models.practitioner import PractitionerCredit
from sqlalchemy import func

distributor_routes = APIRouter(prefix="/distributors", tags=["Distributor"])


# ---------------------------------------------------------------------------
#  GET /distributors/:id/practitioners
# ---------------------------------------------------------------------------

@distributor_routes.get("/{distributor_id}/practitioners")
def get_practitioners(
    distributor_id: str = Path(...),
    status: Optional[str] = Query(None),
    user_data: dict = Depends(require_role("distributor", "super-admin")),
):
    """Practitioner network in territory."""
    session = ScopedSession()
    try:
        query = session.query(DistributorPractitioner).filter(
            DistributorPractitioner.distributor_id == distributor_id,
            DistributorPractitioner.is_deleted.is_(False),
        )
        if status:
            query = query.filter(DistributorPractitioner.status == status)

        rels = query.all()
        result = []
        for r in rels:
            prac_user = session.query(Users).filter(Users.user_id == r.practitioner_id).first()
            prac_profile = session.query(UserProfile).filter(UserProfile.user_id == r.practitioner_id).first()

            # Get practitioner credit info
            prac_credit = session.query(PractitionerCredit).filter(
                PractitionerCredit.practitioner_id == r.practitioner_id
            ).first()

            result.append({
                "relationship_id": str(r.id),
                "practitioner_id": str(r.practitioner_id),
                "email": prac_user.email if prac_user else None,
                "first_name": prac_profile.first_name if prac_profile else None,
                "last_name": prac_profile.last_name if prac_profile else None,
                "status": r.status,
                "onboarded_at": r.onboarded_at.isoformat() if r.onboarded_at else None,
                "credits_available": float(prac_credit.available_credits) if prac_credit else 0,
            })

        return create_response("Practitioners retrieved", True, SUCCESS_CODE, data={
            "practitioners": result,
            "total": len(result),
        })
    except Exception as e:
        logger.error(f"Error getting practitioners: {e}")
        return create_response("Failed to retrieve practitioners", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  POST /distributors/:id/practitioners
# ---------------------------------------------------------------------------

@distributor_routes.post("/{distributor_id}/practitioners")
def onboard_practitioner(
    distributor_id: str = Path(...),
    practitioner_id: str = Body(..., embed=True),
    user_data: dict = Depends(require_role("distributor", "super-admin")),
):
    """Onboard a new practitioner into the distributor's network."""
    session = ScopedSession()
    try:
        # Verify practitioner exists
        prac = session.query(Users).filter(Users.user_id == practitioner_id).first()
        if not prac:
            return create_response("Practitioner not found", False, NOT_FOUND, status_code=404)

        # Check duplicate
        existing = session.query(DistributorPractitioner).filter(
            DistributorPractitioner.distributor_id == distributor_id,
            DistributorPractitioner.practitioner_id == practitioner_id,
            DistributorPractitioner.is_deleted.is_(False),
        ).first()
        if existing:
            return create_response("Practitioner already in network", False, VALIDATION_ERROR_CODE, status_code=400)

        dp = DistributorPractitioner(
            id=uuid.uuid4(),
            distributor_id=distributor_id,
            practitioner_id=practitioner_id,
        )
        session.add(dp)
        session.commit()

        return create_response("Practitioner onboarded", True, SUCCESS_CODE, data={
            "relationship_id": str(dp.id),
            "practitioner_id": practitioner_id,
        })
    except Exception as e:
        session.rollback()
        logger.error(f"Error onboarding practitioner: {e}")
        return create_response("Failed to onboard practitioner", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  GET /distributors/:id/credits
# ---------------------------------------------------------------------------

@distributor_routes.get("/{distributor_id}/credits")
def get_credits(
    distributor_id: str = Path(...),
    user_data: dict = Depends(require_role("distributor", "super-admin")),
):
    """Credit stats — purchased, allocated, available, used."""
    session = ScopedSession()
    try:
        credit = session.query(DistributorCredit).filter(
            DistributorCredit.distributor_id == distributor_id
        ).first()

        if not credit:
            return create_response("Credits retrieved", True, SUCCESS_CODE, data={
                "distributor_id": distributor_id,
                "total_purchased": 0,
                "total_allocated": 0,
                "total_used": 0,
                "available": 0,
            })

        return create_response("Credits retrieved", True, SUCCESS_CODE, data={
            "distributor_id": distributor_id,
            "total_purchased": float(credit.total_purchased),
            "total_allocated": float(credit.total_allocated),
            "total_used": float(credit.total_used),
            "available": float(credit.available),
        })
    except Exception as e:
        logger.error(f"Error getting credits: {e}")
        return create_response("Failed to retrieve credits", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  POST /distributors/:id/credits/allocate
# ---------------------------------------------------------------------------

@distributor_routes.post("/{distributor_id}/credits/allocate")
def allocate_credits(
    distributor_id: str = Path(...),
    practitioner_id: str = Body(..., embed=True),
    amount: float = Body(..., embed=True, gt=0),
    description: Optional[str] = Body(None, embed=True),
    user_data: dict = Depends(require_role("distributor", "super-admin")),
):
    """Allocate credits to a practitioner."""
    session = ScopedSession()
    try:
        # Get distributor credit record
        dist_credit = session.query(DistributorCredit).filter(
            DistributorCredit.distributor_id == distributor_id
        ).first()
        if not dist_credit:
            return create_response("No credit account found", False, NOT_FOUND, status_code=404)

        if float(dist_credit.available) < amount:
            return create_response(
                f"Insufficient credits. Available: {float(dist_credit.available)}, Requested: {amount}",
                False, VALIDATION_ERROR_CODE, status_code=400,
            )

        # Verify practitioner is in network
        dp = session.query(DistributorPractitioner).filter(
            DistributorPractitioner.distributor_id == distributor_id,
            DistributorPractitioner.practitioner_id == practitioner_id,
            DistributorPractitioner.is_deleted.is_(False),
        ).first()
        if not dp:
            return create_response("Practitioner not in your network", False, VALIDATION_ERROR_CODE, status_code=400)

        # Update distributor credits
        dist_credit.total_allocated = Decimal(str(float(dist_credit.total_allocated) + amount))

        # Update or create practitioner credits
        prac_credit = session.query(PractitionerCredit).filter(
            PractitionerCredit.practitioner_id == practitioner_id
        ).first()
        if not prac_credit:
            prac_credit = PractitionerCredit(
                id=uuid.uuid4(),
                practitioner_id=practitioner_id,
                total_credits=Decimal(str(amount)),
            )
            session.add(prac_credit)
        else:
            prac_credit.total_credits = Decimal(str(float(prac_credit.total_credits) + amount))

        # Log transaction
        txn = CreditTransaction(
            id=uuid.uuid4(),
            distributor_id=distributor_id,
            practitioner_id=practitioner_id,
            transaction_type=TransactionTypeEnum.ALLOCATION,
            amount=Decimal(str(amount)),
            description=description or f"Allocated {amount} credits",
        )
        session.add(txn)
        session.commit()

        return create_response("Credits allocated", True, SUCCESS_CODE, data={
            "transaction_id": str(txn.id),
            "practitioner_id": practitioner_id,
            "amount": amount,
            "distributor_available": float(dist_credit.available),
        })
    except Exception as e:
        session.rollback()
        logger.error(f"Error allocating credits: {e}")
        return create_response("Failed to allocate credits", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  GET /distributors/:id/transactions
# ---------------------------------------------------------------------------

@distributor_routes.get("/{distributor_id}/transactions")
def get_transactions(
    distributor_id: str = Path(...),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user_data: dict = Depends(require_role("distributor", "super-admin")),
):
    """Recent transactions log."""
    session = ScopedSession()
    try:
        query = session.query(CreditTransaction).filter(
            CreditTransaction.distributor_id == distributor_id
        )
        total = query.count()
        offset = (page - 1) * limit
        txns = query.order_by(CreditTransaction.created_at.desc()).offset(offset).limit(limit).all()

        result = []
        for t in txns:
            result.append({
                "transaction_id": str(t.id),
                "type": t.transaction_type.value,
                "amount": float(t.amount),
                "practitioner_id": str(t.practitioner_id) if t.practitioner_id else None,
                "description": t.description,
                "reference_id": t.reference_id,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })

        return create_response("Transactions retrieved", True, SUCCESS_CODE, data={
            "transactions": result,
            "pagination": {"total": total, "page": page, "limit": limit, "has_more": offset + limit < total},
        })
    except Exception as e:
        logger.error(f"Error getting transactions: {e}")
        return create_response("Failed to retrieve transactions", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  GET /distributors/:id/territory
# ---------------------------------------------------------------------------

@distributor_routes.get("/{distributor_id}/territory")
def get_territory(
    distributor_id: str = Path(...),
    user_data: dict = Depends(require_role("distributor", "super-admin")),
):
    """Territory information and stats."""
    session = ScopedSession()
    try:
        territory = session.query(DistributorTerritory).filter(
            DistributorTerritory.distributor_id == distributor_id,
            DistributorTerritory.is_deleted.is_(False),
        ).first()

        practitioner_count = session.query(func.count(DistributorPractitioner.id)).filter(
            DistributorPractitioner.distributor_id == distributor_id,
            DistributorPractitioner.is_deleted.is_(False),
        ).scalar() or 0

        active_count = session.query(func.count(DistributorPractitioner.id)).filter(
            DistributorPractitioner.distributor_id == distributor_id,
            DistributorPractitioner.status == "active",
            DistributorPractitioner.is_deleted.is_(False),
        ).scalar() or 0

        territory_data = {
            "territory_id": str(territory.id) if territory else None,
            "name": territory.name if territory else None,
            "region": territory.region if territory else None,
            "country": territory.country if territory else None,
            "description": territory.description if territory else None,
        } if territory else None

        return create_response("Territory retrieved", True, SUCCESS_CODE, data={
            "distributor_id": distributor_id,
            "territory": territory_data,
            "practitioner_count": practitioner_count,
            "active_practitioners": active_count,
        })
    except Exception as e:
        logger.error(f"Error getting territory: {e}")
        return create_response("Failed to retrieve territory", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()
