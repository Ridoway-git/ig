import hashlib
import hmac
import time
import secrets
from functools import wraps
from flask import request, session, redirect, url_for, current_app
import logging

logger = logging.getLogger(__name__)

def generate_csrf_token():
    """Generate a CSRF token"""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']

def validate_csrf_token():
    """Validate CSRF token from request"""
    token = request.form.get('csrf_token')
    if not token or token != session.get('csrf_token'):
        logger.warning("CSRF token validation failed")
        return False
    return True

def csrf_protect(f):
    """Decorator to protect routes from CSRF attacks"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == "POST":
            if not validate_csrf_token():
                return jsonify({'error': 'Invalid CSRF token'}), 403
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('instagram_authenticated'):
            logger.warning(f"Unauthorized access attempt to {request.path}")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def sanitize_filename(filename):
    """Sanitize filename to prevent directory traversal"""
    import os
    from werkzeug.utils import secure_filename
    
    # Get the base name and extension
    base, ext = os.path.splitext(filename)
    
    # Check if extension is allowed
    if ext.lower() not in current_app.config['ALLOWED_EXTENSIONS']:
        raise ValueError(f"Invalid file extension: {ext}")
    
    # Sanitize the filename
    safe_filename = secure_filename(base) + ext.lower()
    
    # Ensure the filename is not empty
    if not safe_filename:
        raise ValueError("Invalid filename")
    
    return safe_filename

def validate_session_id(session_id):
    """Validate Instagram session ID format"""
    if not session_id or len(session_id) < 20:
        return False
    
    # Basic format validation
    try:
        # Session ID should contain at least one colon
        if ':' not in session_id:
            return False
        
        # Check for common session ID patterns
        parts = session_id.split(':')
        if len(parts) < 2:
            return False
        
        # First part should be numeric (user ID)
        if not parts[0].isdigit():
            return False
        
        return True
    except:
        return False

def hash_password(password):
    """Hash password using PBKDF2"""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return f"{salt}${key.hex()}"

def verify_password(stored_password, provided_password):
    """Verify password against stored hash"""
    try:
        salt, key = stored_password.split('$')
        new_key = hashlib.pbkdf2_hmac(
            'sha256',
            provided_password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return hmac.compare_digest(key, new_key.hex())
    except:
        return False

def rate_limit_key():
    """Generate rate limit key based on user IP and session"""
    return f"{request.remote_addr}:{session.get('instagram_sessionid', '')}"

def validate_instagram_url(url):
    """Validate Instagram URL format"""
    import re
    pattern = r'^https?://(?:www\.)?instagram\.com/[a-zA-Z0-9_\.]+/?$'
    return bool(re.match(pattern, url))

def validate_username(username):
    """Validate Instagram username format"""
    import re
    pattern = r'^[a-zA-Z0-9_\.]{1,30}$'
    return bool(re.match(pattern, username)) 