import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.tasks.check_prices import check_all_products

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    scheduler.add_job(
        check_all_products,
        trigger=IntervalTrigger(hours=settings.check_interval_hours),
        id="check_prices",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info("Scheduler запущен, интервал: %s ч", settings.check_interval_hours)


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)