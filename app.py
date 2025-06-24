from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_file, Response, make_response
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
import psycopg2
from psycopg2.extras import RealDictCursor

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
            scan_id VARCHAR(255)
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
    
    try:
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        file.save(filepath)
        
        # Save the uploaded image for history
        saved_image_path = None
        try:
            # Create uploads directory if it doesn't exist
            uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads', 'history')
            os.makedirs(uploads_dir, exist_ok=True)
            
            # Generate unique filename for the saved image
            image_filename = f"scan_{session['user_id']}_{int(time.time())}_{secure_filename(file.filename)}"
            saved_image_path = os.path.join(uploads_dir, image_filename)
            
            # Copy the uploaded file to permanent location
            import shutil
            shutil.copy2(filepath, saved_image_path)
            
            # Store relative URL for serving
            image_url = f"/uploads/history/{image_filename}"
            
        except Exception as e:
            print(f"Error saving image for history: {e}")
            image_url = ""
        
        result = scan_image_for_ingredients(filepath)
        
        # Extract text from image for history display
        extracted_text = ""
        try:
            extracted_text = extract_text_from_image(filepath)
        except Exception as e:
            print(f"Error extracting text for history: {e}")
        
        # Store more detailed scan information
        conn = get_db_connection()
        cursor = conn.cursor()
        
        new_scans_used = user_data['scans_used'] + 1 if not user_data['is_premium'] else user_data['scans_used']
        new_total_scans = user_data['total_scans_ever'] + 1
        
        # Convert result to JSON string for better storage
        import json
        ingredients_json = json.dumps(result.get('matched_ingredients', {}))
        
        # Use appropriate placeholder for database type
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            cursor.execute('''
                UPDATE users 
                SET scans_used = %s, total_scans_ever = %s
                WHERE id = %s
            ''', (new_scans_used, new_total_scans, session['user_id']))
            
            cursor.execute('''
                INSERT INTO scan_history (user_id, result_rating, ingredients_found, scan_date, scan_id, image_url, extracted_text)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s)
            ''', (session['user_id'], result.get('rating', ''), ingredients_json, str(uuid.uuid4()), image_url, extracted_text[:1000]))  # Limit text length
        else:
            cursor.execute('''
                UPDATE users 
                SET scans_used = ?, total_scans_ever = ?
                WHERE id = ?
            ''', (new_scans_used, new_total_scans, session['user_id']))
            
            cursor.execute('''
                INSERT INTO scan_history (user_id, result_rating, ingredients_found, scan_date, scan_id, image_url, extracted_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (session['user_id'], result.get('rating', ''), ingredients_json, 
                  format_datetime_for_db(), str(uuid.uuid4()), image_url, extracted_text[:1000]))  # Limit text length
        
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
            
            # Parse ingredients_found (it's now stored as JSON)
            ingredients_found_str = row['ingredients_found'] or '{}'
            detected_ingredients = []
            ingredient_summary = {}
            has_gmo = False
            
            try:
                # Try to parse the ingredients_found as JSON first
                import json
                ingredients_dict = json.loads(ingredients_found_str)
                
                # Extract ingredients and build summary
                for category, ingredients_list in ingredients_dict.items():
                    if isinstance(ingredients_list, list):
                        detected_ingredients.extend(ingredients_list)
                        ingredient_summary[category] = len(ingredients_list)
                        if category == 'gmo' and len(ingredients_list) > 0:
                            has_gmo = True
                        stats['ingredients_found'] += len(ingredients_list)
                    elif isinstance(ingredients_list, str) and ingredients_list:
                        detected_ingredients.append(ingredients_list)
                        ingredient_summary[category] = 1
                        if category == 'gmo':
                            has_gmo = True
                        stats['ingredients_found'] += 1
                        
            except json.JSONDecodeError:
                # If JSON parsing fails, try the old string parsing method
                try:
                    if ingredients_found_str.startswith('{') and ingredients_found_str.endswith('}'):
                        import ast
                        ingredients_dict = ast.literal_eval(ingredients_found_str)
                        
                        for category, ingredients_list in ingredients_dict.items():
                            if isinstance(ingredients_list, list):
                                detected_ingredients.extend(ingredients_list)
                                ingredient_summary[category] = len(ingredients_list)
                                if category == 'gmo' and len(ingredients_list) > 0:
                                    has_gmo = True
                            stats['ingredients_found'] += len(ingredients_list) if isinstance(ingredients_list, list) else 0
                    else:
                        # If it's just a string, treat it as a single ingredient
                        if ingredients_found_str.strip():
                            detected_ingredients = [ingredients_found_str.strip()]
                            ingredient_summary['other'] = 1
                            stats['ingredients_found'] += 1
                except:
                    # If all parsing fails, just use the raw string
                    if ingredients_found_str.strip():
                        detected_ingredients = [ingredients_found_str.strip()]
                        ingredient_summary['other'] = 1
                        stats['ingredients_found'] += 1
            
            scan_entry = {
                'scan_id': row['scan_id'],
                'date': scan_date.strftime("%m/%d/%Y"),
                'time': scan_date.strftime("%I:%M %p"),
                'rating_type': rating_type,
                'raw_rating': rating,
                'detected_ingredients': detected_ingredients,
                'ingredient_summary': ingredient_summary,
                'has_gmo': has_gmo,
                'confidence': 'medium',  # Default confidence level
                'image_url': row.get('image_url', ''),  # May be empty
                'extracted_text': row.get('extracted_text', ''),  # Extracted text from image
                'text_length': len(row.get('extracted_text', '')),  # Text length for display
            }
            
            scans.append(scan_entry)
            stats['total_scans'] += 1
        
        conn.close()
        return render_template('history.html', scans=scans, stats=stats)
        
    except Exception as e:
        print(f"History error: {e}")
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
        # You'll need to create these price IDs in your Stripe dashboard
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

@app.route('/debug-history')
@login_required
def debug_history():
    """Debug route to show raw scan history data"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            cursor.execute('''
                SELECT * FROM scan_history 
                WHERE user_id = %s 
                ORDER BY scan_date DESC 
                LIMIT 20
            ''', (session['user_id'],))
        else:
            cursor.execute('''
                SELECT * FROM scan_history 
                WHERE user_id = ? 
                ORDER BY scan_date DESC 
                LIMIT 20
            ''', (session['user_id'],))
        
        scans = cursor.fetchall()
        conn.close()
        
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Debug History - FoodFixr</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { font-family: Arial; padding: 20px; background: #f5f5f5; }
                .container { max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }
                table { width: 100%; border-collapse: collapse; margin: 20px 0; }
                th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
                th { background-color: #f8f9fa; }
                .btn { padding: 8px 16px; margin: 5px; background: #e91e63; color: white; text-decoration: none; border-radius: 5px; }
                .scan-data { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                .full-data { max-width: none; white-space: pre-wrap; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔍 Debug Scan History</h1>
                <a href="/history" class="btn">← Back to History</a>
                
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Date</th>
                            <th>Rating</th>
                            <th>Ingredients Found</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        for scan in scans:
            html += f"""
                        <tr>
                            <td>{scan['id']}</td>
                            <td>{scan['scan_date']}</td>
                            <td>{scan['result_rating'] or 'None'}</td>
                            <td class="scan-data" title="{scan['ingredients_found'] or 'None'}">{scan['ingredients_found'] or 'None'}</td>
                            <td>
                                <button onclick="toggleData(this)" class="btn" style="font-size: 12px;">Show Full</button>
                            </td>
                        </tr>
            """
        
        html += """
                    </tbody>
                </table>
            </div>
            
            <script>
                function toggleData(btn) {
                    const cell = btn.parentElement.previousElementSibling;
                    if (cell.classList.contains('full-data')) {
                        cell.classList.remove('full-data');
                        btn.textContent = 'Show Full';
                    } else {
                        cell.classList.add('full-data');
                        btn.textContent = 'Hide';
                    }
                }
            </script>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        return f"Debug history error: {str(e)}"

@app.route('/clear-history', methods=['POST'])
@login_required
def clear_history():
    """Clear user's scan history (Premium feature)"""
    user_data = get_user_data(session['user_id'])
    if not user_data or not user_data['is_premium']:
        return jsonify({'success': False, 'error': 'Premium subscription required'}), 403
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            cursor.execute('DELETE FROM scan_history WHERE user_id = %s', (session['user_id'],))
        else:
            cursor.execute('DELETE FROM scan_history WHERE user_id = ?', (session['user_id'],))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'History cleared successfully'})
        
    except Exception as e:
        print(f"Clear history error: {e}")
        return jsonify({'success': False, 'error': 'Failed to clear history'}), 500

@app.route('/export-history')
@login_required
def export_history():
    """Export user's scan history as CSV (Premium feature)"""
    user_data = get_user_data(session['user_id'])
    if not user_data or not user_data['is_premium']:
        flash('Premium subscription required for history export', 'error')
        return redirect(url_for('history'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            cursor.execute('''
                SELECT scan_date, result_rating, ingredients_found 
                FROM scan_history 
                WHERE user_id = %s 
                ORDER BY scan_date DESC
            ''', (session['user_id'],))
        else:
            cursor.execute('''
                SELECT scan_date, result_rating, ingredients_found 
                FROM scan_history 
                WHERE user_id = ? 
                ORDER BY scan_date DESC
            ''', (session['user_id'],))
        
        scans = cursor.fetchall()
        conn.close()
        
        # Create CSV content
        csv_content = "Date,Time,Result,Ingredients\n"
        for scan in scans:
            scan_date = safe_datetime_parse(scan['scan_date'])
            date_str = scan_date.strftime("%Y-%m-%d")
            time_str = scan_date.strftime("%H:%M:%S")
            result = (scan['result_rating'] or '').replace(',', ';')  # Replace commas to avoid CSV issues
            ingredients = (scan['ingredients_found'] or '').replace(',', ';')
            csv_content += f'"{date_str}","{time_str}","{result}","{ingredients}"\n'
        
        # Return CSV file
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=foodfixr_history_{datetime.now().strftime("%Y%m%d")}.csv'
        
        return response
        
    except Exception as e:
        print(f"Export history error: {e}")
        flash('Failed to export history', 'error')
        return redirect(url_for('history'))

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
            select {{ width: 100%; padding: 12px; border: 2px solid #ddd; border-radius: 8px; box-sizing: border-box; font-size: 16px; }}
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

# SIMPLE LOGIN PAGE
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
                    <input type="email" name="email" required style="width: 100%; padding: 12px; border: 2px solid #ddd; border-radius: 5px; box-sizing: border-box;">
                </div>
                
                <div style="margin-bottom: 25px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold;">Password:</label>
                    <input type="password" name="password" required style="width: 100%; padding: 12px; border: 2px solid #ddd; border-radius: 5px; box-sizing: border-box;">
                </div>
                
                <button type="submit" style="width: 100%; padding: 15px; background: #e91e63; color: white; border: none; border-radius: 5px; font-size: 16px; cursor: pointer;">
                    Login
                </button>
            </form>
            
            <div style="text-align: center; margin-top: 25px;">
                <a href="/admin-password-reset" style="background: #ff9800; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px; display: inline-block;">Reset Individual Password</a>
                <a href="/check-users" style="background: #2196F3; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px; display: inline-block;">Manage Users</a>
                <a href="/test-upgrade-user" style="background: #4CAF50; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px; display: inline-block;">Test Upgrade</a>
                <a href="/sync-stripe-subscriptions" style="background: #FF5722; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px; display: inline-block;">Sync Stripe</a>
                <a href="/fix-user-subscription" style="background: #673AB7; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px; display: inline-block;">Fix User Sub</a>
                <a href="/test-webhook" style="background: #795548; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px; display: inline-block;">Test Webhook</a>
                <a href="/admin-cleanup-images" style="background: #9C27B0; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px; display: inline-block;">Cleanup Images</a>
            </div>
        </div>
    </body>
    </html>
    """

# IMPROVED PASSWORD MANAGEMENT ROUTES
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
                
                # Check if user exists
                database_url = os.getenv('DATABASE_URL')
                if database_url:
                    cursor.execute('SELECT id, name FROM users WHERE email = %s', (email,))
                else:
                    cursor.execute('SELECT id, name FROM users WHERE email = ?', (email,))
                
                user = cursor.fetchone()
                
                if not user:
                    error_msg = f"No user found with email: {email}"
                else:
                    # Update password
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
            input, select {{ width: 100%; padding: 12px; border: 2px solid #ddd; border-radius: 8px; box-sizing: border-box; font-size: 16px; }}
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

@app.route('/bulk-password-reset', methods=['GET', 'POST'])
def bulk_password_reset():
    """Reset all users to the same password (use with caution)"""
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not new_password or not confirm_password:
            error_msg = "Both password fields are required"
        elif new_password != confirm_password:
            error_msg = "Passwords do not match"
        elif len(new_password) < 6:
            error_msg = "Password must be at least 6 characters long"
        else:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                new_hash = generate_password_hash(new_password)
                
                database_url = os.getenv('DATABASE_URL')
                if database_url:
                    cursor.execute('UPDATE users SET password_hash = %s', (new_hash,))
                else:
                    cursor.execute('UPDATE users SET password_hash = ?', (new_hash,))
                
                updated = cursor.rowcount
                conn.commit()
                conn.close()
                
                success_msg = f"Password updated for {updated} users. All users can now login with: {new_password}"
                
            except Exception as e:
                error_msg = f"Error: {str(e)}"
    else:
        error_msg = None
        success_msg = None
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Bulk Password Reset</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: Arial; padding: 20px; background: #f5f5f5; margin: 0; }}
            .container {{ max-width: 500px; margin: 50px auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            h1 {{ color: #e91e63; text-align: center; margin-bottom: 30px; }}
            .warning {{ background: #fff3cd; color: #856404; padding: 15px; border-radius: 8px; margin: 15px 0; border: 2px solid #ffc107; }}
            .form-group {{ margin-bottom: 20px; }}
            label {{ display: block; margin-bottom: 8px; font-weight: bold; color: #333; }}
            input {{ width: 100%; padding: 12px; border: 2px solid #ddd; border-radius: 8px; box-sizing: border-box; font-size: 16px; }}
            input:focus {{ border-color: #e91e63; outline: none; }}
            .btn {{ padding: 12px 24px; margin: 10px 5px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold; }}
            .btn-danger {{ background: #dc3545; color: white; }}
            .btn-secondary {{ background: #666; color: white; }}
            .btn:hover {{ opacity: 0.9; transform: translateY(-1px); }}
            .success {{ background: #d4edda; color: #155724; padding: 15px; border-radius: 8px; margin: 15px 0; border: 1px solid #4CAF50; }}
            .error {{ background: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; margin: 15px 0; border: 1px solid #f44336; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>⚠️ Bulk Password Reset</h1>
            
            <div class="warning">
                <strong>⚠️ WARNING:</strong> This will change the password for ALL users in the database. Use with caution!
            </div>
            
            {'<div class="success">' + success_msg + '</div>' if 'success_msg' in locals() and success_msg else ''}
            {'<div class="error">' + error_msg + '</div>' if 'error_msg' in locals() and error_msg else ''}
            
            <form method="POST">
                <div class="form-group">
                    <label for="new_password">New Password for All Users:</label>
                    <input type="password" id="new_password" name="new_password" placeholder="Enter password (min 6 chars)" required minlength="6">
                </div>
                
                <div class="form-group">
                    <label for="confirm_password">Confirm Password:</label>
                    <input type="password" id="confirm_password" name="confirm_password" placeholder="Confirm password" required minlength="6">
                </div>
                
                <div style="text-align: center; margin-top: 30px;">
                    <button type="submit" class="btn btn-danger" onclick="return confirm('Are you sure you want to reset ALL user passwords?')">
                        ⚠️ Reset All Passwords
                    </button>
                    <a href="/admin-password-reset" class="btn btn-secondary">👤 Individual Reset</a>
                    <a href="/check-users" class="btn btn-secondary">👥 View Users</a>
                </div>
            </form>
        </div>
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
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
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
                    <a href="/bulk-password-reset" class="btn btn-secondary">⚠️ Bulk Password Reset</a>
                    <a href="/simple-login" class="btn btn-success">🚪 Test Login</a>
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

@app.route('/uploads/history/<filename>')
@login_required
def serve_history_image(filename):
    """Serve uploaded scan history images"""
    try:
        # Security check - only serve images for the current user
        # Extract user_id from filename (format: scan_USERID_timestamp_originalname)
        if not filename.startswith(f'scan_{session["user_id"]}_'):
            return "Unauthorized", 403
        
        uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads', 'history')
        filepath = os.path.join(uploads_dir, filename)
        
        if os.path.exists(filepath):
            from flask import send_file
            return send_file(filepath)
        else:
            return "Image not found", 404
            
    except Exception as e:
        print(f"Error serving history image: {e}")
        return "Error loading image", 500

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files including emoji images"""
    # For now, we'll redirect to a generic emoji or return a placeholder
    # In production, you'd want to add actual image files
    from flask import send_from_directory
    import os
    
    # Try to serve from static directory if it exists
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    if os.path.exists(static_dir) and os.path.exists(os.path.join(static_dir, filename)):
        return send_from_directory(static_dir, filename)
    
    # Return a placeholder response for missing static files
    if filename.endswith('.png'):
        return """
        <svg width="32" height="32" xmlns="http://www.w3.org/2000/svg">
            <circle cx="16" cy="16" r="15" fill="#e91e63"/>
            <text x="16" y="20" text-anchor="middle" fill="white" font-size="12">🍎</text>
        </svg>
        """, 200, {'Content-Type': 'image/svg+xml'}
    
    return "File not found", 404

@app.route('/sync-stripe-subscriptions')
def sync_stripe_subscriptions():
    """Sync all active Stripe subscriptions with database"""
    try:
        synced_count = 0
        errors = []
        
        # Get all users from database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            cursor.execute('SELECT id, email, stripe_customer_id FROM users')
        else:
            cursor.execute('SELECT id, email, stripe_customer_id FROM users')
        
        users = cursor.fetchall()
        
        for user in users:
            try:
                user_id = user['id']
                email = user['email']
                stripe_customer_id = user['stripe_customer_id']
                
                # Skip if no Stripe customer ID
                if not stripe_customer_id:
                    continue
                
                # Get active subscriptions for this customer
                subscriptions = stripe.Subscription.list(
                    customer=stripe_customer_id,
                    status='active',
                    limit=10
                )
                
                if subscriptions.data:
                    # User has active subscription - update database
                    subscription = subscriptions.data[0]  # Get first active subscription
                    
                    if database_url:
                        cursor.execute('''
                            UPDATE users 
                            SET is_premium = TRUE,
                                subscription_status = %s,
                                subscription_start_date = %s,
                                stripe_subscription_id = %s
                            WHERE id = %s
                        ''', ('active', 
                              datetime.fromtimestamp(subscription.created).strftime('%Y-%m-%d %H:%M:%S'),
                              subscription.id,
                              user_id))
                    else:
                        cursor.execute('''
                            UPDATE users 
                            SET is_premium = 1,
                                subscription_status = ?,
                                subscription_start_date = ?,
                                stripe_subscription_id = ?
                            WHERE id = ?
                        ''', ('active', 
                              datetime.fromtimestamp(subscription.created).strftime('%Y-%m-%d %H:%M:%S'),
                              subscription.id,
                              user_id))
                    
                    synced_count += 1
                    print(f"✅ Synced subscription for user {email}")
                
            except Exception as e:
                error_msg = f"Error syncing user {email}: {str(e)}"
                errors.append(error_msg)
                print(f"❌ {error_msg}")
        
        conn.commit()
        conn.close()
        
        result = {
            'success': True,
            'synced_count': synced_count,
            'total_users': len(users),
            'errors': errors
        }
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Stripe Sync Results</title>
            <style>
                body {{ font-family: Arial; padding: 20px; background: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
                .success {{ background: #d4edda; color: #155724; padding: 15px; border-radius: 8px; margin: 10px 0; }}
                .error {{ background: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; margin: 10px 0; }}
                .btn {{ padding: 10px 20px; background: #e91e63; color: white; text-decoration: none; border-radius: 5px; margin: 10px 5px; display: inline-block; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔄 Stripe Subscription Sync Results</h1>
                
                <div class="success">
                    <strong>✅ Sync Complete!</strong><br>
                    Synced {synced_count} active subscriptions out of {len(users)} total users.
                </div>
                
                {''.join([f'<div class="error">❌ {error}</div>' for error in errors]) if errors else ''}
                
                <div style="margin-top: 30px;">
                    <a href="/check-users" class="btn">👥 Check Users</a>
                    <a href="/simple-login" class="btn">🔐 Login</a>
                    <a href="/" class="btn">🏠 Home</a>
                </div>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        return f"""
        <div style="padding: 20px; background: #f8d7da; color: #721c24; border-radius: 8px; margin: 20px;">
            <h3>❌ Sync Failed</h3>
            <p>Error: {str(e)}</p>
            <a href="/check-users" style="background: #e91e63; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px;">Back to Users</a>
        </div>
        """

@app.route('/fix-user-subscription', methods=['GET', 'POST'])
def fix_user_subscription():
    """Fix subscription for a specific user"""
    if request.method == 'POST':
        user_email = request.form.get('email', '').strip()
        
        if not user_email:
            return "Email is required", 400
        
        try:
            # Find user in database
            conn = get_db_connection()
            cursor = conn.cursor()
            
            database_url = os.getenv('DATABASE_URL')
            if database_url:
                cursor.execute('SELECT * FROM users WHERE email = %s', (user_email,))
            else:
                cursor.execute('SELECT * FROM users WHERE email = ?', (user_email,))
            
            user = cursor.fetchone()
            
            if not user:
                conn.close()
                return f"User with email {user_email} not found in database", 404
            
            # Check if user has Stripe customer ID
            if not user['stripe_customer_id']:
                # Find customer by email in Stripe
                customers = stripe.Customer.list(email=user_email, limit=1)
                if customers.data:
                    stripe_customer_id = customers.data[0].id
                    # Update database with customer ID
                    if database_url:
                        cursor.execute('UPDATE users SET stripe_customer_id = %s WHERE id = %s', 
                                     (stripe_customer_id, user['id']))
                    else:
                        cursor.execute('UPDATE users SET stripe_customer_id = ? WHERE id = ?', 
                                     (stripe_customer_id, user['id']))
                    conn.commit()
                else:
                    conn.close()
                    return f"No Stripe customer found for {user_email}", 404
            else:
                stripe_customer_id = user['stripe_customer_id']
            
            # Get active subscriptions
            subscriptions = stripe.Subscription.list(
                customer=stripe_customer_id,
                status='active',
                limit=5
            )
            
            if subscriptions.data:
                # Update user to premium
                subscription = subscriptions.data[0]
                
                if database_url:
                    cursor.execute('''
                        UPDATE users 
                        SET is_premium = TRUE,
                            subscription_status = %s,
                            subscription_start_date = %s,
                            stripe_subscription_id = %s
                        WHERE id = %s
                    ''', ('active', 
                          datetime.fromtimestamp(subscription.created).strftime('%Y-%m-%d %H:%M:%S'),
                          subscription.id,
                          user['id']))
                else:
                    cursor.execute('''
                        UPDATE users 
                        SET is_premium = 1,
                            subscription_status = ?,
                            subscription_start_date = ?,
                            stripe_subscription_id = ?
                        WHERE id = ?
                    ''', ('active', 
                          datetime.fromtimestamp(subscription.created).strftime('%Y-%m-%d %H:%M:%S'),
                          subscription.id,
                          user['id']))
                
                conn.commit()
                conn.close()
                
                return f"""
                <div style="padding: 20px; background: #d4edda; color: #155724; border-radius: 8px; margin: 20px;">
                    <h3>✅ Subscription Fixed!</h3>
                    <p><strong>User:</strong> {user_email}</p>
                    <p><strong>Status:</strong> Premium Active</p>
                    <p><strong>Subscription ID:</strong> {subscription.id}</p>
                    <p><strong>Start Date:</strong> {datetime.fromtimestamp(subscription.created).strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <a href="/check-users" style="background: #e91e63; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin-top: 10px; display: inline-block;">Back to Users</a>
                </div>
                """
            else:
                conn.close()
                return f"No active subscriptions found for {user_email} in Stripe", 404
                
        except Exception as e:
            return f"Error fixing subscription: {str(e)}", 500
    
    # GET request - show form
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Fix User Subscription</title>
        <style>
            body {{ font-family: Arial; padding: 20px; background: #f5f5f5; }}
            .container {{ max-width: 500px; margin: 50px auto; background: white; padding: 30px; border-radius: 10px; }}
            h1 {{ color: #e91e63; text-align: center; }}
            .form-group {{ margin-bottom: 20px; }}
            label {{ display: block; margin-bottom: 8px; font-weight: bold; }}
            input {{ width: 100%; padding: 12px; border: 2px solid #ddd; border-radius: 8px; box-sizing: border-box; }}
            .btn {{ padding: 12px 24px; background: #e91e63; color: white; border: none; border-radius: 8px; cursor: pointer; width: 100%; font-size: 16px; }}
            .btn:hover {{ background: #c2185b; }}
            .info {{ background: #d1ecf1; color: #0c5460; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔧 Fix User Subscription</h1>
            
            <div class="info">
                <strong>ℹ️ This tool:</strong> Finds active Stripe subscriptions and syncs them with the database for a specific user.
            </div>
            
            <form method="POST">
                <div class="form-group">
                    <label for="email">User Email:</label>
                    <input type="email" id="email" name="email" required placeholder="user@example.com">
                </div>
                
                <button type="submit" class="btn">🔄 Fix Subscription</button>
            </form>
            
            <div style="text-align: center; margin-top: 20px;">
                <a href="/sync-stripe-subscriptions" style="background: #4CAF50; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px;">Sync All Users</a>
                <a href="/check-users" style="background: #2196F3; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px;">Check Users</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/test-webhook', methods=['GET', 'POST'])
def test_webhook():
    """Test webhook functionality"""
    if request.method == 'POST':
        action = request.form.get('action')
        user_email = request.form.get('email')
        
        if not user_email:
            return "Email required", 400
        
        try:
            # Find user
            conn = get_db_connection()
            cursor = conn.cursor()
            
            database_url = os.getenv('DATABASE_URL')
            if database_url:
                cursor.execute('SELECT * FROM users WHERE email = %s', (user_email,))
            else:
                cursor.execute('SELECT * FROM users WHERE email = ?', (user_email,))
            
            user = cursor.fetchone()
            conn.close()
            
            if not user:
                return f"User {user_email} not found", 404
            
            # Simulate webhook actions
            if action == 'activate':
                # Simulate subscription.created webhook
                fake_subscription = {
                    'id': f'sub_test_{int(time.time())}',
                    'customer': user.get('stripe_customer_id', 'cus_test'),
                    'status': 'active',
                    'created': int(time.time())
                }
                handle_subscription_created(fake_subscription)
                message = f"✅ Activated premium for {user_email}"
                
            elif action == 'cancel':
                # Simulate subscription.deleted webhook
                fake_subscription = {
                    'id': user.get('stripe_subscription_id', 'sub_test'),
                }
                handle_subscription_deleted(fake_subscription)
                message = f"❌ Canceled premium for {user_email}"
                
            else:
                return "Invalid action", 400
            
            return f"""
            <div style="padding: 20px; background: #d4edda; color: #155724; border-radius: 8px; margin: 20px;">
                <h3>🔄 Webhook Test Result</h3>
                <p>{message}</p>
                <a href="/check-users" style="background: #e91e63; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px;">Check Users</a>
                <a href="/test-webhook" style="background: #6c757d; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin-left: 10px;">Test Again</a>
            </div>
            """
            
        except Exception as e:
            return f"Error: {str(e)}", 500
    
    # GET request - show form
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Webhook - FoodFixr</title>
        <style>
            body {{ font-family: Arial; padding: 20px; background: #f5f5f5; }}
            .container {{ max-width: 500px; margin: 50px auto; background: white; padding: 30px; border-radius: 10px; }}
            h1 {{ color: #e91e63; text-align: center; }}
            .form-group {{ margin-bottom: 20px; }}
            label {{ display: block; margin-bottom: 8px; font-weight: bold; }}
            input, select {{ width: 100%; padding: 12px; border: 2px solid #ddd; border-radius: 8px; box-sizing: border-box; }}
            .btn {{ padding: 12px 24px; background: #e91e63; color: white; border: none; border-radius: 8px; cursor: pointer; width: 100%; font-size: 16px; }}
            .btn:hover {{ background: #c2185b; }}
            .info {{ background: #d1ecf1; color: #0c5460; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔄 Test Webhook</h1>
            
            <div class="info">
                <strong>ℹ️ This tool:</strong> Simulates Stripe webhook events to test subscription activation/cancellation without actual Stripe calls.
            </div>
            
            <form method="POST">
                <div class="form-group">
                    <label for="email">User Email:</label>
                    <input type="email" id="email" name="email" required placeholder="user@example.com">
                </div>
                
                <div class="form-group">
                    <label for="action">Action:</label>
                    <select id="action" name="action" required>
                        <option value="">Select Action</option>
                        <option value="activate">Activate Premium (subscription.created)</option>
                        <option value="cancel">Cancel Premium (subscription.deleted)</option>
                    </select>
                </div>
                
                <button type="submit" class="btn">🧪 Test Webhook</button>
            </form>
            
            <div style="text-align: center; margin-top: 20px;">
                <a href="/sync-stripe-subscriptions" style="background: #4CAF50; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px;">Sync Stripe</a>
                <a href="/check-users" style="background: #2196F3; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin: 5px;">Check Users</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/admin-cleanup-images')
def admin_cleanup_images():
    """Manual cleanup of old images (admin function)"""
    try:
        cleanup_old_images()
        return jsonify({'success': True, 'message': 'Image cleanup completed'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/debug-routes')
def debug_routes():
    """Show all available routes"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'path': rule.rule
        })
    
    html = "<html><body style='font-family: Arial; padding: 20px;'><h1>Available Routes</h1><table border='1' style='border-collapse: collapse;'>"
    html += "<tr><th style='padding: 8px;'>Path</th><th style='padding: 8px;'>Methods</th><th style='padding: 8px;'>Function</th></tr>"
    
    for route in routes:
        html += f"<tr><td style='padding: 8px;'>{route['path']}</td><td style='padding: 8px;'>{', '.join(route['methods'])}</td><td style='padding: 8px;'>{route['endpoint']}</td></tr>"
    
    html += "</table><br><a href='/simple-login' style='background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;'>Try Simple Login</a></body></html>"
    
    return html

@app.route('/test-login-form')
def test_login_form():
    """Simple test login form that posts to /login"""
    return f"""
    <html>
    <head><title>Test Login Form</title></head>
    <body style="font-family: Arial; padding: 20px;">
    <h1>Test Login Form</h1>
    <p>This form posts directly to /login route</p>
    
    <form method="POST" action="/login" style="max-width: 300px;">
        <div style="margin-bottom: 15px;">
            <label>Email:</label><br>
            <input type="email" name="email" required style="width: 100%; padding: 8px;">
        </div>
        <div style="margin-bottom: 15px;">
            <label>Password:</label><br>
            <input type="password" name="password" required style="width: 100%; padding: 8px;">
        </div>
        <button type="submit" style="padding: 10px 20px; background: #4CAF50; color: white; border: none;">Login</button>
    </form>
    
    <br><br>
    <a href="/admin-password-reset">Reset Individual Passwords</a><br>
    <a href="/check-users">Check Users</a><br>
    <a href="/simple-login">Simple Login</a>
    </body>
    </html>
    """

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
