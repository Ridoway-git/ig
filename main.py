
from flask import Flask, render_template, request, jsonify, send_file
import instaloader
import os
import json
from datetime import datetime
import threading
import time

app = Flask(__name__)

# Create directories for storing data
os.makedirs('scraped_data', exist_ok=True)
os.makedirs('templates', exist_ok=True)

class InstagramScraper:
    def __init__(self):
        self.loader = instaloader.Instaloader()
        # Disable downloading of videos, photos to save space
        self.loader.download_videos = False
        self.loader.download_video_thumbnails = False
        self.loader.download_geotags = False
        self.loader.download_comments = False
        self.loader.save_metadata = False
    
    def scrape_profile(self, username):
        try:
            profile = instaloader.Profile.from_username(self.loader.context, username)
            
            profile_data = {
                'username': profile.username,
                'full_name': profile.full_name,
                'biography': profile.biography,
                'followers': profile.followers,
                'followees': profile.followees,
                'posts_count': profile.mediacount,
                'is_verified': profile.is_verified,
                'is_private': profile.is_private,
                'external_url': profile.external_url,
                'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Get recent posts data
            posts_data = []
            post_count = 0
            for post in profile.get_posts():
                if post_count >= 10:  # Limit to 10 recent posts
                    break
                
                post_info = {
                    'shortcode': post.shortcode,
                    'date': post.date.strftime('%Y-%m-%d %H:%M:%S'),
                    'caption': post.caption,
                    'likes': post.likes,
                    'comments': post.comments,
                    'is_video': post.is_video,
                    'url': f"https://www.instagram.com/p/{post.shortcode}/"
                }
                posts_data.append(post_info)
                post_count += 1
            
            profile_data['recent_posts'] = posts_data
            return profile_data
            
        except Exception as e:
            return {'error': f'Failed to scrape {username}: {str(e)}'}

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
    
    # Process usernames in background thread
    thread = threading.Thread(target=process_scraping, args=(usernames,))
    thread.start()
    
    return jsonify({'message': f'Started scraping {len(usernames)} username(s)', 'status': 'processing'})

def process_scraping(usernames):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'scraped_data/instagram_data_{timestamp}.txt'
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"Instagram Scraping Results - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        for username in usernames:
            f.write(f"PROFILE: @{username}\n")
            f.write("-" * 40 + "\n")
            
            profile_data = scraper.scrape_profile(username)
            
            if 'error' in profile_data:
                f.write(f"ERROR: {profile_data['error']}\n\n")
                continue
            
            # Write profile information
            f.write(f"Full Name: {profile_data.get('full_name', 'N/A')}\n")
            f.write(f"Biography: {profile_data.get('biography', 'N/A')}\n")
            f.write(f"Followers: {profile_data.get('followers', 0):,}\n")
            f.write(f"Following: {profile_data.get('followees', 0):,}\n")
            f.write(f"Posts Count: {profile_data.get('posts_count', 0):,}\n")
            f.write(f"Verified: {'Yes' if profile_data.get('is_verified') else 'No'}\n")
            f.write(f"Private: {'Yes' if profile_data.get('is_private') else 'No'}\n")
            f.write(f"External URL: {profile_data.get('external_url', 'N/A')}\n")
            f.write(f"Scraped At: {profile_data.get('scraped_at')}\n\n")
            
            # Write recent posts
            if profile_data.get('recent_posts'):
                f.write("RECENT POSTS:\n")
                for i, post in enumerate(profile_data['recent_posts'], 1):
                    f.write(f"  Post {i}:\n")
                    f.write(f"    Date: {post.get('date')}\n")
                    f.write(f"    Likes: {post.get('likes', 0):,}\n")
                    f.write(f"    Comments: {post.get('comments', 0):,}\n")
                    f.write(f"    Type: {'Video' if post.get('is_video') else 'Photo'}\n")
                    f.write(f"    URL: {post.get('url')}\n")
                    if post.get('caption'):
                        caption = post['caption'][:200] + '...' if len(post['caption']) > 200 else post['caption']
                        f.write(f"    Caption: {caption}\n")
                    f.write("\n")
            
            f.write("\n" + "=" * 80 + "\n\n")
            
            # Add delay to avoid rate limiting
            time.sleep(2)

@app.route('/files')
def list_files():
    files = [f for f in os.listdir('scraped_data') if f.endswith('.txt')]
    files.sort(reverse=True)  # Most recent first
    return jsonify({'files': files})

@app.route('/download/<filename>')
def download_file(filename):
    try:
        return send_file(f'scraped_data/{filename}', as_attachment=True)
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
