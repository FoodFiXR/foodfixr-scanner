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

@app.route('/test-manual', methods=['GET', 'POST'])
def test_manual():
    """Manual text input for testing ingredient detection"""
    if request.method == 'GET':
        return '''
        <html>
        <head>
            <title>Manual Ingredient Test</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }
                .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }
                textarea { width: 100%; height: 200px; padding: 15px; border: 2px solid #e91e63; border-radius: 5px; font-size: 16px; }
                button { background: #e91e63; color: white; padding: 15px 30px; border: none; border-radius: 5px; font-size: 16px; cursor: pointer; }
                button:hover { background: #c2185b; }
                .preset { margin: 10px 0; padding: 10px; background: #f0f0f0; border-radius: 5px; cursor: pointer; }
                .preset:hover { background: #e0e0e0; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🧪 Manual Ingredient Testing</h1>
                <p>Enter ingredient text to test the detection system:</p>
                
                <form method="post">
                    <textarea name="ingredients" placeholder="Enter ingredients here... e.g., corn syrup, monosodium glutamate, natural flavors"></textarea>
                    <br><br>
                    <button type="submit">🔬 Test Ingredients</button>
                </form>
                
                <h3>Quick Test Presets:</h3>
                <div class="preset" onclick="fillText('corn syrup, monosodium glutamate, natural flavors, salt')">
                    🚨 High Risk Test: corn syrup, monosodium glutamate, natural flavors, salt
                </div>
                <div class="preset" onclick="fillText('partially hydrogenated soybean oil, sugar, salt')">
                    🚨 Trans Fat Test: partially hydrogenated soybean oil, sugar, salt
                </div>
                <div class="preset" onclick="fillText('chicken stock, modified cornstarch, vegetable oil, wheat flour, cream, chicken meat, chicken fat, salt, whey, dried chicken, monosodium glutamate, soy protein concentrate, water, natural flavoring, yeast extract, beta carotene for color, soy protein isolate, sodium phosphate, celery extract, onion extract, butter, garlic juice concentrate')">
                    📸 Campbell's Soup Test (from your image)
                </div>
                
                <script>
                function fillText(text) {
                    document.querySelector('textarea[name="ingredients"]').value = text;
                }
                </script>
                
                <p><a href="/">← Back to Main Scanner</a></p>
            </div>
        </body>
        </html>
        '''
    
    # Handle POST request
    ingredients_text = request.form.get('ingredients', '').strip()
    
    if not ingredients_text:
        return redirect('/test-manual')
    
    try:
        # Test the ingredient detection system directly
        from ingredient_scanner import match_all_ingredients, rate_ingredients_according_to_hierarchy, assess_text_quality_enhanced
        
        print(f"DEBUG: Manual test with text: {ingredients_text}")
        
        # Assess quality
        quality = assess_text_quality_enhanced(ingredients_text)
        print(f"DEBUG: Text quality: {quality}")
        
        # Match ingredients
        matches = match_all_ingredients(ingredients_text)
        print(f"DEBUG: Matches: {matches}")
        
        # Rate ingredients
        rating = rate_ingredients_according_to_hierarchy(matches, quality)
        print(f"DEBUG: Rating: {rating}")
        
        # Create result object
        result = {
            "rating": rating,
            "matched_ingredients": matches,
            "confidence": "high",
            "text_quality": quality,
            "extracted_text_length": len(ingredients_text),
            "gmo_alert": "📣 GMO Alert!" if matches["gmo"] else None
        }
        
        # Render result using the same template as main scanner
        return render_template('scanner.html',
                             result=result,
                             trial_expired=False,
                             trial_time_left="Manual Test",
                             stripe_publishable_key="test")
                             
    except Exception as e:
        print(f"ERROR in manual test: {e}")
        import traceback
        traceback.print_exc()
        
        return f'''
        <html>
        <body>
        <h1>❌ Test Error</h1>
        <p>Error: {str(e)}</p>
        <a href="/test-manual">← Try Again</a>
        </body>
        </html>
        '''
        
@app.route('/debug-ocr', methods=['GET', 'POST'])
def debug_ocr():
    """Debug what OCR is actually reading - Enhanced version"""
    if request.method == 'GET':
        return '''
        <html>
        <head>
            <title>OCR Debug Tool</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }
                .container { max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
                .upload-area { border: 2px dashed #e91e63; border-radius: 10px; padding: 40px; text-align: center; margin: 20px 0; }
                .upload-area:hover { background: #fafafa; }
                input[type="file"] { margin: 10px 0; }
                button { background: #e91e63; color: white; padding: 12px 24px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
                button:hover { background: #c2185b; }
                .back-link { color: #666; text-decoration: none; margin-top: 20px; display: inline-block; }
                .back-link:hover { color: #e91e63; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔍 OCR Debug Tool</h1>
                <p>Upload an image with ingredient text to see exactly what the OCR system detects and how it's processed.</p>
                
                <form method="post" enctype="multipart/form-data">
                    <div class="upload-area">
                        <h3>📸 Select Image</h3>
                        <input type="file" name="image" accept="image/*" required>
                        <br><br>
                        <button type="submit">🔬 Analyze Image</button>
                    </div>
                </form>
                
                <a href="/" class="back-link">← Back to Main Scanner</a>
            </div>
        </body>
        </html>
        '''
    
    if 'image' not in request.files:
        return "No image uploaded"
    
    file = request.files['image']
    if file.filename == '':
        return "No image selected"
    
    try:
        import tempfile
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"debug_{timestamp}_{filename}"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        file.save(filepath)
        
        print(f"DEBUG OCR: Processing {filepath}")
        
        # Use the NEW function names from updated ingredient_scanner
        from ingredient_scanner import extract_text_with_multiple_methods, assess_text_quality_enhanced, match_all_ingredients, rate_ingredients_according_to_hierarchy
        
        # Extract text with full debug output
        text = extract_text_with_multiple_methods(filepath)
        quality = assess_text_quality_enhanced(text)
        matches = match_all_ingredients(text)
        rating = rate_ingredients_according_to_hierarchy(matches, quality)
        
        # Clean up
        os.remove(filepath)
        
        # Format matches for display (removed safe_ingredients)
        matches_display = ""
        total_ingredients = 0
        for category, ingredients in matches.items():
            if ingredients and category != 'all_detected':
                matches_display += f"<div style='margin: 10px 0; padding: 10px; background: #f0f8ff; border-left: 4px solid #e91e63;'>"
                matches_display += f"<strong style='color: #e91e63;'>{category.replace('_', ' ').title()}:</strong><br>"
                matches_display += f"<span style='color: #333;'>{', '.join(ingredients)}</span>"
                matches_display += f"</div>"
                total_ingredients += len(ingredients)
        
        if not matches_display:
            matches_display = "<div style='padding: 20px; background: #fff3e0; border-radius: 5px; color: #f57c00;'>❌ No ingredients detected</div>"
        
        # Color code the rating
        rating_color = "#4CAF50"  # Green for safe
        if "Danger" in rating:
            rating_color = "#f44336"  # Red for danger
        elif "Proceed" in rating:
            rating_color = "#ff9800"  # Orange for caution
        elif "TRY AGAIN" in rating:
            rating_color = "#2196F3"  # Blue for try again
        
        return f"""
        <html>
        <head>
            <title>OCR Debug Results</title>
            <style>
                body {{ font-family: 'Courier New', monospace; padding: 20px; background: #f5f5f5; line-height: 1.6; }}
                .container {{ max-width: 900px; margin: 0 auto; }}
                .section {{ background: white; margin: 20px 0; padding: 20px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .rating {{ font-size: 24px; font-weight: bold; color: {rating_color}; text-align: center; padding: 20px; background: rgba(0,0,0,0.05); border-radius: 10px; }}
                .stats {{ display: flex; justify-content: space-around; background: #e8f5e8; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .stat {{ text-align: center; }}
                .stat-number {{ font-size: 24px; font-weight: bold; color: #2e7d32; }}
                .stat-label {{ color: #666; font-size: 12px; }}
                .text-box {{ border: 1px solid #ddd; padding: 15px; background: #fafafa; border-radius: 5px; max-height: 300px; overflow-y: auto; white-space: pre-wrap; font-size: 14px; }}
                .nav-buttons {{ text-align: center; margin: 30px 0; }}
                .nav-buttons a {{ background: #e91e63; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; margin: 0 10px; display: inline-block; }}
                .nav-buttons a:hover {{ background: #c2185b; }}
                .nav-buttons a.secondary {{ background: #666; }}
                .nav-buttons a.secondary:hover {{ background: #555; }}
                h1 {{ color: #e91e63; text-align: center; }}
                h3 {{ color: #333; border-bottom: 2px solid #e91e63; padding-bottom: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔍 OCR Debug Results</h1>
                
                <div class="section">
                    <div class="rating">Final Rating: {rating}</div>
                    
                    <div class="stats">
                        <div class="stat">
                            <div class="stat-number">{len(text)}</div>
                            <div class="stat-label">Characters</div>
                        </div>
                        <div class="stat">
                            <div class="stat-number">{quality}</div>
                            <div class="stat-label">Quality</div>
                        </div>
                        <div class="stat">
                            <div class="stat-number">{total_ingredients}</div>
                            <div class="stat-label">Ingredients</div>
                        </div>
                        <div class="stat">
                            <div class="stat-number">{len(matches.get('all_detected', []))}</div>
                            <div class="stat-label">Total Detected</div>
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <h3>📝 Raw Text Extracted</h3>
                    <div class="text-box">{text or "❌ NO TEXT DETECTED - Try a clearer image with better lighting"}</div>
                </div>
                
                <div class="section">
                    <h3>🧬 Ingredient Analysis</h3>
                    {matches_display}
                    
                    {'<div style="margin: 15px 0; padding: 15px; background: #fff3e0; border-radius: 5px;"><strong style="color: #f57c00;">📣 GMO Alert!</strong><br>This product contains genetically modified ingredients: ' + ', '.join(matches.get('gmo', [])) + '</div>' if matches.get('gmo') else ''}
                </div>
                
                {'<div class="section"><h3>🔧 Troubleshooting Tips</h3><ul><li>Ensure good lighting when taking the photo</li><li>Hold the camera steady and close enough to read the text clearly</li><li>Make sure the ingredient list is flat and not wrinkled</li><li>Try scanning just the ingredient section, not the entire package</li><li>Clean the camera lens before taking the photo</li></ul></div>' if quality == 'very_poor' or len(text) < 10 else ''}
                
                <div class="nav-buttons">
                    <a href="/debug-ocr">🔬 Test Another Image</a>
                    <a href="/" class="secondary">← Back to Main Scanner</a>
                </div>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"DEBUG OCR Error: {e}")
        print(f"Full traceback: {error_details}")
        
        return f"""
        <html>
        <head>
            <title>OCR Debug Error</title>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
                .error {{ background: #ffebee; border: 1px solid #f44336; border-radius: 5px; padding: 20px; margin: 20px 0; }}
                .error-details {{ background: #fafafa; border-radius: 5px; padding: 15px; font-family: monospace; overflow-x: auto; }}
                a {{ color: #e91e63; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>❌ OCR Debug Error</h1>
                
                <div class="error">
                    <p><strong>Error:</strong> {str(e)}</p>
                </div>
                
                <h3>🔧 Full Error Details:</h3>
                <div class="error-details">
                    <pre>{error_details}</pre>
                </div>
                
                <p><strong>Common Solutions:</strong></p>
                <ul>
                    <li>Make sure you uploaded a valid image file</li>
                    <li>Try a smaller image file (under 16MB)</li>
                    <li>Check OCR.space API connectivity</li>
                    <li>Verify image compression is working</li>
                </ul>
                
                <br>
                <a href="/debug-ocr">← Try Again</a> | 
                <a href="/">Main Scanner</a> | 
                <a href="/debug">System Debug</a>
            </div>
        </body>
        </html>
        """

@app.route('/test-scan')
def test_scan():
    """Test scanning without actual image"""
    try:
        # Test if all imports work
        from ingredient_scanner import scan_image_for_ingredients
        
        # Create a dummy result (removed safe_ingredients)
        test_result = {
            "rating": "✅ Yay! Safe!",
            "matched_ingredients": {
                "trans_fat": [],
                "excitotoxins": [],
                "corn": [],
                "sugar": [],
                "gmo": [],
                "all_detected": []
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
    
    # Test OCR.space API connection
    try:
        import requests
        api_url = 'https://api.ocr.space/parse/image'
        response = requests.get(api_url, timeout=10)
        debug_info.append(f"✅ OCR.space API: Reachable (status: {response.status_code})")
    except Exception as e:
        debug_info.append(f"❌ OCR.space API: Unreachable - {str(e)}")
    
    html = f"""
    <html>
    <head><title>FoodFixr Debug</title></head>
    <body style="font-family: monospace; padding: 20px;">
    <h1>🔍 FoodFixr Debug Info</h1>
    <div style="background: #f5f5f5; padding: 15px; border-radius: 5px;">
    {'<br>'.join(debug_info)}
    </div>
    <br>
    <a href="/debug-ocr" style="background: #2196F3; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px;">🔬 Test OCR</a>
    <a href="/test-manual" style="background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px;">🧪 Manual Test</a>
    <a href="/" style="background: #e91e63; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">← Back to Scanner</a>
    </div>
    </body>
    </html>
    """
    return html
        
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
