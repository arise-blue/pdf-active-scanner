import logging
import re
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher

import feedparser
import httpx
from bs4 import BeautifulSoup

try:
    import spacy
    SPACY_AVAILABLE = True
except:
    SPACY_AVAILABLE = False

from app.models import Officer, Article
from app.parser import (
    extract_service_type, extract_status, extract_investigating_agency,
    generate_charge_summary, extract_state_from_text, sanitize_officer_name
)

logger = logging.getLogger(__name__)

SCRAPE_KEYWORDS = [
    "IAS", "IPS", "IRS", "IFS", "arrested", "suspended", "CBI", "ED raid",
    "bribery", "corruption", "disproportionate assets", "money laundering",
    "chargesheeted", "convicted", "dismissed from service"
]

RSS_FEEDS = [
    "https://news.google.com/rss/search?q=IAS+officer+arrested+India&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=IPS+officer+arrested+corruption+India&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=IAS+officer+suspended+corruption&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=IAS+IPS+CBI+arrested+bribery+India&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=IAS+officer+ED+money+laundering+India&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=IPS+officer+disproportionate+assets+India&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=IAS+convicted+corruption+India&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=bureaucrat+arrested+CBI+India&hl=en-IN&gl=IN&ceid=IN:en",
]


@dataclass
class ScrapeResult:
    new_officers: int = 0
    updated_officers: int = 0
    new_articles: int = 0
    skipped: int = 0
    errors: int = 0
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

    def to_dict(self):
        return {
            "new_officers": self.new_officers,
            "updated_officers": self.updated_officers,
            "new_articles": self.new_articles,
            "skipped": self.skipped,
            "errors": self.errors,
            "timestamp": self.timestamp.isoformat(),
        }


class ArticleScraper:
    def __init__(self):
        self.nlp = None
        if SPACY_AVAILABLE:
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except Exception as e:
                logger.warning(f"Failed to load spaCy model: {e}. Using regex fallback.")

    def fetch_article_text(self, url: str) -> Optional[str]:
        """Fetch full article text from URL."""
        try:
            timeout = httpx.Timeout(10.0)
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')

                for tag in soup(['script', 'style', 'nav', 'footer']):
                    tag.decompose()

                paragraphs = soup.find_all(['p', 'article', 'main'])
                text = ' '.join([p.get_text(strip=True) for p in paragraphs])

                if not text or len(text) < 100:
                    text = soup.get_text(strip=True)

                return text[:5000] if text else None

        except httpx.TimeoutException:
            logger.debug(f"Timeout fetching {url}")
            return None
        except Exception as e:
            logger.debug(f"Error fetching article from {url}: {e}")
            return None

    def extract_person_name_nlp(self, text: str) -> Optional[str]:
        """Extract person name using spaCy NLP."""
        if not self.nlp or not text:
            return None

        try:
            doc = self.nlp(text[:5000])
            person_entities = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]

            if person_entities:
                return person_entities[0]
        except Exception as e:
            logger.debug(f"spaCy extraction failed: {e}")

        return None

    def extract_person_name_regex(self, text: str) -> Optional[str]:
        """Fallback regex-based person name extraction."""
        patterns = [
            r'(?:IAS|IPS|IRS|IFS)\s+officer\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'(?:Mr|Ms|Mrs|Dr|Shri|Smt)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()

        return None

    def extract_officer_name(self, text: str) -> Optional[str]:
        """Extract officer name from text using NLP or regex."""
        if self.nlp:
            name = self.extract_person_name_nlp(text)
            if name:
                return name

        return self.extract_person_name_regex(text)

    def extract_cadre_nlp(self, text: str) -> Optional[str]:
        """Extract cadre/state using spaCy."""
        if not self.nlp:
            return None

        try:
            doc = self.nlp(text[:5000])
            gpe_entities = [ent.text for ent in doc.ents if ent.label_ == "GPE"]

            for gpe in gpe_entities:
                if len(gpe.split()) <= 2:
                    return gpe
        except Exception as e:
            logger.debug(f"spaCy GPE extraction failed: {e}")

        return None

    def process_article(self, entry: Dict, db) -> Tuple[Optional[Officer], Optional[Article]]:
        """Process a single RSS entry and create/update records."""
        try:
            url = entry.get('link', '')
            if not url:
                return None, None

            existing_article = db.query(Article).filter(Article.url == url).first()
            if existing_article:
                return None, None

            headline = entry.get('title', '').strip()
            snippet = entry.get('summary', '')[:300] if entry.get('summary') else None
            published_at_str = entry.get('published', '')

            published_at = None
            try:
                if published_at_str:
                    from email.utils import parsedate_to_datetime
                    published_at = parsedate_to_datetime(published_at_str)
            except:
                pass

            matched_keywords = [kw for kw in SCRAPE_KEYWORDS if kw.lower() in headline.lower()]
            if not matched_keywords:
                return None, None

            full_text = self.fetch_article_text(url)
            if not full_text:
                full_text = snippet or headline

            officer_name = self.extract_officer_name(full_text or headline)
            if not officer_name:
                officer_name = self.extract_officer_name(snippet or headline)

            officer = None
            if officer_name:
                officer_name = sanitize_officer_name(officer_name)

                existing_officer = self._find_similar_officer(officer_name, db)

                if existing_officer:
                    officer = existing_officer
                    officer.last_updated_at = datetime.utcnow()

                    if not officer.status or officer.status == "Under inquiry":
                        officer.status = extract_status(full_text or headline)

                    if not officer.investigating_agency:
                        officer.investigating_agency = extract_investigating_agency(full_text or headline)

                    if not officer.service or officer.service == "Unknown":
                        officer.service = extract_service_type(full_text or headline)

                    if not officer.cadre:
                        officer.cadre = extract_state_from_text(full_text or headline)

                    if not officer.charge_summary:
                        officer.charge_summary = generate_charge_summary(full_text or headline)

                    db.add(officer)
                    db.flush()

                else:
                    officer = Officer(
                        name=officer_name,
                        service=extract_service_type(full_text or headline),
                        cadre=extract_state_from_text(full_text or headline),
                        charge_summary=generate_charge_summary(full_text or headline),
                        investigating_agency=extract_investigating_agency(full_text or headline),
                        status=extract_status(full_text or headline),
                        source_url=url,
                    )
                    db.add(officer)
                    db.flush()

            article = Article(
                officer_id=officer.id if officer else None,
                headline=headline,
                source_name=entry.get('source', {}).get('title', 'Unknown'),
                url=url,
                published_at=published_at,
                full_text=full_text,
                snippet=snippet,
                matched_keywords=",".join(matched_keywords),
                raw_entities=None,
            )
            db.add(article)
            db.flush()

            return officer, article

        except Exception as e:
            logger.error(f"Error processing article: {e}")
            return None, None

    def _find_similar_officer(self, name: str, db) -> Optional[Officer]:
        """Find similar officer using fuzzy matching."""
        existing_officers = db.query(Officer).all()

        for existing in existing_officers:
            similarity = SequenceMatcher(None, name.lower(), existing.name.lower()).ratio()
            if similarity >= 0.85:
                return existing

        return None

    def scrape(self, db) -> ScrapeResult:
        """Run full scraper and update database."""
        result = ScrapeResult()

        for feed_url in RSS_FEEDS:
            try:
                logger.info(f"Fetching feed: {feed_url}")
                feed = feedparser.parse(feed_url)

                for entry in feed.entries:
                    officer, article = self.process_article(entry, db)

                    if officer and article:
                        if officer.id is None:
                            result.new_officers += 1
                        else:
                            result.updated_officers += 1
                        result.new_articles += 1
                    elif article:
                        result.new_articles += 1
                    else:
                        result.skipped += 1

            except Exception as e:
                logger.error(f"Error processing feed {feed_url}: {e}")
                result.errors += 1

        try:
            db.commit()
        except Exception as e:
            logger.error(f"Database commit error: {e}")
            db.rollback()
            result.errors += 1

        return result
