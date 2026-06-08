from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import Article

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("")
async def list_articles(
    officer_id: int = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List recent articles, optionally filtered by officer."""
    query = db.query(Article).order_by(desc(Article.published_at))

    if officer_id:
        query = query.filter(Article.officer_id == officer_id)

    articles = query.limit(limit).all()

    return {
        "data": [article.to_dict() for article in articles],
        "count": len(articles),
    }


@router.get("/{article_id}")
async def get_article(article_id: int, db: Session = Depends(get_db)):
    """Get single article details."""
    article = db.query(Article).filter(Article.id == article_id).first()

    if not article:
        return {"error": "Article not found"}, 404

    return article.to_dict()
