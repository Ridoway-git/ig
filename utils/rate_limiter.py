import time
from collections import defaultdict
from threading import Lock
from functools import wraps
from flask import request, jsonify
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, max_requests, window):
        self.max_requests = max_requests
        self.window = window
        self.requests = defaultdict(list)
        self.lock = Lock()
    
    def is_rate_limited(self, key):
        with self.lock:
            now = time.time()
            # Remove old requests
            self.requests[key] = [req_time for req_time in self.requests[key] 
                                if now - req_time < self.window]
            
            # Check if rate limit exceeded
            if len(self.requests[key]) >= self.max_requests:
                return True
            
            # Add new request
            self.requests[key].append(now)
            return False
    
    def get_remaining_requests(self, key):
        with self.lock:
            now = time.time()
            self.requests[key] = [req_time for req_time in self.requests[key] 
                                if now - req_time < self.window]
            return max(0, self.max_requests - len(self.requests[key]))

def rate_limit(max_requests, window):
    limiter = RateLimiter(max_requests, window)
    
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Get client IP or use a default key
            key = request.remote_addr or 'default'
            
            if limiter.is_rate_limited(key):
                remaining_time = window - (time.time() - limiter.requests[key][0])
                logger.warning(f"Rate limit exceeded for {key}")
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'retry_after': int(remaining_time),
                    'remaining_requests': 0
                }), 429
            
            remaining = limiter.get_remaining_requests(key)
            response = f(*args, **kwargs)
            
            # Add rate limit headers
            if isinstance(response, tuple):
                response_data, status_code = response
                if isinstance(response_data, dict):
                    response_data['remaining_requests'] = remaining
                    return jsonify(response_data), status_code
            return response
        
        return wrapped
    return decorator

# Create global rate limiters
api_limiter = RateLimiter(100, 3600)  # 100 requests per hour
scrape_limiter = RateLimiter(50, 3600)  # 50 scrapes per hour 