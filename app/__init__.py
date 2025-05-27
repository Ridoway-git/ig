from flask import Flask
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_compress import Compress
from flask_talisman import Talisman
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
import os
from config import Config

# Initialize extensions
cache = Cache()
limiter = Limiter(key_func=get_remote_address)
compress = Compress()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize Sentry if DSN is provided
    if os.environ.get('SENTRY_DSN'):
        sentry_sdk.init(
            dsn=os.environ.get('SENTRY_DSN'),
            integrations=[FlaskIntegration()],
            traces_sample_rate=1.0,
            environment=os.environ.get('FLASK_ENV', 'production')
        )
    
    # Initialize extensions
    cache.init_app(app)
    limiter.init_app(app)
    compress.init_app(app)
    
    # Initialize Talisman for security headers
    Talisman(
        app,
        force_https=app.config.get('SESSION_COOKIE_SECURE', True),
        strict_transport_security=True,
        session_cookie_secure=True,
        content_security_policy={
            'default-src': "'self'",
            'script-src': "'self' 'unsafe-inline' 'unsafe-eval'",
            'style-src': "'self' 'unsafe-inline'",
            'img-src': "'self' data: https:",
            'connect-src': "'self' https://www.instagram.com"
        }
    )
    
    # Register blueprints
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Initialize metrics
    if app.config.get('ENABLE_METRICS'):
        from utils.metrics import MetricsMiddleware
        app.wsgi_app = MetricsMiddleware(app.wsgi_app)
    
    # Initialize logging
    config_class.init_app(app)
    
    return app 