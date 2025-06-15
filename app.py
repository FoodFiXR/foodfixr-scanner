from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
import tempfile
from werkzeug.utils import secure_filename
from ingredient_scanner import scan_image_for_ingredients
import json
from datetime import datetime, timedelta
import uuid
import stripe

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Stripe Configuration
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')  # Add this to your environment variables
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')

# Your domain for Stripe redirects
DOMAIN = os.getenv('DOMAIN', 'https://foodfixr-scanner.onrender.com')

# Configuration
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Ensure upload directory exists
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_session():
    """Initialize session with trial data"""
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
        session['trial_start'] = datetime.now().isoformat()
        session['scans_used'] = 0
        session['is_premium'] = False
        session.permanent = True

def is_trial_expired():
    """Check if 48-hour trial has expired"""
    if 'trial_start' not in session:
        return True
    
    trial_start = datetime.fromisoformat(session['trial_start'])
    trial_end = trial_start + timedelta(hours=48)
    return datetime.now() > trial_end

def get_trial_time_left():
    """Get remaining trial time as formatted string"""
    if 'trial_start' not in session:
        return "0h 0m"
    
    trial_start = datetime.fromisoformat(session['trial_start'])
    trial_end = trial_start + timedelta(hours=48)
    time_left = trial_end - datetime.now()
    
    if time_left.total_seconds() <= 0:
        return "0h 0m"
    
    hours = int(time_left.total_seconds() // 3600)
    minutes = int((time_left.total_seconds() % 3600) // 60)
    return f"{hours}h {minutes}m"

def can_scan():
    """Check if user can perform a scan"""
    if session.get('is_premium'):
        return True
    
    if session.get('scans_used', 0) >= 10:
        return False
        
    if is_trial_expired():
        return False
        
    return True

@app.route('/')
def index():
    """Main scanner page"""
    init_session()
    
    trial_expired = is_trial_expired()
    trial_time_left = get_trial_time_left()
    
    return render_template('scanner.html', 
                         trial_expired=trial_expired,
                         trial_time_left=trial_time_left,
                         stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)

@app.route('/', methods=['POST'])
def scan():
    """Handle image scanning with trial limits"""
    try:
        init_session()
        
        # Check if user can scan
        if not can_scan():
            return render_template('scanner.html',
                                 trial_expired=is_trial_expired(),
                                 trial_time_left=get_trial_time_left(),
                                 error="Trial limit reached. Please upgrade to continue scanning.",
                                 stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)
        
        # Check if image was uploaded
        if 'image' not in request.files:
            return render_template('scanner.html',
                                 trial_expired=is_trial_expired(),
                                 trial_time_left=get_trial_time_left(),
                                 error="No image uploaded.",
                                 stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)
        
        file = request.files['image']
        if file.filename == '':
            return render_template('scanner.html',
                                 trial_expired=is_trial_expired(),
                                 trial_time_left=get_trial_time_left(),
                                 error="No image selected.",
                                 stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)
        
        if not allowed_file(file.filename):
            return render_template('scanner.html',
                                 trial_expired=is_trial_expired(),
                                 trial_time_left=get_trial_time_left(),
                                 error="Invalid file type. Please upload an image.",
                                 stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)
        
        try:
            # Save uploaded file to temp directory
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{filename}"
            
            # Use temp directory instead of uploads folder
            import tempfile
            filepath = os.path.join(tempfile.gettempdir(), filename)
            file.save(filepath)
            
            print(f"DEBUG: File saved to {filepath}")
            print(f"DEBUG: File exists: {os.path.exists(filepath)}")
            
            # Increment scan count for non-premium users
            if not session.get('is_premium'):
                session['scans_used'] = session.get('scans_used', 0) + 1
            
            # Scan the image
            print("DEBUG: Starting image scan...")
            result = scan_image_for_ingredients(filepath)
            print(f"DEBUG: Scan result: {result}")
            
            # Clean up uploaded file
            try:
                os.remove(filepath)
                print("DEBUG: Temp file cleaned up")
            except Exception as cleanup_error:
                print(f"DEBUG: Cleanup error: {cleanup_error}")
            
            # Log scan for analytics
            log_scan_result(session.get('user_id'), result, session.get('scans_used', 0))
            
            return render_template('scanner.html',
                                 result=result,
                                 trial_expired=is_trial_expired(),
                                 trial_time_left=get_trial_time_left(),
                                 stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)
            
        except Exception as scan_error:
            print(f"DEBUG: Scanning error: {scan_error}")
            import traceback
            traceback.print_exc()
            
            return render_template('scanner.html',
                                 trial_expired=is_trial_expired(),
                                 trial_time_left=get_trial_time_left(),
                                 error=f"Scanning failed: {str(scan_error)}. Please try again.",
                                 stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)
    
    except Exception as outer_error:
        print(f"DEBUG: Outer error in scan route: {outer_error}")
        import traceback
        traceback.print_exc()
        
        # Return a basic error page if template rendering fails
        return f"""
        <html>
        <head><title>FoodFixr Error</title></head>
        <body>
        <h1>Error occurred</h1>
        <p>Error: {str(outer_error)}</p>
        <a href="/">Try Again</a>
        </body>
        </html>
        """, 500

@app.route('/test-scan')
def test_scan():
    """Test scanning without actual image"""
    try:
        # Test if all imports work
        from ingredient_scanner import scan_image_for_ingredients
        from scanner_config import safe_ingredients
        
        # Create a dummy result
        test_result = {
            "rating": "✅ Yay! Safe!",
            "matched_ingredients": {
                "trans_fat": [],
                "excitotoxins": [],
                "corn": [],
                "sugar": [],
                "gmo": [],
                "safe_ingredients": ["water", "salt"],
                "all_detected": ["water", "salt"]
            },
            "confidence": "high",
            "text_quality": "good",
            "extracted_text_length": 20,
            "gmo_alert": None
        }
        
        return render_template('scanner.html',
                             result=test_result,
                             trial_expired=False,
                             trial_time_left="48h 0m",
                             stripe_publishable_key="test")
                             
    except Exception as e:
        return f"Test failed: {str(e)}<br><a href='/'>Back to Scanner</a>"
        
@app.route('/upgrade')
def upgrade():
    """Upgrade page for premium plans"""
    init_session()
    
    trial_expired = is_trial_expired()
    trial_time_left = get_trial_time_left()
    
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
        
        # Check if Stripe is configured
        if not stripe.api_key:
            print("ERROR: Stripe API key not configured")
            return jsonify({'error': 'Payment system not configured. Please contact support.'}), 500
        
        # Define pricing based on your upgrade.html plans
        prices = {
            'weekly': {
                'price_id': os.getenv('STRIPE_WEEKLY_PRICE_ID'),
                'amount': 3.99
            },
            'monthly': {
                'price_id': os.getenv('STRIPE_MONTHLY_PRICE_ID'),
                'amount': 11.99
            },
            'yearly': {
                'price_id': os.getenv('STRIPE_YEARLY_PRICE_ID'),
                'amount': 95.00
            }
        }
        
        if plan not in prices:
            print(f"ERROR: Invalid plan selected: {plan}")
            return jsonify({'error': 'Invalid plan selected'}), 400
        
        price_id = prices[plan]['price_id']
        
        if not price_id:
            print(f"ERROR: No price ID configured for plan: {plan}")
            return jsonify({'error': f'Price not configured for {plan} plan. Please contact support.'}), 500
        
        # Log for debugging
        print(f"Creating checkout session for plan: {plan}, price_id: {price_id}")
        
        success_url = f"{DOMAIN}/success?session_id={{CHECKOUT_SESSION_ID}}&plan={plan}"
        cancel_url = f"{DOMAIN}/upgrade"
        
        # Create checkout session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'user_id': session.get('user_id'),
                'plan': plan
            },
            customer_email=data.get('email') if data.get('email') else None,
        )
        
        print(f"Checkout session created successfully: {checkout_session.id}")
        return jsonify({'checkout_url': checkout_session.url})
        
    except stripe.error.StripeError as e:
        print(f"Stripe error: {str(e)}")
        return jsonify({'error': f'Payment error: {str(e)}'}), 400
    except Exception as e:
        print(f"Unexpected error in create_checkout_session: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to create checkout session. Please try again.'}), 500

@app.route('/success')
def success():
    """Handle successful payment"""
    try:
        session_id = request.args.get('session_id')
        plan = request.args.get('plan', 'monthly')
        
        if session_id:
            # Verify the session with Stripe
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            
            if checkout_session.payment_status == 'paid':
                # Mark user as premium
                session['is_premium'] = True
                session['premium_start'] = datetime.now().isoformat()
                session['premium_plan'] = plan
                session['stripe_customer_id'] = checkout_session.customer
                session['scans_used'] = 0  # Reset scan count
                
                # Log successful payment
                log_payment(session.get('user_id'), plan, checkout_session.id)
                
                return render_template('success.html', plan=plan)
        
        return redirect(url_for('index'))
        
    except Exception as e:
        print(f"Success page error: {e}")
        return redirect(url_for('index'))

@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhooks for subscription events"""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    endpoint_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError:
        return 'Invalid signature', 400
    
    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session_data = event['data']['object']
        user_id = session_data['metadata'].get('user_id')
        plan = session_data['metadata'].get('plan')
        
        # Update user premium status in database
        # For now, we're using Flask sessions, but in production you'd update a database
        print(f"User {user_id} subscribed to {plan} plan")
        
    elif event['type'] == 'invoice.payment_succeeded':
        # Handle successful subscription renewal
        print("Subscription payment succeeded")
        
    elif event['type'] == 'customer.subscription.deleted':
        # Handle subscription cancellation
        print("Subscription cancelled")
        
    return 'Success', 200

@app.route('/cancel-subscription', methods=['POST'])
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
                # Cancel the subscription
                stripe.Subscription.delete(subscription.id)
                
                # Update session
                session['is_premium'] = False
                session['premium_end'] = datetime.now().isoformat()
                
                return jsonify({'success': True, 'message': 'Subscription cancelled'})
        
        return jsonify({'error': 'No active subscription found'}), 400
        
    except Exception as e:
        print(f"Cancellation error: {e}")
        return jsonify({'error': 'Failed to cancel subscription'}), 500

@app.route('/account')
def account():
    """User account page"""
    init_session()
    return render_template('account.html',
                         trial_expired=is_trial_expired(),
                         trial_time_left=get_trial_time_left())

@app.route('/reset-trial')
def reset_trial():
    """Reset trial for testing purposes (remove in production)"""
    session.clear()
    return redirect(url_for('index'))

@app.route('/debug')
def debug():
    """Debug endpoint to check system status"""
    import sys
    import platform
    
    debug_info = {
        "Python version": sys.version,
        "Platform": platform.platform(),
        "Tesseract available": False,
        "Upload folder": app.config['UPLOAD_FOLDER'],
        "Upload folder exists": os.path.exists(app.config['UPLOAD_FOLDER']),
        "Upload folder writable": os.access(app.config['UPLOAD_FOLDER'], os.W_OK)
    }
    
    try:
        import pytesseract
        version = pytesseract.image_to_string(Image.new('RGB', (100, 30), color='white'))
        debug_info["Tesseract available"] = True
        debug_info["Tesseract test"] = "Success"
    except Exception as e:
        debug_info["Tesseract error"] = str(e)
    
    return f"<pre>{json.dumps(debug_info, indent=2)}</pre>"

def log_scan_result(user_id, result, scan_count):
    """Log scan results for analytics"""
    try:
        log_data = {
            'user_id': user_id,
            'timestamp': datetime.now().isoformat(),
            'scan_count': scan_count,
            'rating': result.get('rating'),
            'confidence': result.get('confidence'),
            'ingredients_found': len(result.get('matched_ingredients', {}).get('all_detected', []))
        }
        
        # Save to file or database
        with open('scan_logs.json', 'a') as f:
            f.write(json.dumps(log_data) + '\n')
            
    except Exception as e:
        print(f"Logging error: {e}")

def log_payment(user_id, plan, session_id):
    """Log successful payments"""
    try:
        payment_data = {
            'user_id': user_id,
            'timestamp': datetime.now().isoformat(),
            'plan': plan,
            'stripe_session_id': session_id,
            'amount': 3.99 if plan == 'weekly' else (11.99 if plan == 'monthly' else 95.00)
        }
        
        with open('payment_logs.json', 'a') as f:
            f.write(json.dumps(payment_data) + '\n')
            
    except Exception as e:
        print(f"Payment logging error: {e}")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
