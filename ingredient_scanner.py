import pytesseract
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import re
import os
from scanner_config import *

def preprocess_image_advanced(image):
    """Advanced image preprocessing with multiple techniques"""
    try:
        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Convert to grayscale
        gray = image.convert('L')
        
        # Resize if too small (critical for mobile photos)
        width, height = gray.size
        if width < 1000:
            scale_factor = 1000 / width
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            gray = gray.resize((new_width, new_height), Image.Resampling.LANCZOS)
            print(f"DEBUG: Resized image from {width}x{height} to {new_width}x{new_height}")
        
        # Multiple preprocessing approaches
        processed_images = []
        
        # Method 1: High contrast with sharpening
        enhancer = ImageEnhance.Contrast(gray)
        high_contrast = enhancer.enhance(3.5)
        enhancer = ImageEnhance.Sharpness(high_contrast)
        sharpened = enhancer.enhance(2.5)
        processed_images.append(("high_contrast_sharp", sharpened))
        
        # Method 2: Auto-level and equalize
        auto_level = ImageOps.autocontrast(gray)
        equalized = ImageOps.equalize(auto_level)
        processed_images.append(("auto_equalized", equalized))
        
        # Method 3: Extreme contrast for bold text
        extreme_contrast = ImageOps.autocontrast(gray, cutoff=15)
        enhancer = ImageEnhance.Contrast(extreme_contrast)
        extreme = enhancer.enhance(4.0)
        processed_images.append(("extreme_contrast", extreme))
        
        # Method 4: Noise reduction then enhance
        denoised = gray.filter(ImageFilter.MedianFilter(size=3))
        enhancer = ImageEnhance.Contrast(denoised)
        clean_contrast = enhancer.enhance(2.8)
        processed_images.append(("clean_contrast", clean_contrast))
        
        return processed_images
        
    except Exception as e:
        print(f"DEBUG: Advanced preprocessing failed: {e}, using original")
        return [("original", image)]

def extract_text_with_multiple_methods(image_path):
    """Extract text using multiple OCR configurations and image processing"""
    try:
        print(f"DEBUG: Starting enhanced text extraction from {image_path}")
        
        # Load image
        image = Image.open(image_path)
        print(f"DEBUG: Original image size: {image.size}, mode: {image.mode}")
        
        all_extracted_texts = []
        
        # Get processed images
        processed_images = preprocess_image_advanced(image)
        
        # OCR configurations to try
        ocr_configs = [
            '--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789(),-. ',
            '--oem 3 --psm 4',
            '--oem 3 --psm 3',
            '--oem 3 --psm 6',
            '--oem 3 --psm 8',
            '--oem 3 --psm 7',
            '--oem 3 --psm 11',
            '--oem 3 --psm 12',
            '--oem 1 --psm 6',
        ]
        
        # Try each processed image with each OCR config
        for method_name, processed_img in processed_images:
            for i, config in enumerate(ocr_configs):
                try:
                    text = pytesseract.image_to_string(processed_img, config=config)
                    text = text.strip()
                    if text and len(text) > 3:
                        all_extracted_texts.append({
                            'text': text,
                            'method': f"{method_name}_config_{i+1}",
                            'length': len(text),
                            'word_count': len(text.split())
                        })
                        print(f"DEBUG: {method_name} config {i+1} extracted {len(text)} chars")
                except Exception as e:
                    print(f"DEBUG: {method_name} config {i+1} failed: {e}")
        
        # If we have multiple extractions, combine them intelligently
        if all_extracted_texts:
            # Sort by length (longer is usually better)
            all_extracted_texts.sort(key=lambda x: x['length'], reverse=True)
            
            # Take the longest text as base
            best_text = all_extracted_texts[0]['text']
            
            # Extract all unique words from all extractions
            all_words = set()
            for extraction in all_extracted_texts:
                words = re.findall(r'\b[a-zA-Z]{2,}\b', extraction['text'].lower())
                all_words.update(words)
            
            # Add missing words to best text
            best_words = set(re.findall(r'\b[a-zA-Z]{2,}\b', best_text.lower()))
            missing_words = all_words - best_words
            
            if missing_words:
                best_text += " " + " ".join(missing_words)
            
            print(f"DEBUG: COMBINED TEXT LENGTH: {len(best_text)} characters")
            print(f"DEBUG: COMBINED TEXT PREVIEW: {best_text[:300]}...")
            return best_text
        else:
            print("DEBUG: No text extracted by any method")
            return ""
            
    except Exception as e:
        print(f"❌ Error in extract_text_with_multiple_methods: {e}")
        import traceback
        traceback.print_exc()
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
    """Main scanning function with enhanced processing and debug output"""
    try:
        print(f"\n{'='*80}")
        print(f"🔬 STARTING ENHANCED INGREDIENT SCAN: {image_path}")
        print(f"{'='*80}")
        print(f"DEBUG: File exists: {os.path.exists(image_path)}")
        
        # Test tesseract availability
        try:
            test_img = Image.new('RGB', (100, 30), color='white')
            pytesseract.image_to_string(test_img, config='--psm 6')
            print("✅ Tesseract OCR is working")
        except Exception as e:
            print(f"❌ Tesseract error: {e}")
            return create_error_result("OCR system not available")
        
        # Extract text using enhanced methods
        print("🔍 Starting enhanced text extraction...")
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
        print("🧬 Starting enhanced ingredient matching...")
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
