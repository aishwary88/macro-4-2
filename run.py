"""
run.py — Entry point for SentrySpeed Traffic Analyzer.
Usage: python run.py
"""

import uvicorn
from core.config import settings
from modules.data.database import init_db
from modules.utils.logger import get_logger

logger = get_logger("run")


def main():
    logger.info("=" * 60)
    logger.info("Traffic Analyzer v2.0")
    logger.info("=" * 60)

    # Initialize database
    init_db()
    settings.ensure_directories()

    logger.info(f"Starting server on http://{settings.HOST}:{settings.PORT}")
    logger.info(f"Dashboard: http://localhost:{settings.PORT}/")
    logger.info(f"API Docs:  http://localhost:{settings.PORT}/docs")

    uvicorn.run(
        "app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )


if __name__ == "__main__":
    main()
