from flask import render_template, request, jsonify, session, current_app
from app.main import bp
from app.utils.security import login_required, csrf_protect, validate_username
from app.utils.rate_limiter import rate_limit
from app.utils.metrics import track_metrics, track_scrape
from app import limiter
import logging

logger = logging.getLogger(__name__)

@bp.route('/')
@track_metrics('index')
def index():
    auth_status = session.get('instagram_authenticated', False)
    return render_template('index.html', authenticated=auth_status)

@bp.route('/scrape', methods=['POST'])
@login_required
@csrf_protect
@limiter.limit("50/hour")
@track_metrics('scrape')
def scrape_usernames():
    try:
        data = request.get_json()
        if not data or 'usernames' not in data:
            return jsonify({'error': 'No usernames provided'}), 400
        
        usernames = data.get('usernames', [])
        if not usernames:
            return jsonify({'error': 'Empty username list'}), 400
        
        # Validate usernames
        valid_usernames = []
        for username in usernames:
            if validate_username(username):
                valid_usernames.append(username)
            else:
                logger.warning(f"Invalid username format: {username}")
        
        if not valid_usernames:
            return jsonify({'error': 'No valid usernames provided'}), 400
        
        # Process usernames in background
        from app.tasks import process_scraping
        process_scraping.delay(valid_usernames)
        
        track_scrape('started')
        return jsonify({
            'message': f'Started scraping {len(valid_usernames)} username(s)',
            'status': 'processing',
            'usernames': valid_usernames
        })
        
    except Exception as e:
        logger.error(f"Error in scrape_usernames: {str(e)}")
        track_scrape('error')
        return jsonify({'error': 'Internal server error'}), 500

@bp.route('/files')
@login_required
@track_metrics('files')
def list_files():
    try:
        from app.utils.file_manager import get_file_list
        files = get_file_list()
        return jsonify({'files': files})
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        return jsonify({'error': 'Error listing files'}), 500

@bp.route('/download/<filename>')
@login_required
@track_metrics('download')
def download_file(filename):
    try:
        from app.utils.file_manager import get_file_path, validate_file_access
        if not validate_file_access(filename):
            return jsonify({'error': 'Invalid file access'}), 403
        
        file_path = get_file_path(filename)
        if not file_path:
            return jsonify({'error': 'File not found'}), 404
        
        from flask import send_file
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' 
            if filename.endswith('.xlsx') else 'text/plain'
        )
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        return jsonify({'error': 'Error downloading file'}), 500

@bp.route('/delete/<filename>')
@login_required
@csrf_protect
@track_metrics('delete')
def delete_file(filename):
    try:
        from app.utils.file_manager import delete_file as delete_file_util
        success, message = delete_file_util(filename)
        if success:
            return jsonify({'message': message})
        return jsonify({'error': message}), 400
    except Exception as e:
        logger.error(f"Error deleting file: {str(e)}")
        return jsonify({'error': 'Error deleting file'}), 500

@bp.route('/health')
@track_metrics('health')
def health_check():
    try:
        from app.utils.metrics import get_health_metrics
        metrics = get_health_metrics()
        return jsonify(metrics)
    except Exception as e:
        logger.error(f"Error in health check: {str(e)}")
        return jsonify({'status': 'error'}), 500 