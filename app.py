from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_file, Response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import RequestTimeout
import os
import tempfile
from werkzeug.utils import secure_filename
from ingredient_scanner import scan_image_for_ingredients, before_scan_cleanup, safe_ocr_with_fallback_professional
import json
from datetime import datetime, timedelta
import uuid
import stripe
from PIL import Image
import time
import sqlite3
from functools import wraps
import psycopg2
from psycopg2.extras import RealDictCursor
import gc
import shutil
from pathlib import Path
import signal
import sys
import psutil

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Professional tier optimizations
app.config.update(
    MAX_CONTENT_LENGTH=15 * 1024 * 1024,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=4),
    REQUEST_TIMEOUT=180,
)

# Detect if running on professional tier
PROFESSIONAL_TIER = os.getenv('RENDER_TIER') == 'professional' or os.getenv('WEB_CONCURRENCY', '1') != '1'

if PROFESSIONAL_TIER:
    print("INFO: Professional tier - enabling large file support")
    app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024
    MAX_FILE_SIZE_MB = 12
else:
    print("INFO: Free tier - using conservative file limits")
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
    MAX_FILE_SIZE_MB = 3

# Stripe Configuration
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
DOMAIN = os.getenv('DOMAIN', 'https://foodfixr-scanner-1.onrender.com')

# Configuration
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.permanent_session_lifetime = timedelta(days=30)

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Request timeout tracking
@app.before_request
def before_request_timeout():
    request.start_time = time.time()
    try:
        gc.collect()
        Image.MAX_IMAGE_PIXELS = 30000000
        memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
        if memory_mb > 250:
            print(f"WARNING: High memory usage before request: {memory_mb:.1f}MB")
            gc.collect()
            time.sleep(0.1)
        print(f"DEBUG: Pre-request cleanup completed, memory: {memory_mb:.1f}MB")
    except Exception as e:
        print(f"DEBUG: Pre-request cleanup error: {e}")

@app.after_request
def after_request_cleanup(response):
    try:
        if hasattr(request, 'start_time'):
            processing_time = time.time() - request.start_time
            if processing_time > 60:
                print(f"WARNING: Long request took {processing_time:.1f}s for {request.endpoint}")
            elif processing_time > 30:
                print(f"INFO: Moderate request took {processing_time:.1f}s for {request.endpoint}")
        
        for _ in range(2):
            gc.collect()
        
        if response.status_code >= 500:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        
        try:
            memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
            if memory_mb > 300:
                print(f"WARNING: High memory after request: {memory_mb:.1f}MB")
        except:
            pass
    except Exception as e:
        print(f"DEBUG: After-request cleanup error: {e}")
    
    return response

# Database connection function
def get_db_connection():
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        return psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    else:
        import sqlite3
        conn = sqlite3.connect('foodfixr.db')
        conn.row_factory = sqlite3.Row
        return conn

# Database initialization
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_premium BOOLEAN DEFAULT FALSE,
            stripe_customer_id VARCHAR(255),
            subscription_status VARCHAR(50) DEFAULT 'trial',
            subscription_start_date TIMESTAMP,
            next_billing_date TIMESTAMP,
            trial_start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            trial_end_date TIMESTAMP,
            scans_used INTEGER DEFAULT 0,
            total_scans_ever INTEGER DEFAULT 0,
            last_login TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scan_history (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            result_rating TEXT,
            ingredients_found TEXT,
            image_url TEXT,
            scan_id VARCHAR(255),
            extracted_text TEXT,
            text_length INTEGER DEFAULT 0,
            confidence VARCHAR(20) DEFAULT 'medium',
            text_quality VARCHAR(20) DEFAULT 'unknown',
            has_safety_labels BOOLEAN DEFAULT FALSE
        )
    ''')
    
    try:
        cursor.execute("ALTER TABLE scan_history ADD COLUMN IF NOT EXISTS extracted_text TEXT")
        cursor.execute("ALTER TABLE scan_history ADD COLUMN IF NOT EXISTS text_length INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE scan_history ADD COLUMN IF NOT EXISTS confidence VARCHAR(20) DEFAULT 'medium'")
        cursor.execute("ALTER TABLE scan_history ADD COLUMN IF NOT EXISTS text_quality VARCHAR(20) DEFAULT 'unknown'")
        cursor.execute("ALTER TABLE scan_history ADD COLUMN IF NOT EXISTS has_safety_labels BOOLEAN DEFAULT FALSE")
    except Exception as e:
        print(f"Column addition note: {e}")
    
    conn.commit()
    conn.close()
    print("Database initialized successfully with all required columns")

init_db()

# Memory monitoring and worker restart handling
def setup_memory_monitoring():
    def memory_check():
        try:
            memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
            if memory_mb > 400:
                print(f"CRITICAL: Memory usage: {memory_mb:.1f}MB - forcing cleanup")
                gc.collect()
                return False
            return True
        except Exception as e:
            print(f"Memory check error: {e}")
            return True
    
    def signal_handler(signum, frame):
        print(f"Received signal {signum}, cleaning up...")
        gc.collect()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

setup_memory_monitoring()

# Helper functions
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_user_data(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def safe_datetime_parse(date_string):
    if not date_string:
        return datetime.now()
    
    if isinstance(date_string, datetime):
        return date_string
    
    formats = ['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']
    
    for fmt in formats:
        try:
            return datetime.strptime(date_string, fmt)
        except ValueError:
            continue
    
    try:
        clean_date = date_string.split('.')[0]
        return datetime.strptime(clean_date, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return datetime.now()

def calculate_trial_time_left(trial_start_date):
    trial_start = safe_datetime_parse(trial_start_date)
    trial_end = trial_start + timedelta(hours=48)
    now = datetime.now()
    
    if now >= trial_end:
        return "0h 0m", True, 0, 0
    
    time_left = trial_end - now
    hours = int(time_left.total_seconds() // 3600)
    minutes = int((time_left.total_seconds() % 3600) // 60)
    
    return f"{hours}h {minutes}m", False, hours, minutes

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def can_scan():
    if 'user_id' not in session:
        return False
        
    user_data = get_user_data(session['user_id'])
    if not user_data:
        return False
        
    if user_data['is_premium']:
        return True
    
    if user_data['scans_used'] >= 10:
        return False
        
    trial_start = safe_datetime_parse(user_data['trial_start_date'])
    trial_end = trial_start + timedelta(hours=48)
    if datetime.now() > trial_end:
        return False
        
    return True

def format_datetime_for_db(dt=None):
    if dt is None:
        dt = datetime.now()
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def cleanup_uploaded_file(filepath):
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
            print(f"DEBUG: Cleaned up uploaded file: {filepath}")
    except Exception as e:
        print(f"DEBUG: Error cleaning up file {filepath}: {e}")

def save_scan_image(temp_filepath, user_id):
    try:
        if not temp_filepath or not os.path.exists(temp_filepath):
            return None
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_extension = os.path.splitext(temp_filepath)[1].lower()
        new_filename = f"scan_{user_id}_{timestamp}_{uuid.uuid4().hex[:8]}{original_extension}"
        
        user_dir = os.path.join(UPLOADS_DIR, str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        
        permanent_path = os.path.join(user_dir, new_filename)
        shutil.copy2(temp_filepath, permanent_path)
        
        relative_path = f"static/uploads/{user_id}/{new_filename}"
        print(f"DEBUG: Saved image to: {relative_path}")
        
        return relative_path
        
    except Exception as e:
        print(f"DEBUG: Error saving scan image: {e}")
        return None

def with_timeout(seconds):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Request timed out after {seconds} seconds")
            
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
            
            try:
                result = func(*args, **kwargs)
                return result
            except TimeoutError:
                gc.collect()
                raise
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        
        return wrapper
    return decorator

# AUTHENTICATION ROUTES
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not all([name, email, password, confirm_password]):
            flash('All fields are required', 'error')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return render_template('register.html')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE email = %s', (email,))
        if cursor.fetchone():
            flash('An account with this email already exists. Please login instead.', 'error')
            conn.close()
            return render_template('register.html')
        
        password_hash = generate_password_hash(password)
        
        try:
            database_url = os.getenv('DATABASE_URL')
            if database_url:
                cursor.execute('''
                    INSERT INTO users (name, email, password_hash, trial_start_date, trial_end_date, last_login)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '48 hours', CURRENT_TIMESTAMP)
                    RETURNING id
                ''', (name, email, password_hash))
                
                user_result = cursor.fetchone()
                user_id = user_result['id']
            else:
                now = datetime.now()
                trial_start = format_datetime_for_db(now)
                trial_end = format_datetime_for_db(now + timedelta(hours=48))
                
                cursor.execute('''
                    INSERT INTO users (name, email, password_hash, trial_start_date, trial_end_date, last_login)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (name, email, password_hash, trial_start, trial_end, format_datetime_for_db(now)))
                
                user_id = cursor.lastrowid
            
            conn.commit()
            conn.close()
            
            session.clear()
            session.permanent = True
            session['user_id'] = user_id
            session['user_email'] = email
            session['user_name'] = name
            session['is_premium'] = False
            session['scans_used'] = 0
            session['stripe_customer_id'] = None
            
            return redirect('/')
            
        except Exception as e:
            print(f"Registration error: {e}")
            flash('Registration failed. Please try again.', 'error')
            conn.close()
            return render_template('register.html')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        if not email or not password:
            flash('Please enter both email and password', 'error')
            return render_template('login.html')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        else:
            cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        
        user = cursor.fetchone()
        
        if user:
            if check_password_hash(user['password_hash'], password):
                if database_url:
                    cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s', (user['id'],))
                else:
                    cursor.execute('UPDATE users SET last_login = ? WHERE id = ?', 
                                 (format_datetime_for_db(), user['id']))
                
                conn.commit()
                conn.close()
                
                session.clear()
                session.permanent = True
                session['user_id'] = user['id']
                session['user_email'] = user['email']
                session['user_name'] = user['name']
                session['is_premium'] = bool(user['is_premium'])
                session['scans_used'] = user['scans_used']
                session['stripe_customer_id'] = user['stripe_customer_id']
                
                return redirect('/')
            else:
                flash('Invalid email or password', 'error')
                conn.close()
        else:
            flash('Invalid email or password', 'error')
            if 'conn' in locals():
                conn.close()
    
    return render_template('login.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not all([email, new_password, confirm_password]):
            flash('All fields are required', 'error')
            return render_template('reset_password.html')
        
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('reset_password.html')
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return render_template('reset_password.html')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            database_url = os.getenv('DATABASE_URL')
            if database_url:
                cursor.execute('SELECT id, name FROM users WHERE email = %s', (email,))
            else:
                cursor.execute('SELECT id, name FROM users WHERE email = ?', (email,))
            
            user = cursor.fetchone()
            
            if not user:
                flash('No account found with this email address', 'error')
                conn.close()
                return render_template('reset_password.html')
            
            password_hash = generate_password_hash(new_password)
            
            if database_url:
                cursor.execute('UPDATE users SET password_hash = %s WHERE email = %s', 
                             (password_hash, email))
            else:
                cursor.execute('UPDATE users SET password_hash = ? WHERE email = ?', 
                             (password_hash, email))
            
            conn.commit()
            conn.close()
            
            flash(f'Password successfully reset for {user["name"]}! You can now login with your new password.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            print(f"Password reset error: {e}")
            flash('Password reset failed. Please try again.', 'error')
            return render_template('reset_password.html')
    
    return render_template('reset_password.html')

@app.route('/logout')
def logout():
    user_name = session.get('user_name', 'User')
    session.clear()
    flash(f'Goodbye {user_name}! You have been logged out.', 'info')
    return redirect(url_for('login'))

# MAIN APPLICATION ROUTES
@app.route('/')
@login_required
def index():
    user_data = get_user_data(session['user_id'])
    if not user_data:
        return redirect(url_for('logout'))
    
    trial_time_left, trial_expired, _, _ = calculate_trial_time_left(user_data['trial_start_date'])
    session['scans_used'] = user_data['scans_used']
    session['is_premium'] = bool(user_data['is_premium'])
    
    return render_template('scanner.html', 
                         trial_expired=trial_expired,
                         trial_time_left=trial_time_left,
                         user_name=user_data['name'],
                         stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)

@app.route('/', methods=['POST'])
@login_required
@with_timeout(90)
def scan():
    print("DEBUG: Starting scan with comprehensive error prevention")
    
    before_scan_cleanup()
    
    initial_memory = psutil.Process().memory_info().rss / 1024 / 1024
    print(f"DEBUG: Initial memory: {initial_memory:.1f}MB")
    
    if initial_memory > 250:
        print("DEBUG: High initial memory, forcing aggressive cleanup")
        gc.collect()
        time.sleep(0.5)
        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024
        print(f"DEBUG: Memory after cleanup: {initial_memory:.1f}MB")
    
    user_data = get_user_data(session['user_id'])
    if not user_data:
        return redirect(url_for('logout'))
    
    if not can_scan():
        flash('You have used all your free scans. Please upgrade to continue.', 'error')
        return redirect(url_for('upgrade'))
    
    trial_time_left, trial_expired, _, _ = calculate_trial_time_left(user_data['trial_start_date'])
    
    if 'image' not in request.files:
        return render_template('scanner.html',
                             trial_expired=trial_expired,
                             trial_time_left=trial_time_left,
                             user_name=user_data['name'],
                             error="No image uploaded.")
    
    file = request.files['image']
    if file.filename == '' or not allowed_file(file.filename):
        return render_template('scanner.html',
                             trial_expired=trial_expired,
                             trial_time_left=trial_time_left,
                             user_name=user_data['name'],
                             error="Invalid file. Please upload an image.")
    
    filepath = None
    try:
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        
        print(f"DEBUG: Saving uploaded file to: {filepath}")
        file.save(filepath)
        
        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        print(f"DEBUG: Uploaded file size: {file_size_mb:.2f} MB")
        
        max_size_mb = 10 if initial_memory > 200 else 12
        
        if file_size_mb > max_size_mb:
            cleanup_uploaded_file(filepath)
            return render_template('scanner.html',
                                 trial_expired=trial_expired,
                                 trial_time_left=trial_time_left,
                                 user_name=user_data['name'],
                                 error=f"Image too large ({file_size_mb:.1f}MB). Please upload a smaller image (max {max_size_mb}MB).")
        
        saved_image_path = save_scan_image(filepath, session['user_id'])
        
        print("DEBUG: Starting image processing with timeout protection...")
        
        try:
            result = scan_image_for_ingredients(filepath)
            
            if result.get('error'):
                cleanup_uploaded_file(filepath)
                error_msg = result['error']
                if 'memory' in error_msg.lower() or 'timeout' in error_msg.lower():
                    error_msg = "Processing failed due to resource constraints. Please try with a smaller, clearer image."
                
                return render_template('scanner.html',
                                     trial_expired=trial_expired,
                                     trial_time_left=trial_time_left,
                                     user_name=user_data['name'],
                                     error=error_msg)
            
        except TimeoutError:
            cleanup_uploaded_file(filepath)
            gc.collect()
            return render_template('scanner.html',
                                 trial_expired=trial_expired,
                                 trial_time_left=trial_time_left,
                                 user_name=user_data['name'],
                                 error="Scan timed out after 90 seconds. Please try with a smaller or clearer image.")
        
        except MemoryError:
            cleanup_uploaded_file(filepath)
            gc.collect()
            return render_template('scanner.html',
                                 trial_expired=trial_expired,
                                 trial_time_left=trial_time_left,
                                 user_name=user_data['name'],
                                 error="Out of memory. Please try with a much smaller image.")
        
        except Exception as e:
            cleanup_uploaded_file(filepath)
            gc.collect()
            print(f"DEBUG: Scan processing error: {e}")
            return render_template('scanner.html',
                                 trial_expired=trial_expired,
                                 trial_time_left=trial_time_left,
                                 user_name=user_data['name'],
                                 error="Processing failed. Please try again with a different image.")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        new_scans_used = user_data['scans_used'] + 1 if not user_data['is_premium'] else user_data['scans_used']
        new_total_scans = user_data['total_scans_ever'] + 1
        
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            cursor.execute('''
                UPDATE users 
                SET scans_used = %s, total_scans_ever = %s
                WHERE id = %s
            ''', (new_scans_used, new_total_scans, session['user_id']))
            
            cursor.execute('''
                INSERT INTO scan_history (
                    user_id, result_rating, ingredients_found, scan_date, scan_id,
                    extracted_text, text_length, confidence, text_quality, has_safety_labels, image_url
                )
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                session['user_id'], 
                result.get('rating', ''), 
                json.dumps(result.get('matched_ingredients', {})),
                str(uuid.uuid4()),
                result.get('extracted_text', '')[:1000],
                result.get('extracted_text_length', 0),
                result.get('confidence', 'medium'),
                result.get('text_quality', 'unknown'),
                result.get('has_safety_labels', False),
                saved_image_path
            ))
        else:
            cursor.execute('''
                UPDATE users 
                SET scans_used = ?, total_scans_ever = ?
                WHERE id = ?
            ''', (new_scans_used, new_total_scans, session['user_id']))
            
            cursor.execute('''
                INSERT INTO scan_history (
                    user_id, result_rating, ingredients_found, scan_date, scan_id,
                    extracted_text, text_length, confidence, text_quality, has_safety_labels, image_url
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session['user_id'], 
                result.get('rating', ''), 
                json.dumps(result.get('matched_ingredients', {})),
                format_datetime_for_db(),
                str(uuid.uuid4()),
                result.get('extracted_text', '')[:1000],
                result.get('extracted_text_length', 0),
                result.get('confidence', 'medium'),
                result.get('text_quality', 'unknown'),
                int(result.get('has_safety_labels', False)),
                saved_image_path
            ))
        
        conn.commit()
        conn.close()
        
        session['scans_used'] = new_scans_used
        
        cleanup_uploaded_file(filepath)
        
        final_memory = psutil.Process().memory_info().rss / 1024 / 1024
        print(f"DEBUG: Final memory after scan: {final_memory:.1f}MB")
        print("DEBUG: Scan completed successfully")
        
        return render_template('scanner.html',
                             result=result,
                             trial_expired=trial_expired,
                             trial_time_left=trial_time_left,
                             user_name=user_data['name'])
        
    except Exception as e:
        print(f"DEBUG: Critical scan error: {e}")
        import traceback
        traceback.print_exc()
        
        cleanup_uploaded_file(filepath)
        gc.collect()
        
        error_message = "Scanning failed. Please try again with a smaller, clearer image."
        if "memory" in str(e).lower():
            error_message = "Out of memory. Please try with a much smaller image."
        elif "timeout" in str(e).lower():
            error_message = "Scan timed out. Please try with a smaller image."
        
        return render_template('scanner.html',
                             trial_expired=trial_expired,
                             trial_time_left=trial_time_left,
                             user_name=user_data['name'],
                             error=error_message)
    
    finally:
        cleanup_uploaded_file(filepath)
        gc.collect()

@app.route('/account')
@login_required
def account():
    user_data = get_user_data(session['user_id'])
    if not user_data:
        return redirect(url_for('logout'))
    
    trial_time_left, trial_expired, trial_hours, trial_minutes = calculate_trial_time_left(user_data['trial_start_date'])
    
    trial_start = safe_datetime_parse(user_data['trial_start_date'])
    formatted_trial_start = trial_start.strftime('%B %d, %Y')
    
    return render_template('account.html',
                         user_name=user_data['name'],
                         user_created_date=formatted_created_date,
                         total_scans_ever=user_data['total_scans_ever'],
                         trial_start_date=formatted_trial_start,
                         trial_time_left=trial_time_left,
                         trial_expired=trial_expired,
                         trial_hours_left=trial_hours,
                         trial_minutes_left=trial_minutes)

@app.route('/history')
@login_required
def history():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            cursor.execute('''
                SELECT * FROM scan_history 
                WHERE user_id = %s 
                ORDER BY scan_date DESC 
                LIMIT 50
            ''', (session['user_id'],))
        else:
            cursor.execute('''
                SELECT * FROM scan_history 
                WHERE user_id = ? 
                ORDER BY scan_date DESC 
                LIMIT 50
            ''', (session['user_id'],))
        
        scans = []
        stats = {'total_scans': 0, 'safe_scans': 0, 'danger_scans': 0, 'ingredients_found': 0}
        
        for row in cursor.fetchall():
            scan_date = safe_datetime_parse(row['scan_date'])
            
            rating = row['result_rating'] or ''
            rating_type = 'retry'
            if 'Safe' in rating or 'Yay' in rating:
                rating_type = 'safe'
                stats['safe_scans'] += 1
            elif 'Danger' in rating or 'NOOOO' in rating:
                rating_type = 'danger'
                stats['danger_scans'] += 1
            elif 'Proceed' in rating or 'carefully' in rating:
                rating_type = 'caution'
            
            ingredients_data = {}
            try:
                if row['ingredients_found']:
                    if row['ingredients_found'].startswith('{'):
                        ingredients_data = json.loads(row['ingredients_found'])
                    else:
                        ingredients_data = eval(row['ingredients_found'])
            except:
                ingredients_data = {}
            
            ingredient_summary = {}
            detected_ingredients = []
            has_gmo = False
            has_chemstuffs = False
            
            if isinstance(ingredients_data, dict):
                for category, items in ingredients_data.items():
                    if isinstance(items, list) and items:
                        ingredient_summary[category] = len(items)
                        detected_ingredients.extend(items)
                        if category == 'gmo' and items:
                            has_gmo = True
                        elif category == 'chemstuffs' and items:
                            has_chemstuffs = True
                    elif category == 'all_detected' and isinstance(items, list):
                        detected_ingredients = items
                        
            detected_ingredients = list(set(detected_ingredients))
            stats['ingredients_found'] += len(detected_ingredients)
            
            scan_entry = {
                'scan_id': row['scan_id'],
                'date': scan_date.strftime("%m/%d/%Y"),
                'time': scan_date.strftime("%I:%M %p"),
                'rating_type': rating_type,
                'raw_rating': rating,
                'ingredient_summary': ingredient_summary,
                'detected_ingredients': detected_ingredients,
                'has_gmo': has_gmo,
                'has_chemstuffs': has_chemstuffs,
                'image_url': row.get('image_url', ''),
                'extracted_text': row.get('extracted_text', ''),
                'text_length': row.get('text_length', 0),
                'confidence': row.get('confidence', 'medium')
            }
            
            scans.append(scan_entry)
            stats['total_scans'] += 1
        
        conn.close()
        return render_template('history.html', scans=scans, stats=stats)
        
    except Exception as e:
        print(f"History error: {e}")
        import traceback
        traceback.print_exc()
        return render_template('history.html', scans=[], stats={'total_scans': 0, 'safe_scans': 0, 'danger_scans': 0, 'ingredients_found': 0})

@app.route('/upgrade')
@login_required
def upgrade():
    user_data = get_user_data(session['user_id'])
    trial_time_left, trial_expired, _, _ = calculate_trial_time_left(user_data['trial_start_date'])
    
    return render_template('upgrade.html',
                         trial_expired=trial_expired,
                         trial_time_left=trial_time_left,
                         stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)

@app.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    try:
        data = request.get_json()
        plan = data.get('plan', 'monthly')
        
        plan_price_mapping = {
            'weekly': os.getenv('STRIPE_WEEKLY_PRICE_ID', 'price_weekly_placeholder'),
            'monthly': os.getenv('STRIPE_MONTHLY_PRICE_ID', 'price_monthly_placeholder'), 
            'yearly': os.getenv('STRIPE_YEARLY_PRICE_ID', 'price_yearly_placeholder')
        }
        
        price_id = plan_price_mapping.get(plan)
        if not price_id:
            return jsonify({'error': 'Invalid plan selected'}), 400
        
        user_data = get_user_data(session['user_id'])
        if not user_data:
            return jsonify({'error': 'User not found'}), 404
        
        stripe_customer_id = user_data.get('stripe_customer_id')
        
        if not stripe_customer_id:
            customer = stripe.Customer.create(
                email=user_data['email'],
                name=user_data['name'],
                metadata={'user_id': str(user_data['id'])}
            )
            stripe_customer_id = customer.id
            
            conn = get_db_connection()
            cursor = conn.cursor()
            database_url = os.getenv('DATABASE_URL')
            if database_url:
                cursor.execute('UPDATE users SET stripe_customer_id = %s WHERE id = %s', 
                             (stripe_customer_id, user_data['id']))
            else:
                cursor.execute('UPDATE users SET stripe_customer_id = ? WHERE id = ?', 
                             (stripe_customer_id, user_data['id']))
            conn.commit()
            conn.close()
        
        checkout_session = stripe.checkout.Session.create(
            customer=stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=f"{DOMAIN}/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{DOMAIN}/upgrade?canceled=true",
            metadata={
                'user_id': str(user_data['id']),
                'user_email': user_data['email'],
                'plan': plan
            }
        )
        
        return jsonify({'checkout_url': checkout_session.url})
        
    except Exception as e:
        print(f"Stripe checkout error: {e}")
        return jsonify({'error': f'Failed to create checkout session: {str(e)}'}), 500

@app.route('/payment-success')
@login_required
def payment_success():
    session_id = request.args.get('session_id')
    
    if not session_id:
        flash('Invalid payment session', 'error')
        return redirect(url_for('upgrade'))
    
    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        
        if checkout_session.payment_status == 'paid':
            conn = get_db_connection()
            cursor = conn.cursor()
            
            database_url = os.getenv('DATABASE_URL')
            if database_url:
                cursor.execute('''
                    UPDATE users 
                    SET is_premium = TRUE, 
                        subscription_status = 'active',
                        subscription_start_date = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (session['user_id'],))
            else:
                cursor.execute('''
                    UPDATE users 
                    SET is_premium = 1, 
                        subscription_status = 'active',
                        subscription_start_date = ?
                    WHERE id = ?
                ''', (format_datetime_for_db(), session['user_id']))
            
            conn.commit()
            conn.close()
            
            session['is_premium'] = True
            
            flash('🎉 Welcome to FoodFixr Premium! Enjoy unlimited scans!', 'success')
            return redirect('/')
        else:
            flash('Payment was not completed successfully', 'error')
            return redirect(url_for('upgrade'))
            
    except Exception as e:
        print(f"Payment success error: {e}")
        flash('Error processing payment confirmation', 'error')
        return redirect(url_for('upgrade'))

@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError as e:
        print(f"Invalid payload: {e}")
        return '', 400
    except stripe.error.SignatureVerificationError as e:
        print(f"Invalid signature: {e}")
        return '', 400
    
    if event['type'] == 'checkout.session.completed':
        session_data = event['data']['object']
        user_id = session_data['metadata'].get('user_id')
        
        if user_id:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                database_url = os.getenv('DATABASE_URL')
                if database_url:
                    cursor.execute('''
                        UPDATE users 
                        SET is_premium = TRUE, 
                            subscription_status = 'active',
                            subscription_start_date = CURRENT_TIMESTAMP
                        WHERE id = %s
                    ''', (user_id,))
                else:
                    cursor.execute('''
                        UPDATE users 
                        SET is_premium = 1, 
                            subscription_status = 'active',
                            subscription_start_date = ?
                        WHERE id = ?
                    ''', (format_datetime_for_db(), user_id))
                
                conn.commit()
                conn.close()
                print(f"User {user_id} upgraded to premium via webhook")
                
            except Exception as e:
                print(f"Webhook database error: {e}")
    
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription['customer']
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            database_url = os.getenv('DATABASE_URL')
            if database_url:
                cursor.execute('''
                    UPDATE users 
                    SET is_premium = FALSE, 
                        subscription_status = 'canceled'
                    WHERE stripe_customer_id = %s
                ''', (customer_id,))
            else:
                cursor.execute('''
                    UPDATE users 
                    SET is_premium = 0, 
                        subscription_status = 'canceled'
                    WHERE stripe_customer_id = ?
                ''', (customer_id,))
            
            conn.commit()
            conn.close()
            print(f"Subscription canceled for customer {customer_id}")
            
        except Exception as e:
            print(f"Webhook cancellation error: {e}")
    
    return '', 200

@app.route('/clear-history', methods=['POST'])
@login_required
def clear_history():
    try:
        user_data = get_user_data(session['user_id'])
        if not user_data or not user_data['is_premium']:
            return jsonify({'success': False, 'error': 'Premium required'}), 403
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        user_upload_dir = os.path.join(UPLOADS_DIR, str(session['user_id']))
        if os.path.exists(user_upload_dir):
            shutil.rmtree(user_upload_dir)
            print(f"DEBUG: Deleted user images directory: {user_upload_dir}")
        
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            cursor.execute('DELETE FROM scan_history WHERE user_id = %s', (session['user_id'],))
        else:
            cursor.execute('DELETE FROM scan_history WHERE user_id = ?', (session['user_id'],))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Clear history error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/export-history')
@login_required
def export_history():
    try:
        user_data = get_user_data(session['user_id'])
        if not user_data or not user_data['is_premium']:
            flash('Premium subscription required for export feature', 'error')
            return redirect(url_for('history'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            cursor.execute('SELECT * FROM scan_history WHERE user_id = %s ORDER BY scan_date DESC', (session['user_id'],))
        else:
            cursor.execute('SELECT * FROM scan_history WHERE user_id = ? ORDER BY scan_date DESC', (session['user_id'],))
        
        scans_data = []
        for row in cursor.fetchall():
            ingredients_data = {}
            try:
                if row['ingredients_found']:
                    if row['ingredients_found'].startswith('{'):
                        ingredients_data = json.loads(row['ingredients_found'])
                    else:
                        ingredients_data = eval(row['ingredients_found'])
            except:
                ingredients_data = {}
            
            scan_data = {
                'scan_id': row['scan_id'],
                'scan_date': str(row['scan_date']),
                'result_rating': row['result_rating'],
                'ingredients_found': ingredients_data,
                'extracted_text': row.get('extracted_text', ''),
                'confidence': row.get('confidence', 'unknown'),
                'text_quality': row.get('text_quality', 'unknown'),
                'has_chemstuffs': bool(ingredients_data.get('chemstuffs', [])),
                'has_gmo': bool(ingredients_data.get('gmo', []))
            }
            scans_data.append(scan_data)
        
        conn.close()
        
        export_data = {
            'user_email': session['user_email'],
            'export_date': datetime.now().isoformat(),
            'total_scans': len(scans_data),
            'scans': scans_data,
            'includes_chemstuffs_data': True
        }
        
        response = Response(
            json.dumps(export_data, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename=foodfixr_history_{session["user_email"]}_{datetime.now().strftime("%Y%m%d")}.json'}
        )
        
        return response
        
    except Exception as e:
        print(f"Export history error: {e}")
        flash('Export failed. Please try again.', 'error')
        return redirect(url_for('history'))

@app.route('/static/uploads/<int:user_id>/<filename>')
@login_required
def uploaded_file(user_id, filename):
    if session['user_id'] != user_id:
        return "Access denied", 403
        
    user_upload_dir = os.path.join(UPLOADS_DIR, str(user_id))
    return send_file(os.path.join(user_upload_dir, filename))

@app.route('/health')
def health_check():
    try:
        start_time = time.time()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        conn.close()
        
        memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
        
        if memory_mb > 350:
            print(f"HEALTH CHECK: Critical memory level {memory_mb:.1f}MB, forcing cleanup")
            gc.collect()
            time.sleep(0.1)
            memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
        
        response_time = (time.time() - start_time) * 1000
        
        status = 'healthy'
        http_code = 200
        
        if memory_mb > 400:
            status = 'critical_memory'
            http_code = 503
        elif response_time > 1000:
            status = 'slow_response'
            http_code = 503
        elif memory_mb > 300:
            status = 'high_memory'
        
        return jsonify({
            'status': status,
            'memory_mb': round(memory_mb, 1),
            'response_time_ms': round(response_time, 1),
            'timestamp': datetime.now().isoformat(),
            'database': 'connected',
            'chemstuffs_enabled': True
        }), http_code
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503

@app.errorhandler(413)
def too_large(e):
    gc.collect()
    return render_template('error.html', 
                         error_title="File Too Large", 
                         error_message="The uploaded image is too large. Please upload an image smaller than 5MB."), 413

@app.errorhandler(500)
def internal_error(e):
    gc.collect()
    return render_template('error.html', 
                         error_title="Internal Server Error", 
                         error_message="Something went wrong. Please try again with a smaller image."), 500

@app.errorhandler(TimeoutError)
def timeout_error(e):
    gc.collect()
    return render_template('error.html',
                         error_title="Request Timeout",
                         error_message="The request took too long to process. Please try with a smaller image."), 504

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print("WARNING: Running with Flask development server. Use Gunicorn for production!")
    print("✅ ChemStuffs category fully integrated and ready!")
    app.run(host="0.0.0.0", port=port, debug=False)
