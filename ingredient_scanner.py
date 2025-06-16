import pytesseract
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import re
import os
from scanner_config import *
import requests
import time

# Add this function to your ingredient_scanner.py
# Replace the existing preprocess_image_advanced function

def preprocess_image_advanced(image):
    """Advanced image preprocessing specifically for challenging images like curved cans"""
    try:
        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        processed_images = []
        
        # Method 1: Original grayscale approach
        gray = image.convert('L')
        width, height = gray.size
        if width < 1200:  # Increase minimum size
            scale_factor = 1200 / width
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            gray = gray.resize((new_width, new_height), Image.Resampling.LANCZOS)
            print(f"DEBUG: Resized image from {width}x{height} to {new_width}x{new_height}")
        
        # Standard processing
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(3.0)
        enhancer = ImageEnhance.Sharpness(enhanced)
        enhanced = enhancer.enhance(2.0)
        processed_images.append(("standard_enhanced", enhanced))
        
        # Method 2: Invert colors (for white text on dark background)
        inverted = ImageOps.invert(gray)
        enhancer = ImageEnhance.Contrast(inverted)
        inverted_enhanced = enhancer.enhance(3.5)
        processed_images.append(("inverted_enhanced", inverted_enhanced))
        
        # Method 3: Extreme contrast for curved surfaces
        extreme = ImageOps.autocontrast(gray, cutoff=20)
        enhancer = ImageEnhance.Contrast(extreme)
        extreme_contrast = enhancer.enhance(5.0)
        processed_images.append(("extreme_contrast", extreme_contrast))
        
        # Method 4: Color channel separation (sometimes better for colored backgrounds)
        try:
            rgb_img = image if image.mode == 'RGB' else image.convert('RGB')
            r, g, b = rgb_img.split()
            
            # Try each color channel
            for channel_name, channel in [("red", r), ("green", g), ("blue", b)]:
                # Resize channel if needed
                if channel.size[0] < 1200:
                    scale_factor = 1200 / channel.size[0]
                    new_size = (int(channel.size[0] * scale_factor), int(channel.size[1] * scale_factor))
                    channel = channel.resize(new_size, Image.Resampling.LANCZOS)
                
                enhancer = ImageEnhance.Contrast(channel)
                channel_enhanced = enhancer.enhance(4.0)
                processed_images.append((f"{channel_name}_channel", channel_enhanced))
        except Exception as e:
            print(f"DEBUG: Color channel processing failed: {e}")
        
        # Method 5: High-pass filter effect (edge enhancement)
        try:
            from PIL import ImageFilter
            edges = gray.filter(ImageFilter.EDGE_ENHANCE_MORE)
            enhancer = ImageEnhance.Contrast(edges)
            edge_enhanced = enhancer.enhance(3.0)
            processed_images.append(("edge_enhanced", edge_enhanced))
        except Exception as e:
            print(f"DEBUG: Edge enhancement failed: {e}")
        
        # Method 6: Threshold-based binary conversion
        try:
            # Try multiple threshold values
            for threshold in [100, 128, 150, 180]:
                binary = gray.point(lambda x: 0 if x < threshold else 255, '1')
                binary_rgb = binary.convert('L')
                processed_images.append((f"binary_{threshold}", binary_rgb))
        except Exception as e:
            print(f"DEBUG: Binary conversion failed: {e}")
        
        print(f"DEBUG: Created {len(processed_images)} processed versions")
        return processed_images
        
    except Exception as e:
        print(f"DEBUG: Advanced preprocessing failed: {e}, using original")
        return [("original", image)]

def extract_text_with_multiple_methods(image_path):
    """Extract text using OCR.space API with fallback options"""
    try:
        print(f"DEBUG: Starting OCR.space API text extraction from {image_path}")
        
        # Try OCR.space API first
        text = extract_text_ocr_space(image_path)
        
        if text and len(text.strip()) > 5:
            print(f"DEBUG: OCR.space successful - extracted {len(text)} characters")
            return text
        
        # If OCR.space fails, try with different settings
        print("DEBUG: First attempt failed, trying with enhanced settings...")
        text = extract_text_ocr_space_enhanced(image_path)
        
        if text and len(text.strip()) > 5:
            print(f"DEBUG: OCR.space enhanced successful - extracted {len(text)} characters")
            return text
        
        print("DEBUG: OCR.space failed, trying basic pytesseract fallback...")
        return extract_text_pytesseract_fallback(image_path)
        
    except Exception as e:
        print(f"DEBUG: All OCR methods failed: {e}")
        return ""

def extract_text_ocr_space(image_path):
    """Extract text using OCR.space API - standard settings"""
    try:
        api_url = 'https://api.ocr.space/parse/image'
        
        # Use free API key (or set OCR_SPACE_API_KEY environment variable for your own)
        api_key = os.getenv('OCR_SPACE_API_KEY', 'helloworld')
        
        with open(image_path, 'rb') as f:
            files = {'file': f}
            
            data = {
                'apikey': api_key,
                'language': 'eng',
                'isOverlayRequired': False,
                'detectOrientation': True,
                'scale': True,
                'OCREngine': 2,  # Engine 2 is more accurate
                'isTable': False
            }
            
            print("DEBUG: Sending request to OCR.space API (standard)...")
            response = requests.post(api_url, files=files, data=data, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                return parse_ocr_space_response(result)
            else:
                print(f"DEBUG: OCR.space API returned status {response.status_code}")
                return ""
                
    except Exception as e:
        print(f"DEBUG: OCR.space standard method failed: {e}")
        return ""

def extract_text_ocr_space_enhanced(image_path):
    """Extract text using OCR.space API - enhanced settings for difficult images"""
    try:
        api_url = 'https://api.ocr.space/parse/image'
        api_key = os.getenv('OCR_SPACE_API_KEY', 'helloworld')
        
        with open(image_path, 'rb') as f:
            files = {'file': f}
            
            # Enhanced settings for challenging images
            data = {
                'apikey': api_key,
                'language': 'eng',
                'isOverlayRequired': False,
                'detectOrientation': True,
                'scale': True,
                'OCREngine': 1,  # Try engine 1 for difficult images
                'isTable': True,  # Sometimes helps with structured text
                'isSearchablePdfHideTextLayer': False
            }
            
            print("DEBUG: Sending request to OCR.space API (enhanced)...")
            response = requests.post(api_url, files=files, data=data, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                return parse_ocr_space_response(result)
            else:
                print(f"DEBUG: OCR.space enhanced API returned status {response.status_code}")
                return ""
                
    except Exception as e:
        print(f"DEBUG: OCR.space enhanced method failed: {e}")
        return ""

def parse_ocr_space_response(result):
    """Parse OCR.space API response"""
    try:
        if result.get('IsErroredOnProcessing', True):
            error_msg = result.get('ErrorMessage', 'Unknown error')
            print(f"DEBUG: OCR.space processing error: {error_msg}")
            return ""
        
        parsed_results = result.get('ParsedResults', [])
        if not parsed_results:
            print("DEBUG: OCR.space returned no parsed results")
            return ""
        
        # Get text from first result
        extracted_text = parsed_results[0].get('ParsedText', '')
        
        if extracted_text and len(extracted_text.strip()) > 0:
            # Clean up the text
            cleaned_text = extracted_text.replace('\r', ' ').replace('\n', ' ')
            cleaned_text = ' '.join(cleaned_text.split())  # Remove extra whitespace
            
            print(f"DEBUG: OCR.space extracted {len(cleaned_text)} characters")
            print(f"DEBUG: Raw text preview: {cleaned_text[:300]}...")
            return cleaned_text
        else:
            print("DEBUG: OCR.space returned empty text")
            return ""
            
    except Exception as e:
        print(f"DEBUG: Error parsing OCR.space response: {e}")
        return ""

def extract_text_pytesseract_fallback(image_path):
    """Fallback to pytesseract if available"""
    try:
        print("DEBUG: Attempting pytesseract fallback...")
        import pytesseract
        from PIL import Image
        
        image = Image.open(image_path)
        
        # Simple preprocessing
        if image.mode != 'L':
            image = image.convert('L')
            
        # Try basic OCR
        text = pytesseract.image_to_string(image, config='--psm 6')
        
        if text and len(text.strip()) > 0:
            print(f"DEBUG: Pytesseract fallback worked: {len(text)} chars")
            return text.strip()
        else:
            print("DEBUG: Pytesseract fallback returned empty")
            return ""
            
    except ImportError:
        print("DEBUG: Pytesseract not available")
        return ""
    except Exception as e:
        print(f"DEBUG: Pytesseract fallback failed: {e}")
        return ""
def normalize_ingredient_text(text):
    """Enhanced text normalization with comprehensive OCR error correction"""
    if not text:
        return ""
    
    # Convert to lowercase and basic cleanup
    text = text.lower().strip()
    
    # Remove excessive whitespace and newlines
    text = re.sub(r'\s+', ' ', text)
    
    # Remove common OCR artifacts
    text = re.sub(r'[^\w\s\-\(\),.]', ' ', text)
    
    # Comprehensive OCR error corrections
    corrections = {
        # Numbers to letters
        '0': 'o', '1': 'l', '5': 's', '8': 'b', '6': 'g', '3': 'e',
        
        # Common character combinations
        'rn': 'm', 'vv': 'w', 'ii': 'll', 'cl': 'd', 'ri': 'n',
        
        # Specific ingredient corrections
        'corn5yrup': 'corn syrup',
        'cornsynup': 'corn syrup',
        'com syrup': 'corn syrup',
        'hfc5': 'hfcs',
        'hfc3': 'hfcs',
        'm5g': 'msg',
        'ms9': 'msg',
        'rns9': 'msg',
        'aspartame': 'aspartame',
        'aspertame': 'aspartame',
        'aspartarne': 'aspartame',
        'naturalflavors': 'natural flavors',
        'naturalflavor': 'natural flavor',
        'naturalflavoring': 'natural flavoring',
        'partiallyhydrogenated': 'partially hydrogenated',
        'hydrogenatedoil': 'hydrogenated oil',
        'modifiedstarch': 'modified starch',
        'modifiedcornstarch': 'modified corn starch',
        'soylecithin': 'soy lecithin',
        'canolaoil': 'canola oil',
        'cottonseedoil': 'cottonseed oil',
        'maltodextrin': 'maltodextrin',
        'maltodextnn': 'maltodextrin',
        'yeastextract': 'yeast extract',
        'monosodiumglutamate': 'monosodium glutamate',
        'highfructose': 'high fructose',
        'highfructosecornsyrup': 'high fructose corn syrup',
        'vegetableoil': 'vegetable oil',
        'vegetableprotein': 'vegetable protein',
        'texturedvegetableprotein': 'textured vegetable protein',
        'hydrolyzedprotein': 'hydrolyzed protein',
        'hydrolyzedvegetableprotein': 'hydrolyzed vegetable protein',
        'disodiuminosinate': 'disodium inosinate',
        'disodiumguanylate': 'disodium guanylate',
        'calciumcaseinate': 'calcium caseinate',
        'sodiumcaseinate': 'sodium caseinate',
    }
    
    # Apply corrections
    for wrong, correct in corrections.items():
        text = text.replace(wrong, correct)
    
    return text

def advanced_ingredient_matching(text, ingredient_list, category_name=""):
    """Advanced fuzzy matching with multiple strategies"""
    matches = []
    normalized_text = normalize_ingredient_text(text)
    
    print(f"DEBUG: Searching for {category_name} ingredients in normalized text: {normalized_text[:200]}...")
    
    for ingredient in ingredient_list:
        normalized_ingredient = normalize_ingredient_text(ingredient)
        
        if len(normalized_ingredient) < 2:
            continue
        
        # Strategy 1: Exact match
        if normalized_ingredient in normalized_text:
            matches.append(ingredient)
            print(f"DEBUG: ✅ EXACT MATCH: '{normalized_ingredient}' -> '{ingredient}'")
            continue
        
        # Strategy 2: Word boundary match
        pattern = r'\b' + re.escape(normalized_ingredient) + r'\b'
        if re.search(pattern, normalized_text):
            matches.append(ingredient)
            print(f"DEBUG: ✅ WORD BOUNDARY MATCH: '{normalized_ingredient}' -> '{ingredient}'")
            continue
        
        # Strategy 3: Partial match for compound ingredients
        if ' ' in normalized_ingredient:
            words = normalized_ingredient.split()
            if len(words) >= 2:
                # Check if all significant words are present
                significant_words = [w for w in words if len(w) > 2]
                found_words = 0
                word_positions = []
                
                for word in significant_words:
                    word_pattern = r'\b' + re.escape(word) + r'\b'
                    match = re.search(word_pattern, normalized_text)
                    if match:
                        found_words += 1
                        word_positions.append(match.start())
                
                # If all significant words found within reasonable distance
                if found_words == len(significant_words):
                    if len(word_positions) == 1 or (max(word_positions) - min(word_positions) < 100):
                        matches.append(ingredient)
                        print(f"DEBUG: ✅ COMPOUND MATCH: '{normalized_ingredient}' -> '{ingredient}'")
                        continue
        
        # Strategy 4: Fuzzy matching for critical ingredients
        critical_keywords = ['msg', 'aspartame', 'corn syrup', 'hfcs', 'partially hydrogenated', 
                           'trans fat', 'natural flavor', 'maltodextrin', 'yeast extract']
        
        if any(keyword in normalized_ingredient for keyword in critical_keywords):
            # More lenient matching for critical ingredients
            main_words = [w for w in normalized_ingredient.split() if len(w) > 3]
            if main_words:
                main_word = max(main_words, key=len)
                if main_word in normalized_text:
                    matches.append(ingredient)
                    print(f"DEBUG: ✅ CRITICAL FUZZY MATCH: '{main_word}' in '{normalized_ingredient}' -> '{ingredient}'")
                    continue
        
        # Strategy 5: Substring match for single important words
        if ' ' not in normalized_ingredient and len(normalized_ingredient) > 4:
            if normalized_ingredient in normalized_text:
                matches.append(ingredient)
                print(f"DEBUG: ✅ SUBSTRING MATCH: '{normalized_ingredient}' -> '{ingredient}'")
    
    unique_matches = list(set(matches))
    print(f"DEBUG: {category_name} category found {len(unique_matches)} matches: {unique_matches}")
    return unique_matches

def assess_text_quality_enhanced(text):
    """Enhanced text quality assessment"""
    if not text or len(text.strip()) < 1:
        return "very_poor"
    
    # Count meaningful words (2+ chars, mostly letters)
    words = re.findall(r'\b[a-zA-Z]{2,}\b', text)
    
    # Count ingredient-like words
    ingredient_words = []
    common_food_words = ['oil', 'sugar', 'salt', 'water', 'acid', 'flavor', 'protein', 
                        'extract', 'syrup', 'starch', 'lecithin', 'natural', 'modified']
    
    for word in words:
        if any(food_word in word.lower() for food_word in common_food_words):
            ingredient_words.append(word)
    
    print(f"DEBUG: Text quality assessment - Total words: {len(words)}, Ingredient words: {len(ingredient_words)}")
    
    if len(words) < 2:
        return "very_poor"
    elif len(words) < 5 and len(ingredient_words) < 1:
        return "poor"
    elif len(ingredient_words) >= 1 or len(words) >= 10:
        return "good"
    else:
        return "fair"

def match_all_ingredients(text):
    """Enhanced ingredient matching with comprehensive categories"""
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
    
    # Match each category using advanced matching
    trans_fat_matches = advanced_ingredient_matching(text, trans_fat_high_risk + trans_fat_moderate_risk, "Trans Fat")
    excitotoxin_matches = advanced_ingredient_matching(text, excitotoxin_high_risk + excitotoxin_moderate_risk, "Excitotoxin")
    corn_matches = advanced_ingredient_matching(text, corn_high_risk + corn_moderate_risk, "Corn")
    sugar_matches = advanced_ingredient_matching(text, sugar_keywords, "Sugar")
    gmo_matches = advanced_ingredient_matching(text, gmo_keywords, "GMO")
    safe_matches = advanced_ingredient_matching(text, safe_ingredients, "Safe")
    
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
    
    print(f"DEBUG: INGREDIENT MATCHING RESULTS:")
    for category, ingredients in result.items():
        if ingredients:
            print(f"  ✅ {category}: {ingredients}")
        else:
            print(f"  ❌ {category}: No matches")
    
    return result

def rate_ingredients_according_to_hierarchy(matches, text_quality):
    """Rating system following exact hierarchy rules from document"""
    
    print(f"DEBUG: Rating ingredients with text quality: {text_quality}")
    
    # If text quality is very poor, suggest trying again
    if text_quality == "very_poor":
        return "↪️ TRY AGAIN"
    
    # HIGH RISK TRANS FATS - ANY ONE = immediate danger (ranks 1-10)
    high_risk_trans_fat_keywords = [
        "partially hydrogenated", "vegetable shortening", "shortening", 
        "interesterified", "high-stability"
    ]
    
    for ingredient in matches["trans_fat"]:
        if any(keyword in ingredient.lower() for keyword in high_risk_trans_fat_keywords):
            print(f"🚨 HIGH RISK Trans Fat detected: {ingredient}")
            return "🚨 Oh NOOOO! Danger!"
    
    # HIGH RISK EXCITOTOXINS - ANY ONE = immediate danger (ranks 1-10)
    high_risk_excitotoxin_keywords = [
        "monosodium glutamate", "msg", "aspartame", "hydrolyzed", 
        "disodium inosinate", "disodium guanylate", "yeast extract", 
        "autolyzed", "caseinate", "torula"
    ]
    
    for ingredient in matches["excitotoxins"]:
        if any(keyword in ingredient.lower() for keyword in high_risk_excitotoxin_keywords):
            print(f"🚨 HIGH RISK Excitotoxin detected: {ingredient}")
            return "🚨 Oh NOOOO! Danger!"
    
    # COUNT ALL OTHER PROBLEMATIC INGREDIENTS
    total_problematic_count = 0
    
    # Count moderate trans fats
    moderate_trans_fat_keywords = [
        "hydrogenated fat", "margarine", "vegetable oil", "frying oil",
        "modified fat", "synthetic fat", "monoglycerides", "diglycerides"
    ]
    
    for ingredient in matches["trans_fat"]:
        if any(keyword in ingredient.lower() for keyword in moderate_trans_fat_keywords):
            total_problematic_count += 1
            print(f"⚠️ Moderate trans fat counted: {ingredient}")
    
    # Count moderate excitotoxins
    moderate_excitotoxin_keywords = [
        "natural flavor", "spices", "seasoning", "soy sauce", 
        "enzyme modified", "whey protein", "bouillon", "broth", "stock"
    ]
    
    for ingredient in matches["excitotoxins"]:
        if any(keyword in ingredient.lower() for keyword in moderate_excitotoxin_keywords):
            total_problematic_count += 1
            print(f"⚠️ Moderate excitotoxin counted: {ingredient}")
    
    # Count ALL corn and sugar ingredients
    corn_count = len(matches["corn"])
    sugar_count = len(matches["sugar"])
    total_problematic_count += corn_count + sugar_count
    
    print(f"⚖️ TOTAL PROBLEMATIC COUNT: {total_problematic_count}")
    print(f"   - Corn ingredients: {corn_count}")
    print(f"   - Sugar ingredients: {sugar_count}")
    
    # Apply hierarchy rules
    if total_problematic_count >= 3:
        return "🚨 Oh NOOOO! Danger!"
    elif total_problematic_count >= 1:
        return "⚠️ Proceed carefully"
    
    # If some ingredients detected but no problematic ones
    if len(matches["all_detected"]) > 0:
        return "✅ Yay! Safe!"
    
    # If poor text quality and no ingredients detected
    if text_quality in ["poor", "fair"]:
        return "↪️ TRY AGAIN"
    
    return "✅ Yay! Safe!"

def scan_image_for_ingredients(image_path):
    """Main scanning function with OCR.space integration"""
    try:
        print(f"\n{'='*80}")
        print(f"🔬 STARTING OCR.SPACE INGREDIENT SCAN: {image_path}")
        print(f"{'='*80}")
        print(f"DEBUG: File exists: {os.path.exists(image_path)}")
        
        # Extract text using OCR.space
        print("🔍 Starting OCR.space text extraction...")
        text = extract_text_with_multiple_methods(image_path)
        print(f"📝 Extracted text length: {len(text)} characters")
        
        if text:
            print(f"📋 Text preview (first 500 chars):\n{text[:500]}...")
        else:
            print("❌ No text extracted!")
        
        # Assess text quality
        text_quality = assess_text_quality_enhanced(text)
        print(f"📊 Text quality assessment: {text_quality}")
        
        # Match ingredients using enhanced system
        print("🧬 Starting ingredient matching...")
        matches = match_all_ingredients(text)
        
        # Rate ingredients according to hierarchy
        print("⚖️ Applying hierarchy-based rating...")
        rating = rate_ingredients_according_to_hierarchy(matches, text_quality)
        print(f"🏆 Final rating: {rating}")
        
        # Determine confidence
        confidence = determine_confidence(text_quality, text, matches)
        
        # Check for GMO Alert
        gmo_alert = "📣 GMO Alert!" if matches["gmo"] else None
        
        # Create comprehensive result
        result = {
            "rating": rating,
            "matched_ingredients": matches,
            "confidence": confidence,
            "extracted_text_length": len(text),
            "text_quality": text_quality,
            "extracted_text": text[:500] + "..." if len(text) > 500 else text,
            "gmo_alert": gmo_alert
        }
        
        # Print comprehensive summary
        print_scan_summary(result)
        
        return result
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR in scan_image_for_ingredients: {e}")
        import traceback
        traceback.print_exc()
        return create_error_result(str(e))

def determine_confidence(text_quality, text, matches):
    """Determine confidence level based on multiple factors"""
    if text_quality == "very_poor":
        return "very_low"
    elif text_quality == "poor":
        return "low"
    elif text_quality == "fair":
        return "medium"
    elif len(text) > 50 and len(matches["all_detected"]) > 0:
        return "high"
    elif len(text) > 20:
        return "medium"
    else:
        return "low"

def create_error_result(error_message):
    """Create standardized error result"""
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
        "error": error_message
    }

def print_scan_summary(result):
    """Print comprehensive scan summary"""
    print(f"\n{'🎯 SCAN SUMMARY':=^80}")
    print(f"🏆 FINAL RATING: {result['rating']}")
    print(f"🎯 Confidence: {result['confidence']}")
    print(f"📊 Text Quality: {result['text_quality']}")
    print(f"📝 Text Length: {result['extracted_text_length']} characters")
    
    if result['gmo_alert']:
        print(f"📣 {result['gmo_alert']}")
    
    print(f"\n🧬 DETECTED INGREDIENTS BY CATEGORY:")
    for category, ingredients in result['matched_ingredients'].items():
        if ingredients:
            emoji = get_category_emoji(category)
            print(f"  {emoji} {category.replace('_', ' ').title()}: {ingredients}")
        else:
            print(f"  ❌ {category.replace('_', ' ').title()}: None detected")
    
    total_detected = len(result['matched_ingredients']['all_detected'])
    print(f"\n📊 TOTAL UNIQUE INGREDIENTS DETECTED: {total_detected}")
    print(f"{'='*80}\n")

def get_category_emoji(category):
    """Get emoji for ingredient category"""
    emoji_map = {
        'trans_fat': '🚫',
        'excitotoxins': '⚠️',
        'corn': '🌽',
        'sugar': '🍯',
        'gmo': '🧬',
        'safe_ingredients': '✅',
        'all_detected': '📋'
    }
    return emoji_map.get(category, '📝')
