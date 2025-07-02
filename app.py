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
import gc  # Add for memory management
import shutil
from pathlib import Path
import signal
import sys
import psutil

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Professional tier optimizations
app.config.update(
    # Can handle larger files now
    MAX_CONTENT_LENGTH=15 * 1024 * 1024,  # 15MB (was 5MB)
    
    # Less aggressive session timeout
    PERMANENT_SESSION_LIFETIME=timedelta(hours=4),  # 4 hours (was 1 hour)
    
    # Professional tier request timeout
    REQUEST_TIMEOUT=180,  # 3 minutes (was 90 seconds)
)

# Detect if running on professional tier
PROFESSIONAL_TIER = os.getenv('RENDER_TIER') == 'professional' or os.getenv('WEB_CONCURRENCY', '1') != '1'

if PROFESSIONAL_TIER:
    print("INFO: Professional tier - enabling large file support")
    app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024  # 15MB
    MAX_FILE_SIZE_MB = 12  # 12MB processing limit
else:
    print("INFO: Free tier - using conservative file limits")
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024   # 5MB
    MAX_FILE_SIZE_MB = 3   # 3MB processing limit

# Stripe Configuration
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
DOMAIN = os.getenv('DOMAIN', 'https://foodfixr-scanner-1.onrender.com')

# Configuration - Reduced limits for memory-constrained environments
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.permanent_session_lifetime = timedelta(days=30)

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Request timeout tracking
@app.before_request
def before_request_timeout():
    """Track request start time and perform memory management"""
    request.start_time = time.time()
    
    try:
        # Force garbage collection
        gc.collect()
        
        # Set conservative PIL limits
        Image.MAX_IMAGE_PIXELS = 30000000  # More conservative limit
        
        # Check memory usage
        memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
        if memory_mb > 250:  # High memory threshold
            print(f"WARNING: High memory usage before request: {memory_mb:.1f}MB")
            gc.collect()
            time.sleep(0.1)  # Brief pause for cleanup
        
        print(f"DEBUG: Pre-request cleanup completed, memory: {memory_mb:.1f}MB")
    except Exception as e:
        print(f"DEBUG: Pre-request cleanup error: {e}")

@app.after_request
def after_request_cleanup(response):
    """Comprehensive cleanup after each request with timeout monitoring"""
    try:
        # Check processing time and log warnings
        if hasattr(request, 'start_time'):
            processing_time = time.time() - request.start_time
            if processing_time > 60:  # Log long requests
                print(f"WARNING: Long request took {processing_time:.1f}s for {request.endpoint}")
            elif processing_time > 30:
                print(f"INFO: Moderate request took {processing_time:.1f}s for {request.endpoint}")
        
        # Force aggressive garbage collection
        for _ in range(2):
            gc.collect()
        
        # Add headers to prevent caching of errors
        if response.status_code >= 500:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        
        # Log final memory usage
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
    """Get database connection - PostgreSQL for production, SQLite for local"""
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        return psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    else:
        # Fallback to SQLite for local development
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
    
    # Add missing columns to existing table (PostgreSQL specific)
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
    """Setup memory monitoring and graceful shutdown"""
    def memory_check():
        try:
            memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
            if memory_mb > 400:  # Critical threshold
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
    """Safely clean up uploaded files"""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
            print(f"DEBUG: Cleaned up uploaded file: {filepath}")
    except Exception as e:
        print(f"DEBUG: Error cleaning up file {filepath}: {e}")

def save_scan_image(temp_filepath, user_id):
    """Save uploaded image permanently for history viewing"""
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

# CRITICAL: Add request timeout wrapper
def with_timeout(seconds):
    """Decorator to add timeout protection to routes"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Request timed out after {seconds} seconds")
            
            # Set the alarm
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
            
            try:
                result = func(*args, **kwargs)
                return result
            except TimeoutError:
                gc.collect()  # Force cleanup on timeout
                raise
            finally:
                # Always restore the alarm
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
    print(f"DEBUG: Login route called with method: {request.method}")
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        print(f"DEBUG: Login attempt for email: {email}")
        
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
            print(f"DEBUG: User found: {user['name']}")
            if check_password_hash(user['password_hash'], password):
                print("DEBUG: Password correct, logging in...")
                
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
                
                print("DEBUG: Session set, redirecting to scanner...")
                return redirect('/')
            else:
                print("DEBUG: Invalid password")
                flash('Invalid email or password', 'error')
                conn.close()
        else:
            print("DEBUG: User not found")
            flash('Invalid email or password', 'error')
            if 'conn' in locals():
                conn.close()
    
    print("DEBUG: Rendering login.html template")
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
@with_timeout(90)  # 90 second timeout protection
def scan():
    """Enhanced scan route with comprehensive 502 error prevention"""
    print("DEBUG: Starting scan with comprehensive error prevention")
    
    # CRITICAL: Memory cleanup before processing
    before_scan_cleanup()
    
    # Check initial memory state
    initial_memory = psutil.Process().memory_info().rss / 1024 / 1024
    print(f"DEBUG: Initial memory: {initial_memory:.1f}MB")
    
    if initial_memory > 250:  # High initial memory
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
        # Save uploaded file with memory-conscious handling
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        
        print(f"DEBUG: Saving uploaded file to: {filepath}")
        file.save(filepath)
        
        # Check file size before processing - be more restrictive
        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        print(f"DEBUG: Uploaded file size: {file_size_mb:.2f} MB")
        
        # Dynamic file size limits based on current memory
        max_size_mb = 10 if initial_memory > 200 else 12 # Very restrictive
        
        if file_size_mb > max_size_mb:
            cleanup_uploaded_file(filepath)
            return render_template('scanner.html',
                                 trial_expired=trial_expired,
                                 trial_time_left=trial_time_left,
                                 user_name=user_data['name'],
                                 error=f"Image too large ({file_size_mb:.1f}MB). Please upload a smaller image (max {max_size_mb}MB).")
        
        # Save image permanently for history (before processing to avoid memory issues)
        saved_image_path = save_scan_image(filepath, session['user_id'])
        
        # Process the image with enhanced memory management
        print("DEBUG: Starting image processing with timeout protection...")
        
        try:
            # Use the safe OCR function with circuit breaker
            result = scan_image_for_ingredients(filepath)
            
            # Check if scan failed due to memory/timeout issues
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
        
        # Update user scan counts
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
        
        # Clean up temp uploaded file
        cleanup_uploaded_file(filepath)
        
        # Final memory check
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
        
        # Clean up uploaded file on error
        cleanup_uploaded_file(filepath)
        
        # Force memory cleanup on error
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
        # Always ensure cleanup
        cleanup_uploaded_file(filepath)
        gc.collect()

@app.route('/account')
@login_required
def account():
    user_data = get_user_data(session['user_id'])
    if not user_data:
        return redirect(url_for('logout'))
    
    trial_time_left, trial_expired, trial_hours, trial_minutes = calculate_trial_time_left(user_data['trial_start_date'])
    
    created_date = safe_datetime_parse(user_data['created_at'])
    formatted_created_date = created_date.strftime('%B %d, %Y')
    
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
            has_chemstuffs = False  # NEW
            
            if isinstance(ingredients_data, dict):
                for category, items in ingredients_data.items():
                    if isinstance(items, list) and items:
                        ingredient_summary[category] = len(items)
                        detected_ingredients.extend(items)
                        if category == 'gmo' and items:
                            has_gmo = True
                        elif category == 'chemstuffs' and items:  # NEW
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
                'has_chemstuffs': has_chemstuffs,  # NEW
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

# STRIPE PAYMENT PROCESSING ROUTES
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

# CLEAR HISTORY ROUTE
@app.route('/clear-history', methods=['POST'])
@login_required
def clear_history():
    """Clear user's scan history (Premium feature)"""
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
        
# EXPORT HISTORY ROUTE
@app.route('/export-history')
@login_required
def export_history():
    """Export user's scan history as JSON (Premium feature)"""
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
            scan_data = {
                'scan_id': row['scan_id'],
                'scan_date': str(row['scan_date']),
                'result_rating': row['result_rating'],
                'ingredients_found': row['ingredients_found'],
                'extracted_text': row.get('extracted_text', ''),
                'confidence': row.get('confidence', 'unknown'),
                'text_quality': row.get('text_quality', 'unknown')
            }
            scans_data.append(scan_data)
        
        conn.close()
        
        export_data = {
            'user_email': session['user_email'],
            'export_date': datetime.now().isoformat(),
            'total_scans': len(scans_data),
            'scans': scans_data
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
    """Serve uploaded images (only to the user who uploaded them)"""
    if session['user_id'] != user_id:
        return "Access denied", 403
        
    user_upload_dir = os.path.join(UPLOADS_DIR, str(user_id))
    return send_file(os.path.join(user_upload_dir, filename))

# CRITICAL: Health check endpoint for load balancer
@app.route('/health')
def health_check():
    """Enhanced health check endpoint for load balancer and monitoring"""
    try:
        start_time = time.time()
        
        # Quick database check
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        conn.close()
        
        # Memory check with automatic cleanup
        memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
        
        if memory_mb > 350:  # Critical memory level
            print(f"HEALTH CHECK: Critical memory level {memory_mb:.1f}MB, forcing cleanup")
            gc.collect()
            time.sleep(0.1)
            memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
        
        # Check response time
        response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        # Determine health status
        status = 'healthy'
        http_code = 200
        
        if memory_mb > 400:
            status = 'critical_memory'
            http_code = 503
        elif response_time > 1000:  # 1 second
            status = 'slow_response'
            http_code = 503
        elif memory_mb > 300:
            status = 'high_memory'
        
        return jsonify({
            'status': status,
            'memory_mb': round(memory_mb, 1),
            'response_time_ms': round(response_time, 1),
            'timestamp': datetime.now().isoformat(),
            'database': 'connected'
        }), http_code
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503

# ADMIN/DEBUG ROUTES
@app.route('/test-upgrade-user', methods=['GET', 'POST'])
@login_required
def test_upgrade_user():
    """Test route to upgrade current user to premium without Stripe"""
    if request.method == 'POST':
        plan = request.form.get('plan', 'monthly')
        
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
            
            success_msg = f"✅ Test upgrade successful! You are now Premium ({plan} plan)"
            
        except Exception as e:
            success_msg = f"❌ Test upgrade failed: {str(e)}"
    else:
        success_msg = None
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Upgrade User</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: Arial; padding: 20px; background: #f5f5f5; margin: 0; }}
            .container {{ max-width: 500px; margin: 50px auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            h1 {{ color: #e91e63; text-align: center; margin-bottom: 30px; }}
            .form-group {{ margin-bottom: 20px; }}
            label {{ display: block; margin-bottom: 8px; font-weight: bold; color: #333; }}
            select {{ width: 100%%; padding: 12px; border: 2px solid #ddd; border-radius: 8px; box-sizing: border-box; font-size: 16px; }}
            .btn {{ padding: 12px 24px; margin: 10px 5px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold; }}
            .btn-primary {{ background: #e91e63; color: white; }}
            .btn-secondary {{ background: #666; color: white; }}
            .btn:hover {{ opacity: 0.9; transform: translateY(-1px); }}
            .success {{ background: #d4edda; color: #155724; padding: 15px; border-radius: 8px; margin: 15px 0; border: 1px solid #4CAF50; }}
            .info {{ background: #d1ecf1; color: #0c5460; padding: 15px; border-radius: 8px; margin: 15px 0; border: 1px solid #17a2b8; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🧪 Test User Upgrade</h1>
            
            <div class="info">
                <strong>ℹ️ Debug Tool:</strong> This bypasses Stripe and directly upgrades the current user to Premium.
                <br><strong>Current User:</strong> {session.get('user_name', 'Unknown')} ({session.get('user_email', 'Unknown')})
                <br><strong>Premium Status:</strong> {'✅ Premium' if session.get('is_premium') else '❌ Trial'}
            </div>
            
            {'<div class="success">' + success_msg + '</div>' if success_msg else ''}
            
            <form method="POST">
                <div class="form-group">
                    <label for="plan">Select Plan:</label>
                    <select id="plan" name="plan" required>
                        <option value="weekly">Weekly ($3.99/week)</option>
                        <option value="monthly" selected>Monthly ($11.99/month)</option>
                        <option value="yearly">Yearly ($95.00/year)</option>
                    </select>
                </div>
                
                <div style="text-align: center; margin-top: 30px;">
                    <button type="submit" class="btn btn-primary">🚀 Test Upgrade to Premium</button>
                    <a href="/upgrade" class="btn btn-secondary">💳 Real Stripe Upgrade</a>
                    <a href="/" class="btn btn-secondary">🏠 Back to Scanner</a>
                </div>
            </form>
        </div>
    </body>
    </html>
    """

@app.route('/simple-login', methods=['GET', 'POST'])
def simple_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        if not email or not password:
            error_msg = "Please enter both email and password"
        else:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                database_url = os.getenv('DATABASE_URL')
                if database_url:
                    cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
                else:
                    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
                
                user = cursor.fetchone()
                
                if user and check_password_hash(user['password_hash'], password):
                    session.clear()
                    session.permanent = True
                    session['user_id'] = user['id']
                    session['user_email'] = user['email']
                    session['user_name'] = user['name']
                    session['is_premium'] = bool(user['is_premium'])
                    session['scans_used'] = user['scans_used']
                    session['stripe_customer_id'] = user['stripe_customer_id']
                    
                    conn.close()
                    return redirect('/')
                else:
                    error_msg = "Invalid email or password"
                    
                conn.close()
            except Exception as e:
                error_msg = f"Login error: {str(e)}"
    else:
        error_msg = None
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>FoodFixr Login</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
    </head>
    <body style="font-family: Arial; padding: 20px; background: #f5f5f5; margin: 0;">
        <div style="max-width: 400px; margin: 50px auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <h1 style="text-align: center; color: #e91e63; margin-bottom: 30px;">🍎 FoodFixr Login</h1>
            
            {'<div style="background: #ffebee; color: #c62828; padding: 10px; border-radius: 5px; margin-bottom: 20px; text-align: center;">' + error_msg + '</div>' if error_msg else ''}
            
            <form method="POST" action="/simple-login">
                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold;">Email:</label>
                    <input type="email" name="email" required style="width: 100%%; padding: 12px; border: 2px solid #ddd; border-radius: 5px; box-sizing: border-box;">
                </div>
                
                <div style="margin-bottom: 25px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold;">Password:</label>
                    <input type="password" name="password" required style="width: 100%%; padding: 12px; border: 2px solid #ddd; border-radius: 5px; box-sizing: border-box;">
                </div>
                
                <button type="submit" style="width: 100%%; padding: 15px; background: #e91e63; color: white; border: none; border-radius: 5px; font-size: 16px; cursor: pointer;">
                    Login
                </button>
            </form>
            
            <div style="text-align: center; margin-top: 25px;">
                <a href="/admin-password-reset" style="background: #ff9800; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px; display: inline-block;">Reset Individual Password</a>
                <a href="/check-users" style="background: #2196F3; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px; display: inline-block;">Manage Users</a>
                <a href="/test-upgrade-user" style="background: #4CAF50; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px; display: inline-block;">Test Upgrade</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/admin-password-reset', methods=['GET', 'POST'])
def admin_password_reset():
    """Admin route to reset individual user passwords"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        new_password = request.form.get('new_password', '')
        
        if not email or not new_password:
            error_msg = "Both email and password are required"
        elif len(new_password) < 6:
            error_msg = "Password must be at least 6 characters long"
        else:
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
                    error_msg = f"No user found with email: {email}"
                else:
                    password_hash = generate_password_hash(new_password)
                    
                    if database_url:
                        cursor.execute('UPDATE users SET password_hash = %s WHERE email = %s', 
                                     (password_hash, email))
                    else:
                        cursor.execute('UPDATE users SET password_hash = ? WHERE email = ?', 
                                     (password_hash, email))
                    
                    conn.commit()
                    success_msg = f"Password updated for {user['name']} ({email})"
                
                conn.close()
                
            except Exception as e:
                error_msg = f"Database error: {str(e)}"
    else:
        error_msg = None
        success_msg = None
    
    # Get all users for the dropdown
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT email, name FROM users ORDER BY name')
        users = cursor.fetchall()
        conn.close()
    except:
        users = []
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Password Reset</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: Arial; padding: 20px; background: #f5f5f5; margin: 0; }}
            .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            h1 {{ color: #e91e63; text-align: center; margin-bottom: 30px; }}
            .form-group {{ margin-bottom: 20px; }}
            label {{ display: block; margin-bottom: 8px; font-weight: bold; color: #333; }}
            input, select {{ width: 100%%; padding: 12px; border: 2px solid #ddd; border-radius: 8px; box-sizing: border-box; font-size: 16px; }}
            input:focus, select:focus {{ border-color: #e91e63; outline: none; }}
            .btn {{ padding: 12px 24px; margin: 10px 5px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold; }}
            .btn-primary {{ background: #e91e63; color: white; }}
            .btn-secondary {{ background: #666; color: white; }}
            .btn:hover {{ opacity: 0.9; transform: translateY(-1px); }}
            .success {{ background: #d4edda; color: #155724; padding: 15px; border-radius: 8px; margin: 15px 0; border: 1px solid #4CAF50; }}
            .error {{ background: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; margin: 15px 0; border: 1px solid #f44336; }}
            .user-list {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }}
            .user-item {{ padding: 8px; border-bottom: 1px solid #ddd; }}
            .quick-fill {{ font-size: 12px; color: #666; margin-top: 5px; }}
            .quick-fill button {{ background: #f0f0f0; border: 1px solid #ccc; padding: 4px 8px; margin: 2px; border-radius: 4px; cursor: pointer; font-size: 11px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Admin Password Reset</h1>
            
            {'<div class="success">' + success_msg + '</div>' if 'success_msg' in locals() and success_msg else ''}
            {'<div class="error">' + error_msg + '</div>' if 'error_msg' in locals() and error_msg else ''}
            
            <form method="POST">
                <div class="form-group">
                    <label for="email">Select User Email:</label>
                    <select id="email" name="email" onchange="fillEmail(this.value)" required>
                        <option value="">-- Select a user --</option>
                        {''.join([f'<option value="{user[0]}">{user[1]} ({user[0]})</option>' for user in users])}
                    </select>
                    <div class="quick-fill">
                        Or type manually: 
                        <input type="email" id="manual_email" placeholder="user@example.com" onchange="document.getElementById('email').value = this.value">
                    </div>
                </div>
                
                <div class="form-group">
                    <label for="new_password">New Password:</label>
                    <input type="password" id="new_password" name="new_password" placeholder="Enter new password (min 6 chars)" required minlength="6">
                    <div class="quick-fill">
                        Quick passwords: 
                        <button type="button" onclick="setPassword('password123')">password123</button>
                        <button type="button" onclick="setPassword('admin123')">admin123</button>
                        <button type="button" onclick="setPassword('test123')">test123</button>
                        <button type="button" onclick="setPassword('user123')">user123</button>
                    </div>
                </div>
                
                <div style="text-align: center; margin-top: 30px;">
                    <button type="submit" class="btn btn-primary">🔐 Reset Password</button>
                    <a href="/check-users" class="btn btn-secondary">👥 View Users</a>
                    <a href="/simple-login" class="btn btn-secondary">🚪 Test Login</a>
                </div>
            </form>
            
            <div class="user-list">
                <h3>📋 Registered Users ({len(users)} total):</h3>
                {''.join([f'<div class="user-item"><strong>{user[1]}</strong> - {user[0]}</div>' for user in users]) if users else '<p>No users found</p>'}
            </div>
        </div>
        
        <script>
            function fillEmail(email) {{
                document.getElementById('manual_email').value = email;
            }}
            
            function setPassword(password) {{
                document.getElementById('new_password').value = password;
            }}
        </script>
    </body>
    </html>
    """

@app.route('/check-users')
def check_users():
    """Enhanced user management interface"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, name, email, created_at, is_premium, scans_used FROM users ORDER BY created_at DESC')
        users = cursor.fetchall()
        conn.close()
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>User Management</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ font-family: Arial; padding: 20px; background: #f5f5f5; margin: 0; }}
                .container {{ max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                h1 {{ color: #e91e63; text-align: center; margin-bottom: 30px; }}
                table {{ width: 100%%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f8f9fa; font-weight: bold; color: #333; }}
                tr:hover {{ background-color: #f5f5f5; }}
                .btn {{ padding: 8px 16px; margin: 5px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-size: 14px; }}
                .btn-primary {{ background: #e91e63; color: white; }}
                .btn-secondary {{ background: #666; color: white; }}
                .btn-success {{ background: #28a745; color: white; }}
                .btn:hover {{ opacity: 0.9; transform: translateY(-1px); }}
                .stats {{ display: flex; gap: 20px; margin: 20px 0; }}
                .stat-box {{ background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; flex: 1; }}
                .stat-number {{ font-size: 24px; font-weight: bold; color: #e91e63; }}
                .premium {{ color: #28a745; font-weight: bold; }}
                .trial {{ color: #ffc107; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>👥 User Management Dashboard</h1>
                
                <div class="stats">
                    <div class="stat-box">
                        <div class="stat-number">{len(users)}</div>
                        <div>Total Users</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{len([u for u in users if u[4]])}</div>
                        <div>Premium Users</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{sum(u[5] or 0 for u in users)}</div>
                        <div>Total Scans</div>
                    </div>
                </div>
                
                <div style="text-align: center; margin: 20px 0;">
                    <a href="/admin-password-reset" class="btn btn-primary">🔐 Reset Individual Password</a>
                    <a href="/simple-login" class="btn btn-success">🚪 Test Login</a>
                    <a href="/" class="btn btn-secondary">🏠 Back to App</a>
                    <a href="/health" class="btn btn-secondary">🏥 Health Check</a>
                </div>
                
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Name</th>
                            <th>Email</th>
                            <th>Status</th>
                            <th>Scans Used</th>
                            <th>Created</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join([f'''
                        <tr>
                            <td>{user[0]}</td>
                            <td>{user[1]}</td>
                            <td>{user[2]}</td>
                            <td class="{'premium' if user[4] else 'trial'}">{'Premium' if user[4] else 'Trial'}</td>
                            <td>{user[5] or 0}</td>
                            <td>{user[3]}</td>
                        </tr>
                        ''' for user in users]) if users else '<tr><td colspan="6" style="text-align: center;">No users found</td></tr>'}
                    </tbody>
                </table>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        return f"""
        <html>
        <body style="font-family: Arial; padding: 20px;">
            <h1>❌ Database Error</h1>
            <p><strong>Error:</strong> {str(e)}</p>
            <a href="/simple-login" style="background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Try Simple Login</a>
        </body>
        </html>
        """

# Error handlers with better error pages
@app.errorhandler(413)
def too_large(e):
    gc.collect()  # Clean up on error
    return render_template('error.html', 
                         error_title="File Too Large", 
                         error_message="The uploaded image is too large. Please upload an image smaller than 5MB."), 413

@app.errorhandler(500)
def internal_error(e):
    gc.collect()  # Force cleanup on 500 errors
    return render_template('error.html', 
                         error_title="Internal Server Error", 
                         error_message="Something went wrong. Please try again with a smaller image."), 500

@app.errorhandler(TimeoutError)
def timeout_error(e):
    gc.collect()  # Force cleanup on timeout
    return render_template('error.html',
                         error_title="Request Timeout",
                         error_message="The request took too long to process. Please try with a smaller image."), 504

# CRITICAL: Use Gunicorn for production
if __name__ == '__main__':
    # Only for local development - production uses Gunicorn
    port = int(os.environ.get("PORT", 5000))
    print("WARNING: Running with Flask development server. Use Gunicorn for production!")
    app.run(host="0.0.0.0", port=port, debug=False)
