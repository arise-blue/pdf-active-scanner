import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db, SessionLocal
from app.models import Officer, Settings
from app.scraper import ArticleScraper, ScrapeResult
from app.scheduler import start_scheduler, stop_scheduler
from app.routers import officers, articles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

scraper = ArticleScraper()
startup_done = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global startup_done
    logger.info("Application startup...")

    db = SessionLocal()
    try:
        officer_count = db.query(Officer).count()
        if officer_count == 0:
            logger.info("First boot detected. Running initial scrape...")
            result = scraper.scrape(db)
            logger.info(
                f"Initial scrape: {result.new_officers} new officers, "
                f"{result.new_articles} new articles"
            )

            setting = Settings(key="last_scraped_at", value=datetime.utcnow().isoformat())
            db.add(setting)
            db.commit()

        start_scheduler(SessionLocal, scraper)
        startup_done = True

    except Exception as e:
        logger.error(f"Startup error: {e}")
    finally:
        db.close()

    yield

    logger.info("Application shutdown...")
    stop_scheduler()


app = FastAPI(title="India Bureaucrat Accountability Tracker", lifespan=lifespan)

app.include_router(officers.router)
app.include_router(articles.router)

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "change_me_to_a_secret_token")

env = Environment(loader=FileSystemLoader("app/templates"))


def verify_admin_token(x_admin_token: str = Header(None)):
    """Verify admin token from request header."""
    if not x_admin_token or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    return True


@app.get("/", response_class=HTMLResponse)
async def root(db: Session = Depends(get_db)):
    """Serve the frontend SPA."""
    template = env.get_template("index.html")
    return template.render()


@app.get("/api/health")
async def health(db: Session = Depends(get_db)):
    """Health check endpoint."""
    try:
        officer_count = db.query(Officer).count()
        setting = db.query(Settings).filter(Settings.key == "last_scraped_at").first()
        last_scraped_at = setting.value if setting else None

        return {
            "status": "ok",
            "db_record_count": officer_count,
            "last_scraped_at": last_scraped_at,
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {"status": "error", "message": str(e)}, 500


@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get global statistics."""
    from app.routers.officers import get_stats as officers_get_stats
    return await officers_get_stats(db)


@app.post("/api/scrape/trigger")
async def trigger_scrape(
    verified: bool = Depends(verify_admin_token),
    db: Session = Depends(get_db),
):
    """Manually trigger a scrape run."""
    try:
        logger.info("Manual scrape triggered...")
        result = scraper.scrape(db)

        setting = db.query(Settings).filter(Settings.key == "last_scraped_at").first()
        if not setting:
            setting = Settings(key="last_scraped_at", value=datetime.utcnow().isoformat())
            db.add(setting)
        else:
            setting.value = datetime.utcnow().isoformat()

        db.commit()

        logger.info(
            f"Manual scrape completed: {result.new_officers} new officers, "
            f"{result.new_articles} new articles"
        )

        return {
            "status": "success",
            "result": result.to_dict(),
        }

    except Exception as e:
        logger.error(f"Scrape error: {e}")
        db.rollback()
        return {
            "status": "error",
            "message": str(e),
        }, 500
