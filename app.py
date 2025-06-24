from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
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

# AUTHENTICATION ROUTES
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        if not email or not password:
            flash('Please enter both email and password', 'error')
            return render_template('login.html')
        
        conn = sqlite3.connect('foodfixr.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
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
            flash('Invalid email or password', 'error')
            conn.close()
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
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
        
        # Create new user with trial period
        password_hash = generate_password_hash(password)
        now = datetime.now()
        trial_start = format_datetime_for_db(now)
        trial_end = format_datetime_for_db(now + timedelta(hours=48))
        last_login = format_datetime_for_db(now)
        
        cursor.execute('''
            INSERT INTO users (name, email, password_hash, trial_start_date, trial_end_date, last_login)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, email, password_hash, trial_start, trial_end, last_login))
        
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Auto-login after registration
        session.permanent = True
        session['user_id'] = user_id
        session['user_email'] = email
        session['user_name'] = name
        session['is_premium'] = False
        session['scans_used'] = 0
        session['stripe_customer_id'] = None
        
        flash(f'Welcome to FoodFixr, {name}! Your free trial has started.', 'success')
        return redirect(url_for('index'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    user_name = session.get('user_name', 'User')
    session.clear()
    flash(f'Goodbye {user_name}! You have been logged out.', 'info')
    return redirect(url_for('login'))

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

@app.route('/history')
@login_required
def history():
    """Display scan history from database"""
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
            if 'Safe' in rating:
                rating_type = 'safe'
                stats['safe_scans'] += 1
            elif 'Danger' in rating:
                rating_type = 'danger'
                stats['danger_scans'] += 1
            elif 'Proceed' in rating:
                rating_type = 'caution'
            
            # Process ingredients (stored as JSON string)
            ingredient_summary = {}
            has_gmo = False
            
            try:
                if row['ingredients_found']:
                    matched_ingredients = json.loads(row['ingredients_found'])
                    for category, ingredients in matched_ingredients.items():
                        if isinstance(ingredients, list) and ingredients:
                            ingredient_summary[category] = len(ingredients)
                            if category == 'gmo':
                                has_gmo = True
                    stats['ingredients_found'] += len(matched_ingredients.get('all_detected', []))
            except:
                pass
            
            scan_entry = {
                'scan_id': row['scan_id'],
                'date': scan_date.strftime("%m/%d/%Y"),
                'time': scan_date.strftime("%I:%M %p"),
                'rating_type': rating_type,
                'confidence': 'high',
                'ingredient_summary': ingredient_summary,
                'has_gmo': has_gmo,
                'image_url': row['image_url']
            }
            
            scans.append(scan_entry)
            stats['total_scans'] += 1
        
        conn.close()
        return render_template('history.html', scans=scans, stats=stats)
        
    except Exception as e:
        print(f"History error: {e}")
        return render_template('history.html', scans=[], stats=None)

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
