from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base


class Officer(Base):
    __tablename__ = "officers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False, index=True)
    service = Column(String, default="Unknown")  # IAS, IPS, IRS, IFS, etc.
    batch_year = Column(String, nullable=True)
    cadre = Column(String, nullable=True, index=True)  # State/cadre
    charge_summary = Column(Text, nullable=True)
    investigating_agency = Column(String, nullable=True)  # CBI, ED, CVC, etc.
    status = Column(String, default="Under inquiry")  # Suspended, Arrested, Convicted, etc.
    current_position = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_verified = Column(Boolean, default=False)

    articles = relationship("Article", back_populates="officer", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "service": self.service,
            "batch_year": self.batch_year,
            "cadre": self.cadre,
            "charge_summary": self.charge_summary,
            "investigating_agency": self.investigating_agency,
            "status": self.status,
            "current_position": self.current_position,
            "source_url": self.source_url,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None,
            "is_verified": self.is_verified,
            "article_count": len(self.articles),
        }


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    officer_id = Column(Integer, ForeignKey("officers.id"), nullable=True)
    headline = Column(String, nullable=False)
    source_name = Column(String, nullable=True)
    url = Column(String, unique=True, nullable=False, index=True)
    published_at = Column(DateTime, nullable=True)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    full_text = Column(Text, nullable=True)
    snippet = Column(Text, nullable=True)
    matched_keywords = Column(String, nullable=True)
    raw_entities = Column(Text, nullable=True)

    officer = relationship("Officer", back_populates="articles")

    def to_dict(self):
        return {
            "id": self.id,
            "officer_id": self.officer_id,
            "headline": self.headline,
            "source_name": self.source_name,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
            "snippet": self.snippet,
            "matched_keywords": self.matched_keywords,
        }


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, default=1)
    key = Column(String, unique=True, nullable=False)
    value = Column(Text, nullable=True)
