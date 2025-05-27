from celery import Celery
from app import create_app
from app.utils.metrics import track_scrape
from app.utils.file_manager import cleanup_old_files
import logging

logger = logging.getLogger(__name__)

# Initialize Celery
celery = Celery('instagram_scraper',
                broker='redis://localhost:6379/0',
                backend='redis://localhost:6379/0')

# Configure Celery
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour
    worker_max_tasks_per_child=100,
    worker_prefetch_multiplier=1
)

@celery.task(bind=True, max_retries=3)
def process_scraping(self, usernames):
    """Process scraping in background"""
    try:
        # Create Flask app context
        app = create_app()
        with app.app_context():
            from app.scraper import InstagramScraper
            scraper = InstagramScraper()
            
            # Clean up old files before starting
            cleanup_old_files()
            
            # Process usernames
            successful = 0
            failed = 0
            rate_limited = 0
            
            for username in usernames:
                try:
                    result = scraper.scrape_profile(username)
                    if result.get('error'):
                        if 'rate limit' in result['error'].lower():
                            rate_limited += 1
                            track_scrape('rate_limited')
                        else:
                            failed += 1
                            track_scrape('failed')
                    else:
                        successful += 1
                        track_scrape('success')
                except Exception as e:
                    logger.error(f"Error scraping {username}: {str(e)}")
                    failed += 1
                    track_scrape('error')
            
            return {
                'status': 'completed',
                'successful': successful,
                'failed': failed,
                'rate_limited': rate_limited,
                'total': len(usernames)
            }
            
    except Exception as e:
        logger.error(f"Error in process_scraping: {str(e)}")
        track_scrape('error')
        # Retry the task
        self.retry(exc=e, countdown=60)  # Retry after 1 minute

@celery.task
def cleanup_task():
    """Periodic cleanup task"""
    try:
        app = create_app()
        with app.app_context():
            deleted = cleanup_old_files()
            logger.info(f"Cleanup task completed. Deleted {deleted} files.")
            return {'deleted': deleted}
    except Exception as e:
        logger.error(f"Error in cleanup task: {str(e)}")
        return {'error': str(e)}

# Schedule periodic tasks
celery.conf.beat_schedule = {
    'cleanup-old-files': {
        'task': 'app.tasks.cleanup_task',
        'schedule': 86400.0,  # Run daily
    },
} 