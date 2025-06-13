import re
import os
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
from scanner_config import *

# Check if pytesseract is available
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
    print("✅ Tesseract is available")
except ImportError:
    TESSERACT_AVAILABLE = False
    print("⚠️ Tesseract not available, using fallback")

def preprocess_image(image):
    """Enhanced image preprocessing for better OCR accuracy"""
    try:
        # Convert to grayscale
        if image.mode != 'L':
            image = image.convert('L')
        
        # Resize if too large (helps with processing speed and memory)
        max_size = 1200
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)
        
        # Enhance sharpness
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.2)
        
        # Auto-level the image
        image = ImageOps.autocontrast(image)
        
        return image
    except Exception as e:
        print(f"Image preprocessing error: {e}")
        return image

def correct_image_orientation(image):
    """Improved orientation correction with fallback"""
    try:
        if TESSERACT_AVAILABLE:
            osd = pytesseract.image_to_osd(image)
            rotation_match = re.search(r'(?<=Rotate: )\d+', osd)
            if rotation_match:
                rotation_angle = int(rotation_match.group(0))
                if rotation_angle != 0:
                    return image.rotate(360 - rotation_angle, expand=True)
        return image
    except Exception as e:
        print(f"Orientation detection failed: {e}, using original image")
        return image

def extract_text_with_tesseract(image_path):
    """Extract text using Tesseract OCR with timeout protection"""
    try:
        image = Image.open(image_path)
        image = correct_image_orientation(image)
        image = preprocess_image(image)
        
        # Use optimized OCR configuration
        config = '--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ,.():-/'
        
        # Try multiple OCR configurations for better accuracy
        configs = [
            config,  # Primary config
            '--oem 3 --psm 8',  # Single word
            '--oem 3 --psm 7',  # Single text line
            '--oem 3 --psm 4',  # Single column of text
        ]
        
        texts = []
        for cfg in configs:
            try:
                text = pytesseract.image_to_string(image, config=cfg, timeout=20)
                if text and text.strip():
                    texts.append(text.strip())
            except Exception as e:
                print(f"OCR config failed: {e}")
                continue
        
        # Combine all extracted texts
        combined_text = ' '.join(texts) if texts else ""
        
        # Clean and normalize the text
        combined_text = re.sub(r'\s+', ' ', combined_text)  # Normalize whitespace
        combined_text = re.sub(r'[^\w\s,.-]', '', combined_text)  # Remove special chars
        combined_text = combined_text.strip()
        
        print(f"Tesseract extracted: {combined_text[:150]}...")
        return combined_text
        
    except Exception as e:
        print(f"Tesseract extraction error: {e}")
        return ""

def extract_text_fallback(image_path):
    """
    Conservative fallback - returns empty text to trigger TRY AGAIN
    rather than simulating ingredients that might be wrong
    """
    try:
        print("Using fallback - unable to detect ingredients properly")
        # Return empty text which will trigger TRY AGAIN rating
        return ""
        
    except Exception as e:
        print(f"Fallback extraction error: {e}")
        return ""

def extract_text_from_image(image_path):
    """Main text extraction function with comprehensive fallback"""
    print(f"🔍 Processing image: {os.path.basename(image_path)}")
    
    extracted_text = ""
    
    # Try Tesseract if available
    if TESSERACT_AVAILABLE:
        extracted_text = extract_text_with_tesseract(image_path)
        
        # Check if we got meaningful text
        if extracted_text and len(extracted_text.strip()) > 10:
            print(f"✅ Tesseract success: {len(extracted_text)} characters")
            return extracted_text
        else:
            print("⚠️ Tesseract didn't extract enough text, using fallback")
    
    # Use fallback if Tesseract failed or unavailable
    return extract_text_fallback(image_path)

def normalize_text(text):
    """Enhanced text normalization"""
    if not text:
        return ""
    
    text = text.lower()
    
    # Fix common OCR errors
    ocr_corrections = {
        '0': 'o',
        '1': 'l', 
        '5': 's',
        '8': 'b',
        'rn': 'm',
        'vv': 'w',
        'ii': 'll',
        'com ': 'corn ',
        'natur ': 'natural ',
        'artif ': 'artificial ',
        'preserv ': 'preservative ',
    }
    
    for wrong, correct in ocr_corrections.items():
        text = text.replace(wrong, correct)
    
    # Remove punctuation but keep spaces and common separators
    text = re.sub(r'[^\w\s,-]', ' ', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def fuzzy_match_ingredient(text, ingredient_list):
    """Improved ingredient matching with more precise matching"""
    matches = []
    normalized_text = normalize_text(text)
    
    for ingredient in ingredient_list:
        normalized_ingredient = normalize_text(ingredient)
        
        # Skip empty ingredients
        if not normalized_ingredient:
            continue
        
        # Exact match (must be surrounded by word boundaries)
        if re.search(r'\b' + re.escape(normalized_ingredient) + r'\b', normalized_text):
            matches.append(ingredient)
            continue
        
        # For compound ingredients, check if all words are present as separate words
        ingredient_words = normalized_ingredient.split()
        if len(ingredient_words) > 1:
            # Check if all words of the ingredient are present as whole words
            if all(re.search(r'\b' + re.escape(word) + r'\b', normalized_text) for word in ingredient_words):
                # Additional check: words should be reasonably close to each other
                positions = []
                for word in ingredient_words:
                    match = re.search(r'\b' + re.escape(word) + r'\b', normalized_text)
                    if match:
                        positions.append(match.start())
                
                # If words are within 50 characters of each other, consider it a match
                if positions and max(positions) - min(positions) < 50:
                    matches.append(ingredient)
                    continue
        
        # Check for exact abbreviations only
        if ingredient.lower() in ['msg', 'hfcs', 'hvp', 'bha', 'bht', 'tbhq']:
            if re.search(r'\b' + re.escape(ingredient.lower()) + r'\b', normalized_text):
                matches.append(ingredient)
    
    return matches

def match_ingredients(text):
    """Enhanced ingredient matching that follows the hierarchy from the requirements"""
    if not text:
        return {
            "trans_fat": [],
            "excitotoxins": [],
            "corn": [],
            "sugar": [],
            "gmo": [],
            "safe_ingredients": [],
            "all_detected": [],
            "confidence_score": 0
        }
    
    print(f"🔬 Analyzing text: {text[:100]}...")
    
    # First, check if we can identify ANY common ingredients at all
    # This helps us determine if the scan quality is good enough
    common_test_ingredients = [
        "water", "salt", "sugar", "flour", "oil", "milk", "eggs", "butter",
        "corn", "soy", "wheat", "rice", "natural", "artificial", "flavor",
        "color", "preservative", "acid", "sodium", "modified", "extract"
    ]
    
    # Count how many common ingredient words we can find
    common_found = 0
    normalized_text = normalize_text(text)
    for test_word in common_test_ingredients:
        if re.search(r'\b' + re.escape(test_word.lower()) + r'\b', normalized_text):
            common_found += 1
    
    # Calculate confidence score based on common ingredients found
    confidence_score = min(common_found / 5.0, 1.0)  # At least 5 common words for full confidence
    
    # Use precise matching for each category
    trans_fat_matches = fuzzy_match_ingredient(text, trans_fat_high_risk + trans_fat_moderate_risk)
    excitotoxin_matches = fuzzy_match_ingredient(text, excitotoxin_high_risk + excitotoxin_moderate_risk)
    corn_matches = fuzzy_match_ingredient(text, corn_high_risk + corn_moderate_risk)
    sugar_matches = fuzzy_match_ingredient(text, sugar_keywords)
    gmo_matches = fuzzy_match_ingredient(text, gmo_keywords)
    
    # Also detect common safe ingredients
    safe_ingredients = [
        "water", "salt", "flour", "wheat flour", "rice", "oats", "milk", "eggs", 
        "butter", "olive oil", "vinegar", "lemon juice", "garlic", "onion", 
        "tomatoes", "cheese", "cream", "vanilla", "cinnamon", "pepper", "herbs",
        "spices", "whole wheat", "brown rice", "quinoa", "almonds", "nuts",
        "coconut", "cocoa", "chocolate", "vanilla extract", "baking soda",
        "baking powder", "yeast", "honey", "maple syrup", "sea salt", "iodized salt",
        "garlic powder", "onion powder", "paprika", "oregano", "basil", "coconut oil",
        "palm oil", "ghee", "cold-pressed oil", "avocado oil", "walnut oil"
    ]
    
    safe_matches = fuzzy_match_ingredient(text, safe_ingredients)
    
    # Combine all detected ingredients
    all_detected = list(set(trans_fat_matches + excitotoxin_matches + corn_matches + 
                           sugar_matches + gmo_matches + safe_matches))
    
    print(f"📊 Found ingredients:")
    print(f"  • Trans fat: {trans_fat_matches}")
    print(f"  • Excitotoxins: {excitotoxin_matches}")
    print(f"  • Corn: {corn_matches}")
    print(f"  • Sugar: {sugar_matches}")
    print(f"  • GMO: {gmo_matches}")
    print(f"  • Safe: {safe_matches}")
    print(f"  • Total: {len(all_detected)} ingredients")
    print(f"  • Confidence: {confidence_score:.2f}")
    
    return {
        "trans_fat": list(set(trans_fat_matches)),
        "excitotoxins": list(set(excitotoxin_matches)),
        "corn": list(set(corn_matches)),
        "sugar": list(set(sugar_matches)),
        "gmo": list(set(gmo_matches)),
        "safe_ingredients": list(set(safe_matches)),
        "all_detected": all_detected,
        "confidence_score": confidence_score
    }

def rate_ingredients(matches, text_quality):
    """
    Updated ingredient rating with stricter confidence requirements.
    If we can't confidently detect ingredients, we ask to try again.
    """
    
    # Get confidence score from matches
    confidence_score = matches.get("confidence_score", 0)
    
    # If text quality is poor or we have very low confidence, suggest trying again
    if text_quality == "very_poor" or confidence_score < 0.3:
        return "↪️ TRY AGAIN"
    
    # If we detected very few ingredients (less than 3) and text quality isn't good
    # This likely means we couldn't read the label properly
    total_detected = len(matches["all_detected"])
    if total_detected < 3 and text_quality != "good":
        return "↪️ TRY AGAIN"
    
    # If we have low confidence but detected some dangerous ingredients
    # We should be cautious and ask to rescan rather than give wrong info
    dangerous_found = len(matches["trans_fat"]) + len(matches["excitotoxins"])
    if confidence_score < 0.5 and dangerous_found > 0:
        # We're not confident enough about dangerous ingredients
        return "↪️ TRY AGAIN"
    
    # Now proceed with normal rating if we have enough confidence
    
    # Check for HIGH DANGER ingredients (Trans Fats and Excitotoxins)
    high_danger_found = []
    
    # Check trans fats - any trans fat is immediate danger
    if matches["trans_fat"]:
        for ingredient in matches["trans_fat"]:
            if ingredient.lower() in [i.lower() for i in trans_fat_high_risk]:
                high_danger_found.append(f"Trans Fat: {ingredient}")
                break
    
    # Check excitotoxins - any excitotoxin is immediate danger
    if matches["excitotoxins"]:
        for ingredient in matches["excitotoxins"]:
            if ingredient.lower() in [i.lower() for i in excitotoxin_high_risk]:
                high_danger_found.append(f"Excitotoxin: {ingredient}")
                break
    
    # If any HIGH DANGER ingredients found with good confidence, return danger
    if high_danger_found and confidence_score >= 0.5:
        print(f"🚨 HIGH DANGER: Found dangerous ingredients: {high_danger_found}")
        return "🚨 Oh NOOOO! Danger!"
    
    # Count moderate and low danger ingredients
    moderate_count = 0
    
    # Corn (Moderate Danger)
    if matches["corn"]:
        moderate_count += len(matches["corn"])
    
    # Sugar (Low Danger)
    if matches["sugar"]:
        moderate_count += len(matches["sugar"])
    
    # Also count moderate risk trans fats and excitotoxins
    for ingredient in matches["trans_fat"]:
        if ingredient.lower() in [i.lower() for i in trans_fat_moderate_risk]:
            moderate_count += 1
    
    for ingredient in matches["excitotoxins"]:
        if ingredient.lower() in [i.lower() for i in excitotoxin_moderate_risk]:
            moderate_count += 1
    
    print(f"⚖️ Total moderate/low danger ingredients: {moderate_count}")
    print(f"📊 Confidence score: {confidence_score:.2f}")
    
    # If we have low confidence and found moderate dangers, be cautious
    if confidence_score < 0.6 and moderate_count > 0:
        return "↪️ TRY AGAIN"
    
    # Per requirements: if 1-2 stays Proceed Carefully, if 3+ = Danger
    if moderate_count >= 3:
        return "🚨 Oh NOOOO! Danger!"
    elif moderate_count >= 1:
        return "⚠️ Proceed carefully"
    
    # If we only found safe ingredients with good confidence
    if len(matches["safe_ingredients"]) > 0 and confidence_score >= 0.5:
        return "✅ Yay! Safe!"
    
    # If we're not sure (low ingredients detected, medium confidence)
    if total_detected < 5 and confidence_score < 0.7:
        return "↪️ TRY AGAIN"
    
    # Default to safe only if we have good confidence
    if confidence_score >= 0.6:
        return "✅ Yay! Safe!"
    else:
        return "↪️ TRY AGAIN"

def assess_text_quality(text):
    """Assess the quality of extracted text to determine if we should suggest trying again"""
    if not text or len(text.strip()) < 5:
        return "very_poor"
    
    # Check for meaningless character sequences that suggest poor OCR
    meaningless_patterns = [
        r'^[^a-zA-Z]*$',  # Only numbers/symbols
        r'^.{1,3}$',      # Too short
        r'[^\w\s]{5,}',   # Too many special characters in sequence
    ]
    
    for pattern in meaningless_patterns:
        if re.search(pattern, text):
            return "very_poor"
    
    # Check for reasonable word-like content
    words = re.findall(r'\b[a-zA-Z]{2,}\b', text)
    if len(words) < 2:
        return "poor"
    
    # Check text length and word ratio
    if len(text) < 15 or len(words) / len(text.split()) < 0.3:
        return "poor"
    
    return "good"

def get_emoji_shower_type(rating):
    """Determine emoji shower type based on rating - returns None for TRY AGAIN"""
    if "TRY AGAIN" in rating:
        return None  # No emoji shower for try again
    elif "Danger" in rating:
        return "danger"
    elif "Proceed carefully" in rating:
        return "caution"
    elif "Safe" in rating:
        return "safe"
    else:
        return None

def scan_image_for_ingredients(image_path):
    """Main scanning function with enhanced processing and stricter confidence requirements"""
    print(f"🚀 Starting ingredient scan for: {os.path.basename(image_path)}")
    
    try:
        # Extract text from image
        text = extract_text_from_image(image_path)
        print(f"📝 Extracted text length: {len(text)}")
        
        # Assess text quality
        text_quality = assess_text_quality(text)
        print(f"🎯 Text quality: {text_quality}")
        
        # Match ingredients
        matches = match_ingredients(text)
        
        # Get confidence score
        confidence_score = matches.get("confidence_score", 0)
        
        # Rate the ingredients
        rating = rate_ingredients(matches, text_quality)
        print(f"🏆 Final rating: {rating}")
        
        # Determine emoji shower type
        emoji_shower_type = get_emoji_shower_type(rating)
        print(f"🎊 Emoji shower type: {emoji_shower_type}")
        
        # Determine overall confidence
        if confidence_score >= 0.7:
            confidence = "high"
        elif confidence_score >= 0.5:
            confidence = "medium"
        elif confidence_score >= 0.3:
            confidence = "low"
        else:
            confidence = "very_low"
        
        # Add GMO alert if GMO ingredients found
        gmo_alert = "📣 GMO Alert!" if matches["gmo"] else None
        
        result = {
            "rating": rating,
            "matched_ingredients": matches,
            "confidence": confidence,
            "confidence_score": confidence_score,
            "extracted_text_length": len(text),
            "text_quality": text_quality,
            "extracted_text": text[:200] + "..." if len(text) > 200 else text,
            "emoji_shower_type": emoji_shower_type,
            "gmo_alert": gmo_alert
        }
        
        print(f"✅ Scan complete! Rating: {rating}, Confidence: {confidence} ({confidence_score:.2f})")
        if gmo_alert:
            print(f"📣 GMO ingredients detected!")
        
        return result
        
    except Exception as e:
        print(f"❌ Critical error in scan_image_for_ingredients: {e}")
        import traceback
        traceback.print_exc()
        
        # Return "try again" result instead of incorrect safe result
        return {
            "rating": "↪️ TRY AGAIN",
            "matched_ingredients": {
                "trans_fat": [],
                "excitotoxins": [],
                "corn": [],
                "sugar": [],
                "gmo": [],
                "safe_ingredients": [],
                "all_detected": []
            },
            "confidence": "very_low",
            "confidence_score": 0,
            "text_quality": "very_poor",
            "extracted_text_length": 0,
            "extracted_text": "",
            "emoji_shower_type": None,
            "gmo_alert": None
        }
