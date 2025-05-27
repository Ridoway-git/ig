from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from instascrape import Profile, Post
import os
import json
from datetime import datetime
import threading
import time
import requests
from urllib.parse import urlparse
import re
import pandas as pd
import io

app = Flask(__name__)
app.secret_key = 'your_secret_key_change_this_in_production'

# Create directories for storing data
os.makedirs('scraped_data', exist_ok=True)
os.makedirs('templates', exist_ok=True)

class InstagramScraper:
    def __init__(self):
        # Instagram session cookies and headers
        self.session = requests.Session()
        self.authenticated = False
        self.session_id = None
        self.csrf_token = None
        
        # Basic headers to mimic a real browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'X-Requested-With': 'XMLHttpRequest',
        })
    
    def set_instagram_session(self, sessionid, csrf_token=None):
        """Set Instagram session cookies for authentication"""
        try:
            # Store original sessionid (don't decode it if it's already encoded properly)
            self.session_id = sessionid
            self.csrf_token = csrf_token
            
            # Clear existing cookies
            self.session.cookies.clear()
            
            # Set the sessionid cookie - use original format
            self.session.cookies.set('sessionid', sessionid, domain='.instagram.com', path='/')
            
            # Set CSRF token if provided
            if csrf_token:
                self.session.cookies.set('csrftoken', csrf_token, domain='.instagram.com', path='/')
                self.session.headers.update({'X-CSRFToken': csrf_token})
            else:
                # Set a basic CSRF token
                self.session.cookies.set('csrftoken', 'GeBa58zESybAaWM8YDzOF5', domain='.instagram.com', path='/')
            
            # Add essential Instagram cookies
            self.session.cookies.set('mid', 'aDSa3AALAAGieULhLm97NP5dqp_Z', domain='.instagram.com', path='/')
            self.session.cookies.set('ig_did', '3B433670-1F70-4284-AAE8-6C2843AD70FA', domain='.instagram.com', path='/')
            self.session.cookies.set('ig_nrcb', '1', domain='.instagram.com', path='/')
            self.session.cookies.set('datr', '3Jo0aG_zLBi8BQ1nckRuwUuI', domain='.instagram.com', path='/')
            self.session.cookies.set('rur', 'CLN', domain='.instagram.com', path='/')
            self.session.cookies.set('ps_l', '1', domain='.instagram.com', path='/')
            self.session.cookies.set('ps_n', '1', domain='.instagram.com', path='/')
            
            # Extract user ID from sessionid for ds_user_id
            try:
                # SessionID format is usually: user_id:hash:other_parts
                if '%3A' in sessionid:
                    import urllib.parse
                    decoded_sessionid = urllib.parse.unquote(sessionid)
                    user_id = decoded_sessionid.split(':')[0]
                else:
                    user_id = sessionid.split(':')[0]
                self.session.cookies.set('ds_user_id', user_id, domain='.instagram.com', path='/')
                print(f"Set ds_user_id to: {user_id}")
            except:
                print("Could not extract user ID from sessionid")
            
            # Update headers to mimic real browser
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
            
            self.authenticated = True
            print(f"Session setup complete with {len(self.session.cookies)} cookies")
            return True
        except Exception as e:
            print(f"Error setting Instagram session: {e}")
            return False
    
    def verify_authentication(self):
        """Verify if the current session is valid"""
        try:
            if not self.session_id:
                return False
            
            # Test authentication by trying to access Instagram's main page first
            test_url = 'https://www.instagram.com/'
            response = self.session.get(test_url, allow_redirects=False)
            
            # Check if we're redirected to login (indicates invalid session)
            if response.status_code == 302:
                location = response.headers.get('Location', '')
                if 'accounts/login' in location:
                    self.authenticated = False
                    print("Session expired or invalid - redirected to login")
                    return False
            
            # If we get 200 or other success codes, try a simple API call
            if response.status_code in [200, 302]:
                # Try to access a simple endpoint
                api_url = 'https://www.instagram.com/api/v1/users/web_profile_info/?username=instagram'
                api_response = self.session.get(api_url)
                
                if api_response.status_code == 200:
                    try:
                        data = api_response.json()
                        if 'data' in data and 'user' in data['data']:
                            self.authenticated = True
                            print("Authentication verified successfully")
                            return True
                    except:
                        pass
                
                # Even if API fails, if we're not redirected to login, consider it authenticated
                self.authenticated = True
                return True
            
            self.authenticated = False
            return False
            
        except Exception as e:
            print(f"Authentication verification failed: {e}")
            self.authenticated = False
            return False
    
    def clean_username(self, username):
        """Clean and validate username"""
        # Remove @ symbol if present
        username = username.strip().lstrip('@')
        
        # Remove any URL parts if user pasted a full Instagram URL
        if 'instagram.com' in username:
            try:
                parsed = urlparse(username)
                path_parts = parsed.path.strip('/').split('/')
                if path_parts and path_parts[0]:
                    username = path_parts[0]
            except:
                pass
        
        # Remove any query parameters or fragments
        username = username.split('?')[0].split('#')[0]
        
        return username
    
    def scrape_profile(self, username):
        try:
            # Check if authenticated
            if not self.authenticated:
                return {
                    'error': f'Instagram authentication required. Please login first.',
                    'username': username,
                    'scraping_status': 'auth_required'
                }
            
            # Clean the username
            clean_user = self.clean_username(username)
            
            if not clean_user or len(clean_user) < 1:
                return {'error': f'Invalid username: {username}'}
            
            # Create profile URL
            profile_url = f'https://www.instagram.com/{clean_user}/'
            
            # Try to create and scrape profile with retry logic
            max_retries = 3
            retry_delay = 5
            
            for attempt in range(max_retries):
                try:
                    # Create profile with proper session handling
                    profile = Profile(profile_url)
                    
                    # Properly inject our authenticated session into the profile
                    profile._session = self.session
                    
                    # Create headers with cookies for instascrape
                    scrape_headers = self.session.headers.copy()
                    
                    # Get cookies as a string for the Cookie header
                    cookie_string = '; '.join([f'{cookie.name}={cookie.value}' for cookie in self.session.cookies])
                    scrape_headers['Cookie'] = cookie_string
                    
                    # Scrape the profile data with proper headers and session
                    profile.scrape(headers=scrape_headers, session=self.session)
                    
                    # Extract basic profile information
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
                    
                    # Try to get basic post count information
                    try:
                        # Attempt to get recent posts if available and profile is public
                        if not profile_data.get('is_private', True):
                            posts_data = self.get_basic_posts_info(profile)
                            profile_data['recent_posts'] = posts_data
                        else:
                            profile_data['recent_posts'] = []
                            profile_data['note'] = 'Profile is private - limited data available'
                    except Exception as posts_error:
                        profile_data['recent_posts'] = []
                        profile_data['posts_error'] = f'Could not retrieve posts: {str(posts_error)}'
                    
                    return profile_data
                    
                except Exception as e:
                    error_msg = str(e)
                    print(f"Attempt {attempt + 1} failed for {clean_user}: {error_msg}")
                    
                    # Check if it's an authentication error
                    if 'unauthorized' in error_msg.lower() or '401' in error_msg or 'login' in error_msg.lower():
                        self.authenticated = False
                        return {
                            'error': f'Instagram authentication failed for {clean_user}. Please check your session credentials.',
                            'username': clean_user,
                            'scraping_status': 'auth_failed'
                        }
                    
                    # Check if it's a rate limit error
                    if 'rate limit' in error_msg.lower() or '429' in error_msg:
                        if attempt < max_retries - 1:
                            print(f"Rate limited, waiting {retry_delay} seconds before retry...")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                            continue
                        else:
                            return {
                                'error': f'Instagram rate limit reached for {clean_user}. Please try again later.',
                                'username': clean_user,
                                'scraping_status': 'rate_limited'
                            }
                    
                    # If it's the last attempt, try the fallback method
                    if attempt == max_retries - 1:
                        print(f"Trying fallback method for {clean_user}")
                        fallback_result = self.scrape_profile_fallback(clean_user)
                        if fallback_result and 'error' not in fallback_result:
                            return fallback_result
                        
                        return {
                            'error': f'Failed to scrape {clean_user} after {max_retries} attempts: {error_msg}',
                            'username': clean_user,
                            'scraping_status': 'failed'
                        }
                    
                    # Wait before retry
                    time.sleep(retry_delay)
            
        except Exception as e:
            return {
                'error': f'Unexpected error scraping {username}: {str(e)}',
                'username': username,
                'scraping_status': 'error'
            }
    
    def scrape_profile_fallback(self, username):
        """Fallback method using Instagram's web API directly"""
        try:
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
                else:
                    print(f"No user data found in API response for {username}")
                    return None
            else:
                print(f"API request failed with status {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Fallback scraping failed for {username}: {e}")
            return None
    
    def get_basic_posts_info(self, profile):
        """Try to get basic post information"""
        posts_data = []
        try:
            # This is a simplified approach since Instagram heavily restricts post data access
            posts_data.append({
                'note': 'Post details require Instagram authentication',
                'suggestion': 'Use Instagram Business API for detailed post analytics'
            })
        except Exception as e:
            print(f"Error getting posts info: {e}")
        
        return posts_data

scraper = InstagramScraper()

@app.route('/')
def index():
    auth_status = session.get('instagram_authenticated', False)
    return render_template('index.html', authenticated=auth_status)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        sessionid = request.form.get('sessionid', '').strip()
        csrf_token = request.form.get('csrf_token', '').strip()
        
        if not sessionid:
            return render_template('login.html', error='Session ID is required')
        
        if len(sessionid) < 20:
            return render_template('login.html', error='Session ID appears to be too short. Please copy the complete sessionid cookie value.')
        
        print(f"Attempting login with sessionid length: {len(sessionid)}")
        print(f"CSRF token provided: {'Yes' if csrf_token else 'No'}")
        
        # Set Instagram session
        if scraper.set_instagram_session(sessionid, csrf_token):
            print("Session cookies set successfully")
            if scraper.verify_authentication():
                session['instagram_authenticated'] = True
                session['instagram_sessionid'] = sessionid
                if csrf_token:
                    session['instagram_csrf'] = csrf_token
                print("Authentication successful!")
                return redirect(url_for('index'))
            else:
                error_msg = 'Authentication failed. This could mean:\n'
                error_msg += '• Session ID is expired or invalid\n'
                error_msg += '• Instagram detected automated access\n'
                error_msg += '• Try logging out and back into Instagram, then get a fresh Session ID'
                return render_template('login.html', error=error_msg)
        else:
            return render_template('login.html', error='Failed to set Instagram session. Please check your Session ID format.')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    scraper.authenticated = False
    scraper.session_id = None
    scraper.csrf_token = None
    return redirect(url_for('index'))

@app.route('/auth_status')
def auth_status():
    is_authenticated = session.get('instagram_authenticated', False)
    if is_authenticated and session.get('instagram_sessionid'):
        # Restore session if it exists
        scraper.set_instagram_session(session.get('instagram_sessionid'))
    
    return jsonify({
        'authenticated': is_authenticated,
        'scraper_authenticated': scraper.authenticated
    })

@app.route('/scrape', methods=['POST'])
def scrape_usernames():
    # Check authentication first
    if not session.get('instagram_authenticated') or not scraper.authenticated:
        return jsonify({'error': 'Instagram authentication required. Please login first.'}), 401
    
    data = request.get_json()
    usernames = data.get('usernames', [])
    
    if not usernames:
        return jsonify({'error': 'No usernames provided'}), 400
    
    # Clean usernames
    cleaned_usernames = []
    for username in usernames:
        clean_user = scraper.clean_username(username)
        if clean_user:
            cleaned_usernames.append(clean_user)
    
    if not cleaned_usernames:
        return jsonify({'error': 'No valid usernames provided'}), 400
    
    # Process usernames in background thread
    thread = threading.Thread(target=process_scraping, args=(cleaned_usernames,))
    thread.start()
    
    return jsonify({
        'message': f'Started scraping {len(cleaned_usernames)} username(s)', 
        'status': 'processing',
        'usernames': cleaned_usernames
    })

def process_scraping(usernames):
    # Clean up old files before starting new scraping
    cleanup_old_files()
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Create more descriptive filenames
    main_txt = f'scraped_data/all_profiles_{timestamp}.txt'
    main_excel = f'scraped_data/all_profiles_{timestamp}.xlsx'
    
    # Separate files for different post count groups with clear names
    low_posts_txt = f'scraped_data/profiles_under_5_posts_{timestamp}.txt'
    high_posts_txt = f'scraped_data/profiles_over_5_posts_{timestamp}.txt'
    low_posts_excel = f'scraped_data/profiles_under_5_posts_{timestamp}.xlsx'
    high_posts_excel = f'scraped_data/profiles_over_5_posts_{timestamp}.xlsx'
    
    successful_scrapes = 0
    failed_scrapes = 0
    rate_limited = 0
    
    # Lists to store profile data for different groups
    low_posts_data = []  # 1-5 posts
    high_posts_data = []  # >5 posts
    
    with open(main_txt, 'w', encoding='utf-8') as f:
        f.write(f"Instagram Profile Data Scraping Results\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Powered by: insta-scrape \n")
        f.write("=" * 80 + "\n\n")
        
        f.write("IMPORTANT NOTES:\n")
        f.write("- Instagram heavily restricts automated data access\n")
        f.write("- This tool provides basic public profile information only\n")
        f.write("- For detailed analytics, use Instagram Business API\n")
        f.write("- Respect Instagram's Terms of Service and rate limits\n")
        f.write("=" * 80 + "\n\n")
        
        for i, username in enumerate(usernames, 1):
            f.write(f"PROFILE {i}/{len(usernames)}: @{username}\n")
            f.write("-" * 50 + "\n")
            
            profile_data = scraper.scrape_profile(username)
            
            if 'error' in profile_data:
                f.write(f"❌ ERROR: {profile_data['error']}\n")
                
                if profile_data.get('scraping_status') == 'rate_limited':
                    rate_limited += 1
                    f.write("💡 TIP: Try again later when rate limits reset\n")
                else:
                    failed_scrapes += 1
                
                f.write("\n")
                continue
            
            successful_scrapes += 1
            
            # Write profile information
            f.write(f"✅ Successfully scraped: @{profile_data.get('username', username)}\n")
            f.write(f"📁 Profile URL: {profile_data.get('profile_url', 'N/A')}\n")
            f.write(f"👤 Full Name: {profile_data.get('full_name', 'N/A')}\n")
            f.write(f"📝 Biography: {profile_data.get('biography', 'N/A')}\n")
            f.write(f"👥 Followers: {profile_data.get('followers', 'N/A')}\n")
            f.write(f"➡️ Following: {profile_data.get('following', 'N/A')}\n")
            f.write(f"📸 Posts Count: {profile_data.get('posts_count', 'N/A')}\n")
            f.write(f"✔️ Verified: {'Yes' if profile_data.get('is_verified') else 'No'}\n")
            f.write(f"🔒 Private: {'Yes' if profile_data.get('is_private') else 'No'}\n")
            f.write(f"🔗 External URL: {profile_data.get('external_url', 'N/A')}\n")
            f.write(f"🖼️ Profile Picture: {profile_data.get('profile_pic_url', 'N/A')}\n")
            f.write(f"⏰ Scraped At: {profile_data.get('scraped_at')}\n")
            
            # Add notes if any
            if profile_data.get('note'):
                f.write(f"📋 Note: {profile_data['note']}\n")
            
            if profile_data.get('posts_error'):
                f.write(f"⚠️ Posts Info: {profile_data['posts_error']}\n")
            
            # Prepare data for Excel
            excel_data = {
                'Username': profile_data.get('username', username),
                'Full Name': profile_data.get('full_name', 'N/A'),
                'Biography': profile_data.get('biography', 'N/A'),
                'Followers': profile_data.get('followers', 'N/A'),
                'Following': profile_data.get('following', 'N/A'),
                'Posts Count': profile_data.get('posts_count', 'N/A'),
                'Verified': 'Yes' if profile_data.get('is_verified') else 'No',
                'Private': 'Yes' if profile_data.get('is_private') else 'No',
                'External URL': profile_data.get('external_url', 'N/A'),
                'Profile Picture URL': profile_data.get('profile_pic_url', 'N/A'),
                'Scraped At': profile_data.get('scraped_at', 'N/A'),
                'Status': 'Success',
                'Note': profile_data.get('note', ''),
                'Posts Error': profile_data.get('posts_error', '')
            }
            
            # Sort into appropriate group based on post count
            try:
                posts_count = int(profile_data.get('posts_count', 0))
                if 1 <= posts_count <= 5:
                    low_posts_data.append(excel_data)
                else:
                    high_posts_data.append(excel_data)
            except (ValueError, TypeError):
                # If posts count is not a valid number, add to high posts group
                high_posts_data.append(excel_data)
            
            f.write("\n" + "=" * 80 + "\n\n")
            
            # Add delay between requests to be respectful
            if i < len(usernames):  # Don't sleep after the last username
                time.sleep(3)
        
        # Write summary
        f.write("SCRAPING SUMMARY:\n")
        f.write("-" * 30 + "\n")
        f.write(f"✅ Successful: {successful_scrapes}\n")
        f.write(f"❌ Failed: {failed_scrapes}\n")
        f.write(f"⏱️ Rate Limited: {rate_limited}\n")
        f.write(f"📊 Total Processed: {len(usernames)}\n")
        f.write(f"👥 Profiles with 1-5 Posts: {len(low_posts_data)}\n")
        f.write(f"👥 Profiles with More than 5 Posts: {len(high_posts_data)}\n")
        f.write(f"⏰ Completed At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Create separate Excel files for each group
    try:
        if low_posts_data:
            df_low = pd.DataFrame(low_posts_data)
            df_low.to_excel(low_posts_excel, index=False, engine='openpyxl')
            
            # Write low posts text file
            with open(low_posts_txt, 'w', encoding='utf-8') as f:
                f.write("Instagram Profiles with 1-5 Posts\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Total Profiles: {len(low_posts_data)}\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("-" * 50 + "\n\n")
                for profile in low_posts_data:
                    f.write(f"Username: {profile['Username']}\n")
                    f.write(f"Posts Count: {profile['Posts Count']}\n")
                    f.write(f"Full Name: {profile['Full Name']}\n")
                    f.write(f"Followers: {profile['Followers']}\n")
                    f.write(f"Following: {profile['Following']}\n")
                    f.write("-" * 30 + "\n")
        
        if high_posts_data:
            df_high = pd.DataFrame(high_posts_data)
            df_high.to_excel(high_posts_excel, index=False, engine='openpyxl')
            
            # Write high posts text file
            with open(high_posts_txt, 'w', encoding='utf-8') as f:
                f.write("Instagram Profiles with More than 5 Posts\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Total Profiles: {len(high_posts_data)}\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("-" * 50 + "\n\n")
                for profile in high_posts_data:
                    f.write(f"Username: {profile['Username']}\n")
                    f.write(f"Posts Count: {profile['Posts Count']}\n")
                    f.write(f"Full Name: {profile['Full Name']}\n")
                    f.write(f"Followers: {profile['Followers']}\n")
                    f.write(f"Following: {profile['Following']}\n")
                    f.write("-" * 30 + "\n")
        
        # Create main Excel file with all data
        df = pd.DataFrame(low_posts_data + high_posts_data)
        df.to_excel(main_excel, index=False, engine='openpyxl')
        
    except Exception as e:
        print(f"Error creating Excel files: {e}")

@app.route('/delete/<filename>')
def delete_file(filename):
    try:
        file_path = os.path.join('scraped_data', filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({'success': True, 'message': f'File {filename} deleted successfully'})
        else:
            return jsonify({'success': False, 'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/files')
def list_files():
    try:
        files = []
        for f in os.listdir('scraped_data'):
            if f.endswith(('.txt', '.xlsx')):
                file_path = os.path.join('scraped_data', f)
                file_stats = os.stat(file_path)
                files.append({
                    'name': f,
                    'type': 'Excel' if f.endswith('.xlsx') else 'Text',
                    'size': file_stats.st_size,
                    'created': datetime.fromtimestamp(file_stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                    'modified': datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
        files.sort(key=lambda x: x['modified'], reverse=True)  # Most recent first
        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'files': [], 'error': str(e)})

@app.route('/download/<filename>')
def download_file(filename):
    try:
        file_path = os.path.join('scraped_data', filename)
        if os.path.exists(file_path):
            return send_file(
                file_path,
                as_attachment=True,
                download_name=filename,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if filename.endswith('.xlsx') else 'text/plain'
            )
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'scraped_files': len([f for f in os.listdir('scraped_data') if f.endswith('.txt')])
    })

# Add cleanup function to remove old files
def cleanup_old_files(days=7):
    """Remove files older than specified days"""
    try:
        current_time = time.time()
        for filename in os.listdir('scraped_data'):
            file_path = os.path.join('scraped_data', filename)
            if os.path.isfile(file_path):
                file_time = os.path.getmtime(file_path)
                if (current_time - file_time) > (days * 86400):  # 86400 seconds in a day
                    os.remove(file_path)
                    print(f"Removed old file: {filename}")
    except Exception as e:
        print(f"Error during cleanup: {e}")

if __name__ == '__main__':
    print("🚀 Instagram Scraper Starting...")
    print("📋 Available at: http://0.0.0.0:5000")
    print("⚠️ Note: Instagram limits automated access - use responsibly!")
    app.run(host='0.0.0.0', port=5000, debug=True)
