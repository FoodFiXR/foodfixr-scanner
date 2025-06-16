import pytesseract
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import re
import os
from scanner_config import *
import cv2
import numpy as np

def enhance_image_for_ocr(image):
    """Enhanced image preprocessing specifically for ingredient lists on mobile photos"""
    try:
        # Convert PIL to OpenCV format
        if hasattr(image, 'mode'):
            image_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        else:
            image_cv = image
        
        # Convert to grayscale
        gray = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)
        
        # Multiple enhancement stages
        
        # 1. Resize if too small (critical for mobile photos)
        height, width = gray.shape
        if width < 1000:
            scale_factor = 1000 / width
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            gray = cv2.resize(gray, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
            print(f"DEBUG: Resized image from {width}x{height} to {new_width}x{new_height}")
        
        # 2. Noise reduction
        gray = cv2.medianBlur(gray, 3)
        
        # 3. Contrast enhancement
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        gray = clahe.apply(gray)
        
        # 4. Adaptive thresholding (better for varying lighting)
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                     cv2.THRESH_BINARY, 11, 2)
        
        # 5. Morphological operations to clean up text
        kernel = np.ones((1,1), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        
        # Convert back to PIL
        enhanced_image = Image.fromarray(binary)
        return enhanced_image
        
    except Exception as e:
        print(f"DEBUG: Image enhancement failed: {e}, using original")
        return image

def extract_text_from_image(image_path):
    """Enhanced text extraction with better preprocessing and multiple OCR attempts"""
    try:
        print(f"DEBUG: Starting text extraction from {image_path}")
        
        # Load and preprocess image
        image = Image.open(image_path)
        print(f"DEBUG: Original image size: {image.size}, mode: {image.mode}")
        
        # Try multiple preprocessing approaches
        extracted_texts = []
        
        # Method 1: Enhanced preprocessing
        try:
            enhanced_img = enhance_image_for_ocr(image)
            
            # Multiple OCR configurations with enhanced image
            configs = [
                '--oem 3 --psm 6',   # Uniform block of text
                '--oem 3 --psm 4',   # Single column
                '--oem 3 --psm 3',   # Fully automatic
                '--oem 3 --psm 8',   # Single word
                '--oem 3 --psm 7',   # Single text line
                '--oem 3 --psm 11',  # Sparse text
                '--oem 3 --psm 12',  # Sparse text with OSD
            ]
            
            for config in configs:
                try:
                    text = pytesseract.image_to_string(enhanced_img, config=config)
                    if text.strip() and len(text.strip()) > 3:
                        extracted_texts.append(text.strip())
                        print(f"DEBUG: Config {config} extracted {len(text)} chars")
                except Exception as e:
                    print(f"DEBUG: Config {config} failed: {e}")
                    continue
        except Exception as e:
            print(f"DEBUG: Enhanced preprocessing failed: {e}")
        
        # Method 2: Simple grayscale + contrast
        try:
            simple_img = image.convert('L')
            enhancer = ImageEnhance.Contrast(simple_img)
            simple_img = enhancer.enhance(2.0)
            
            text = pytesseract.image_to_string(simple_img, config='--oem 3 --psm 6')
            if text.strip() and len(text.strip()) > 3:
                extracted_texts.append(text.strip())
                print(f"DEBUG: Simple method extracted {len(text)} chars")
        except Exception as e:
            print(f"DEBUG: Simple method failed: {e}")
        
        # Method 3: Original image with different configs
        try:
            for config in ['--oem 3 --psm 6', '--oem 3 --psm 3']:
                text = pytesseract.image_to_string(image, config=config)
                if text.strip() and len(text.strip()) > 3:
                    extracted_texts.append(text.strip())
                    print(f"DEBUG: Original image config {config} extracted {len(text)} chars")
        except Exception as e:
            print(f"DEBUG: Original image OCR failed: {e}")
        
        # Combine all extracted texts
        if extracted_texts:
            # Take the longest text as it's likely the most complete
            combined_text = max(extracted_texts, key=len)
            
            # Also combine unique words from all extractions
            all_words = set()
            for text in extracted_texts:
                words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
                all_words.update(words)
            
            # Add unique words to the main text
            main_words = set(re.findall(r'\b[a-zA-Z]{2,}\b', combined_text.lower()))
            missing_words = all_words - main_words
            if missing_words:
                combined_text += " " + " ".join(missing_words)
            
            print(f"DEBUG: FINAL TEXT LENGTH: {len(combined_text)} characters")
            print(f"DEBUG: FINAL TEXT PREVIEW: {combined_text[:200]}...")
            return combined_text
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
    
    # Fix common OCR errors specific to ingredient labels
    ocr_fixes = {
        # Common character misreads
        '0': 'o', '1': 'l', '5': 's', '8': 'b', '6': 'g',
        'rn': 'm', 'vv': 'w', 'ii': 'll', 'cl': 'd',
        
        # Common ingredient OCR errors
        'corn5yrup': 'corn syrup',
        'cornsynup': 'corn syrup',
        'com syrup': 'corn syrup',
        'hfc5': 'hfcs',
        'm5g': 'msg',
        'ms9': 'msg',
        'aspertame': 'aspartame',
        'hydrogenatedoil': 'hydrogenated oil',
        'naturalflavors': 'natural flavors',
        'modifiedstarch': 'modified starch',
        'highfructose': 'high fructose',
        'partiallyhydrogenated': 'partially hydrogenated',
        'monosodiumglutamate': 'monosodium glutamate',
        'yeastextract': 'yeast extract',
        'soylecithin': 'soy lecithin',
        'canolaoil': 'canola oil',
        'cottonseedoil': 'cottonseed oil',
        'dextrose': 'dextrose',
        'maltodextrin': 'maltodextrin',
    }
    
    # Apply OCR fixes
    for wrong, correct in ocr_fixes.items():
        text = text.replace(wrong, correct)
    
    # Apply config-based fixes if available
    if 'common_ocr_errors' in globals():
        for wrong, correct in common_ocr_errors.items():
            text = text.replace(wrong, correct)
    
    return text

def fuzzy_match_ingredient(text, ingredient_list):
    """Improved ingredient matching with more lenient matching"""
    matches = []
    normalized_text = normalize_text(text)
    
    print(f"DEBUG: Searching in text: {normalized_text[:100]}...")
    
    for ingredient in ingredient_list:
        normalized_ingredient = normalize_text(ingredient)
        
        # Skip very short ingredients that could cause false positives
        if len(normalized_ingredient) < 3:
            continue
        
        # Create variations to check
        variations = [normalized_ingredient]
        
        # Handle slash variations
        if '/' in ingredient:
            parts = ingredient.split('/')
            variations.extend([normalize_text(part.strip()) for part in parts])
        
        # Handle parenthetical variations
        if '(' in ingredient:
            base = ingredient.split('(')[0].strip()
            variations.append(normalize_text(base))
        
        # Handle hyphenated variations
        if '-' in normalized_ingredient:
            no_hyphen = normalized_ingredient.replace('-', ' ')
            variations.append(no_hyphen)
            variations.append(normalized_ingredient.replace('-', ''))
        
        # Check all variations
        for variant in variations:
            variant = variant.strip()
            if not variant or len(variant) < 3:
                continue
                
            # Exact word boundary match
            pattern = r'\b' + re.escape(variant) + r'\b'
            if re.search(pattern, normalized_text):
                matches.append(ingredient)
                print(f"DEBUG: Found exact match: '{variant}' -> '{ingredient}'")
                break
            
            # Partial match for compound ingredients (more lenient)
            variant_words = variant.split()
            if len(variant_words) > 1:
                # Check if all words are present within reasonable distance
                word_positions = []
                for word in variant_words:
                    word_pattern = r'\b' + re.escape(word) + r'\b'
                    match = re.search(word_pattern, normalized_text)
                    if match:
                        word_positions.append(match.start())
                    else:
                        break
                
                # If all words found and within reasonable distance
                if len(word_positions) == len(variant_words):
                    if len(word_positions) == 1 or (max(word_positions) - min(word_positions) < 100):
                        matches.append(ingredient)
                        print(f"DEBUG: Found compound match: '{variant}' -> '{ingredient}'")
                        break
            
            # Fuzzy match for very important ingredients (allow small errors)
            if ingredient.lower() in ['msg', 'aspartame', 'corn syrup', 'high fructose corn syrup']:
                # More lenient matching for critical ingredients
                if variant in normalized_text or any(word in normalized_text for word in variant.split() if len(word) > 3):
                    matches.append(ingredient)
                    print(f"DEBUG: Found fuzzy match: '{variant}' -> '{ingredient}'")
                    break
    
    return list(set(matches))  # Remove duplicates

def assess_text_quality(text):
    """More lenient text quality assessment"""
    if not text or len(text.strip()) < 2:
        return "very_poor"
    
    # Count words (sequences of letters)
    words = re.findall(r'\b[a-zA-Z]{2,}\b', text)
    
    if len(words) < 1:
        return "very_poor"
    elif len(words) < 3 or len(text) < 10:
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
    
    # RULE 1: Check HIGH RISK Trans Fats (ranks 1-10) - ANY ONE = immediate danger
    for ingredient in matches["trans_fat"]:
        if any(high_risk.lower() in ingredient.lower() for high_risk in high_risk_trans_fats):
            print(f"🚨 HIGH RISK Trans Fat found: {ingredient}")
            return "🚨 Oh NOOOO! Danger!"
    
    # RULE 2: Check HIGH RISK Excitotoxins (ranks 1-10) - ANY ONE = immediate danger  
    for ingredient in matches["excitotoxins"]:
        if any(high_risk.lower() in ingredient.lower() for high_risk in high_risk_excitotoxins):
            print(f"🚨 HIGH RISK Excitotoxin found: {ingredient}")
            return "🚨 Oh NOOOO! Danger!"
    
    # RULE 3: Count ALL other problematic ingredients
    total_problematic_count = 0
    problematic_ingredients = []
    
    # Count moderate trans fats (not caught above)
    moderate_trans_fats = [
        "hydrogenated fat", "margarine", "vegetable oil", "frying oil",
        "modified fat", "synthetic fat", "lard substitute", 
        "monoglycerides", "diglycerides"
    ]
    
    for ingredient in matches["trans_fat"]:
        if any(moderate.lower() in ingredient.lower() for moderate in moderate_trans_fats):
            total_problematic_count += 1
            problematic_ingredients.append(f"Trans Fat (moderate): {ingredient}")
    
    # Count moderate excitotoxins (not caught above)
    moderate_excitotoxins = [
        "natural flavors", "natural flavoring", "spices", "seasonings",
        "soy sauce", "enzyme modified cheese", "whey protein isolate", 
        "whey protein hydrolysate", "bouillon", "broth", "stock"
    ]
    
    for ingredient in matches["excitotoxins"]:
        if any(moderate.lower() in ingredient.lower() for moderate in moderate_excitotoxins):
            total_problematic_count += 1
            problematic_ingredients.append(f"Excitotoxin (moderate): {ingredient}")
    
    # Count ALL corn ingredients
    if matches["corn"]:
        total_problematic_count += len(matches["corn"])
        for ingredient in matches["corn"]:
            problematic_ingredients.append(f"Corn: {ingredient}")
    
    # Count ALL sugar ingredients  
    if matches["sugar"]:
        total_problematic_count += len(matches["sugar"])
        for ingredient in matches["sugar"]:
            problematic_ingredients.append(f"Sugar: {ingredient}")
    
    print(f"⚖️ Total problematic ingredients: {total_problematic_count}")
    if problematic_ingredients:
        print("Problematic ingredients found:")
        for ing in problematic_ingredients:
            print(f"  - {ing}")
    
    # Apply the hierarchy rule: 1-2 = Proceed Carefully, 3+ = Danger
    if total_problematic_count >= 3:
        return "🚨 Oh NOOOO! Danger!"
    elif total_problematic_count >= 1:
        return "⚠️ Proceed carefully"
    
    # If some ingredients detected but no problematic ones
    if len(matches["all_detected"]) > 0:
        return "✅ Yay! Safe!"
    
    # If poor text quality and no ingredients detected, suggest trying again
    if text_quality == "poor":
        return "↪️ TRY AGAIN"
    
    # Default safe
    return "✅ Yay! Safe!"

def scan_image_for_ingredients(image_path):
    """Main scanning function with comprehensive error handling and debug output"""
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
        elif len(text) > 50 and len(matches["all_detected"]) > 0:
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
