from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import csv
import json
import stripe
from ingredient_scanner import scan_image_for_ingredients

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')

# Stripe configuration
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Simple user storage (in production, use a database)
users = {}

def get_user_id():
    """Get or create user ID for session"""
    if 'user_id' not in session:
        session['user_id'] = str(datetime.now().timestamp()).replace('.', '')
        users[session['user_id']] = {
            'created_at': datetime.now(),
            'scan_count': 0,
            'is_premium': False,
            'subscription_id': None
        }
    return session['user_id']

def can_scan():
    """Check if user can perform a scan"""
    user_id = get_user_id()
    user = users.get(user_id, {})
    
    # Check if user is premium
    if user.get('is_premium', False):
        return True, "premium"
    
    # Check if within 48-hour free period
    created_at = user.get('created_at', datetime.now())
    if datetime.now() - created_at < timedelta(hours=48):
        return True, "free_trial"
    
    return False, "trial_expired"

@app.route("/")
def home():
    """Landing page with usage info"""
    user_id = get_user_id()
    user = users.get(user_id, {})
    
    can_use, status = can_scan()
    
    # Calculate time remaining in trial
    created_at = user.get('created_at', datetime.now())
    trial_end = created_at + timedelta(hours=48)
    time_remaining = trial_end - datetime.now()
    
    return render_template("landing.html", 
                         can_use=can_use, 
                         status=status,
                         time_remaining=time_remaining,
                         scan_count=user.get('scan_count', 0),
                         stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)

@app.route("/scanner", methods=["GET", "POST"])
def scanner():
    """Main scanner page"""
    can_use, status = can_scan()
    
    if not can_use:
        return redirect(url_for('upgrade'))
    
    result = None
    if request.method == "POST":
        # Increment scan count
        user_id = get_user_id()
        users[user_id]['scan_count'] = users[user_id].get('scan_count', 0) + 1
        
        image = request.files["image"]
        filename = secure_filename(image.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image.save(filepath)
        result = scan_image_for_ingredients(filepath)

        # Log result
        try:
            with open("scan_history.csv", "a", newline="") as csvfile:
                fieldnames = ["timestamp", "user_id", "filename", "rating"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                if csvfile.tell() == 0:
                    writer.writeheader()
                writer.writerow({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "user_id": user_id,
                    "filename": filename,
                    "rating": result.get("rating", "unknown")
                })
        except Exception as e:
            print(f"Logging error: {e}")

        # Clean up uploaded file
        try:
            os.remove(filepath)
        except:
            pass

    return render_template("scanner.html", result=result, status=status)

@app.route("/upgrade")
def upgrade():
    """Upgrade page for expired trial users"""
    return render_template("upgrade.html", stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    """Create Stripe checkout session for subscription"""
    try:
        user_id = get_user_id()
        
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'FoodFixr Premium Scanner',
                        'description': 'Unlimited ingredient scans for $2.99/month'
                    },
                    'unit_amount': 299,  # $2.99 in cents
                    'recurring': {
                        'interval': 'month',
                    },
                },
                'quantity': 1,
            }],
            mode='subscription',
            success_url=request.host_url + 'success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=request.host_url + 'upgrade',
            client_reference_id=user_id,
        )
        
        return jsonify({'id': checkout_session.id})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route("/success")
def success():
    """Payment success page"""
    session_id = request.args.get('session_id')
    
    if session_id:
        try:
            session_obj = stripe.checkout.Session.retrieve(session_id)
            user_id = session_obj.client_reference_id
            
            # Mark user as premium
            if user_id in users:
                users[user_id]['is_premium'] = True
                users[user_id]['subscription_id'] = session_obj.subscription
                
        except Exception as e:
            print(f"Error retrieving session: {e}")
    
    return render_template("success.html")

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhooks"""
    try:
        payload = request.data
        sig_header = request.headers.get('Stripe-Signature')
        endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')

        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        
        # Handle subscription cancellation
        if event['type'] == 'customer.subscription.deleted':
            subscription = event['data']['object']
            for user_id, user_data in users.items():
                if user_data.get('subscription_id') == subscription['id']:
                    users[user_id]['is_premium'] = False
                    break
        
        return "Success", 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return "Error", 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)