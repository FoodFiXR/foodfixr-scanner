import re
import os
import gc
from scanner_config import *
import requests
from PIL import Image, ImageOps, ImageEnhance

def compress_image_for_ocr(image_path, max_size_kb=400):  # Reduced from 900KB
    """Memory-efficient image compression for OCR.space 1MB limit"""
    try:
        print(f"DEBUG: Checking image size for {image_path}")
        
        # Check current file size
        current_size_kb = os.path.getsize(image_path) / 1024
        print(f"DEBUG: Current image size: {current_size_kb:.1f} KB")
        
        if current_size_kb <= max_size_kb:
            print(f"DEBUG: Image size OK ({current_size_kb:.1f} KB), no compression needed")
            return image_path
        
        print(f"DEBUG: Image too large ({current_size_kb:.1f} KB), compressing...")
        
        # Memory-efficient approach: Get dimensions first without loading full image
        with Image.open(image_path) as img:
            original_width, original_height = img.size
            img_mode = img.mode
        
        print(f"DEBUG: Original dimensions: {original_width}x{original_height}")
        
        # More aggressive size limits for memory-constrained environments
        max_dimension = 1200  # Reduced from 2000
        if max(original_width, original_height) > max_dimension:
            if original_width > original_height:
                target_width = max_dimension
                target_height = int(original_height * max_dimension / original_width)
            else:
                target_height = max_dimension
                target_width = int(original_width * max_dimension / original_height)
        else:
            # More aggressive compression ratio
            size_ratio = max_size_kb / current_size_kb
            dimension_ratio = (size_ratio ** 0.5) * 0.6  # More conservative
            
            target_width = max(int(original_width * dimension_ratio), 600)  # Reduced min
            target_height = max(int(original_height * dimension_ratio), 400)  # Reduced min
        
        print(f"DEBUG: Target dimensions: {target_width}x{target_height}")
        
        # Create compressed filename
        base_name, ext = os.path.splitext(image_path)
        compressed_path = f"{base_name}_compressed.jpg"
        
        # Memory-efficient processing with immediate cleanup
        try:
            with Image.open(image_path) as img:
                # Convert mode if needed
                if img_mode in ('RGBA', 'LA', 'P'):
                    print(f"DEBUG: Converting from {img_mode} to RGB")
                    img = img.convert('RGB')
                
                # Resize with memory management
                print(f"DEBUG: Resizing image...")
                img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                
                # Try lower quality settings first
                for quality in [70, 60, 50, 40]:  # Start with lower quality
                    print(f"DEBUG: Trying quality {quality}...")
                    img_resized.save(compressed_path, 'JPEG', 
                                   quality=quality, optimize=True, progressive=True)
                    
                    compressed_size_kb = os.path.getsize(compressed_path) / 1024
                    print(f"DEBUG: Quality {quality}: Size {compressed_size_kb:.1f} KB")
                    
                    if compressed_size_kb <= max_size_kb:
                        print(f"✅ Successfully compressed to {compressed_size_kb:.1f} KB")
                        # Clean up memory immediately
                        del img_resized
                        gc.collect()
                        return compressed_path
                
                # If still too large, emergency compression
                print("DEBUG: Still too large, emergency compression...")
                emergency_width = min(800, target_width // 2)
                emergency_height = min(600, target_height // 2)
                
                img_emergency = img_resized.resize((emergency_width, emergency_height), Image.Resampling.LANCZOS)
                img_emergency.save(compressed_path, 'JPEG', quality=30, optimize=True)
                
                final_size_kb = os.path.getsize(compressed_path) / 1024
                print(f"DEBUG: Emergency compression: {final_size_kb:.1f} KB")
                
                # Clean up memory
                del img_emergency
                del img_resized
                gc.collect()
                
                return compressed_path
                
        except MemoryError:
            print("DEBUG: Memory error during compression, trying fallback...")
            # Emergency fallback: Very conservative dimensions
            safe_width = min(800, original_width // 3)
            safe_height = min(600, original_height // 3)
            
            with Image.open(image_path) as img:
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                img_safe = img.resize((safe_width, safe_height), Image.Resampling.LANCZOS)
                img_safe.save(compressed_path, 'JPEG', quality=25, optimize=True)
                
                fallback_size_kb = os.path.getsize(compressed_path) / 1024
                print(f"DEBUG: Memory-safe fallback: {fallback_size_kb:.1f} KB")
                
                # Clean up memory
                del img_safe
                gc.collect()
                
                return compressed_path
            
    except Exception as e:
        print(f"DEBUG: Image compression failed: {e}")
        # Force cleanup on error
        gc.collect()
        return image_path  # Return original path if compression fails

def extract_text_with_multiple_methods(image_path):
    """Extract text using OCR.space API with fallback options"""
    try:
        print(f"DEBUG: Starting OCR.space API text extraction from {image_path}")
        
        # Force garbage collection before starting
        gc.collect()
        
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
        # Force cleanup on error
        gc.collect()
        return ""

def extract_text_ocr_space(image_path):
    """Extract text using OCR.space API - with memory management"""
    try:
        # Compress image with smaller limit
        processed_image_path = compress_image_for_ocr(image_path, max_size_kb=300)
        
        # Force garbage collection after compression
        gc.collect()
        
        api_url = 'https://api.ocr.space/parse/image'
        api_key = os.getenv('OCR_SPACE_API_KEY', 'helloworld')
        
        print(f"DEBUG: Using image: {processed_image_path}")
        print(f"DEBUG: Final file size: {os.path.getsize(processed_image_path)/1024:.1f} KB")
        
        # Use context manager for file handling
        with open(processed_image_path, 'rb') as f:
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
            
            print("DEBUG: Sending compressed image to OCR.space API (standard)...")
            
            # Shorter timeout to prevent memory buildup
            response = requests.post(api_url, files=files, data=data, timeout=30)
        
        # Clean up compressed file immediately
        if processed_image_path != image_path:
            try:
                os.remove(processed_image_path)
                print("DEBUG: Cleaned up compressed image file")
            except:
                pass
        
        # Force garbage collection after API call
        gc.collect()
        
        if response.status_code == 200:
            result = response.json()
            return parse_ocr_space_response(result)
        else:
            print(f"DEBUG: OCR.space API returned status {response.status_code}")
            print(f"DEBUG: Response: {response.text[:500]}")
            return ""
            
    except Exception as e:
        print(f"DEBUG: OCR.space standard method failed: {e}")
        # Force cleanup on error
        gc.collect()
        return ""

def extract_text_ocr_space_enhanced(image_path):
    """Extract text using OCR.space API - enhanced settings with memory management"""
    try:
        # Compress image with smaller limit
        processed_image_path = compress_image_for_ocr(image_path, max_size_kb=300)
        
        # Force garbage collection
        gc.collect()
        
        api_url = 'https://api.ocr.space/parse/image'
        api_key = os.getenv('OCR_SPACE_API_KEY', 'helloworld')
        
        with open(processed_image_path, 'rb') as f:
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
            
            print("DEBUG: Sending compressed image to OCR.space API (enhanced)...")
            response = requests.post(api_url, files=files, data=data, timeout=30)
        
        # Clean up compressed file immediately
        if processed_image_path != image_path:
            try:
                os.remove(processed_image_path)
                print("DEBUG: Cleaned up compressed image file")
            except:
                pass
        
        # Force garbage collection
        gc.collect()
        
        if response.status_code == 200:
            result = response.json()
            return parse_ocr_space_response(result)
        else:
            print(f"DEBUG: OCR.space enhanced API returned status {response.status_code}")
            print(f"DEBUG: Response: {response.text[:500]}")
            return ""
            
    except Exception as e:
        print(f"DEBUG: OCR.space enhanced method failed: {e}")
        # Force cleanup on error
        gc.collect()
        return ""

def parse_ocr_space_response(result):
    """Parse OCR.space API response with better error handling"""
    try:
        print(f"DEBUG: OCR.space response keys: {list(result.keys())}")
        
        if result.get('IsErroredOnProcessing', True):
            error_messages = result.get('ErrorMessage', ['Unknown error'])
            if isinstance(error_messages, list):
                error_msg = ', '.join(error_messages)
            else:
                error_msg = str(error_messages)
            print(f"DEBUG: OCR.space processing error: {error_msg}")
            return ""
        
        parsed_results = result.get('ParsedResults', [])
        if not parsed_results:
            print("DEBUG: OCR.space returned no parsed results")
            return ""
        
        # Get text from first result
        first_result = parsed_results[0]
        print(f"DEBUG: First result keys: {list(first_result.keys())}")
        
        extracted_text = first_result.get('ParsedText', '')
        
        if extracted_text and len(extracted_text.strip()) > 0:
            # Clean up the text
            cleaned_text = extracted_text.replace('\r', ' ').replace('\n', ' ')
            cleaned_text = ' '.join(cleaned_text.split())  # Remove extra whitespace
            
            print(f"DEBUG: OCR.space extracted {len(cleaned_text)} characters")
            print(f"DEBUG: Raw text preview: {cleaned_text[:300]}...")
            return cleaned_text
        else:
            print("DEBUG: OCR.space returned empty text")
            # Check if there's an error in the parsed result
            if 'ErrorMessage' in first_result:
                print(f"DEBUG: ParsedResult error: {first_result['ErrorMessage']}")
            return ""
            
    except Exception as e:
        print(f"DEBUG: Error parsing OCR.space response: {e}")
        print(f"DEBUG: Raw response: {result}")
        return ""

def extract_text_pytesseract_fallback(image_path):
    """Fallback to pytesseract if available"""
    try:
        print("DEBUG: Attempting pytesseract fallback...")
        import pytesseract
        from PIL import Image
        
        # Force garbage collection before loading image
        gc.collect()
        
        image = Image.open(image_path)
        
        # Simple preprocessing
        if image.mode != 'L':
            image = image.convert('L')
            
        # Try basic OCR
        text = pytesseract.image_to_string(image, config='--psm 6')
        
        # Clean up image from memory
        del image
        gc.collect()
        
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
        # Force cleanup on error
        gc.collect()
        return ""

def normalize_ingredient_text(text):
    """CONSERVATIVE text normalization - only fix obvious OCR errors"""
    if not text:
        return ""
    
    # Convert to lowercase and basic cleanup
    text = text.lower().strip()
    
    # Remove excessive whitespace and newlines
    text = re.sub(r'\s+', ' ', text)
    
    # Remove common OCR artifacts but be conservative
    text = re.sub(r'[^\w\s\-\(\),.]', ' ', text)
    
    # ONLY fix the most obvious OCR errors - be very conservative
    obvious_corrections = {
        # Only fix clear number-to-letter mistakes that are obvious
        'rn': 'm',  # common OCR error
        'cornsynup': 'corn syrup',  # specific known error
        'com syrup': 'corn syrup',  # specific known error
        'hfc5': 'hfcs',  # specific known error
        'naturalflavors': 'natural flavors',  # compound word fix
        'naturalflavor': 'natural flavor',  # compound word fix
        'soylecithin': 'soy lecithin',  # compound word fix
        'monosodiumglutamate': 'monosodium glutamate',  # compound word fix
        'highfructose': 'high fructose',  # compound word fix
        'vegetableoil': 'vegetable oil',  # compound word fix
    }
    
    # Apply only obvious corrections
    for wrong, correct in obvious_corrections.items():
        text = text.replace(wrong, correct)
    
    return text

def precise_ingredient_matching(text, ingredient_list, category_name=""):
    """MUCH MORE PRECISE matching - avoid false positives"""
    matches = []
    normalized_text = normalize_ingredient_text(text)
    
    print(f"DEBUG: Searching for {category_name} ingredients in normalized text")
    print(f"DEBUG: Text preview: {normalized_text[:200]}...")
    
    for ingredient in ingredient_list:
        normalized_ingredient = normalize_ingredient_text(ingredient)
        
        if len(normalized_ingredient) < 2:
            continue
        
        # Strategy 1: EXACT word boundary match (most reliable)
        pattern = r'\b' + re.escape(normalized_ingredient) + r'\b'
        if re.search(pattern, normalized_text):
            matches.append(ingredient)
            print(f"DEBUG: ✅ EXACT WORD MATCH: '{normalized_ingredient}' -> '{ingredient}'")
            continue
        
        # Strategy 2: For multi-word ingredients, check if ALL words are present nearby
        if ' ' in normalized_ingredient:
            words = normalized_ingredient.split()
            if len(words) >= 2:
                # ALL words must be found within 50 characters of each other
                all_word_positions = []
                all_words_found = True
                
                for word in words:
                    if len(word) <= 2:  # Skip very short words
                        continue
                    word_pattern = r'\b' + re.escape(word) + r'\b'
                    matches_found = list(re.finditer(word_pattern, normalized_text))
                    if matches_found:
                        all_word_positions.extend([m.start() for m in matches_found])
                    else:
                        all_words_found = False
                        break
                
                if all_words_found and all_word_positions:
                    # Check if words are reasonably close together (within 50 chars)
                    min_pos = min(all_word_positions)
                    max_pos = max(all_word_positions)
                    if max_pos - min_pos <= 50:
                        matches.append(ingredient)
                        print(f"DEBUG: ✅ MULTI-WORD MATCH: '{normalized_ingredient}' -> '{ingredient}'")
                        continue
        
        # Strategy 3: For single critical ingredients only, allow partial matching
        # But ONLY for ingredients longer than 5 characters to avoid false positives
        if (' ' not in normalized_ingredient and 
            len(normalized_ingredient) > 5 and
            normalized_ingredient in normalized_text):
            
            # Double-check this isn't a substring of a larger word
            # Find all occurrences and check word boundaries
            for match in re.finditer(re.escape(normalized_ingredient), normalized_text):
                start, end = match.span()
                
                # Check characters before and after
                char_before = normalized_text[start-1] if start > 0 else ' '
                char_after = normalized_text[end] if end < len(normalized_text) else ' '
                
                # Only match if surrounded by non-letter characters
                if not char_before.isalpha() and not char_after.isalpha():
                    matches.append(ingredient)
                    print(f"DEBUG: ✅ PARTIAL MATCH: '{normalized_ingredient}' -> '{ingredient}'")
                    break
    
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
    """Enhanced ingredient matching with tiered safety system"""
    if not text:
        print("DEBUG: No text provided for ingredient matching")
        return {
            "trans_fat": [],
            "excitotoxins": [],
            "corn": [],
            "sugar": [],
            "gmo": [],
            "tier_1_safe": [],
            "tier_2_safe": [],
            "tier_3_caution": [],
            "tier_4_danger": [],
            "all_detected": []
        }
    
    print(f"DEBUG: Matching ingredients in text of {len(text)} characters")
    print(f"DEBUG: Text sample: {text[:200]}...")
    
    # Define tiered ingredient lists based on your data
    tier_1_ingredients = ["broccoli", "spinach", "kale"]  # Most safe
    tier_2_ingredients = ["citric acid", "xanthan gum", "msg", "monosodium glutamate", "stevia"]  # Generally safe
    tier_3_ingredients = ["carrageenan"]  # Caution
    tier_4_ingredients = ["brominated vegetable oil", "potassium bromate", "aspartame"]  # High concern
    
    # Match each category using PRECISE matching
    trans_fat_matches = precise_ingredient_matching(text, trans_fat_high_risk + trans_fat_moderate_risk, "Trans Fat")
    excitotoxin_matches = precise_ingredient_matching(text, excitotoxin_high_risk + excitotoxin_moderate_risk + excitotoxin_low_risk, "Excitotoxin")
    corn_matches = precise_ingredient_matching(text, corn_high_risk + corn_moderate_risk, "Corn")
    sugar_matches = precise_ingredient_matching(text, sugar_keywords, "Sugar")
    gmo_matches = precise_ingredient_matching(text, gmo_keywords, "GMO")
    
    # Match tiered ingredients
    tier_1_matches = precise_ingredient_matching(text, tier_1_ingredients, "Tier 1 Safe")
    tier_2_matches = precise_ingredient_matching(text, tier_2_ingredients, "Tier 2 Safe")
    tier_3_matches = precise_ingredient_matching(text, tier_3_ingredients, "Tier 3 Caution")
    tier_4_matches = precise_ingredient_matching(text, tier_4_ingredients, "Tier 4 Danger")
    
    # Combine all detected ingredients
    all_detected = list(set(trans_fat_matches + excitotoxin_matches + corn_matches + 
                           sugar_matches + gmo_matches + tier_1_matches + tier_2_matches + 
                           tier_3_matches + tier_4_matches))
    
    result = {
        "trans_fat": list(set(trans_fat_matches)),
        "excitotoxins": list(set(excitotoxin_matches)),
        "corn": list(set(corn_matches)),
        "sugar": list(set(sugar_matches)),
        "gmo": list(set(gmo_matches)),
        "tier_1_safe": list(set(tier_1_matches)),
        "tier_2_safe": list(set(tier_2_matches)),
        "tier_3_caution": list(set(tier_3_matches)),
        "tier_4_danger": list(set(tier_4_matches)),
        "all_detected": all_detected
    }
    
    print(f"DEBUG: TIERED INGREDIENT MATCHING RESULTS:")
    for category, ingredients in result.items():
        if ingredients:
            print(f"  ✅ {category}: {ingredients}")
        else:
            print(f"  ❌ {category}: No matches")
    
    return result

def rate_ingredients_according_to_hierarchy(matches, text_quality):
    """
    Updated rating system with tiered safety approach:
    
    1. Tier 4 ingredients = immediate danger
    2. HIGH RISK TRANS FATS - ANY ONE = immediate danger
    3. HIGH RISK EXCITOTOXINS - ANY ONE = immediate danger  
    4. Tier 3 ingredients = caution
    5. Count ALL other problematic ingredients (moderate trans fats, moderate excitotoxins, corn, sugar)
    6. If total count >= 3 = danger, if >= 1 = proceed carefully
    7. Tier 1 & 2 ingredients = safe
    """
    
    print(f"DEBUG: Rating ingredients with text quality: {text_quality}")
    
    # If text quality is very poor, suggest trying again
    if text_quality == "very_poor":
        return "↪️ TRY AGAIN"
    
    # RULE 1: Tier 4 ingredients = immediate danger
    if matches["tier_4_danger"]:
        print(f"🚨 TIER 4 DANGER ingredients detected: {matches['tier_4_danger']}")
        return "🚨 Oh NOOOO! Danger!"
    
    # RULE 2: HIGH RISK TRANS FATS - ANY ONE = immediate danger
    high_risk_trans_fat_found = []
    for ingredient in matches["trans_fat"]:
        for high_risk_item in trans_fat_high_risk:
            if high_risk_item.lower() in ingredient.lower():
                high_risk_trans_fat_found.append(ingredient)
                print(f"🚨 HIGH RISK Trans Fat detected: {ingredient}")
                return "🚨 Oh NOOOO! Danger!"
    
    # RULE 3: HIGH RISK EXCITOTOXINS - ANY ONE = immediate danger  
    high_risk_excitotoxin_found = []
    for ingredient in matches["excitotoxins"]:
        for high_risk_item in excitotoxin_high_risk:
            if high_risk_item.lower() in ingredient.lower():
                high_risk_excitotoxin_found.append(ingredient)
                print(f"🚨 HIGH RISK Excitotoxin detected: {ingredient}")
                return "🚨 Oh NOOOO! Danger!"
    
    # RULE 4: Tier 3 ingredients = caution (but check total count too)
    tier_3_count = len(matches["tier_3_caution"])
    if tier_3_count > 0:
        print(f"⚠️ TIER 3 CAUTION ingredients detected: {matches['tier_3_caution']}")
    
    # RULE 5: COUNT ALL OTHER PROBLEMATIC INGREDIENTS
    total_problematic_count = 0
    
    # Count moderate trans fats (not already counted as high risk)
    moderate_trans_fat_count = 0
    for ingredient in matches["trans_fat"]:
        if ingredient not in high_risk_trans_fat_found:
            for moderate_item in trans_fat_moderate_risk:
                if moderate_item.lower() in ingredient.lower():
                    moderate_trans_fat_count += 1
                    print(f"⚠️ Moderate trans fat counted: {ingredient}")
                    break
    
    # Count moderate excitotoxins (not already counted as high risk)  
    moderate_excitotoxin_count = 0
    for ingredient in matches["excitotoxins"]:
        if ingredient not in high_risk_excitotoxin_found:
            for moderate_item in excitotoxin_moderate_risk:
                if moderate_item.lower() in ingredient.lower():
                    moderate_excitotoxin_count += 1
                    print(f"⚠️ Moderate excitotoxin counted: {ingredient}")
                    break
            for low_item in excitotoxin_low_risk:
                if low_item.lower() in ingredient.lower():
                    moderate_excitotoxin_count += 1
                    print(f"⚠️ Low risk excitotoxin counted: {ingredient}")
                    break
    
    # Count ALL corn and sugar ingredients
    corn_count = len(matches["corn"])
    sugar_count = len(matches["sugar"])
    
    # Calculate total problematic count (including Tier 3)
    total_problematic_count = moderate_trans_fat_count + moderate_excitotoxin_count + corn_count + sugar_count + tier_3_count
    
    print(f"⚖️ TOTAL PROBLEMATIC COUNT: {total_problematic_count}")
    print(f"   - Tier 3 caution: {tier_3_count}")
    print(f"   - Moderate trans fats: {moderate_trans_fat_count}")
    print(f"   - Moderate excitotoxins: {moderate_excitotoxin_count}")
    print(f"   - Corn ingredients: {corn_count}")
    print(f"   - Sugar ingredients: {sugar_count}")
    
    # RULE 6: Apply hierarchy rules
    if total_problematic_count >= 3:
        return "🚨 Oh NOOOO! Danger!"
    elif total_problematic_count >= 1:
        return "⚠️ Proceed carefully"
    
    # RULE 7: Check for safe ingredients
    safe_count = len(matches["tier_1_safe"]) + len(matches["tier_2_safe"])
    if safe_count > 0:
        print(f"✅ Safe ingredients detected: Tier 1: {matches['tier_1_safe']}, Tier 2: {matches['tier_2_safe']}")
        return "✅ Yay! Safe!"
    
    # If some ingredients detected but none categorized
    if len(matches["all_detected"]) > 0:
        return "✅ Yay! Safe!"
    
    # If poor text quality and no ingredients detected
    if text_quality in ["poor", "fair"]:
        return "↪️ TRY AGAIN"
    
    return "✅ Yay! Safe!"

def scan_image_for_ingredients(image_path):
    """Main scanning function with memory management"""
    try:
        # Force garbage collection at start
        gc.collect()
        
        print(f"\n{'='*80}")
        print(f"🔬 STARTING MEMORY-EFFICIENT SCAN: {image_path}")
        print(f"{'='*80}")
        print(f"DEBUG: File exists: {os.path.exists(image_path)}")
        
        # Extract text using OCR.space
        print("🔍 Starting OCR.space text extraction...")
        text = extract_text_with_multiple_methods(image_path)
        print(f"📝 Extracted text length: {len(text)} characters")
        
        if text:
            print(f"📋 EXTRACTED TEXT:\n{text}")
        else:
            print("❌ No text extracted!")
        
        # Assess text quality
        text_quality = assess_text_quality_enhanced(text)
        print(f"📊 Text quality assessment: {text_quality}")
        
        # Match ingredients using PRECISE system
        print("🧬 Starting PRECISE ingredient matching...")
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
            "extracted_text": text,
            "gmo_alert": gmo_alert
        }
        
        # Print comprehensive summary
        print_scan_summary(result)
        
        # Force final cleanup
        gc.collect()
        
        return result
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR in scan_image_for_ingredients: {e}")
        import traceback
        traceback.print_exc()
        
        # Force cleanup on error
        gc.collect()
        
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
    """Create standardized error result with tiered system"""
    return {
        "rating": "↪️ TRY AGAIN",
        "matched_ingredients": {
            "trans_fat": [], "excitotoxins": [], "corn": [], 
            "sugar": [], "gmo": [], "tier_1_safe": [], "tier_2_safe": [],
            "tier_3_caution": [], "tier_4_danger": [], "all_detected": []
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
    """Get emoji for ingredient category with tiered system"""
    emoji_map = {
        'trans_fat': '🚫',
        'excitotoxins': '⚠️',
        'corn': '🌽',
        'sugar': '🍯',
        'gmo': '🧬',
        'tier_1_safe': '🟢',
        'tier_2_safe': '🔵',
        'tier_3_caution': '🟡',
        'tier_4_danger': '🔴',
        'all_detected': '📋'
    }
    return emoji_map.get(category, '📝')
