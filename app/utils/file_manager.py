import os
import shutil
from datetime import datetime
from flask import current_app
from .security import sanitize_filename
import logging

logger = logging.getLogger(__name__)

def get_file_path(filename):
    """Get the full path of a file"""
    try:
        safe_filename = sanitize_filename(filename)
        return os.path.join(current_app.config['SCRAPED_DATA_DIR'], safe_filename)
    except Exception as e:
        logger.error(f"Error getting file path: {str(e)}")
        return None

def validate_file_access(filename):
    """Validate if a file can be accessed"""
    try:
        # Check if file exists
        file_path = get_file_path(filename)
        if not file_path or not os.path.exists(file_path):
            return False
        
        # Check if file is within allowed directory
        real_path = os.path.realpath(file_path)
        allowed_path = os.path.realpath(current_app.config['SCRAPED_DATA_DIR'])
        if not real_path.startswith(allowed_path):
            return False
        
        # Check file extension
        _, ext = os.path.splitext(filename)
        if ext.lower() not in current_app.config['ALLOWED_EXTENSIONS']:
            return False
        
        return True
    except Exception as e:
        logger.error(f"Error validating file access: {str(e)}")
        return False

def get_file_list():
    """Get list of files with metadata"""
    try:
        files = []
        for filename in os.listdir(current_app.config['SCRAPED_DATA_DIR']):
            if not filename.endswith(tuple(current_app.config['ALLOWED_EXTENSIONS'])):
                continue
            
            file_path = os.path.join(current_app.config['SCRAPED_DATA_DIR'], filename)
            try:
                stats = os.stat(file_path)
                files.append({
                    'name': filename,
                    'type': 'Excel' if filename.endswith('.xlsx') else 'Text',
                    'size': stats.st_size,
                    'created': datetime.fromtimestamp(stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                    'modified': datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
            except Exception as e:
                logger.error(f"Error getting stats for {filename}: {str(e)}")
                continue
        
        # Sort by modified date, newest first
        files.sort(key=lambda x: x['modified'], reverse=True)
        return files
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        return []

def delete_file(filename):
    """Delete a file"""
    try:
        if not validate_file_access(filename):
            return False, "Invalid file access"
        
        file_path = get_file_path(filename)
        if not file_path:
            return False, "File not found"
        
        os.remove(file_path)
        logger.info(f"Deleted file: {filename}")
        return True, f"File {filename} deleted successfully"
    except Exception as e:
        logger.error(f"Error deleting file: {str(e)}")
        return False, f"Error deleting file: {str(e)}"

def cleanup_old_files():
    """Remove files older than specified days"""
    try:
        current_time = datetime.now()
        max_age = current_app.config['MAX_FILE_AGE_DAYS']
        deleted_count = 0
        
        for filename in os.listdir(current_app.config['SCRAPED_DATA_DIR']):
            file_path = os.path.join(current_app.config['SCRAPED_DATA_DIR'], filename)
            if not os.path.isfile(file_path):
                continue
            
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            age_days = (current_time - file_time).days
            
            if age_days > max_age:
                try:
                    os.remove(file_path)
                    deleted_count += 1
                    logger.info(f"Removed old file: {filename}")
                except Exception as e:
                    logger.error(f"Error removing old file {filename}: {str(e)}")
        
        return deleted_count
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
        return 0

def create_backup(filename):
    """Create a backup of a file"""
    try:
        if not validate_file_access(filename):
            return False, "Invalid file access"
        
        file_path = get_file_path(filename)
        if not file_path:
            return False, "File not found"
        
        backup_dir = os.path.join(current_app.config['SCRAPED_DATA_DIR'], 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"{os.path.splitext(filename)[0]}_{timestamp}{os.path.splitext(filename)[1]}"
        backup_path = os.path.join(backup_dir, backup_filename)
        
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup: {backup_filename}")
        return True, f"Backup created: {backup_filename}"
    except Exception as e:
        logger.error(f"Error creating backup: {str(e)}")
        return False, f"Error creating backup: {str(e)}" 