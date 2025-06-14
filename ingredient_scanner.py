import pytesseract
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import re
from scanner_config import *

def preprocess_image(image):
    """Enhanced image preprocessing for better OCR accuracy"""
    # Convert to grayscale
    if image.mode != 'L':
        image = image.convert('L')
    
    # Enhance contrast
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)
    
    # Enhance sharpness
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(2.0)
    
    # Apply slight blur to reduce noise
    image = image.filter(ImageFilter.MedianFilter(size=3))
    
    # Auto-level the image
    image = ImageOps.autocontrast(image)
    
    return image

def correct_image_orientation(image):
    """Improved orientation correction with fallback"""
    try:
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

def extract_text_from_image(image_path):
    """Enhanced text extraction with multiple OCR configurations"""
    try:
        image = Image.open(image_path)
        image = correct_image_orientation(image)
        image = preprocess_image(image)
        
        # Try multiple OCR configurations for better accuracy
        configs = [
            '--oem 3 --psm 6',  # Default: uniform block of text
            '--oem 3 --psm 8',  # Single word
            '--oem 3 --psm 7',  # Single text line
            '--oem 3 --psm 4',  # Single column of text
            '--oem 3 --psm 3',  # Fully automatic page segmentation
        ]
        
        texts = []
        for config in configs:
            try:
                text = pytesseract.image_to_string(image, config=config)
                if text.strip():
                    texts.append(text)
            except Exception:
                continue
        
        # Combine all extracted texts
        combined_text = ' '.join(texts)
        
        # Clean and normalize the text
        combined_text = re.sub(r'\s+', ' ', combined_text)  # Normalize whitespace
        combined_text = re.sub(r'[^\w\s,.-]', '', combined_text)  # Remove special chars except common punctuation
        
        print(f"Extracted text: {combined_text[:200]}...")  # Debug output
        return combined_text
        
    except Exception as e:
        print(f"❌ Error reading image: {e}")
        return ""

def normalize_text(text):
    """Enhanced text normalization"""
    if not text:
        return ""
    
    text = text.lower()
    
    # Fix common OCR errors from config
    for wrong, correct in common_ocr_errors.items():
        text = text.replace(wrong, correct)
    
    # Additional OCR fixes
    ocr_corrections = {
        '0': 'o',
        '1': 'l',
        '5': 's',
        '8': 'b',
        'rn': 'm',
        'vv': 'w',
        'ii': 'll',
        'oo': '00',
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
    """Enhanced ingredient matching that finds ALL ingredients"""
    if not text:
        return {
            "trans_fat": [],
            "excitotoxins": [],
            "corn": [],
            "sugar": [],
            "gmo": [],
            "safe_ingredients": [],
            "all_detected": []
        }
    
    # Use precise matching for each category
    trans_fat_matches = fuzzy_match_ingredient(text, trans_fat_high_risk + trans_fat_moderate_risk)
    excitotoxin_matches = fuzzy_match_ingredient(text, excitotoxin_high_risk + excitotoxin_moderate_risk)
    corn_matches = fuzzy_match_ingredient(text, corn_high_risk + corn_moderate_risk)
    sugar_matches = fuzzy_match_ingredient(text, sugar_keywords)
    gmo_matches = fuzzy_match_ingredient(text, gmo_keywords)
    safe_matches = fuzzy_match_ingredient(text, safe_ingredients)
    
    # Combine all detected ingredients
    all_detected = list(set(trans_fat_matches + excitotoxin_matches + corn_matches + 
                           sugar_matches + gmo_matches + safe_matches))
    
    return {
        "trans_fat": list(set(trans_fat_matches)),
        "excitotoxins": list(set(excitotoxin_matches)),
        "corn": list(set(corn_matches)),
        "sugar": list(set(sugar_matches)),
        "gmo": list(set(gmo_matches)),
        "safe_ingredients": list(set(safe_matches)),
        "all_detected": all_detected
    }

def rate_ingredients(matches, text_quality):
    """
    Updated ingredient rating following EXACT hierarchy rules:
    1. Trans Fats: High danger (even 1 = danger)
    2. Excitotoxins: High danger (even 1 = danger)
    3. Corn: Moderate Danger  
    4. Sugar: Low danger
    5. GMO: Not part of ranking but flagged
    
    Per category: if 1-2 stays Proceed Carefully, if 3+ = Oh NOOO! Danger!
    """
    
    # If text quality is too poor, suggest trying again
    if text_quality == "very_poor":
        return "↪️ TRY AGAIN"
    
    # Rule 1: Check for HIGH DANGER ingredients (Trans Fats and Excitotoxins)
    # Even 1 = danger for these categories
    
    # Check trans fats - ANY trans fat from high risk list = immediate danger
    if matches["trans_fat"]:
        for ingredient in matches["trans_fat"]:
            if ingredient.lower() in [i.lower() for i in trans_fat_high_risk]:
                print(f"🚨 HIGH DANGER: Found high-risk trans fat: {ingredient}")
                return "🚨 Oh NOOOO! Danger!"
    
    # Check excitotoxins - ANY excitotoxin from high risk list = immediate danger
    if matches["excitotoxins"]:
        for ingredient in matches["excitotoxins"]:
            if ingredient.lower() in [i.lower() for i in excitotoxin_high_risk]:
                print(f"🚨 HIGH DANGER: Found high-risk excitotoxin: {ingredient}")
                return "🚨 Oh NOOOO! Danger!"
    
    # Rule 2: Count ALL problematic ingredients for the 1-2 vs 3+ rule
    # This includes: moderate trans fats, moderate excitotoxins, corn, and sugar
    total_problematic_count = 0
    
    # Count moderate risk trans fats
    if matches["trans_fat"]:
        for ingredient in matches["trans_fat"]:
            if ingredient.lower() in [i.lower() for i in trans_fat_moderate_risk]:
                total_problematic_count += 1
    
    # Count moderate risk excitotoxins
    if matches["excitotoxins"]:
        for ingredient in matches["excitotoxins"]:
            if ingredient.lower() in [i.lower() for i in excitotoxin_moderate_risk]:
                total_problematic_count += 1
    
    # Count ALL corn ingredients (high + moderate risk)
    if matches["corn"]:
        total_problematic_count += len(matches["corn"])
    
    # Count ALL sugar ingredients
    if matches["sugar"]:
        total_problematic_count += len(matches["sugar"])
    
    print(f"⚖️ Total problematic ingredients: {total_problematic_count}")
    
    # Apply the hierarchy rule: 1-2 = Proceed Carefully, 3+ = Danger
    if total_problematic_count >= 3:
        return "🚨 Oh NOOOO! Danger!"
    elif total_problematic_count >= 1:
        return "⚠️ Proceed carefully"
    
    # If poor text quality and no clear ingredients detected, suggest trying again
    if text_quality == "poor" and len(matches["all_detected"]) == 0:
        return "↪️ TRY AGAIN"
    
    # No dangerous ingredients found
    return "✅ Yay! Safe!"

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

def scan_image_for_ingredients(image_path):
    """Main scanning function with enhanced processing and quality assessment"""
    try:
        text = extract_text_from_image(image_path)
        text_quality = assess_text_quality(text)
        
        matches = match_ingredients(text)
        rating = rate_ingredients(matches, text_quality)
        
        # Add confidence score based on text extraction quality
        if text_quality == "very_poor":
            confidence = "very_low"
        elif text_quality == "poor":
            confidence = "low"
        elif len(text) > 50:
            confidence = "high"
        else:
            confidence = "medium"
        
        # Check for GMO Alert
        gmo_alert = "📣 GMO Alert!" if matches["gmo"] else None
        
        result = {
            "rating": rating,
            "matched_ingredients": matches,
            "confidence": confidence,
            "extracted_text_length": len(text),
            "text_quality": text_quality,
            "extracted_text": text[:200] + "..." if len(text) > 200 else text,
            "gmo_alert": gmo_alert
        }
        
        print(f"Scan result: {rating}, Confidence: {confidence}, Text quality: {text_quality}")
        print(f"Detected ingredients by category:")
        print(f"  - Trans Fat: {len(matches.get('trans_fat', []))}")
        print(f"  - Excitotoxins: {len(matches.get('excitotoxins', []))}")
        print(f"  - Corn: {len(matches.get('corn', []))}")
        print(f"  - Sugar: {len(matches.get('sugar', []))}")
        print(f"  - GMO: {len(matches.get('gmo', []))}")
        print(f"  - Safe: {len(matches.get('safe_ingredients', []))}")
        if gmo_alert:
            print(f"{gmo_alert}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error in scan_image_for_ingredients: {e}")
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
            "text_quality": "very_poor",
            "extracted_text_length": 0,
            "gmo_alert": None
        }
