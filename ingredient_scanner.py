import pytesseract
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import re
import signal
import os
from scanner_config import *

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("OCR operation timed out")

def preprocess_image_fast(image):
    """Fast image preprocessing for better OCR accuracy"""
    # Convert to grayscale
    if image.mode != 'L':
        image = image.convert('L')
    
    # Resize if too large (speeds up processing)
    max_size = 1200
    if max(image.size) > max_size:
        ratio = max_size / max(image.size)
        new_size = tuple(int(dim * ratio) for dim in image.size)
        image = image.resize(new_size, Image.Resampling.LANCZOS)
    
    # Enhance contrast
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.5)
    
    # Auto-level the image
    image = ImageOps.autocontrast(image)
    
    return image

def extract_text_from_image(image_path):
    """Fast text extraction with timeout protection"""
    try:
        # Set timeout for the entire OCR operation
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(30)  # 30 second timeout
        
        image = Image.open(image_path)
        image = preprocess_image_fast(image)
        
        # Use fast OCR configuration
        config = '--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ,.-()'
        
        try:
            text = pytesseract.image_to_string(image, config=config, timeout=25)
            signal.alarm(0)  # Cancel alarm
            
            # Clean and normalize the text
            text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
            text = re.sub(r'[^\w\s,.-]', '', text)  # Remove special chars
            
            print(f"Extracted text: {text[:100]}...")  # Debug output
            return text
            
        except pytesseract.TesseractError as e:
            signal.alarm(0)
            print(f"Tesseract error: {e}")
            return ""
            
    except TimeoutError:
        signal.alarm(0)
        print("OCR timeout - image too complex")
        return ""
    except Exception as e:
        signal.alarm(0)
        print(f"❌ Error reading image: {e}")
        return ""

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
    }
    
    for wrong, correct in ocr_corrections.items():
        text = text.replace(wrong, correct)
    
    # Remove punctuation but keep spaces and common separators
    text = re.sub(r'[^\w\s,-]', ' ', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def fuzzy_match_ingredient(text, ingredient_list):
    """Fast ingredient matching"""
    matches = []
    normalized_text = normalize_text(text)
    
    for ingredient in ingredient_list:
        normalized_ingredient = normalize_text(ingredient)
        
        # Exact match (word boundaries)
        if re.search(r'\b' + re.escape(normalized_ingredient) + r'\b', normalized_text):
            matches.append(ingredient)
            continue
        
        # Check abbreviations
        if ingredient.lower() in ['msg', 'hfcs', 'bha', 'bht', 'tbhq']:
            if re.search(r'\b' + re.escape(ingredient.lower()) + r'\b', normalized_text):
                matches.append(ingredient)
    
    return matches

def match_ingredients(text):
    """Enhanced ingredient matching"""
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
    
    # Common safe ingredients
    safe_ingredients = [
        "water", "salt", "flour", "wheat flour", "rice", "oats", "milk", "eggs", 
        "butter", "olive oil", "vinegar", "lemon juice", "garlic", "onion", 
        "tomatoes", "cheese", "cream", "vanilla", "cinnamon", "pepper", "herbs",
        "spices", "whole wheat", "brown rice", "quinoa", "almonds", "nuts",
        "coconut", "cocoa", "chocolate", "vanilla extract", "baking soda",
        "baking powder", "yeast", "honey", "maple syrup", "sea salt"
    ]
    
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
    """Ingredient rating logic"""
    
    if text_quality == "very_poor":
        return "↪️ TRY AGAIN"
    
    # Check for TOP 5 MOST DANGEROUS ingredients
    top5_danger_found = []
    
    if matches["trans_fat"]:
        top5_trans_fats = [kw for kw in matches["trans_fat"] if kw in trans_fat_top5_danger]
        if top5_trans_fats:
            top5_danger_found.extend(top5_trans_fats)
    
    if matches["excitotoxins"]:
        top5_excitotoxins = [kw for kw in matches["excitotoxins"] if kw in excitotoxin_top5_danger]
        if top5_excitotoxins:
            top5_danger_found.extend(top5_excitotoxins)
    
    if matches["gmo"]:
        top5_gmo = [kw for kw in matches["gmo"] if kw in gmo_top5_danger]
        if top5_gmo:
            top5_danger_found.extend(top5_gmo)
    
    if top5_danger_found:
        return "🚨 Oh NOOOO! Danger!"
    
    # Count problematic ingredients
    total_problematic_count = (
        len(matches["trans_fat"]) + 
        len(matches["excitotoxins"]) + 
        len(matches["corn"]) + 
        len(matches["sugar"]) + 
        len(matches["gmo"])
    )
    
    if total_problematic_count >= 3:
        return "🚨 Oh NOOOO! Danger!"
    elif total_
