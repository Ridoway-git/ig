import os
from datetime import timedelta

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(days=1)
    
    # Instagram scraping settings
    MAX_RETRIES = 3
    RETRY_DELAY = 5
    REQUEST_TIMEOUT = 30
    RATE_LIMIT_REQUESTS = 50  # requests per hour
    RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds
    
    # File management
    SCRAPED_DATA_DIR = 'scraped_data'
    MAX_FILE_AGE_DAYS = 7
    MAX_FILES_PER_USER = 100
    
    # Security
    ALLOWED_EXTENSIONS = {'.txt', '.xlsx'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_FILE = 'instagram_scraper.log'
    
    # API settings
    API_RATE_LIMIT = 100  # requests per hour
    API_TIMEOUT = 30  # seconds
    
    # Cache settings
    CACHE_TYPE = 'simple'
    CACHE_DEFAULT_TIMEOUT = 300  # 5 minutes
    
    # Monitoring
    ENABLE_METRICS = True
    METRICS_PORT = 9090
    
    @staticmethod
    def init_app(app):
        # Create necessary directories
        os.makedirs(Config.SCRAPED_DATA_DIR, exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        
        # Configure logging
        import logging
        from logging.handlers import RotatingFileHandler
        
        handler = RotatingFileHandler(
            Config.LOG_FILE,
            maxBytes=10000000,  # 10MB
            backupCount=5
        )
        handler.setFormatter(logging.Formatter(Config.LOG_FORMAT))
        app.logger.addHandler(handler)
        app.logger.setLevel(Config.LOG_LEVEL) 