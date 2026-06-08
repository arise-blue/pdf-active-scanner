import logging
from datetime import datetime
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def scrape_job(db_session, scraper):
    """Background job for periodic scraping."""
    try:
        logger.info("Starting scheduled scrape job...")
        result = scraper.scrape(db_session)

        logger.info(
            f"Scrape completed: {result.new_officers} new officers, "
            f"{result.updated_officers} updated, {result.new_articles} new articles, "
            f"{result.skipped} skipped, {result.errors} errors"
        )

        from app.models import Settings
        try:
            setting = db_session.query(Settings).filter(Settings.key == "last_scraped_at").first()
            if not setting:
                setting = Settings(key="last_scraped_at", value=datetime.utcnow().isoformat())
                db_session.add(setting)
            else:
                setting.value = datetime.utcnow().isoformat()
            db_session.commit()
        except Exception as e:
            logger.error(f"Failed to update last_scraped_at: {e}")

    except Exception as e:
        logger.error(f"Scrape job failed: {e}")
    finally:
        db_session.close()


def start_scheduler(db_session_factory, scraper):
    """Start the background scheduler."""
    if scheduler.running:
        return

    try:
        ist = pytz.timezone("Asia/Kolkata")

        scheduler.add_job(
            scrape_job,
            CronTrigger(hour=2, minute=0, timezone=ist),
            args=[db_session_factory(), scraper],
            id="scraper_daily",
            name="Daily scraper at 02:00 IST",
            replace_existing=True,
        )

        scheduler.start()
        logger.info("Scheduler started. Daily scrape scheduled for 02:00 IST.")

    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")


def stop_scheduler():
    """Stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped.")
