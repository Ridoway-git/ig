import requests
from instascrape import Profile, Post
from datetime import datetime
import time
import logging
from flask import current_app
from .utils.metrics import track_scrape
from .utils.security import validate_username, validate_instagram_url

logger = logging.getLogger(__name__)

class InstagramScraper:
    def __init__(self):
        self.session = requests.Session()
        self.authenticated = False
        self.session_id = None
        self.csrf_token = None
        self.last_request_time = 0
        self.min_request_interval = 2  # Minimum seconds between requests
        
        # Set default headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'X-IG-App-ID': '936619743392459',
            'X-IG-WWW-Claim': '0',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://www.instagram.com/',
        })
    
    def _respect_rate_limit(self):
        """Ensure we don't exceed rate limits"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last_request
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def set_instagram_session(self, sessionid, csrf_token=None):
        """Set Instagram session cookies for authentication"""
        try:
            if not sessionid or len(sessionid) < 20:
                logger.error("Invalid session ID format")
                return False
            
            # Store original sessionid
            self.session_id = sessionid
            self.csrf_token = csrf_token
            
            # Clear existing cookies
            self.session.cookies.clear()
            
            # Set the sessionid cookie
            self.session.cookies.set('sessionid', sessionid, domain='.instagram.com', path='/')
            
            # Set CSRF token if provided
            if csrf_token:
                self.session.cookies.set('csrftoken', csrf_token, domain='.instagram.com', path='/')
                self.session.headers.update({'X-CSRFToken': csrf_token})
            
            # Add essential Instagram cookies
            self.session.cookies.set('mid', 'aDSa3AALAAGieULhLm97NP5dqp_Z', domain='.instagram.com', path='/')
            self.session.cookies.set('ig_did', '3B433670-1F70-4284-AAE8-6C2843AD70FA', domain='.instagram.com', path='/')
            self.session.cookies.set('ig_nrcb', '1', domain='.instagram.com', path='/')
            
            # Extract user ID from sessionid
            try:
                if '%3A' in sessionid:
                    import urllib.parse
                    decoded_sessionid = urllib.parse.unquote(sessionid)
                    user_id = decoded_sessionid.split(':')[0]
                else:
                    user_id = sessionid.split(':')[0]
                self.session.cookies.set('ds_user_id', user_id, domain='.instagram.com', path='/')
            except:
                logger.warning("Could not extract user ID from sessionid")
            
            self.authenticated = True
            logger.info("Session setup complete")
            return True
            
        except Exception as e:
            logger.error(f"Error setting Instagram session: {str(e)}")
            return False
    
    def verify_authentication(self):
        """Verify if the current session is valid"""
        try:
            if not self.session_id:
                return False
            
            self._respect_rate_limit()
            
            # Test authentication
            test_url = 'https://www.instagram.com/'
            response = self.session.get(test_url, allow_redirects=False)
            
            if response.status_code == 302:
                location = response.headers.get('Location', '')
                if 'accounts/login' in location:
                    self.authenticated = False
                    logger.warning("Session expired or invalid")
                    return False
            
            if response.status_code in [200, 302]:
                api_url = 'https://www.instagram.com/api/v1/users/web_profile_info/?username=instagram'
                api_response = self.session.get(api_url)
                
                if api_response.status_code == 200:
                    try:
                        data = api_response.json()
                        if 'data' in data and 'user' in data['data']:
                            self.authenticated = True
                            logger.info("Authentication verified")
                            return True
                    except:
                        pass
                
                self.authenticated = True
                return True
            
            self.authenticated = False
            return False
            
        except Exception as e:
            logger.error(f"Authentication verification failed: {str(e)}")
            self.authenticated = False
            return False
    
    def clean_username(self, username):
        """Clean and validate username"""
        try:
            # Remove @ symbol if present
            username = username.strip().lstrip('@')
            
            # Handle full URLs
            if 'instagram.com' in username:
                if not validate_instagram_url(username):
                    raise ValueError("Invalid Instagram URL")
                from urllib.parse import urlparse
                parsed = urlparse(username)
                path_parts = parsed.path.strip('/').split('/')
                if path_parts and path_parts[0]:
                    username = path_parts[0]
            
            # Validate username format
            if not validate_username(username):
                raise ValueError("Invalid username format")
            
            return username
            
        except Exception as e:
            logger.error(f"Error cleaning username: {str(e)}")
            raise
    
    def scrape_profile(self, username):
        """Scrape Instagram profile data"""
        try:
            if not self.authenticated:
                return {
                    'error': 'Instagram authentication required',
                    'username': username,
                    'scraping_status': 'auth_required'
                }
            
            # Clean and validate username
            try:
                clean_user = self.clean_username(username)
            except ValueError as e:
                return {'error': str(e)}
            
            # Create profile URL
            profile_url = f'https://www.instagram.com/{clean_user}/'
            
            # Try to scrape with retry logic
            max_retries = current_app.config['MAX_RETRIES']
            retry_delay = current_app.config['RETRY_DELAY']
            
            for attempt in range(max_retries):
                try:
                    self._respect_rate_limit()
                    
                    # Create profile with proper session
                    profile = Profile(profile_url)
                    profile._session = self.session
                    
                    # Create headers with cookies
                    scrape_headers = self.session.headers.copy()
                    cookie_string = '; '.join([f'{cookie.name}={cookie.value}' for cookie in self.session.cookies])
                    scrape_headers['Cookie'] = cookie_string
                    
                    # Scrape the profile
                    profile.scrape(headers=scrape_headers, session=self.session)
                    
                    # Extract profile data
                    profile_data = {
                        'username': clean_user,
                        'profile_url': profile_url,
                        'full_name': getattr(profile, 'full_name', 'N/A'),
                        'biography': getattr(profile, 'biography', 'N/A'),
                        'followers': getattr(profile, 'followers', 'N/A'),
                        'following': getattr(profile, 'following', 'N/A'),
                        'posts_count': getattr(profile, 'posts', 'N/A'),
                        'is_verified': getattr(profile, 'is_verified', False),
                        'is_private': getattr(profile, 'is_private', False),
                        'external_url': getattr(profile, 'external_url', 'N/A'),
                        'profile_pic_url': getattr(profile, 'profile_pic_url', 'N/A'),
                        'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'scraping_status': 'success',
                        'authenticated': True,
                        'method': 'insta-scrape'
                    }
                    
                    # Get recent posts if profile is public
                    if not profile_data.get('is_private', True):
                        try:
                            posts_data = self.get_basic_posts_info(profile)
                            profile_data['recent_posts'] = posts_data
                        except Exception as posts_error:
                            logger.error(f"Error getting posts: {str(posts_error)}")
                            profile_data['recent_posts'] = []
                            profile_data['posts_error'] = str(posts_error)
                    else:
                        profile_data['recent_posts'] = []
                        profile_data['note'] = 'Profile is private'
                    
                    return profile_data
                    
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Attempt {attempt + 1} failed for {clean_user}: {error_msg}")
                    
                    if 'unauthorized' in error_msg.lower() or '401' in error_msg:
                        self.authenticated = False
                        return {
                            'error': 'Authentication failed',
                            'username': clean_user,
                            'scraping_status': 'auth_failed'
                        }
                    
                    if 'rate limit' in error_msg.lower() or '429' in error_msg:
                        if attempt < max_retries - 1:
                            logger.warning(f"Rate limited, waiting {retry_delay} seconds")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                            continue
                        else:
                            return {
                                'error': 'Rate limit reached',
                                'username': clean_user,
                                'scraping_status': 'rate_limited'
                            }
                    
                    if attempt == max_retries - 1:
                        logger.warning(f"Trying fallback method for {clean_user}")
                        fallback_result = self.scrape_profile_fallback(clean_user)
                        if fallback_result and 'error' not in fallback_result:
                            return fallback_result
                        
                        return {
                            'error': f'Failed to scrape after {max_retries} attempts',
                            'username': clean_user,
                            'scraping_status': 'failed'
                        }
                    
                    time.sleep(retry_delay)
            
        except Exception as e:
            logger.error(f"Unexpected error scraping {username}: {str(e)}")
            return {
                'error': f'Unexpected error: {str(e)}',
                'username': username,
                'scraping_status': 'error'
            }
    
    def scrape_profile_fallback(self, username):
        """Fallback method using Instagram's web API"""
        try:
            self._respect_rate_limit()
            
            api_url = f'https://www.instagram.com/api/v1/users/web_profile_info/?username={username}'
            response = self.session.get(api_url)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'data' in data and 'user' in data['data']:
                    user_data = data['data']['user']
                    
                    return {
                        'username': username,
                        'profile_url': f'https://www.instagram.com/{username}/',
                        'full_name': user_data.get('full_name', 'N/A'),
                        'biography': user_data.get('biography', 'N/A'),
                        'followers': user_data.get('edge_followed_by', {}).get('count', 'N/A'),
                        'following': user_data.get('edge_follow', {}).get('count', 'N/A'),
                        'posts_count': user_data.get('edge_owner_to_timeline_media', {}).get('count', 'N/A'),
                        'is_verified': user_data.get('is_verified', False),
                        'is_private': user_data.get('is_private', False),
                        'external_url': user_data.get('external_url', 'N/A'),
                        'profile_pic_url': user_data.get('profile_pic_url_hd', 'N/A'),
                        'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'scraping_status': 'success',
                        'authenticated': True,
                        'method': 'api_fallback'
                    }
            
            logger.warning(f"Fallback API request failed for {username}")
            return None
                
        except Exception as e:
            logger.error(f"Fallback scraping failed for {username}: {str(e)}")
            return None
    
    def get_basic_posts_info(self, profile):
        """Get basic post information"""
        posts_data = []
        try:
            self._respect_rate_limit()
            
            # This is a simplified approach since Instagram heavily restricts post data access
            posts_data.append({
                'note': 'Post details require Instagram authentication',
                'suggestion': 'Use Instagram Business API for detailed post analytics'
            })
            
        except Exception as e:
            logger.error(f"Error getting posts info: {str(e)}")
        
        return posts_data 