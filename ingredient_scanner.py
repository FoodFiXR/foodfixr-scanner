import pytesseract
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import re
import os
from scanner_config import *

def preprocess_image_simple(image):
    """Simplified image preprocessing using only PIL"""
    try:
        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Convert to grayscale
        gray = image.convert('L')
        
        # Resize if too small (critical for mobile photos)
        width, height = gray.size
        if width < 800:
            scale_factor = 800 / width
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            gray = gray.resize((new_width, new_height), Image.Resampling.LANCZOS)
            print(f"DEBUG: Resized image from {width}x{height} to {new_width}x{new_height}")
        
        # Enhance contrast aggressively
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(3.0)
        
        # Enhance sharpness
        enhancer = ImageEnhance.Sharpness(enhanced)
        enhanced = enhancer.enhance(2.0)
        
        # Apply median filter to reduce noise
        enhanced = enhanced.filter(ImageFilter.MedianFilter(size=3))
        
        # Auto-level
        enhanced = ImageOps.autocontrast(enhanced)
        
        # Equalize histogram
        enhanced = ImageOps.equalize(enhanced)
        
        print(f"DEBUG: Image preprocessing completed")
        return enhanced
        
    except Exception as e:
        print(f"DEBUG: Image preprocessing failed: {e}, using original")
        return image

def extract_text_from_image(image_path):
    """Simplified text extraction with aggressive preprocessing"""
    try:
        print(f"DEBUG: Starting text extraction from {image_path}")
        
        # Load image
        image = Image.open(image_path)
        print(f"DEBUG: Original image size: {image.size}, mode: {image.mode}")
        
        extracted_texts = []
        
        # Method 1: Heavily preprocessed image
        try:
            processed_img = preprocess_image_simple(image)
            
            # Try multiple OCR configurations
            configs = [
                '--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789(),-.',
                '--oem 3 --psm 4',
                '--oem 3 --psm 3',
                '--oem 3 --psm 6',
                '--oem 3 --psm 8',
                '--oem 3 --psm 7',
            ]
            
            for i, config in enumerate(configs):
                try:
                    text = pytesseract.image_to_string(processed_img, config=config)
                    text = text.strip()
                    if text and len(text) > 2:
                        extracted_texts.append(text)
                        print(f"DEBUG: Config {i+1} extracted {len(text)} chars: {text[:50]}...")
                except Exception as e:
                    print(f"DEBUG: Config {i+1} failed: {e}")
        except Exception as e:
            print(f"DEBUG: Processed image method failed: {e}")
        
        # Method 2: Simple grayscale with high contrast
        try:
            simple_gray = image.convert('L')
            enhancer = ImageEnhance.Contrast(simple_gray)
            high_contrast = enhancer.enhance(4.0)
            
            text = pytesseract.image_to_string(high_contrast, config='--oem 3 --psm 6')
            text = text.strip()
            if text and len(text) > 2:
                extracted_texts.append(text)
                print(f"DEBUG: Simple method extracted {len(text)} chars: {text[:50]}...")
        except Exception as e:
            print(f"DEBUG: Simple method failed: {e}")
        
        # Method 3: Original image
        try:
            text = pytesseract.image_to_string(image, config='--oem 3 --psm 6')
            text = text.strip()
            if text and len(text) > 2:
                extracted_texts.append(text)
                print(f"DEBUG: Original image extracted {len(text)} chars: {text[:50]}...")
        except Exception as e:
            print(f"DEBUG: Original image method failed: {e}")
        
        # Method 4: Black and white with threshold
        try:
            bw_img = image.convert('L')
            # Convert to pure black and white
            threshold = 128
            bw_img = bw_img.point(lambda x: 0 if x < threshold else 255, '1')
            
            text = pytesseract.image_to_string(bw_img, config='--oem 3 --psm 6')
            text = text.strip()
            if text and len(text) > 2:
                extracted_texts.append(text)
                print(f"DEBUG: B&W method extracted {len(text)} chars: {text[:50]}...")
        except Exception as e:
            print(f"DEBUG: B&W method failed: {e}")
        
        # Combine results
        if extracted_texts:
            # Take the longest text as it's likely most complete
            final_text = max(extracted_texts, key=len)
            
            # Add unique words from other extractions
            all_words = set()
            for text in extracted_texts:
                words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
                all_words.update(words)
            
            main_words = set(re.findall(r'\b[a-zA-Z]{2,}\b', final_text.lower()))
            missing_words = all_words - main_words
            if missing_words:
                final_text += " " + " ".join(missing_words)
            
            print(f"DEBUG: FINAL TEXT LENGTH: {len(final_text)} characters")
            print(f"DEBUG: FINAL TEXT PREVIEW: {final_text[:200]}...")
            return final_text
        else:
            print("DEBUG: No text extracted by any method")
            return ""
            
    except Exception as e:
        print(f"❌ Error in extract_text_from_image: {e}")
        import traceback
        traceback.print_exc()
        return ""

def normalize_text(text):
    """Enhanced text normalization with better OCR error correction"""
    if not text:
        return ""
    
    text = text.lower().strip()
    
    # Remove newlines and normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Fix common OCR errors
    ocr_fixes = {
        # Numbers to letters
        '0': 'o', '1': 'l', '5': 's', '8': 'b', '6': 'g',
        # Common character combinations
        'rn': 'm', 'vv': 'w', 'ii': 'll', 'cl': 'd',
        # Ingredient-specific fixes
        'corn5yrup': 'corn syrup',
        'hfc5': 'hfcs',
        'm5g': 'msg',
        'ms9': 'msg',
        'naturalflavors': 'natural flavors',
        'cornsynup': 'corn syrup',
        'com syrup': 'corn syrup',
        'partiallyhydrogenated': 'partially hydrogenated',
        'hydrogenatedoil': 'hydrogenated oil',
        'modifiedstarch': 'modified starch',
        'soylecithin': 'soy lecithin',
        'canolaoil': 'canola oil',
        'maltodextrin': 'maltodextrin',
    }
    
    for wrong, correct in ocr_fixes.items():
        text = text.replace(wrong, correct)
    
    return text

def fuzzy_match_ingredient(text, ingredient_list):
    """Improved ingredient matching"""
    matches = []
    normalized_text = normalize_text(text)
    
    print(f"DEBUG: Searching for ingredients in: {normalized_text[:100]}...")
    
    for ingredient in ingredient_list:
        normalized_ingredient = normalize_text(ingredient)
        
        if len(normalized_ingredient) < 3:
            continue
        
        # Exact match
        pattern = r'\b' + re.escape(normalized_ingredient) + r'\b'
        if re.search(pattern, normalized_text):
            matches.append(ingredient)
            print(f"DEBUG: Found exact match: '{normalized_ingredient}' -> '{ingredient}'")
            continue
        
        # Handle compound ingredients
        if ' ' in normalized_ingredient:
            words = normalized_ingredient.split()
            # Check if all words are present within reasonable distance
            word_positions = []
            for word in words:
                if len(word) > 2:  # Skip very short words
                    word_pattern = r'\b' + re.escape(word) + r'\b'
                    match = re.search(word_pattern, normalized_text)
                    if match:
                        word_positions.append(match.start())
                    else:
                        break
            
            if len(word_positions) == len(words):
                if len(word_positions) == 1 or (max(word_positions) - min(word_positions) < 80):
                    matches.append(ingredient)
                    print(f"DEBUG: Found compound match: '{normalized_ingredient}' -> '{ingredient}'")
        
        # Special handling for critical ingredients with fuzzy matching
        critical_ingredients = ['msg', 'aspartame', 'corn syrup', 'high fructose corn syrup', 'partially hydrogenated']
        if any(crit in ingredient.lower() for crit in critical_ingredients):
            # More lenient matching for critical ingredients
            ingredient_words = normalized_ingredient.split()
            main_word = max(ingredient_words, key=len) if ingredient_words else normalized_ingredient
            if len(main_word) > 3 and main_word in normalized_text:
                matches.append(ingredient)
                print(f"DEBUG: Found critical ingredient match: '{main_word}' -> '{ingredient}'")
    
    return list(set(matches))

def assess_text_quality(text):
    """More lenient text quality assessment"""
    if not text or len(text.strip()) < 1:
        return "very_poor"
    
    # Count meaningful words
    words = re.findall(r'\b[a-zA-Z]{2,}\b', text)
    
    if len(words) < 1:
        return "very_poor"
    elif len(words) < 2 or len(text) < 8:
        return "poor"
    else:
        return "good"

def match_ingredients(text):
    """Enhanced ingredient matching with debug output"""
    if not text:
        print("DEBUG: No text provided for ingredient matching")
        return {
            "trans_fat": [],
            "excitotoxins": [],
            "corn": [],
            "sugar": [],
            "gmo": [],
            "safe_ingredients": [],
            "all_detected": []
        }
    
    print(f"DEBUG: Matching ingredients in text of {len(text)} characters")
    
    # Use fuzzy matching for each category
    trans_fat_matches = fuzzy_match_ingredient(text, trans_fat_high_risk + trans_fat_moderate_risk)
    excitotoxin_matches = fuzzy_match_ingredient(text, excitotoxin_high_risk + excitotoxin_moderate_risk)
    corn_matches = fuzzy_match_ingredient(text, corn_high_risk + corn_moderate_risk)
    sugar_matches = fuzzy_match_ingredient(text, sugar_keywords)
    gmo_matches = fuzzy_match_ingredient(text, gmo_keywords)
    safe_matches = fuzzy_match_ingredient(text, safe_ingredients)
    
    # Combine all detected ingredients
    all_detected = list(set(trans_fat_matches + excitotoxin_matches + corn_matches + 
                           sugar_matches + gmo_matches + safe_matches))
    
    result = {
        "trans_fat": list(set(trans_fat_matches)),
        "excitotoxins": list(set(excitotoxin_matches)),
        "corn": list(set(corn_matches)),
        "sugar": list(set(sugar_matches)),
        "gmo": list(set(gmo_matches)),
        "safe_ingredients": list(set(safe_matches)),
        "all_detected": all_detected
    }
    
    print(f"DEBUG: Ingredient matching results:")
    for category, ingredients in result.items():
        if ingredients:
            print(f"  {category}: {ingredients}")
    
    return result

def rate_ingredients(matches, text_quality):
    """Rating system following exact hierarchy rules"""
    
    print(f"DEBUG: Rating ingredients with text quality: {text_quality}")
    
    # If text quality is very poor, suggest trying again
    if text_quality == "very_poor":
        return "↪️ TRY AGAIN"
    
    # Define high risk ingredients (ranks 1-10 from hierarchy document)
    high_risk_trans_fats = [
        "partially hydrogenated oil",
        "partially hydrogenated soybean oil", 
        "partially hydrogenated cottonseed oil",
        "partially hydrogenated palm oil",
        "partially hydrogenated canola oil",
        "vegetable shortening",
        "shortening",
        "hydrogenated oil",
        "interesterified fats",
        "high-stability oil"
    ]
    
    high_risk_excitotoxins = [
        "monosodium glutamate", "msg",
        "aspartame",
        "hydrolyzed vegetable protein", "hvp",
        "disodium inosinate",
        "disodium guanylate", 
        "yeast extract",
        "autolyzed yeast",
        "calcium caseinate",
        "sodium caseinate",
        "torula yeast"
    ]
    
    # RULE 1: Check HIGH RISK Trans Fats - ANY ONE = immediate danger
    for ingredient in matches["trans_fat"]:
        if any(high_risk.lower() in ingredient.lower() for high_risk in high_risk_trans_fats):
            print(f"🚨 HIGH RISK Trans Fat found: {ingredient}")
            return "🚨 Oh NOOOO! Danger!"
    
    # RULE 2: Check HIGH RISK Excitotoxins - ANY ONE = immediate danger  
    for ingredient in matches["excitotoxins"]:
        if any(high_risk.lower() in ingredient.lower() for high_risk in high_risk_excitotoxins):
            print(f"🚨 HIGH RISK Excitotoxin found: {ingredient}")
            return "🚨 Oh NOOOO! Danger!"
    
    # RULE 3: Count ALL other problematic ingredients
    total_problematic_count = 0
    
    # Count moderate trans fats
    moderate_trans_fats = [
        "hydrogenated fat", "margarine", "vegetable oil", "frying oil",
        "modified fat", "synthetic fat", "lard substitute", 
        "monoglycerides", "diglycerides"
    ]
    
    for ingredient in matches["trans_fat"]:
        if any(moderate.lower() in ingredient.lower() for moderate in moderate_trans_fats):
            total_problematic_count += 1
    
    # Count moderate excitotoxins
    moderate_excitotoxins = [
        "natural flavors", "natural flavoring", "spices", "seasonings",
        "soy sauce", "enzyme modified cheese", "whey protein isolate", 
        "whey protein hydrolysate", "bouillon", "broth", "stock"
    ]
    
    for ingredient in matches["excitotoxins"]:
        if any(moderate.lower() in ingredient.lower() for moderate in moderate_excitotoxins):
            total_problematic_count += 1
    
    # Count ALL corn and sugar ingredients
    total_problematic_count += len(matches["corn"]) + len(matches["sugar"])
    
    print(f"⚖️ Total problematic ingredients: {total_problematic_count}")
    
    # Apply hierarchy rules
    if total_problematic_count >= 3:
        return "🚨 Oh NOOOO! Danger!"
    elif total_problematic_count >= 1:
        return "⚠️ Proceed carefully"
    
    # If some ingredients detected but no problematic ones
    if len(matches["all_detected"]) > 0:
        return "✅ Yay! Safe!"
    
    # If poor text quality and no ingredients detected
    if text_quality == "poor":
        return "↪️ TRY AGAIN"
    
    return "✅ Yay! Safe!"

def scan_image_for_ingredients(image_path):
    """Main scanning function with comprehensive error handling"""
    try:
        print(f"DEBUG: Starting scan for {image_path}")
        print(f"DEBUG: File exists: {os.path.exists(image_path)}")
        
        # Check if tesseract is available
        try:
            test_img = Image.new('RGB', (100, 30), color='white')
            pytesseract.image_to_string(test_img, config='--psm 6')
            print("DEBUG: Tesseract is working")
        except Exception as e:
            print(f"DEBUG: Tesseract error: {e}")
            return {
                "rating": "↪️ TRY AGAIN",
                "matched_ingredients": {
                    "trans_fat": [], "excitotoxins": [], "corn": [], 
                    "sugar": [], "gmo": [], "safe_ingredients": [], "all_detected": []
                },
                "confidence": "very_low",
                "text_quality": "very_poor", 
                "extracted_text_length": 0,
                "gmo_alert": None,
                "error": "OCR system not available"
            }
        
        # Extract text
        text = extract_text_from_image(image_path)
        print(f"DEBUG: Extracted text length: {len(text)}")
        if text:
            print(f"DEBUG: Text preview: {text[:200]}...")
        else:
            print("DEBUG: No text extracted!")
        
        # Assess text quality
        text_quality = assess_text_quality(text)
        print(f"DEBUG: Text quality: {text_quality}")
        
        # Match ingredients
        matches = match_ingredients(text)
        
        # Rate ingredients
        rating = rate_ingredients(matches, text_quality)
        print(f"DEBUG: Final rating: {rating}")
        
        # Determine confidence
        if text_quality == "very_poor":
            confidence = "very_low"
        elif text_quality == "poor":
            confidence = "low"  
        elif len(text) > 30 and len(matches["all_detected"]) > 0:
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
            "extracted_text": text[:300] + "..." if len(text) > 300 else text,
            "gmo_alert": gmo_alert
        }
        
        print(f"\n{'='*60}")
        print(f"SCAN RESULT: {rating}")
        print(f"Confidence: {confidence}, Text quality: {text_quality}")
        print(f"Text length: {len(text)} characters")
        print(f"\nDetected ingredients by category:")
        for category, ingredients in matches.items():
            if ingredients:
                print(f"  - {category}: {ingredients}")
        if gmo_alert:
            print(f"\n{gmo_alert} - Contains GMO ingredients")
        print(f"{'='*60}\n")
        
        return result
        
    except Exception as e:
        print(f"❌ Error in scan_image_for_ingredients: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            "rating": "↪️ TRY AGAIN",
            "matched_ingredients": {
                "trans_fat": [], "excitotoxins": [], "corn": [], 
                "sugar": [], "gmo": [], "safe_ingredients": [], "all_detected": []
            },
            "confidence": "very_low",
            "text_quality": "very_poor",
            "extracted_text_length": 0,
            "gmo_alert": None,
            "error": str(e)
        }
