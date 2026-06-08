from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.database import get_db
from app.models import Officer, Article

router = APIRouter(prefix="/api/officers", tags=["officers"])


@router.get("")
async def list_officers(
    service: str = Query(None),
    status: str = Query(None),
    cadre: str = Query(None),
    agency: str = Query(None),
    q: str = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List officers with optional filters."""
    query = db.query(Officer)

    if service:
        query = query.filter(Officer.service == service)
    if status:
        query = query.filter(Officer.status == status)
    if cadre:
        query = query.filter(Officer.cadre.ilike(f"%{cadre}%"))
    if agency:
        query = query.filter(Officer.investigating_agency == agency)
    if q:
        query = query.filter(
            or_(
                Officer.name.ilike(f"%{q}%"),
                Officer.charge_summary.ilike(f"%{q}%"),
            )
        )

    total = query.count()
    officers = query.offset((page - 1) * per_page).limit(per_page).all()

    return {
        "data": [officer.to_dict() for officer in officers],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/{officer_id}")
async def get_officer(officer_id: int, db: Session = Depends(get_db)):
    """Get single officer with linked articles."""
    officer = db.query(Officer).filter(Officer.id == officer_id).first()

    if not officer:
        raise HTTPException(status_code=404, detail="Officer not found")

    officer_dict = officer.to_dict()
    officer_dict["articles"] = [article.to_dict() for article in officer.articles]

    return officer_dict


@router.get("/stats/summary")
async def get_stats(db: Session = Depends(get_db)):
    """Get statistics about officers and cases."""
    total = db.query(func.count(Officer.id)).scalar() or 0

    by_service = {}
    for service in db.query(Officer.service).distinct():
        count = db.query(func.count(Officer.id)).filter(Officer.service == service[0]).scalar() or 0
        if service[0]:
            by_service[service[0]] = count

    by_status = {}
    for status in db.query(Officer.status).distinct():
        count = db.query(func.count(Officer.id)).filter(Officer.status == status[0]).scalar() or 0
        if status[0]:
            by_status[status[0]] = count

    by_cadre = {}
    for cadre in db.query(Officer.cadre).distinct().filter(Officer.cadre != None):
        count = db.query(func.count(Officer.id)).filter(Officer.cadre == cadre[0]).scalar() or 0
        if cadre[0]:
            by_cadre[cadre[0]] = count

    from app.models import Settings
    last_scraped = db.query(Settings).filter(Settings.key == "last_scraped_at").first()
    last_scraped_at = last_scraped.value if last_scraped else None

    return {
        "total": total,
        "by_service": by_service,
        "by_status": by_status,
        "by_cadre": dict(sorted(by_cadre.items())[:20]),
        "last_scraped_at": last_scraped_at,
    }
