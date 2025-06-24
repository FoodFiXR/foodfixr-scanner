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

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Stripe Configuration
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
DOMAIN = os.getenv('DOMAIN', 'https://foodfixr-scanner-1.onrender.com')

# Configuration
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.permanent_session_lifetime = timedelta(days=30)

# Database initialization
def init_db():
    conn = sqlite3.connect('foodfixr.db')
    cursor = conn.cursor()
    
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
    print("Database initialized successfully")

init_db()

# Helper functions
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/working-login')
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

# WORKING LOGIN ROUTE - COMPLETELY SELF CONTAINED
@app.route('/working-login', methods=['GET', 'POST'])
def working_login():
    error_msg = None
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        print(f"DEBUG: Working login attempt for: {email}")
        
        if not email or not password:
            error_msg = "Please enter both email and password"
        else:
            conn = sqlite3.connect('foodfixr.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
            user = cursor.fetchone()
            
            if user:
                print(f"DEBUG: User found: {user['name']}")
                if check_password_hash(user['password_hash'], password):
                    print("DEBUG: Password correct!")
                    
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
                    
                    print("DEBUG: Session set, redirecting...")
                    return redirect('/')
                else:
                    error_msg = "Invalid password"
                    print("DEBUG: Invalid password")
            else:
                error_msg = "No account found with that email"
                print("DEBUG: User not found")
                
            conn.close()
    
    error_html = ""
    if error_msg:
        error_html = f'<div style="background: #ffebee; color: #c62828; padding: 12px; border-radius: 5px; margin-bottom: 20px; text-align: center; border: 1px solid #ffcdd2;">{error_msg}</div>'
    
    return f'''<!DOCTYPE html>
<html>
<head>
    <title>FoodFixr Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px;">
    <div style="max-width: 400px; margin: 50px auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #e91e63; margin: 0; font-size: 28px;">🍎 FoodFixr</h1>
            <p style="color: #666; margin: 10px 0 0 0;">Smart Ingredient Scanner</p>
        </div>
        
        {error_html}
        
        <form method="POST" action="/working-login">
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 5px; font-weight: bold; color: #333;">Email Address</label>
                <input type="email" name="email" required style="width: 100%; padding: 12px; border: 2px solid #ddd; border-radius: 5px; box-sizing: border-box; font-size: 16px;" placeholder="Enter your email">
            </div>
            
            <div style="margin-bottom: 25px;">
                <label style="display: block; margin-bottom: 5px; font-weight: bold; color: #333;">Password</label>
                <input type="password" name="password" required style="width: 100%; padding: 12px; border: 2px solid #ddd; border-radius: 5px; box-sizing: border-box; font-size: 16px;" placeholder="Enter your password">
            </div>
            
            <button type="submit" style="width: 100%; padding: 15px; background: #e91e63; color: white; border: none; border-radius: 5px; font-size: 16px; cursor: pointer; font-weight: bold;">
                🔑 Login to FoodFixr
            </button>
        </form>
        
        <div style="text-align: center; margin-top: 25px; padding-top: 20px; border-top: 1px solid #eee;">
            <p style="color: #666; margin-bottom: 15px;">Having trouble logging in?</p>
            <a href="/reset-all-passwords" style="display: inline-block; background: #ff9800; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px; font-size: 14px;">🔧 Reset All Passwords</a>
            <a href="/check-users" style="display: inline-block; background: #2196F3; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px; font-size: 14px;">👥 View Users</a>
        </div>
        
        <div style="text-align: center; margin-top: 20px; color: #999; font-size: 14px;">
            <p>Don't have an account? <a href="/register" style="color: #e91e63;">Sign up here</a></p>
        </div>
    </div>
</body>
</html>'''

# MAIN ROUTES
@app.route('/')
@login_required
def index():
    user_data = get_user_data(session['user_id'])
    if not user_data:
        return redirect('/working-login')
    
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
    user_data = get_user_data(session['user_id'])
    if not user_data:
        return redirect('/working-login')
    
    if not can_scan():
        flash('You have used all your free scans. Please upgrade to continue.', 'error')
        return redirect('/upgrade')
    
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
    
    try:
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        file.save(filepath)
        
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
            INSERT INTO scan_history (user_id, result_rating, ingredients_found, scan_date, scan_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (session['user_id'], result.get('rating', ''), str(result.get('matched_ingredients', {})), 
              format_datetime_for_db(), str(uuid.uuid4())))
        
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
                             user_name=user_data['name'])
        
    except Exception as e:
        return render_template('scanner.html',
                             trial_expired=trial_expired,
                             trial_time_left=trial_time_left,
                             user_name=user_data['name'],
                             error=f"Scanning failed: {str(e)}. Please try again.")

# REGISTRATION ROUTE
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
            flash('An account with this email already exists. Please login instead.', 'error')
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
            flash('Registration failed. Please try again.', 'error')
            conn.close()
            return render_template('register.html')
    
    return render_template('register.html')

# LOGOUT ROUTE
@app.route('/logout')
def logout():
    user_name = session.get('user_name', 'User')
    session.clear()
    flash(f'Goodbye {user_name}! You have been logged out.', 'info')
    return redirect('/working-login')

# OTHER ROUTES
@app.route('/account')
@login_required
def account():
    user_data = get_user_data(session['user_id'])
    if not user_data:
        return redirect('/working-login')
    
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
            
            scan_entry = {
                'scan_id': row['scan_id'],
                'date': scan_date.strftime("%m/%d/%Y"),
                'time': scan_date.strftime("%I:%M %p"),
                'rating_type': rating_type,
                'raw_rating': rating,
            }
            
            scans.append(scan_entry)
            stats['total_scans'] += 1
        
        conn.close()
        return render_template('history.html', scans=scans, stats=stats)
        
    except Exception as e:
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

# DEBUG ROUTES
@app.route('/reset-all-passwords')
def reset_all_passwords():
    try:
        conn = sqlite3.connect('foodfixr.db')
        cursor = conn.cursor()
        
        new_hash = generate_password_hash('test123')
        cursor.execute('UPDATE users SET password_hash = ?', (new_hash,))
        updated = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return f'''<html>
<body style="font-family: Arial; padding: 20px;">
<h1>✅ Passwords Reset</h1>
<p><strong>{updated} users updated</strong></p>
<p>All passwords are now: <strong>test123</strong></p>
<br>
<a href="/working-login" style="background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Try Login</a>
</body>
</html>'''
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/check-users')
def check_users():
    try:
        conn = sqlite3.connect('foodfixr.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, name, email, created_at FROM users ORDER BY created_at DESC LIMIT 10')
        users = cursor.fetchall()
        conn.close()
        
        html = '''<html>
<body style="font-family: Arial; padding: 20px;">
<h1>👥 Users in Database</h1>
<table border="1" style="border-collapse: collapse;">
<tr><th style="padding: 8px;">ID</th><th style="padding: 8px;">Name</th><th style="padding: 8px;">Email</th></tr>'''
        
        for user in users:
            html += f'<tr><td style="padding: 8px;">{user["id"]}</td><td style="padding: 8px;">{user["name"]}</td><td style="padding: 8px;">{user["email"]}</td></tr>'
        
        html += '''</table>
<br>
<p>All users can login with password: <strong>test123</strong></p>
<a href="/working-login" style="background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Try Login</a>
</body>
</html>'''
        
        return html
        
    except Exception as e:
        return f"Database error: {str(e)}"

# REDIRECT OLD LOGIN TO NEW LOGIN
@app.route('/login')
def old_login():
    return redirect('/working-login')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
