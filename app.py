from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import os
import tempfile
from werkzeug.utils import secure_filename
from ingredient_scanner import scan_image_for_ingredients
import json
from datetime import datetime, timedelta
import uuid
import stripe
from PIL import Image
import time
import sqlite3
from functools import wraps
import shutil

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Stripe Configuration
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')

# Your domain for Stripe redirects
DOMAIN = os.getenv('DOMAIN', 'https://foodfixr-scanner-1.onrender.com')

# Configuration
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.permanent_session_lifetime = timedelta(days=30)

# Database initialization
def init_db():
    conn = sqlite3.connect('foodfixr.db')
    cursor = conn.cursor()
    
    # Enhanced users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            is_premium BOOLEAN DEFAULT 0,
            stripe_customer_id TEXT,
            subscription_status TEXT DEFAULT 'trial',
            subscription_start_date TEXT,
            next_billing_date TEXT,
            trial_start_date TEXT DEFAULT (datetime('now', 'localtime')),
            trial_end_date TEXT,
            scans_used INTEGER DEFAULT 0,
            total_scans_ever INTEGER DEFAULT 0,
            last_login TEXT
        )
    ''')
    
    # Scan history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scan_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            scan_date TEXT DEFAULT (datetime('now', 'localtime')),
            result_rating TEXT,
            ingredients_found TEXT,
            image_url TEXT,
            scan_id TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully")

# Initialize database
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
    conn = sqlite3.connect('foodfixr.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    
    conn.close()
    return dict(user) if user else None

def safe_datetime_parse(date_string):
    """Safely parse datetime strings with various formats"""
    if not date_string:
        return datetime.now()
    
    if isinstance(date_string, datetime):
        return date_string
    
    # Try multiple datetime formats to handle microseconds and variations
    formats = [
        '%Y-%m-%d %H:%M:%S.%f',      # With microseconds
        '%Y-%m-%d %H:%M:%S',         # Standard format
        '%Y-%m-%d %H:%M',            # Without seconds
        '%Y-%m-%d',                  # Date only
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_string, fmt)
        except ValueError:
            continue
    
    # If all formats fail, try to clean the string
    try:
        # Remove microseconds if present
        clean_date = date_string.split('.')[0]
        return datetime.strptime(clean_date, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        # Last resort: return current time
        print(f"Warning: Could not parse date '{date_string}', using current time")
        return datetime.now()

def calculate_trial_time_left(trial_start_date):
    """Calculate remaining trial time, handling various datetime formats"""
    trial_start = safe_datetime_parse(trial_start_date)
    trial_end = trial_start + timedelta(hours=48)
    now = datetime.now()
    
    if now >= trial_end:
        return "0h 0m", True, 0, 0
    
    time_left = trial_end - now
    hours = int(time_left.total_seconds() // 3600)
    minutes = int((time_left.total_seconds() % 3600) // 60)
    
    return f"{hours}h {minutes}m", False, hours, minutes

def calculate_renewal_days(next_billing_date):
    if not next_billing_date:
        return None
    
    billing_date = safe_datetime_parse(next_billing_date)
    now = datetime.now()
    days_left = (billing_date - now).days
    
    return max(0, days_left)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_trial_expired():
    """Check if 48-hour trial has expired"""
    if 'user_id' not in session:
        return True
        
    user_data = get_user_data(session['user_id'])
    if not user_data:
        return True
        
    if user_data['is_premium']:
        return False
        
    trial_start = safe_datetime_parse(user_data['trial_start_date'])
    trial_end = trial_start + timedelta(hours=48)
    return datetime.now() > trial_end

def get_trial_time_left():
    """Get remaining trial time as formatted string"""
    if 'user_id' not in session:
        return "0h 0m"
        
    user_data = get_user_data(session['user_id'])
    if not user_data:
        return "0h 0m"
        
    if user_data['is_premium']:
        return "Premium"
        
    trial_time_left, _, _, _ = calculate_trial_time_left(user_data['trial_start_date'])
    return trial_time_left

def can_scan():
    """Check if user can perform a scan"""
    if 'user_id' not in session:
        return False
        
    user_data = get_user_data(session['user_id'])
    if not user_data:
        return False
        
    if user_data['is_premium']:
        return True
    
    if user_data['scans_used'] >= 10:
        return False
        
    if is_trial_expired():
        return False
        
    return True

def save_scan_image(image_path, user_id, scan_id=None):
    """Save scanned image for history"""
    try:
        if not scan_id:
            scan_id = str(uuid.uuid4())
        
        # Create images directory if it doesn't exist
        images_dir = os.path.join('static', 'scan_images')
        os.makedirs(images_dir, exist_ok=True)
        
        # Copy image to permanent location
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_filename = f"{user_id}_{scan_id[:8]}_{timestamp}.jpg"
        permanent_path = os.path.join(images_dir, image_filename)
        
        # Copy and compress image
        with Image.open(image_path) as img:
            # Convert to RGB if needed
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            # Resize for storage (max 400px wide)
            img.thumbnail((400, 400), Image.Resampling.LANCZOS)
            img.save(permanent_path, 'JPEG', quality=85, optimize=True)
        
        return f"/static/scan_images/{image_filename}"
        
    except Exception as e:
        print(f"Error saving scan image: {e}")
        return None

def format_datetime_for_db(dt=None):
    """Format datetime for consistent database storage"""
    if dt is None:
        dt = datetime.now()
    return dt.strftime('%Y-%m-%d %H:%M:%S')

# AUTHENTICATION ROUTES - FIXED VERSION
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        print(f"DEBUG: Registration attempt for email: {email}")
        
        # Validation
        if not all([name, email, password, confirm_password]):
            flash('All fields are required', 'error')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return render_template('register.html')
        
        if len(name) < 2:
            flash('Name must be at least 2 characters long', 'error')
            return render_template('register.html')
        
        conn = sqlite3.connect('foodfixr.db')
        cursor = conn.cursor()
        
        # Check if email already exists
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            flash('An account with this email already exists', 'error')
            conn.close()
            return render_template('register.html')
        
        # EXACT SAME METHOD AS LOGIN EXPECTS
        password_hash = generate_password_hash(password)  # Use default method
        print(f"DEBUG: Generated hash method: {password_hash.split('$')[0] if '$' in password_hash else 'pbkdf2' if 'pbkdf2' in password_hash else 'unknown'}")
        
        now = datetime.now()
        trial_start = format_datetime_for_db(now)
        trial_end = format_datetime_for_db(now + timedelta(hours=48))
        last_login = format_datetime_for_db(now)
        
        try:
            cursor.execute('''
                INSERT INTO users (name, email, password_hash, trial_start_date, trial_end_date, last_login)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (name, email, password_hash, trial_start, trial_end, last_login))
            
            user_id = cursor.lastrowid
            conn.commit()
            
            print(f"DEBUG: User created successfully with ID: {user_id}")
            
            # IMMEDIATE TEST - This is the key fix
            test_verify = check_password_hash(password_hash, password)
            print(f"DEBUG: Immediate verification test: {test_verify}")
            
            if not test_verify:
                print("ERROR: Password verification failed immediately after hashing!")
                flash('Registration failed - password verification error. Please try again.', 'error')
                cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
                conn.commit()
                conn.close()
                return render_template('register.html')
            
            # Auto-login after registration
            session.permanent = True
            session['user_id'] = user_id
            session['user_email'] = email
            session['user_name'] = name
            session['is_premium'] = False
            session['scans_used'] = 0
            session['stripe_customer_id'] = None
            
            flash(f'Welcome to FoodFixr, {name}! Your free trial has started.', 'success')
            conn.close()
            return redirect(url_for('index'))
            
        except Exception as e:
            print(f"DEBUG: Database error during registration: {e}")
            flash('Registration failed. Please try again.', 'error')
            conn.close()
            return render_template('register.html')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        print(f"DEBUG: Login attempt for email: {email}")
        print(f"DEBUG: Password provided: {'Yes' if password else 'No'}")
        
        if not email or not password:
            flash('Please enter both email and password', 'error')
            return render_template('login.html')
        
        conn = sqlite3.connect('foodfixr.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        
        if user:
            print(f"DEBUG: User found: {user['name']}")
            print(f"DEBUG: Stored hash starts with: {user['password_hash'][:30]}...")
            
            # EXACT SAME METHOD AS REGISTRATION USES
            is_valid = check_password_hash(user['password_hash'], password)
            print(f"DEBUG: Password verification result: {is_valid}")
            
            if is_valid:
                # Update last login
                cursor.execute('UPDATE users SET last_login = ? WHERE id = ?', 
                             (format_datetime_for_db(), user['id']))
                conn.commit()
                
                # Set session
                session.permanent = True
                session['user_id'] = user['id']
                session['user_email'] = user['email']
                session['user_name'] = user['name']
                session['is_premium'] = bool(user['is_premium'])
                session['scans_used'] = user['scans_used']
                session['stripe_customer_id'] = user['stripe_customer_id']
                
                flash(f'Welcome back, {user["name"]}!', 'success')
                conn.close()
                return redirect(url_for('index'))
            else:
                print(f"DEBUG: Password verification failed for hash: {user['password_hash'][:50]}...")
                flash('Invalid email or password', 'error')
                conn.close()
        else:
            print(f"DEBUG: No user found with email: {email}")
            flash('Invalid email or password', 'error')
            conn.close()
    
    return render_template('login.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """Reset password for users"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        if not email or not new_password or not confirm_password:
            flash('All fields are required', 'error')
            return render_template('reset_password.html')
        
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('reset_password.html')
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return render_template('reset_password.html')
        
        conn = sqlite3.connect('foodfixr.db')
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute('SELECT id, name FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        
        if user:
            # Update password with same method as registration
            new_hash = generate_password_hash(new_password)
            cursor.execute('UPDATE users SET password_hash = ? WHERE email = ?', (new_hash, email))
            conn.commit()
            conn.close()
            
            flash(f'Password updated successfully for {email}!', 'success')
            return redirect(url_for('login'))
        else:
            conn.close()
            flash('No account found with that email address', 'error')
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
    """Main scanner page"""
    user_data = get_user_data(session['user_id'])
    if not user_data:
        return redirect(url_for('logout'))
    
    # Calculate trial status
    trial_time_left, trial_expired, _, _ = calculate_trial_time_left(user_data['trial_start_date'])
    
    # Update session with latest data
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
    """Handle image scanning with trial limits"""
    try:
        user_data = get_user_data(session['user_id'])
        if not user_data:
            return redirect(url_for('logout'))
        
        # Check if user can scan
        if not can_scan():
            flash('You have used all your free scans. Please upgrade to continue.', 'error')
            return redirect(url_for('upgrade'))
        
        # Check if trial expired
        trial_time_left, trial_expired, _, _ = calculate_trial_time_left(user_data['trial_start_date'])
        if not user_data['is_premium'] and trial_expired:
            flash('Your free trial has expired. Please upgrade to continue scanning.', 'error')
            return redirect(url_for('upgrade'))
        
        # Check if image was uploaded
        if 'image' not in request.files:
            return render_template('scanner.html',
                                 trial_expired=trial_expired,
                                 trial_time_left=trial_time_left,
                                 user_name=user_data['name'],
                                 error="No image uploaded.",
                                 stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)
        
        file = request.files['image']
        if file.filename == '':
            return render_template('scanner.html',
                                 trial_expired=trial_expired,
                                 trial_time_left=trial_time_left,
                                 user_name=user_data['name'],
                                 error="No image selected.",
                                 stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)
        
        if not allowed_file(file.filename):
            return render_template('scanner.html',
                                 trial_expired=trial_expired,
                                 trial_time_left=trial_time_left,
                                 user_name=user_data['name'],
                                 error="Invalid file type. Please upload an image.",
                                 stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)
        
        try:
            # Save uploaded file to temp directory
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{filename}"
            
            filepath = os.path.join(tempfile.gettempdir(), filename)
            file.save(filepath)
            
            print(f"DEBUG: File saved to {filepath}")
            
            # SAVE IMAGE FOR HISTORY BEFORE SCANNING
            scan_id = str(uuid.uuid4())
            image_url = save_scan_image(filepath, session.get('user_id'), scan_id)
            print(f"DEBUG: Image URL for history: {image_url}")
            
            # Scan the image
            print("DEBUG: Starting image scan...")
            result = scan_image_for_ingredients(filepath)
            print(f"DEBUG: Scan result: {result}")
            
            # Update scan count in database
            conn = sqlite3.connect('foodfixr.db')
            cursor = conn.cursor()
            
            new_scans_used = user_data['scans_used'] + 1 if not user_data['is_premium'] else user_data['scans_used']
            new_total_scans = user_data['total_scans_ever'] + 1
            
            cursor.execute('''
                UPDATE users 
                SET scans_used = ?, total_scans_ever = ?
                WHERE id = ?
            ''', (new_scans_used, new_total_scans, session['user_id']))
            
            # Save scan to history
            cursor.execute('''
                INSERT INTO scan_history (user_id, result_rating, ingredients_found, image_url, scan_id, scan_date)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session['user_id'], result.get('rating', ''), str(result.get('matched_ingredients', {})), 
                  image_url, scan_id, format_datetime_for_db()))
            
            conn.commit()
            conn.close()
            
            # Update session
            session['scans_used'] = new_scans_used
            
            # Clean up uploaded file
            try:
                os.remove(filepath)
                print("DEBUG: Temp file cleaned up")
            except Exception as cleanup_error:
                print(f"DEBUG: Cleanup error: {cleanup_error}")
            
            # Calculate updated trial status
            trial_time_left, trial_expired, _, _ = calculate_trial_time_left(user_data['trial_start_date'])
            
            return render_template('scanner.html',
                                 result=result,
                                 trial_expired=trial_expired,
                                 trial_time_left=trial_time_left,
                                 user_name=user_data['name'],
                                 stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)
            
        except Exception as scan_error:
            print(f"DEBUG: Scanning error: {scan_error}")
            import traceback
            traceback.print_exc()
            
            return render_template('scanner.html',
                                 trial_expired=trial_expired,
                                 trial_time_left=trial_time_left,
                                 user_name=user_data['name'],
                                 error=f"Scanning failed: {str(scan_error)}. Please try again.",
                                 stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)
    
    except Exception as outer_error:
        print(f"DEBUG: Outer error in scan route: {outer_error}")
        import traceback
        traceback.print_exc()
        
        return render_template('scanner.html',
                             trial_expired=False,
                             trial_time_left="Error",
                             user_name="User",
                             error=f"An error occurred: {str(outer_error)}. Please try again.",
                             stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)

@app.route('/account')
@login_required
def account():
    """User account page with subscription management"""
    user_data = get_user_data(session['user_id'])
    if not user_data:
        return redirect(url_for('logout'))
    
    # Calculate trial time left
    trial_time_left, trial_expired, trial_hours, trial_minutes = calculate_trial_time_left(user_data['trial_start_date'])
    
    # Calculate renewal days for premium users
    days_until_renewal = None
    if user_data['is_premium'] and user_data['next_billing_date']:
        days_until_renewal = calculate_renewal_days(user_data['next_billing_date'])
    
    # Format dates safely
    created_date = safe_datetime_parse(user_data['created_at'])
    formatted_created_date = created_date.strftime('%B %d, %Y')
    
    trial_start = safe_datetime_parse(user_data['trial_start_date'])
    formatted_trial_start = trial_start.strftime('%B %d, %Y')
    
    # Format subscription dates for premium users
    subscription_start_formatted = None
    next_billing_formatted = None
    
    if user_data['is_premium']:
        if user_data['subscription_start_date']:
            sub_start = safe_datetime_parse(user_data['subscription_start_date'])
            subscription_start_formatted = sub_start.strftime('%B %d, %Y')
        
        if user_data['next_billing_date']:
            next_billing = safe_datetime_parse(user_data['next_billing_date'])
            next_billing_formatted = next_billing.strftime('%B %d, %Y')
    
    return render_template('account.html',
                         user_name=user_data['name'],
                         user_created_date=formatted_created_date,
                         total_scans_ever=user_data['total_scans_ever'],
                         trial_start_date=formatted_trial_start,
                         trial_time_left=trial_time_left,
                         trial_expired=trial_expired,
                         trial_hours_left=trial_hours,
                         trial_minutes_left=trial_minutes,
                         subscription_status=user_data['subscription_status'],
                         subscription_start_date=subscription_start_formatted,
                         next_billing_date=next_billing_formatted,
                         days_until_renewal=days_until_renewal,
                         billing_portal_url='/create-customer-portal')

# Add this debug route to your app.py file (you can add it anywhere after your other routes)

@app.route('/debug-billing')
@login_required
def debug_billing():
    """Debug billing portal issues"""
    try:
        user_data = get_user_data(session['user_id'])
        
        debug_info = {
            'user_id': session.get('user_id'),
            'is_premium': session.get('is_premium'),
            'stripe_customer_id_session': session.get('stripe_customer_id'),
            'stripe_customer_id_db': user_data.get('stripe_customer_id') if user_data else None,
            'subscription_status': user_data.get('subscription_status') if user_data else None,
            'stripe_api_key_configured': bool(stripe.api_key),
            'domain': DOMAIN
        }
        
        # Test Stripe connection
        stripe_test = "Not tested"
        customer_valid = "Not tested"
        
        if stripe.api_key:
            try:
                # Test Stripe connection
                stripe.Account.retrieve()
                stripe_test = "✅ Connected"
                
                # Test customer retrieval if we have an ID
                customer_id = user_data.get('stripe_customer_id') if user_data else None
                if customer_id:
                    try:
                        customer = stripe.Customer.retrieve(customer_id)
                        customer_valid = f"✅ Valid customer: {customer.email}"
                    except Exception as e:
                        customer_valid = f"❌ Invalid customer: {str(e)}"
                
            except Exception as e:
                stripe_test = f"❌ Failed: {str(e)}"
        
        debug_info['stripe_connection'] = stripe_test
        debug_info['customer_validation'] = customer_valid
        
        return f"""
        <html>
        <head><title>Billing Debug</title></head>
        <body style="font-family: monospace; padding: 20px; background: #f5f5f5;">
        <h1>💳 Billing Portal Debug</h1>
        <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
        <h3>User Information:</h3>
        <strong>User ID:</strong> {debug_info['user_id']}<br>
        <strong>Is Premium:</strong> {debug_info['is_premium']}<br>
        <strong>Customer ID (Session):</strong> {debug_info['stripe_customer_id_session']}<br>
        <strong>Customer ID (DB):</strong> {debug_info['stripe_customer_id_db']}<br>
        <strong>Subscription Status:</strong> {debug_info['subscription_status']}<br>
        <br>
        <h3>System Configuration:</h3>
        <strong>Stripe API Key:</strong> {debug_info['stripe_api_key_configured']}<br>
        <strong>Domain:</strong> {debug_info['domain']}<br>
        <strong>Stripe Connection:</strong> {debug_info['stripe_connection']}<br>
        <strong>Customer Validation:</strong> {debug_info['customer_validation']}<br>
        </div>
        
        <div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ffc107;">
        <h3>💡 Troubleshooting Tips:</h3>
        <ul>
        <li>If "Is Premium" is False, user needs to upgrade first</li>
        <li>If "Customer ID" is None, user didn't complete Stripe checkout properly</li>
        <li>If "Stripe Connection" shows error, check your STRIPE_SECRET_KEY environment variable</li>
        <li>If "Customer Validation" shows error, the customer might be deleted from Stripe</li>
        </ul>
        </div>
        
        <div style="margin: 20px 0;">
        <a href="/account" style="background: #e91e63; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; margin-right: 10px;">← Back to Account</a>
        <a href="/upgrade" style="background: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; margin-right: 10px;">💎 Upgrade</a>
        <a href="/debug" style="background: #2196F3; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px;">🔍 Full Debug</a>
        </div>
        </body>
        </html>
        """
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return f"""
        <html>
        <head><title>Debug Error</title></head>
        <body style="font-family: monospace; padding: 20px; background: #f5f5f5;">
        <h1>❌ Debug Error</h1>
        <div style="background: #ffebee; padding: 20px; border-radius: 8px; margin: 20px 0;">
        <h3>Error Details:</h3>
        <pre>{str(e)}</pre>
        <h3>Full Traceback:</h3>
        <pre>{error_details}</pre>
        </div>
        <a href="/account" style="background: #e91e63; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px;">← Back to Account</a>
        </body>
        </html>
        """
        
@app.route('/history')
@login_required
def history():
    """Display scan history from database with improved ingredient parsing"""
    try:
        conn = sqlite3.connect('foodfixr.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM scan_history 
            WHERE user_id = ? 
            ORDER BY scan_date DESC 
            LIMIT 50
        ''', (session['user_id'],))
        
        scans = []
        stats = {
            'total_scans': 0,
            'safe_scans': 0,
            'danger_scans': 0,
            'ingredients_found': 0
        }
        
        for row in cursor.fetchall():
            # Parse timestamp safely
            scan_date = safe_datetime_parse(row['scan_date'])
            
            # Determine rating type
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
            
            # Process ingredients (stored as JSON string)
            ingredient_summary = {}
            has_gmo = False
            detected_ingredients = []
            
            try:
                if row['ingredients_found']:
                    # Try to parse the JSON data
                    matched_ingredients = json.loads(row['ingredients_found'])
                    print(f"DEBUG: Parsed ingredients for scan {row['id']}: {matched_ingredients}")
                    
                    # Handle different JSON structures
                    if isinstance(matched_ingredients, dict):
                        for category, ingredients in matched_ingredients.items():
                            if isinstance(ingredients, list) and ingredients:
                                ingredient_summary[category] = len(ingredients)
                                detected_ingredients.extend(ingredients)
                                if category == 'gmo':
                                    has_gmo = True
                                stats['ingredients_found'] += len(ingredients)
                            elif isinstance(ingredients, str) and ingredients:
                                # Handle single string ingredients
                                ingredient_summary[category] = 1
                                detected_ingredients.append(ingredients)
                                if category == 'gmo':
                                    has_gmo = True
                                stats['ingredients_found'] += 1
                    
                    # Also check for 'all_detected' key specifically
                    if 'all_detected' in matched_ingredients:
                        all_detected = matched_ingredients['all_detected']
                        if isinstance(all_detected, list):
                            detected_ingredients.extend(all_detected)
                    
            except json.JSONDecodeError as e:
                print(f"DEBUG: JSON decode error for scan {row['id']}: {e}")
                # Try to handle as plain text
                if row['ingredients_found']:
                    ingredient_summary['other'] = 1
                    detected_ingredients = [row['ingredients_found']]
            except Exception as e:
                print(f"DEBUG: Ingredient parsing error for scan {row['id']}: {e}")
            
            # Create scan entry with all the details
            scan_entry = {
                'scan_id': row['scan_id'],
                'date': scan_date.strftime("%m/%d/%Y"),
                'time': scan_date.strftime("%I:%M %p"),
                'rating_type': rating_type,
                'confidence': 'high',
                'ingredient_summary': ingredient_summary,
                'has_gmo': has_gmo,
                'image_url': row['image_url'],
                'detected_ingredients': detected_ingredients,
                'raw_rating': rating,  # Keep the original rating text
                'extracted_text': '',  # Add if you store this
                'text_length': 0
            }
            
            print(f"DEBUG: Scan entry created: {scan_entry['scan_id']} - {len(ingredient_summary)} categories")
            
            scans.append(scan_entry)
            stats['total_scans'] += 1
        
        conn.close()
        
        print(f"DEBUG: Returning {len(scans)} scans with stats: {stats}")
        return render_template('history.html', scans=scans, stats=stats)
        
    except Exception as e:
        print(f"History error: {e}")
        import traceback
        traceback.print_exc()
        return render_template('history.html', scans=[], stats={
            'total_scans': 0,
            'safe_scans': 0,
            'danger_scans': 0,
            'ingredients_found': 0
        })


# Also add this debug route to check what's actually in your database
@app.route('/debug-history')
@login_required
def debug_history():
    """Debug route to see raw scan history data"""
    try:
        conn = sqlite3.connect('foodfixr.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, scan_date, result_rating, ingredients_found, image_url, scan_id
            FROM scan_history 
            WHERE user_id = ? 
            ORDER BY scan_date DESC 
            LIMIT 10
        ''', (session['user_id'],))
        
        rows = cursor.fetchall()
        conn.close()
        
        html = """
        <html>
        <head><title>Debug Scan History</title></head>
        <body style="font-family: monospace; padding: 20px; background: #f5f5f5;">
        <h1>🔍 Debug Scan History</h1>
        """
        
        for row in rows:
            html += f"""
            <div style="background: white; padding: 20px; margin: 10px 0; border-radius: 8px; border-left: 4px solid #e50ce8;">
            <h3>Scan ID: {row['scan_id']}</h3>
            <p><strong>Date:</strong> {row['scan_date']}</p>
            <p><strong>Rating:</strong> {row['result_rating']}</p>
            <p><strong>Image:</strong> {row['image_url'] or 'None'}</p>
            <p><strong>Ingredients Found (Raw JSON):</strong></p>
            <pre style="background: #f8f9fa; padding: 10px; border-radius: 4px; overflow-x: auto;">{row['ingredients_found'] or 'None'}</pre>
            </div>
            """
        
        html += """
        <br>
        <a href="/history" style="background: #e91e63; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px;">← Back to History</a>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        return f"<html><body><h1>Debug Error</h1><p>{str(e)}</p></body></html>"
        
@app.route('/upgrade')
@login_required
def upgrade():
    """Upgrade page for premium plans"""
    user_data = get_user_data(session['user_id'])
    trial_time_left, trial_expired, _, _ = calculate_trial_time_left(user_data['trial_start_date'])
    
    return render_template('upgrade.html',
                         trial_expired=trial_expired,
                         trial_time_left=trial_time_left,
                         stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)

# STRIPE AND PAYMENT ROUTES
@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    """Create Stripe checkout session"""
    try:
        data = request.get_json()
        plan = data.get('plan', 'monthly')
        
        if not stripe.api_key:
            print("ERROR: Stripe API key not configured")
            return jsonify({'error': 'Payment system not configured. Please contact support.'}), 500
        
        prices = {
            'weekly': {'price_id': os.getenv('STRIPE_WEEKLY_PRICE_ID'), 'amount': 3.99},
            'monthly': {'price_id': os.getenv('STRIPE_MONTHLY_PRICE_ID'), 'amount': 11.99},
            'yearly': {'price_id': os.getenv('STRIPE_YEARLY_PRICE_ID'), 'amount': 95.00}
        }
        
        if plan not in prices:
            return jsonify({'error': 'Invalid plan selected'}), 400
        
        price_id = prices[plan]['price_id']
        if not price_id:
            return jsonify({'error': f'Price not configured for {plan} plan. Please contact support.'}), 500
        
        success_url = f"{DOMAIN}/success?session_id={{CHECKOUT_SESSION_ID}}&plan={plan}"
        cancel_url = f"{DOMAIN}/upgrade"
        
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'user_id': session.get('user_id'),
                'plan': plan
            },
            customer_email=data.get('email') if data.get('email') else None,
        )
        
        return jsonify({'checkout_url': checkout_session.url})
        
    except Exception as e:
        print(f"Unexpected error in create_checkout_session: {str(e)}")
        return jsonify({'error': 'Failed to create checkout session. Please try again.'}), 500

@app.route('/success')
@login_required
def success():
    """Handle successful payment"""
    try:
        session_id = request.args.get('session_id')
        plan = request.args.get('plan', 'monthly')
        
        if session_id:
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            
            if checkout_session.payment_status == 'paid':
                # Update user in database
                conn = sqlite3.connect('foodfixr.db')
                cursor = conn.cursor()
                
                now = datetime.now()
                next_billing = now + timedelta(days=7 if plan == 'weekly' else (30 if plan == 'monthly' else 365))
                
                cursor.execute('''
                    UPDATE users 
                    SET is_premium = 1, subscription_status = 'active', 
                        subscription_start_date = ?, next_billing_date = ?,
                        stripe_customer_id = ?, scans_used = 0
                    WHERE id = ?
                ''', (format_datetime_for_db(now), format_datetime_for_db(next_billing), 
                      checkout_session.customer, session['user_id']))
                
                conn.commit()
                conn.close()
                
                # Update session
                session['is_premium'] = True
                session['stripe_customer_id'] = checkout_session.customer
                session['scans_used'] = 0
                
                return render_template('success.html', plan=plan)
        
        return redirect(url_for('index'))
        
    except Exception as e:
        print(f"Success page error: {e}")
        return redirect(url_for('index'))

@app.route('/create-customer-portal', methods=['POST'])
@login_required
def create_customer_portal():
    """Create Stripe Customer Portal session for subscription management"""
    try:
        if not session.get('is_premium'):
            return jsonify({'error': 'No active subscription'}), 400
        
        customer_id = session.get('stripe_customer_id')
        if not customer_id:
            return jsonify({'error': 'No customer ID found'}), 400
        
        # Create customer portal session
        portal_session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{DOMAIN}/account",
        )
        
        return jsonify({'portal_url': portal_session.url})
        
    except Exception as e:
        print(f"Customer portal error: {e}")
        return jsonify({'error': 'Unable to create portal session'}), 500

@app.route('/cancel-subscription', methods=['POST'])
@login_required
def cancel_subscription():
    """Cancel user's subscription"""
    try:
        if not session.get('is_premium'):
            return jsonify({'error': 'No active subscription'}), 400
        
        customer_id = session.get('stripe_customer_id')
        if not customer_id:
            return jsonify({'error': 'No customer ID found'}), 400
        
        # Get customer's subscriptions
        subscriptions = stripe.Subscription.list(customer=customer_id)
        
        for subscription in subscriptions.data:
            if subscription.status == 'active':
                # Cancel the subscription at period end
                stripe.Subscription.modify(
                    subscription.id,
                    cancel_at_period_end=True
                )
                
                # Update database
                conn = sqlite3.connect('foodfixr.db')
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users 
                    SET subscription_status = 'cancelled'
                    WHERE id = ?
                ''', (session['user_id'],))
                conn.commit()
                conn.close()
                
                return jsonify({
                    'success': True, 
                    'message': 'Subscription will be cancelled at the end of your billing period'
                })
        
        return jsonify({'error': 'No active subscription found'}), 400
        
    except Exception as e:
        print(f"Cancellation error: {e}")
        return jsonify({'error': 'Failed to cancel subscription'}), 500

# UTILITY ROUTES
@app.route('/clear-history', methods=['POST'])
@login_required
def clear_history():
    """Clear user's scan history"""
    try:
        conn = sqlite3.connect('foodfixr.db')
        cursor = conn.cursor()
        
        # Get user's image URLs before deleting
        cursor.execute('SELECT image_url FROM scan_history WHERE user_id = ?', (session['user_id'],))
        image_urls = [row[0] for row in cursor.fetchall() if row[0]]
        
        # Delete user's scan history
        cursor.execute('DELETE FROM scan_history WHERE user_id = ?', (session['user_id'],))
        conn.commit()
        conn.close()
        
        # Delete user's images
        for image_url in image_urls:
            try:
                if image_url.startswith('/static/'):
                    image_path = image_url[1:]  # Remove leading slash
                    if os.path.exists(image_path):
                        os.remove(image_path)
                        print(f"Deleted image: {image_path}")
            except Exception as e:
                print(f"Error deleting image {image_url}: {e}")
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Clear history error: {e}")
        return jsonify({'error': 'Failed to clear history'}), 500

@app.route('/export-history')
@login_required
def export_history():
    """Export user's scan history as JSON"""
    try:
        conn = sqlite3.connect('foodfixr.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM scan_history 
            WHERE user_id = ? 
            ORDER BY scan_date DESC
        ''', (session['user_id'],))
        
        scans = []
        for row in cursor.fetchall():
            scans.append(dict(row))
        
        conn.close()
        
        # Create temporary file for export
        import tempfile
        import json
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(scans, f, indent=2, default=str)
            temp_path = f.name
        
        return send_file(
            temp_path,
            as_attachment=True,
            download_name=f'foodfixr_history_{datetime.now().strftime("%Y%m%d")}.json',
            mimetype='application/json'
        )
        
    except Exception as e:
        print(f"Export error: {e}")
        flash('Failed to export history', 'error')
        return redirect(url_for('history'))

# DEBUG AND TESTING ROUTES
@app.route('/test-password-flow')
def test_password_flow():
    """Test the complete registration and login flow"""
    try:
        # Test password hashing and verification
        test_password = "testpass123"
        
        # Test 1: Hash with your registration method
        reg_hash = generate_password_hash(test_password)
        
        # Test 2: Verify with your login method  
        login_verify = check_password_hash(reg_hash, test_password)
        
        # Test 3: Database round trip
        conn = sqlite3.connect('foodfixr.db')
        cursor = conn.cursor()
        
        # Create a test entry
        test_email = f"test_{int(time.time())}@example.com"
        cursor.execute('''
            INSERT INTO users (name, email, password_hash, trial_start_date, trial_end_date, last_login)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('Test User', test_email, reg_hash, format_datetime_for_db(), 
              format_datetime_for_db(datetime.now() + timedelta(hours=48)), format_datetime_for_db()))
        
        # Retrieve and test
        cursor.execute('SELECT password_hash FROM users WHERE email = ?', (test_email,))
        db_hash = cursor.fetchone()[0]
        db_verify = check_password_hash(db_hash, test_password)
        
        # Clean up
        cursor.execute('DELETE FROM users WHERE email = ?', (test_email,))
        conn.commit()
        conn.close()
        
        # Test 4: Check if werkzeug version changed
        from werkzeug import __version__ as werkzeug_version
        
        results = f"""
        <html>
        <head><title>Password Flow Test</title></head>
        <body style="font-family: monospace; padding: 20px;">
        <h1>🔐 Password Flow Test Results</h1>
        
        <div style="background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px;">
        <strong>Werkzeug Version:</strong> {werkzeug_version}<br>
        <strong>Test Password:</strong> {test_password}<br>
        <strong>Generated Hash:</strong> {reg_hash[:50]}...<br>
        <strong>Hash Method:</strong> {'pbkdf2' if 'pbkdf2' in reg_hash else 'scrypt' if 'scrypt' in reg_hash else 'other'}<br>
        </div>
        
        <div style="background: {'#e8f5e8' if login_verify else '#ffe8e8'}; padding: 15px; margin: 10px 0; border-radius: 5px;">
        <strong>Direct Verification:</strong> {'✅ PASS' if login_verify else '❌ FAIL'}<br>
        </div>
        
        <div style="background: {'#e8f5e8' if db_verify else '#ffe8e8'}; padding: 15px; margin: 10px 0; border-radius: 5px;">
        <strong>Database Round Trip:</strong> {'✅ PASS' if db_verify else '❌ FAIL'}<br>
        <strong>DB Hash Matches:</strong> {'✅ YES' if reg_hash == db_hash else '❌ NO'}<br>
        </div>
        
        <div style="margin: 20px 0;">
        <a href="/register" style="background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Try Register</a>
        <a href="/login" style="background: #2196F3; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-left: 10px;">Try Login</a>
        </div>
        </body>
        </html>
        """
        return results
        
    except Exception as e:
        return f"<html><body><h1>Test Failed</h1><p>Error: {str(e)}</p></body></html>"

@app.route('/diagnose-user/<email>')
def diagnose_user(email):
    """Diagnose a specific user's password hash"""
    try:
        conn = sqlite3.connect('foodfixr.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE email = ?', (email.lower(),))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return f"<html><body><h1>User not found: {email}</h1></body></html>"
        
        hash_info = user['password_hash']
        hash_method = "unknown"
        
        if hash_info.startswith('pbkdf2:'):
            hash_method = "pbkdf2"
        elif hash_info.startswith('scrypt:'):
            hash_method = "scrypt"
        elif '
         in hash_info:
            hash_method = hash_info.split('
        )[0]
        
        return f"""
        <html>
        <head><title>User Diagnosis: {email}</title></head>
        <body style="font-family: monospace; padding: 20px;">
        <h1>🔍 User Diagnosis: {email}</h1>
        <div style="background: #f5f5f5; padding: 15px; border-radius: 5px;">
        <strong>Name:</strong> {user['name']}<br>
        <strong>Email:</strong> {user['email']}<br>
        <strong>Created:</strong> {user['created_at']}<br>
        <strong>Hash Method:</strong> {hash_method}<br>
        <strong>Hash Preview:</strong> {hash_info[:50]}...<br>
        <strong>Full Hash:</strong> {hash_info}<br>
        </div>
        <br>
        <a href="/fix-user-password/{email}" style="background: #ff9800; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Fix This User's Password</a>
        </body>
        </html>
        """
        
    except Exception as e:
        return f"<html><body><h1>Error</h1><p>{str(e)}</p></body></html>"

@app.route('/fix-user-password/<email>')
def fix_user_password(email):
    """Fix a specific user's password to a known value"""
    try:
        conn = sqlite3.connect('foodfixr.db')
        cursor = conn.cursor()
        
        # Set password to 'reset123'
        new_password = 'reset123'
        new_hash = generate_password_hash(new_password)
        
        cursor.execute('UPDATE users SET password_hash = ? WHERE email = ?', (new_hash, email.lower()))
        updated = cursor.rowcount
        conn.commit()
        conn.close()
        
        if updated:
            return f"""
            <html>
            <head><title>Password Fixed</title></head>
            <body style="font-family: Arial; padding: 20px;">
            <h1>✅ Password Fixed for {email}</h1>
            <p><strong>New Password:</strong> reset123</p>
            <a href="/login" style="background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Try Login</a>
            </body>
            </html>
            """
        else:
            return f"<html><body><h1>User not found: {email}</h1></body></html>"
            
    except Exception as e:
        return f"<html><body><h1>Error</h1><p>{str(e)}</p></body></html>"

@app.route('/debug-users')
def debug_users():
    """Debug route to check users in database"""
    try:
        conn = sqlite3.connect('foodfixr.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, name, email, password_hash, created_at FROM users ORDER BY created_at DESC LIMIT 10')
        users = cursor.fetchall()
        
        conn.close()
        
        html = """
        <html>
        <head><title>Debug Users</title></head>
        <body style="font-family: monospace; padding: 20px;">
        <h1>🔍 Users in Database</h1>
        <table border="1" style="border-collapse: collapse; width: 100%;">
        <tr>
            <th style="padding: 8px;">ID</th>
            <th style="padding: 8px;">Name</th>
            <th style="padding: 8px;">Email</th>
            <th style="padding: 8px;">Hash Method</th>
            <th style="padding: 8px;">Created At</th>
            <th style="padding: 8px;">Actions</th>
        </tr>
        """
        
        for user in users:
            hash_method = "pbkdf2" if "pbkdf2" in user['password_hash'] else "scrypt" if "scrypt" in user['password_hash'] else "other"
            html += f"""
            <tr>
                <td style="padding: 8px;">{user['id']}</td>
                <td style="padding: 8px;">{user['name']}</td>
                <td style="padding: 8px;">{user['email']}</td>
                <td style="padding: 8px;">{hash_method}</td>
                <td style="padding: 8px;">{user['created_at']}</td>
                <td style="padding: 8px;"><a href="/diagnose-user/{user['email']}">Diagnose</a></td>
            </tr>
            """
        
        html += """
        </table>
        <br>
        <a href="/fix-all-passwords" style="background: #ff9800; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px;">🔧 Fix All Passwords</a>
        <a href="/create-test-user" style="background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px;">👤 Create Test User</a>
        <a href="/test-password-flow" style="background: #9C27B0; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px;">🔐 Test Password Flow</a>
        <a href="/" style="background: #e91e63; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">← Back</a>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        return f"Database error: {str(e)}"

@app.route('/fix-all-passwords')
def fix_all_passwords():
    """Fix all password hashes to use consistent format"""
    try:
        conn = sqlite3.connect('foodfixr.db')
        cursor = conn.cursor()
        
        # Set all users to have a default password with consistent hashing
        default_password = 'foodfixr123'
        consistent_hash = generate_password_hash(default_password)
        
        cursor.execute('UPDATE users SET password_hash = ?', (consistent_hash,))
        updated_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return f"""
        <html>
        <head><title>Password Fix Complete</title></head>
        <body style="font-family: Arial; padding: 20px;">
        <h1>✅ Password Fix Complete</h1>
        <p><strong>{updated_count} users updated</strong></p>
        <p>All users can now login with password: <code>foodfixr123</code></p>
        <br>
        <a href="/login" style="background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Try Login</a>
        <a href="/debug-users" style="background: #2196F3; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-left: 10px;">Check Users</a>
        </body>
        </html>
        """
        
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/create-test-user')
def create_test_user():
    """Create a test user with known credentials"""
    try:
        conn = sqlite3.connect('foodfixr.db')
        cursor = conn.cursor()
        
        test_email = 'test@foodfixr.com'
        test_password = 'test123'
        
        # Delete existing test user
        cursor.execute('DELETE FROM users WHERE email = ?', (test_email,))
        
        # Create new test user with consistent hashing
        password_hash = generate_password_hash(test_password)
        now = datetime.now()
        trial_start = format_datetime_for_db(now)
        trial_end = format_datetime_for_db(now + timedelta(hours=48))
        
        cursor.execute('''
            INSERT INTO users (name, email, password_hash, trial_start_date, trial_end_date, last_login)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('Test User', test_email, password_hash, trial_start, trial_end, format_datetime_for_db(now)))
        
        conn.commit()
        conn.close()
        
        return f"""
        <html>
        <head><title>Test User Created</title></head>
        <body style="font-family: Arial; padding: 20px;">
        <h1>✅ Test User Created Successfully</h1>
        <div style="background: #f0f8f0; padding: 20px; border-radius: 8px; margin: 20px 0;">
        <p><strong>Email:</strong> test@foodfixr.com</p>
        <p><strong>Password:</strong> test123</p>
        </div>
        <a href="/login" style="background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Try Login</a>
        </body>
        </html>
        """
        
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/debug')
def debug():
    """Debug endpoint to check system status"""
    import sys
    import platform
    
    debug_info = []
    debug_info.append(f"Python version: {sys.version}")
    debug_info.append(f"Platform: {platform.platform()}")
    debug_info.append(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
    debug_info.append(f"Upload folder exists: {os.path.exists(app.config['UPLOAD_FOLDER'])}")
    
    try:
        from ingredient_scanner import extract_text_with_multiple_methods
        debug_info.append("✅ OCR.space functions: Available")
    except Exception as e:
        debug_info.append(f"❌ OCR.space functions: Failed - {str(e)}")
    
    try:
        from PIL import Image
        test_img = Image.new('RGB', (100, 30), color='white')
        debug_info.append("✅ PIL/Pillow: Working")
    except Exception as e:
        debug_info.append(f"❌ PIL/Pillow: Failed - {str(e)}")
    
    try:
        import requests
        response = requests.get('https://httpbin.org/get', timeout=5)
        if response.status_code == 200:
            debug_info.append("✅ Internet connectivity: Working")
        else:
            debug_info.append(f"⚠️ Internet connectivity: HTTP {response.status_code}")
    except Exception as e:
        debug_info.append(f"❌ Internet connectivity: Failed - {str(e)}")
    
    try:
        from ingredient_scanner import scan_image_for_ingredients
        debug_info.append("✅ Modules: All imported successfully")
    except Exception as e:
        debug_info.append(f"❌ Modules: Import failed - {str(e)}")
    
    debug_info.append(f"Templates folder exists: {os.path.exists('templates')}")
    debug_info.append(f"Scanner.html exists: {os.path.exists('templates/scanner.html')}")
    debug_info.append(f"Static folder exists: {os.path.exists('static')}")
    
    # Test database
    try:
        conn = sqlite3.connect('foodfixr.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        user_count = cursor.fetchone()[0]
        debug_info.append(f"✅ Database: {user_count} users registered")
        conn.close()
    except Exception as e:
        debug_info.append(f"❌ Database: Failed - {str(e)}")
    
    # Test Stripe configuration
    try:
        if stripe.api_key:
            debug_info.append("✅ Stripe: API key configured")
            stripe.Account.retrieve()
            debug_info.append("✅ Stripe: Connection successful")
        else:
            debug_info.append("❌ Stripe: API key not configured")
    except Exception as e:
        debug_info.append(f"⚠️ Stripe: {str(e)}")
    
    # Test password hashing
    try:
        test_pass = "test123"
        test_hash = generate_password_hash(test_pass)
        test_verify = check_password_hash(test_hash, test_pass)
        debug_info.append(f"✅ Password hashing: Hash={test_hash[:20]}... Verify={test_verify}")
    except Exception as e:
        debug_info.append(f"❌ Password hashing: Failed - {str(e)}")
    
    # Test Werkzeug version
    try:
        from werkzeug import __version__ as werkzeug_version
        debug_info.append(f"✅ Werkzeug version: {werkzeug_version}")
    except Exception as e:
        debug_info.append(f"❌ Werkzeug version: Failed - {str(e)}")
    
    html = f"""
    <html>
    <head><title>FoodFixr System Debug</title></head>
    <body style="font-family: monospace; padding: 20px; background: #f5f5f5;">
    <h1>🔍 FoodFixr System Debug</h1>
    <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
    {'<br>'.join(debug_info)}
    </div>
    <div style="margin: 20px 0;">
    <a href="/debug-users" style="background: #2196F3; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px;">👥 Debug Users</a>
    <a href="/create-test-user" style="background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px;">👤 Create Test User</a>
    <a href="/fix-all-passwords" style="background: #ff9800; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px;">🔧 Fix Passwords</a>
    <a href="/test-password-flow" style="background: #9C27B0; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px;">🔐 Test Password Flow</a>
    <a href="/" style="background: #e91e63; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">← Back to App</a>
    </div>
    </body>
    </html>
    """
    return html

# DEMO AND SETUP FUNCTIONS
def create_demo_user():
    """Create demo user for testing"""
    try:
        conn = sqlite3.connect('foodfixr.db')
        cursor = conn.cursor()
        
        demo_email = 'demo@foodfixr.com'
        demo_password = 'demo123'
        
        # Check if demo user exists
        cursor.execute('SELECT id FROM users WHERE email = ?', (demo_email,))
        if cursor.fetchone():
            print("Demo user already exists")
            conn.close()
            return
        
        # Create demo user with consistent hashing
        password_hash = generate_password_hash(demo_password)
        now = datetime.now()
        trial_start = now - timedelta(hours=2)
        trial_end = trial_start + timedelta(hours=48)
        
        cursor.execute('''
            INSERT INTO users (name, email, password_hash, trial_start_date, trial_end_date, 
                              scans_used, total_scans_ever, last_login)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('Demo User', demo_email, password_hash, format_datetime_for_db(trial_start), 
              format_datetime_for_db(trial_end), 3, 15, format_datetime_for_db(now)))
        
        demo_user_id = cursor.lastrowid
        
        # Add sample scan history
        sample_scans = [
            ('Safe', '{"sugar": ["organic cane sugar"]}', now - timedelta(hours=1)),
            ('Proceed carefully', '{"corn": ["high fructose corn syrup"]}', now - timedelta(minutes=30)),
            ('Danger', '{"trans_fat": ["partially hydrogenated oil"]}', now - timedelta(minutes=10))
        ]
        
        for rating, ingredients, scan_date in sample_scans:
            cursor.execute('''
                INSERT INTO scan_history (user_id, result_rating, ingredients_found, scan_date, scan_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (demo_user_id, rating, ingredients, format_datetime_for_db(scan_date), str(uuid.uuid4())))
        
        conn.commit()
        conn.close()
        print("✅ Demo user created: demo@foodfixr.com / demo123")
        
    except Exception as e:
        print(f"Error creating demo user: {e}")

if __name__ == '__main__':
    # Create demo user on startup
    create_demo_user()
    
    # Start the application
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
