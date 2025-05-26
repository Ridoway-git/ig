
from flask import Flask, render_template, request, jsonify, send_file
from instascrape import Profile, Post
import os
import json
from datetime import datetime
import threading
import time
import requests
from urllib.parse import urlparse

app = Flask(__name__)

# Create directories for storing data
os.makedirs('scraped_data', exist_ok=True)
os.makedirs('templates', exist_ok=True)

class InstagramScraper:
    def __init__(self):
        # Add session cookies to avoid Instagram login redirect
        self.session = requests.Session()
        # Basic headers to mimic a real browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
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
                    profile = Profile(profile_url)
                    
                    # Add session to profile for better authentication
                    if hasattr(profile, '_session'):
                        profile._session = self.session
                    
                    # Scrape the profile data
                    profile.scrape()
                    
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
                        'scraping_status': 'success'
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
                    
                    # Check if it's a rate limit error
                    if 'unauthorized' in error_msg.lower() or '401' in error_msg:
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
                    
                    # If it's the last attempt, return the error
                    if attempt == max_retries - 1:
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
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def scrape_usernames():
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
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'scraped_data/instagram_data_{timestamp}.txt'
    
    successful_scrapes = 0
    failed_scrapes = 0
    rate_limited = 0
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"Instagram Profile Data Scraping Results\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Powered by: insta-scrape library\n")
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
        f.write(f"⏰ Completed At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

@app.route('/files')
def list_files():
    try:
        files = [f for f in os.listdir('scraped_data') if f.endswith('.txt')]
        files.sort(reverse=True)  # Most recent first
        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'files': [], 'error': str(e)})

@app.route('/download/<filename>')
def download_file(filename):
    try:
        file_path = os.path.join('scraped_data', filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
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

if __name__ == '__main__':
    print("🚀 Instagram Scraper Starting...")
    print("📋 Available at: http://0.0.0.0:5000")
    print("⚠️ Note: Instagram limits automated access - use responsibly!")
    app.run(host='0.0.0.0', port=5000, debug=True)
