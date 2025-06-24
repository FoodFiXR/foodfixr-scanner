from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_file, Response
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
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_string, fmt)
        except ValueError:
            continue
    
    # If all formats fail, try to clean the string
    try:
        clean_date = date_string.split('.')[0]
        return datetime.strptime(clean_date, '%Y-%m-%d %H:%M:%S')
    except ValueError:
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
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
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
        
        conn = sqlite3.connect('foodfixr.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            flash('An account with this email already exists', 'error')
            conn.close()
            return render_template('register.html')
        
        password_hash = generate_password_hash(password)
        now = datetime.now()
        trial_start = format_datetime_for_db(now)
        trial_end = format_datetime_for_db(now + timedelta(hours=48))
        
        try:
            cursor.execute('''
                INSERT INTO users (name, email, password_hash, trial_start_date, trial_end_date, last_login)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (name, email, password_hash, trial_start, trial_end, format_datetime_for_db(now)))
            
            user_id = cursor.lastrowid
            conn.commit()
            
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
        
        conn = sqlite3.connect('foodfixr.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            cursor.execute('UPDATE users SET last_login = ? WHERE id = ?', 
                         (format_datetime_for_db(), user['id']))
            conn.commit()
            
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
    """Handle image scanning with trial limits"""
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
                             error="No image uploaded.",
                             stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)
    
    file = request.files['image']
    if file.filename == '' or not allowed_file(file.filename):
        return render_template('scanner.html',
                             trial_expired=trial_expired,
                             trial_time_left=trial_time_left,
                             user_name=user_data['name'],
                             error="Invalid file. Please upload an image.",
                             stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)
    
    try:
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        file.save(filepath)
        
        scan_id = str(uuid.uuid4())
        image_url = save_scan_image(filepath, session.get('user_id'), scan_id)
        
        result = scan_image_for_ingredients(filepath)
        
        conn = sqlite3.connect('foodfixr.db')
        cursor = conn.cursor()
        
        new_scans_used = user_data['scans_used'] + 1 if not user_data['is_premium'] else user_data['scans_used']
        new_total_scans = user_data['total_scans_ever'] + 1
        
        cursor.execute('''
            UPDATE users 
            SET scans_used = ?, total_scans_ever = ?
            WHERE id = ?
        ''', (new_scans_used, new_total_scans, session['user_id']))
        
        cursor.execute('''
            INSERT INTO scan_history (user_id, result_rating, ingredients_found, image_url, scan_id, scan_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], result.get('rating', ''), str(result.get('matched_ingredients', {})), 
              image_url, scan_id, format_datetime_for_db()))
        
        conn.commit()
        conn.close()
        
        session['scans_used'] = new_scans_used
        
        try:
            os.remove(filepath)
        except:
            pass
        
        return render_template('scanner.html',
                             result=result,
                             trial_expired=trial_expired,
                             trial_time_left=trial_time_left,
                             user_name=user_data['name'],
                             stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)
        
    except Exception as e:
        return render_template('scanner.html',
                             trial_expired=trial_expired,
                             trial_time_left=trial_time_left,
                             user_name=user_data['name'],
                             error=f"Scanning failed: {str(e)}. Please try again.",
                             stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)

@app.route('/account')
@login_required
def account():
    """User account page with subscription management"""
    user_data = get_user_data(session['user_id'])
    if not user_data:
        return redirect(url_for('logout'))
    
    trial_time_left, trial_expired, trial_hours, trial_minutes = calculate_trial_time_left(user_data['trial_start_date'])
    
    days_until_renewal = None
    if user_data['is_premium'] and user_data['next_billing_date']:
        days_until_renewal = calculate_renewal_days(user_data['next_billing_date'])
    
    created_date = safe_datetime_parse(user_data['created_at'])
    formatted_created_date = created_date.strftime('%B %d, %Y')
    
    trial_start = safe_datetime_parse(user_data['trial_start_date'])
    formatted_trial_start = trial_start.strftime('%B %d, %Y')
    
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
                         days_until_renewal=days_until_renewal)

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
            
            ingredient_summary = {}
            has_gmo = False
            detected_ingredients = []
            
            try:
                if row['ingredients_found']:
                    matched_ingredients = json.loads(row['ingredients_found'])
                    
                    if isinstance(matched_ingredients, dict):
                        for category, ingredients in matched_ingredients.items():
                            if isinstance(ingredients, list) and ingredients:
                                ingredient_summary[category] = len(ingredients)
                                detected_ingredients.extend(ingredients)
                                if category == 'gmo':
                                    has_gmo = True
                                stats['ingredients_found'] += len(ingredients)
                            elif isinstance(ingredients, str) and ingredients:
                                ingredient_summary[category] = 1
                                detected_ingredients.append(ingredients)
                                if category == 'gmo':
                                    has_gmo = True
                                stats['ingredients_found'] += 1
                    
                    if 'all_detected' in matched_ingredients:
                        all_detected = matched_ingredients['all_detected']
                        if isinstance(all_detected, list):
                            detected_ingredients.extend(all_detected)
            except:
                if row['ingredients_found']:
                    ingredient_summary['other'] = 1
                    detected_ingredients = [row['ingredients_found']]
            
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
                'raw_rating': rating,
                'extracted_text': '',
                'text_length': 0
            }
            
            scans.append(scan_entry)
            stats['total_scans'] += 1
        
        conn.close()
        return render_template('history.html', scans=scans, stats=stats)
        
    except Exception as e:
        return render_template('history.html', scans=[], stats={
            'total_scans': 0,
            'safe_scans': 0,
            'danger_scans': 0,
            'ingredients_found': 0
        })

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

# STRIPE ROUTES
@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    """Create Stripe checkout session"""
    try:
        data = request.get_json()
        plan = data.get('plan', 'monthly')
        
        if not stripe.api_key:
            return jsonify({'error': 'Payment system not configured'}), 500
        
        prices = {
            'weekly': {'price_id': os.getenv('STRIPE_WEEKLY_PRICE_ID')},
            'monthly': {'price_id': os.getenv('STRIPE_MONTHLY_PRICE_ID')},
            'yearly': {'price_id': os.getenv('STRIPE_YEARLY_PRICE_ID')}
        }
        
        if plan not in prices or not prices[plan]['price_id']:
            return jsonify({'error': f'Plan not configured: {plan}'}), 400
        
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price': prices[plan]['price_id'], 'quantity': 1}],
            mode='subscription',
            success_url=f"{DOMAIN}/success?session_id={{CHECKOUT_SESSION_ID}}&plan={plan}",
            cancel_url=f"{DOMAIN}/upgrade",
            metadata={'user_id': session.get('user_id'), 'plan': plan},
            customer_email=data.get('email') if data.get('email') else None,
        )
        
        return jsonify({'checkout_url': checkout_session.url})
        
    except Exception as e:
        return jsonify({'error': 'Failed to create checkout session'}), 500

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
                
                session['is_premium'] = True
                session['stripe_customer_id'] = checkout_session.customer
                session['scans_used'] = 0
                
                return render_template('success.html', plan=plan)
        
        return redirect(url_for('index'))
        
    except Exception as e:
        return redirect(url_for('index'))

@app.route('/create-customer-portal', methods=['POST'])
@login_required
def create_customer_portal():
    """Create Stripe Customer Portal session"""
    try:
        if not session.get('is_premium'):
            return jsonify({'error': 'No active subscription found'}), 400
        
        customer_id = session.get('stripe_customer_id')
        if not customer_id:
            user_data = get_user_data(session['user_id'])
            if user_data and user_data.get('stripe_customer_id'):
                customer_id = user_data['stripe_customer_id']
                session['stripe_customer_id'] = customer_id
            else:
                return jsonify({'error': 'No customer ID found'}), 400
        
        portal_session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{DOMAIN}/account",
        )
        
        return jsonify({'success': True, 'portal_url': portal_session.url})
        
    except Exception as e:
        return jsonify({'error': 'Unable to create billing portal'}), 500

# UTILITY ROUTES
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
            scan_dict = dict(row)
            for key, value in scan_dict.items():
                if key == 'scan_date' and value:
                    try:
                        parsed_date = safe_datetime_parse(value)
                        scan_dict[key] = parsed_date.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        scan_dict[key] = str(value)
                elif value is None:
                    scan_dict[key] = ""
                else:
                    scan_dict[key] = str(value)
            scans.append(scan_dict)
        
        conn.close()
        
        export_data = {
            'export_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'user_id': session.get('user_id'),
            'total_scans': len(scans),
            'scans': scans
        }
        
        return Response(
            json.dumps(export_data, indent=2, ensure_ascii=False),
            mimetype='application/json',
            headers={
                'Content-Disposition': f'attachment; filename=foodfixr_history_{datetime.now().strftime("%Y%m%d")}.json'
            }
        )
        
    except Exception as e:
        flash('Failed to export history', 'error')
        return redirect(url_for('history'))

# DEBUG ROUTES
@app.route('/debug-billing')
@login_required
def debug_billing():
    """Debug billing portal issues"""
    user_data = get_user_data(session['user_id'])
    
    return f"""
    <html>
    <head><title>Billing Debug</title></head>
    <body style="font-family: monospace; padding: 20px;">
    <h1>💳 Billing Debug</h1>
    <p><strong>User ID:</strong> {session.get('user_id')}</p>
    <p><strong>Is Premium:</strong> {session.get('is_premium')}</p>
    <p><strong>Customer ID (Session):</strong> {session.get('stripe_customer_id')}</p>
    <p><strong>Customer ID (DB):</strong> {user_data.get('stripe_customer_id') if user_data else None}</p>
    <p><strong>Stripe API Key:</strong> {bool(stripe.api_key)}</p>
    <br>
    <a href="/account" style="background: #e91e63; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">← Back to Account</a>
    </body>
    </html>
    """

@app.route('/debug-history')
@login_required
def debug_history():
    """Debug scan history data"""
    try:
        conn = sqlite3.connect('foodfixr.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, scan_date, result_rating, ingredients_found, image_url, scan_id
            FROM scan_history 
            WHERE user_id = ? 
            ORDER BY scan_date DESC 
            LIMIT 5
        ''', (session['user_id'],))
        
        rows = cursor.fetchall()
        conn.close()
        
        html = """
        <html>
        <head><title>Debug History</title></head>
        <body style="font-family: monospace; padding: 20px;">
        <h1>🔍 Debug History</h1>
        """
        
        for row in rows:
            html += f"""
            <div style="background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px;">
            <h3>Scan: {row['scan_id']}</h3>
            <p><strong>Date:</strong> {row['scan_date']}</p>
            <p><strong>Rating:</strong> {row['result_rating']}</p>
            <p><strong>Ingredients:</strong> {row['ingredients_found'] or 'None'}</p>
            </div>
            """
        
        html += '<br><a href="/history" style="background: #e91e63; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">← Back</a></body></html>'
        return html
        
    except Exception as e:
        return f"<html><body><h1>Error</h1><p>{str(e)}</p></body></html>"

if __name__ == '__main__':
    # Start the application
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
