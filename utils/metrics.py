import time
from functools import wraps
from prometheus_client import Counter, Histogram, Gauge
import logging

logger = logging.getLogger(__name__)

# Define metrics
REQUEST_COUNT = Counter(
    'instagram_scraper_requests_total',
    'Total number of requests',
    ['endpoint', 'method', 'status']
)

REQUEST_LATENCY = Histogram(
    'instagram_scraper_request_latency_seconds',
    'Request latency in seconds',
    ['endpoint']
)

SCRAPE_COUNT = Counter(
    'instagram_scraper_scrapes_total',
    'Total number of profile scrapes',
    ['status']
)

ACTIVE_SESSIONS = Gauge(
    'instagram_scraper_active_sessions',
    'Number of active Instagram sessions'
)

FILE_OPERATIONS = Counter(
    'instagram_scraper_file_operations_total',
    'Total number of file operations',
    ['operation', 'file_type']
)

def track_metrics(endpoint=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            start_time = time.time()
            
            try:
                response = f(*args, **kwargs)
                status = 'success'
            except Exception as e:
                status = 'error'
                logger.error(f"Error in {endpoint}: {str(e)}")
                raise
            
            # Record metrics
            REQUEST_COUNT.labels(
                endpoint=endpoint or f.__name__,
                method=request.method,
                status=status
            ).inc()
            
            REQUEST_LATENCY.labels(
                endpoint=endpoint or f.__name__
            ).observe(time.time() - start_time)
            
            return response
        return wrapped
    return decorator

def track_scrape(status):
    """Track scraping metrics"""
    SCRAPE_COUNT.labels(status=status).inc()

def track_file_operation(operation, file_type):
    """Track file operation metrics"""
    FILE_OPERATIONS.labels(
        operation=operation,
        file_type=file_type
    ).inc()

def update_active_sessions(count):
    """Update active sessions gauge"""
    ACTIVE_SESSIONS.set(count)

class MetricsMiddleware:
    def __init__(self, app):
        self.app = app
    
    def __call__(self, environ, start_response):
        start_time = time.time()
        
        def custom_start_response(status, headers, exc_info=None):
            # Record request metrics
            REQUEST_COUNT.labels(
                endpoint=environ.get('PATH_INFO', 'unknown'),
                method=environ.get('REQUEST_METHOD', 'unknown'),
                status=status.split()[0]
            ).inc()
            
            REQUEST_LATENCY.labels(
                endpoint=environ.get('PATH_INFO', 'unknown')
            ).observe(time.time() - start_time)
            
            return start_response(status, headers, exc_info)
        
        return self.app(environ, custom_start_response) 