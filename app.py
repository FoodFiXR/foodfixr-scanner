from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_file, Response
from werkzeug.security import generate_password_hash, check_password_hash
import os
import tempfile
from werkzeug.utils import secure_filename
from ingredient_scanner import scan_image_for_ingredients, before_scan_cleanup
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
import signal
import psutil
import resource
import sys

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Stripe Configuration
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
DOMAIN = os.getenv('DOMAIN', 'https://foodfixr-scanner-1.onrender.com')

# Configuration - Conservative limits for memory-constrained environments
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp'}
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.permanent_session_lifetime = timedelta(days=30)

# Setup worker protection against memory issues
def setup_worker_protection():
    """Set up worker protection against memory issues"""
    try:
        # Set memory limit for the process (soft limit)
        # 150MB limit (conservative for Render)
        memory_limit_mb = 150
        memory_limit_bytes = memory_limit_mb * 1024 * 1024
        
        # Set soft memory limit
        try:
            resource.setrlimit(resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))
            print(f"DEBUG: Set memory limit to {memory_limit_mb} MB")
        except Exception as e:
            print(f"DEBUG: Could not set memory limit: {e}")
        
        # Set up signal handlers for graceful shutdown
        def memory_handler(signum, frame):
            print("DEBUG: Memory limit signal received, forcing cleanup")
            gc.collect()
            sys.exit(1)
        
        def term_handler(signum, frame):
            print("DEBUG: Term signal received, graceful shutdown")
            gc.collect()
            sys.exit(0)
        
        signal.signal(signal.SIGUSR1, memory_handler)
        signal.signal(signal.SIGTERM, term_handler)
        
    except Exception as e:
        print(f"DEBUG: Worker protection setup error: {e}")

# Call this after imports
setup_worker_protection()

def cleanup_old_temp_files():
    """Clean up old temporary files"""
    try:
        temp_dir = tempfile.gettempdir()
        current_time = time.time()
        
        for filename in os.listdir(temp_dir):
            if any(pattern in filename for pattern in ['20250626', 'compressed', 'ultra_']):
                filepath = os.path.join(temp_dir, filename)
                try:
                    if os.path.isfile(filepath):
                        file_age = current_time - os.path.getmtime(filepath)
                        if file_age > 10:  # 10 seconds
                            os.remove(filepath)
                except:
                    pass
    except:
        pass

# Enhanced before_request with memory monitoring
@app.before_request
def before_request():
    """Enhanced memory management before each request"""
    try:
        # Check worker memory
        memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
        
        # If memory is too high, force cleanup
        if memory_mb > 90:
            print(f"DEBUG: High memory detected ({memory_mb:.1f} MB), forcing cleanup")
            for _ in range(5):
                gc.collect()
            
            # Check again after cleanup
            memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
            if memory_mb > 110:
                print(f"DEBUG: Memory still high ({memory_mb:.1f} MB), restarting worker")
                # Gracefully restart worker
                os.kill(os.getpid(), signal.SIGTERM)
        
        # Set conservative PIL limits
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = 20000000  # Very conservative
        
        print(f"DEBUG: Pre-request memory: {memory_mb:.1f} MB")
        
    except Exception as e:
        print(f"DEBUG: Pre-request error: {e}")

# Enhanced after_request with aggressive cleanup
@app.after_request
def after_request(response):
    """Enhanced cleanup after each request"""
    try:
        # Force garbage collection
        for _ in range(3):
            gc.collect()
        
        # Check memory
        memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
        print(f"DEBUG: Post-request memory: {memory_mb:.1f} MB")
        
        # If memory is high, clean up temp files
        if memory_mb > 80:
            cleanup_old_temp_files()
        
    except Exception as e:
        print(f"DEBUG: Post-request cleanup error: {e}")
    
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
    
    # Updated scan_history table with ALL required columns
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
        print(f"Column addition note: {e}")  # May fail if columns already exist
    
    conn.commit()
    conn.close()
    print("Database initialized successfully with all required columns")

init_db()

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
            # Check if we're using PostgreSQL or SQLite
            database_url = os.getenv('DATABASE_URL')
            if database_url:
                # PostgreSQL version
                cursor.execute('''
                    INSERT INTO users (name, email, password_hash, trial_start_date, trial_end_date, last_login)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '48 hours', CURRENT_TIMESTAMP)
                    RETURNING id
                ''', (name, email, password_hash))
                
                user_result = cursor.fetchone()
                user_id = user_result['id']
            else:
                # SQLite version (for local development)
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
        
        # Use appropriate placeholder for database type
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
            
            # Check if user exists
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
            
            # Update password
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
def scan():
    """Memory-protected scanning route"""
    filepath = None
    
    try:
        # CRITICAL: Check worker memory before starting
        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024
        print(f"DEBUG: Worker memory before scan: {initial_memory:.1f} MB")
        
        # If memory is already high, reject the request
        if initial_memory > 100:
            print(f"DEBUG: Worker memory too high ({initial_memory:.1f} MB), rejecting request")
            flash('System busy. Please try again in a moment.', 'error')
            return redirect('/')
        
        # Force cleanup before proceeding
        for _ in range(3):
            gc.collect()
        
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
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        
        file.save(filepath)
        
        # CRITICAL: Check file size immediately
        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        print(f"DEBUG: Uploaded file size: {file_size_mb:.2f} MB")
        
        # Strict size limit to prevent memory issues
        if file_size_mb > 2.0:  # Very conservative limit
            cleanup_uploaded_file(filepath)
            return render_template('scanner.html',
                                 trial_expired=trial_expired,
                                 trial_time_left=trial_time_left,
                                 user_name=user_data['name'],
                                 error="Image too large. Please upload a smaller image (max 2MB).")
        
        # Check memory after file save
        memory_after_save = psutil.Process().memory_info().rss / 1024 / 1024
        if memory_after_save > 110:
            cleanup_uploaded_file(filepath)
            return render_template('scanner.html',
                                 trial_expired=trial_expired,
                                 trial_time_left=trial_time_left,
                                 user_name=user_data['name'],
                                 error="System memory limit reached. Please try with a smaller image.")
        
        # Force cleanup before processing
        before_scan_cleanup()
        
        print("DEBUG: Starting memory-protected image processing...")
        
        # Process with timeout and memory monitoring
        try:
            result = scan_image_for_ingredients(filepath)
        except MemoryError:
            cleanup_uploaded_file(filepath)
            for _ in range(5):
                gc.collect()
            return render_template('scanner.html',
                                 trial_expired=trial_expired,
                                 trial_time_left=trial_time_left,
                                 user_name=user_data['name'],
                                 error="Memory limit reached. Please try with a smaller image.")
        
        # Check if result indicates memory error
        if result.get('error') and 'memory' in result.get('error', '').lower():
            cleanup_uploaded_file(filepath)
            return render_template('scanner.html',
                                 trial_expired=trial_expired,
                                 trial_time_left=trial_time_left,
                                 user_name=user_data['name'],
                                 error=result.get('error', 'Memory limit reached.'))
        
        # Update database
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
                    extracted_text, text_length, confidence, text_quality, has_safety_labels
                )
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s)
            ''', (
                session['user_id'], 
                result.get('rating', ''), 
                json.dumps(result.get('matched_ingredients', {})),
                str(uuid.uuid4()),
                result.get('extracted_text', ''),
                result.get('extracted_text_length', 0),
                result.get('confidence', 'medium'),
                result.get('text_quality', 'unknown'),
                result.get('has_safety_labels', False)
            ))
        else:
            # SQLite version
            cursor.execute('''
                UPDATE users 
                SET scans_used = ?, total_scans_ever = ?
                WHERE id = ?
            ''', (new_scans_used, new_total_scans, session['user_id']))
            
            cursor.execute('''
                INSERT INTO scan_history (
                    user_id, result_rating, ingredients_found, scan_date, scan_id,
                    extracted_text, text_length, confidence, text_quality, has_safety_labels
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session['user_id'], 
                result.get('rating', ''), 
                json.dumps(result.get('matched_ingredients', {})),
                format_datetime_for_db(),
                str(uuid.uuid4()),
                result.get('extracted_text', ''),
                result.get('extracted_text_length', 0),
                result.get('confidence', 'medium'),
                result.get('text_quality', 'unknown'),
                int(result.get('has_safety_labels', False))
            ))
        
        conn.commit()
        conn.close()
        
        session['scans_used'] = new_scans_used
        
        # Clean up uploaded file
        cleanup_uploaded_file(filepath)
        
        # Force final cleanup
        for _ in range(3):
            gc.collect()
        
        final_memory = psutil.Process().memory_info().rss / 1024 / 1024
        print(f"DEBUG: Final memory after scan: {final_memory:.1f} MB")
        
        return render_template('scanner.html',
                             result=result,
                             trial_expired=trial_expired,
                             trial_time_left=trial_time_left,
                             user_name=user_data['name'])
        
    except Exception as e:
        print(f"DEBUG: Scan route error: {e}")
        import traceback
        traceback.print_exc()
        
        # Emergency cleanup
        cleanup_uploaded_file(filepath)
        
        # Force aggressive cleanup on error
        for _ in range(5):
            gc.collect()
        
        return render_template('scanner.html',
                             trial_expired=trial_expired,
                             trial_time_left=trial_time_left,
                             user_name=user_data['name'],
                             error="Scanning failed. Please try again with a smaller image.")

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
        
        # Use appropriate placeholder for database type
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
            
            # Parse ingredients_found safely
            ingredients_data = {}
            try:
                if row['ingredients_found']:
                    # Try to parse as JSON first, then eval as fallback
                    if row['ingredients_found'].startswith('{'):
                        ingredients_data = json.loads(row['ingredients_found'])
                    else:
                        # Fallback for string representation
                        ingredients_data = eval(row['ingredients_found'])
            except:
                ingredients_data = {}
            
            # Create ingredient summary
            ingredient_summary = {}
            detected_ingredients = []
            has_gmo = False
            
            if isinstance(ingredients_data, dict):
                for category, items in ingredients_data.items():
                    if isinstance(items, list) and items:
                        ingredient_summary[category] = len(items)
                        detected_ingredients.extend(items)
                        if category == 'gmo' and items:
                            has_gmo = True
                    elif category == 'all_detected' and isinstance(items, list):
                        detected_ingredients = items
                        
            # Count total unique ingredients
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
        plan = data.get('plan', 'monthly')  # Default to monthly
        
        # Map plan names to Stripe price IDs
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
        
        # Create or retrieve Stripe customer
        stripe_customer_id = user_data.get('stripe_customer_id')
        
        if not stripe_customer_id:
            customer = stripe.Customer.create(
                email=user_data['email'],
                name=user_data['name'],
                metadata={'user_id': str(user_data['id'])}
            )
            stripe_customer_id = customer.id
            
            # Update user with Stripe customer ID
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
        
        # Create checkout session
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
        # Retrieve the checkout session
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        
        if checkout_session.payment_status == 'paid':
            # Update user to premium
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
            
            # Update session
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
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        print(f"Invalid payload: {e}")
        return '', 400
    except stripe.error.SignatureVerificationError as e:
        print(f"Invalid signature: {e}")
        return '', 400
    
    # Handle the event
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
        # Handle subscription cancellation
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
        
        # Create JSON response
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
            
            # Update session
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
                
                # Use appropriate placeholder for database type
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

# Add memory monitoring endpoint
@app.route('/memory-status')
def memory_status():
    """Debug endpoint to check memory usage"""
    try:
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        return jsonify({
            'memory_mb': round(memory_mb, 1),
            'memory_percent': process.memory_percent(),
            'status': 'critical' if memory_mb > 100 else 'ok',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Health check endpoint for monitoring
@app.route('/health')
def health_check():
    """Simple health check endpoint"""
    try:
        # Check database connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        conn.close()
        
        # Check memory usage
        memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
        
        return jsonify({
            'status': 'healthy',
            'memory_mb': round(memory_mb, 1),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

# Error handlers
@app.errorhandler(413)
def too_large(e):
    return render_template('error.html', 
                         error_title="File Too Large", 
                         error_message="The uploaded image is too large. Please upload an image smaller than 3MB."), 413

@app.errorhandler(500)
def internal_error(e):
    # Force cleanup on 500 errors
    gc.collect()
    return render_template('error.html', 
                         error_title="Internal Server Error", 
                         error_message="Something went wrong. Please try again."), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
