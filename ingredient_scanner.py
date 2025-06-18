import re
import os
import gc
from scanner_config import *
import requests
from PIL import Image, ImageOps, ImageEnhance

import gc
import psutil  # Add this for memory monitoring
import os
import tempfile
import time
from PIL import Image
import requests

# Add memory monitoring function
def log_memory_usage(stage=""):
    """Log current memory usage"""
    try:
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        print(f"DEBUG: Memory usage {stage}: {memory_mb:.1f} MB")
        
        # Force garbage collection if memory is high
        if memory_mb > 200:  # If using more than 200MB
            print(f"DEBUG: High memory usage detected, forcing cleanup...")
            gc.collect()
            time.sleep(0.1)  # Brief pause after cleanup
    except:
        pass

def aggressive_cleanup():
    """Ultra-aggressive memory cleanup"""
    try:
        # Force multiple garbage collection cycles
        for _ in range(3):
            gc.collect()
        
        # Clear PIL cache
        Image.MAX_IMAGE_PIXELS = None
        
        # Force Python to release memory back to OS (if possible)
        if hasattr(gc, 'set_threshold'):
            gc.set_threshold(0, 0, 0)  # Disable automatic GC temporarily
            gc.collect()
            gc.set_threshold(700, 10, 10)  # Re-enable with aggressive settings
        
        print("DEBUG: Aggressive cleanup completed")
    except Exception as e:
        print(f"DEBUG: Cleanup error: {e}")

def compress_image_for_ocr(image_path, max_size_kb=150):  # Increased from 100KB
    """Ultra-aggressive memory-efficient image compression for OCR.space"""
    log_memory_usage("before compression")
    
    try:
        print(f"DEBUG: Checking image size for {image_path}")
        
        # Check current file size
        current_size_kb = os.path.getsize(image_path) / 1024
        print(f"DEBUG: Current image size: {current_size_kb:.1f} KB")
        
        if current_size_kb <= max_size_kb:
            print(f"DEBUG: Image size OK ({current_size_kb:.1f} KB), no compression needed")
            return image_path
        
        print(f"DEBUG: Image too large ({current_size_kb:.1f} KB), compressing...")
        
        # Create compressed filename in temp directory
        temp_dir = tempfile.gettempdir()
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        compressed_path = os.path.join(temp_dir, f"{base_name}_compressed_{int(time.time())}.jpg")
        
        # Ultra-conservative approach for memory-constrained environments
        try:
            # Get basic image info without loading into memory
            with Image.open(image_path) as img:
                original_width, original_height = img.size
                img_mode = img.mode
                
            print(f"DEBUG: Original dimensions: {original_width}x{original_height}")
            
            # More aggressive initial sizing for very large images
            max_dimension = 800  # Increased from 600 for better OCR quality
            if max(original_width, original_height) > max_dimension:
                if original_width > original_height:
                    target_width = max_dimension
                    target_height = int(original_height * max_dimension / original_width)
                else:
                    target_height = max_dimension
                    target_width = int(original_width * max_dimension / original_height)
            else:
                # More aggressive compression for smaller images
                size_ratio = max_size_kb / current_size_kb
                dimension_ratio = (size_ratio ** 0.5) * 0.5  # Less aggressive than before
                
                target_width = max(int(original_width * dimension_ratio), 400)
                target_height = max(int(original_height * dimension_ratio), 300)
            
            print(f"DEBUG: Target dimensions: {target_width}x{target_height}")
            
            # Process with immediate cleanup and moderate quality settings
            with Image.open(image_path) as img:
                # Convert mode if needed
                if img_mode in ('RGBA', 'LA', 'P'):
                    print(f"DEBUG: Converting from {img_mode} to RGB")
                    img = img.convert('RGB')
                
                # Resize with memory management
                print(f"DEBUG: Resizing image...")
                img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)  # Better quality
                
                # Force garbage collection after resize
                log_memory_usage("after resize")
                
                # Try moderate quality settings (improved for OCR)
                for quality in [60, 50, 40, 30, 25, 20]:  # Start higher for better OCR
                    print(f"DEBUG: Trying quality {quality}...")
                    try:
                        img_resized.save(compressed_path, 'JPEG', 
                                       quality=quality, optimize=True, progressive=False)
                        
                        compressed_size_kb = os.path.getsize(compressed_path) / 1024
                        print(f"DEBUG: Quality {quality}: Size {compressed_size_kb:.1f} KB")
                        
                        if compressed_size_kb <= max_size_kb:
                            print(f"✅ Successfully compressed to {compressed_size_kb:.1f} KB")
                            # Clean up memory immediately
                            del img_resized
                            aggressive_cleanup()
                            log_memory_usage("after compression success")
                            return compressed_path
                    except Exception as e:
                        print(f"DEBUG: Quality {quality} failed: {e}")
                        continue
                
                # Emergency ultra-compression if still too large
                print("DEBUG: Still too large, emergency ultra-compression...")
                emergency_width = min(500, target_width // 2)  # Slightly larger
                emergency_height = min(400, target_height // 2)  # Slightly larger
                
                # Create new smaller image
                del img_resized  # Free memory first
                aggressive_cleanup()
                
                # Reopen and process with minimal memory
                with Image.open(image_path) as img_new:
                    if img_new.mode in ('RGBA', 'LA', 'P'):
                        img_new = img_new.convert('RGB')
                    
                    img_emergency = img_new.resize((emergency_width, emergency_height), Image.Resampling.LANCZOS)
                    img_emergency.save(compressed_path, 'JPEG', quality=25, optimize=False)  # Slightly better quality
                    
                    final_size_kb = os.path.getsize(compressed_path) / 1024
                    print(f"DEBUG: Emergency compression: {final_size_kb:.1f} KB")
                    
                    # Clean up memory
                    del img_emergency
                    aggressive_cleanup()
                    log_memory_usage("after emergency compression")
                    
                    return compressed_path
                
        except MemoryError as me:
            print(f"DEBUG: Memory error during compression: {me}")
            # Ultra-minimal fallback
            try:
                aggressive_cleanup()
                
                with Image.open(image_path) as img:
                    if img.mode in ('RGBA', 'LA', 'P'):
                        img = img.convert('RGB')
                    
                    # Very small emergency size
                    img_tiny = img.resize((400, 300), Image.Resampling.NEAREST)  # Slightly larger
                    img_tiny.save(compressed_path, 'JPEG', quality=15, optimize=False)
                    
                    tiny_size_kb = os.path.getsize(compressed_path) / 1024
                    print(f"DEBUG: Tiny fallback: {tiny_size_kb:.1f} KB")
                    
                    del img_tiny
                    aggressive_cleanup()
                    return compressed_path
            except:
                print("DEBUG: All compression methods failed")
                aggressive_cleanup()
                return image_path
            
    except Exception as e:
        print(f"DEBUG: Image compression failed: {e}")
        aggressive_cleanup()
        return image_path
    finally:
        # Always clean up
        aggressive_cleanup()
        log_memory_usage("end of compression")

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
    """Extract text using OCR.space API - with aggressive memory management"""
    log_memory_usage("start OCR")
    
    try:
        # Force garbage collection before starting
        aggressive_cleanup()
        
        # Compress image with moderate limit
        processed_image_path = compress_image_for_ocr(image_path, max_size_kb=150)
        
        # Force garbage collection after compression
        aggressive_cleanup()
        
        api_url = 'https://api.ocr.space/parse/image'
        api_key = os.getenv('OCR_SPACE_API_KEY', 'helloworld')
        
        print(f"DEBUG: Using image: {processed_image_path}")
        print(f"DEBUG: Final file size: {os.path.getsize(processed_image_path)/1024:.1f} KB")
        
        # Use context manager for file handling with longer timeout
        response = None
        try:
            with open(processed_image_path, 'rb') as f:
                files = {'file': f}
                
                data = {
                    'apikey': api_key,
                    'language': 'eng',
                    'isOverlayRequired': False,
                    'detectOrientation': True,
                    'scale': True,
                    'OCREngine': 2,
                    'isTable': False
                }
                
                print("DEBUG: Sending compressed image to OCR.space API...")
                
                # Longer timeout to prevent timeout errors
                response = requests.post(api_url, files=files, data=data, timeout=30)
                
                log_memory_usage("after API call")
        
        except Exception as e:
            print(f"DEBUG: OCR API call failed: {e}")
            return ""
        finally:
            # Clean up compressed file immediately - even if API fails
            if processed_image_path != image_path:
                try:
                    os.remove(processed_image_path)
                    print("DEBUG: Cleaned up compressed image file")
                except:
                    pass
            
            # Force garbage collection after API call
            aggressive_cleanup()
            log_memory_usage("after cleanup")
        
        if response and response.status_code == 200:
            result = response.json()
            extracted_text = parse_ocr_space_response(result)
            
            # Clear response object
            del response
            aggressive_cleanup()
            
            return extracted_text
        else:
            if response:
                print(f"DEBUG: OCR.space API returned status {response.status_code}")
                # Try to get error details
                try:
                    error_data = response.json()
                    print(f"DEBUG: API Error details: {error_data}")
                except:
                    print(f"DEBUG: Response text: {response.text[:200]}")
            return ""
            
    except Exception as e:
        print(f"DEBUG: OCR.space method failed: {e}")
        # Force cleanup on error
        aggressive_cleanup()
        return ""
    finally:
        # Always clean up
        aggressive_cleanup()
        log_memory_usage("end OCR")

def extract_text_ocr_space_enhanced(image_path):
    """Extract text using OCR.space API - enhanced settings with aggressive memory management"""
    try:
        # Force garbage collection
        gc.collect()
        
        # Compress image with moderate limit
        processed_image_path = compress_image_for_ocr(image_path, max_size_kb=150)
        
        # Force garbage collection
        gc.collect()
        
        api_url = 'https://api.ocr.space/parse/image'
        api_key = os.getenv('OCR_SPACE_API_KEY', 'helloworld')
        
        try:
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
                response = requests.post(api_url, files=files, data=data, timeout=30)  # Longer timeout
        
        except Exception as e:
            print(f"DEBUG: Enhanced OCR API call failed: {e}")
            return ""
        finally:
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
            try:
                error_data = response.json()
                print(f"DEBUG: Enhanced API Error details: {error_data}")
            except:
                print(f"DEBUG: Enhanced Response text: {response.text[:200]}")
            return ""
            
    except Exception as e:
        print(f"DEBUG: OCR.space enhanced method failed: {e}")
        # Force cleanup on error
        gc.collect()
        return ""

# Add at the very beginning of your main request handler
def cleanup_before_request():
    """Clean up memory before processing each request"""
    try:
        log_memory_usage("before request")
        aggressive_cleanup()
        
        # Clear any temporary files older than 5 minutes
        temp_dir = tempfile.gettempdir()
        current_time = time.time()
        
        for filename in os.listdir(temp_dir):
            if filename.endswith('_compressed.jpg') or 'compressed' in filename:
                filepath = os.path.join(temp_dir, filename)
                try:
                    if os.path.isfile(filepath):
                        file_age = current_time - os.path.getmtime(filepath)
                        if file_age > 300:  # 5 minutes
                            os.remove(filepath)
                            print(f"DEBUG: Cleaned up old temp file: {filename}")
                except:
                    pass
        
        log_memory_usage("after request cleanup")
        print("DEBUG: Pre-request cleanup completed")
        
    except Exception as e:
        print(f"DEBUG: Pre-request cleanup error: {e}")

# This function should be called from your main app.py file
def before_request_cleanup():
    """Run cleanup before each request - call this from your main Flask app"""
    cleanup_before_request()

def process_image_with_memory_management(image_path):
    """Main image processing function with comprehensive memory management"""
    log_memory_usage("start processing")
    
    try:
        # Clean up before starting
        aggressive_cleanup()
        
        # Extract text with multiple fallback methods
        extracted_text = ""
        
        # Try OCR.space first (most memory efficient)
        print("DEBUG: Attempting OCR.space extraction...")
        extracted_text = extract_text_ocr_space(image_path)
        
        if not extracted_text or len(extracted_text.strip()) < 10:
            print("DEBUG: OCR.space failed, trying enhanced method...")
            aggressive_cleanup()  # Clean up before trying again
            extracted_text = extract_text_ocr_space_enhanced(image_path)
        
        if not extracted_text or len(extracted_text.strip()) < 5:
            print("DEBUG: All OCR methods failed")
            return None
        
        log_memory_usage("after OCR")
        
        # Process the extracted text
        result = analyze_ingredients(extracted_text)
        
        # Clean up after processing
        aggressive_cleanup()
        log_memory_usage("end processing")
        
        return result
        
    except Exception as e:
        print(f"DEBUG: Error in image processing: {e}")
        aggressive_cleanup()
        return None
    finally:
        # Always clean up
        aggressive_cleanup()
        
        # Final temp file cleanup
        try:
            if image_path and os.path.exists(image_path):
                os.remove(image_path)
                print("DEBUG: Cleaned up original uploaded file")
        except:
            pass

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
    """Enhanced ingredient matching with precise categories"""
    if not text:
        print("DEBUG: No text provided for ingredient matching")
        return {
            "trans_fat": [],
            "excitotoxins": [],
            "corn": [],
            "sugar": [],
            "sugar_safe": [],
            "gmo": [],
            "all_detected": []
        }
    
    print(f"DEBUG: Matching ingredients in text of {len(text)} characters")
    print(f"DEBUG: Text sample: {text[:200]}...")
    
    # Match each category using PRECISE matching
    trans_fat_matches = precise_ingredient_matching(text, trans_fat_high_risk + trans_fat_moderate_risk, "Trans Fat")
    excitotoxin_matches = precise_ingredient_matching(text, excitotoxin_high_risk + excitotoxin_moderate_risk, "Excitotoxin")
    corn_matches = precise_ingredient_matching(text, corn_high_risk + corn_moderate_risk, "Corn")
    sugar_high_matches = precise_ingredient_matching(text, sugar_high_risk, "High Risk Sugar")
    sugar_safe_matches = precise_ingredient_matching(text, sugar_safe, "Safe Sugar")
    gmo_matches = precise_ingredient_matching(text, gmo_keywords, "GMO")
    
    # Combine all detected ingredients
    all_detected = list(set(trans_fat_matches + excitotoxin_matches + corn_matches + 
                           sugar_high_matches + sugar_safe_matches + gmo_matches))
    
    result = {
        "trans_fat": list(set(trans_fat_matches)),
        "excitotoxins": list(set(excitotoxin_matches)),
        "corn": list(set(corn_matches)),
        "sugar": list(set(sugar_high_matches)),
        "sugar_safe": list(set(sugar_safe_matches)),
        "gmo": list(set(gmo_matches)),
        "all_detected": all_detected
    }
    
    print(f"DEBUG: PRECISE INGREDIENT MATCHING RESULTS:")
    for category, ingredients in result.items():
        if ingredients:
            print(f"  ✅ {category}: {ingredients}")
        else:
            print(f"  ❌ {category}: No matches")
    
    return result

def rate_ingredients_according_to_hierarchy(matches, text_quality):
    """
    Rating system following EXACT hierarchy rules from document:
    
    1. HIGH RISK TRANS FATS - ANY ONE = immediate danger
    2. HIGH RISK EXCITOTOXINS - ANY ONE = immediate danger  
    3. Count ALL other problematic ingredients (moderate trans fats, moderate excitotoxins, corn, sugar)
    4. If total count >= 3 = danger, if >= 1 = proceed carefully
    """
    
    print(f"DEBUG: Rating ingredients with text quality: {text_quality}")
    
    # If text quality is very poor, suggest trying again
    if text_quality == "very_poor":
        return "↪️ TRY AGAIN"
    
    # RULE 1: HIGH RISK TRANS FATS - ANY ONE = immediate danger
    high_risk_trans_fat_found = []
    for ingredient in matches["trans_fat"]:
        # Check against high risk trans fat list from scanner_config
        for high_risk_item in trans_fat_high_risk:
            if high_risk_item.lower() in ingredient.lower():
                high_risk_trans_fat_found.append(ingredient)
                print(f"🚨 HIGH RISK Trans Fat detected: {ingredient}")
                return "🚨 Oh NOOOO! Danger!"
    
    # RULE 2: HIGH RISK EXCITOTOXINS - ANY ONE = immediate danger  
    high_risk_excitotoxin_found = []
    for ingredient in matches["excitotoxins"]:
        # Check against high risk excitotoxin list from scanner_config
        for high_risk_item in excitotoxin_high_risk:
            if high_risk_item.lower() in ingredient.lower():
                high_risk_excitotoxin_found.append(ingredient)
                print(f"🚨 HIGH RISK Excitotoxin detected: {ingredient}")
                return "🚨 Oh NOOOO! Danger!"
    
    # RULE 3: COUNT ALL OTHER PROBLEMATIC INGREDIENTS
    total_problematic_count = 0
    
    # Count moderate trans fats (not already counted as high risk)
    moderate_trans_fat_count = 0
    for ingredient in matches["trans_fat"]:
        if ingredient not in high_risk_trans_fat_found:
            # Check if it's a moderate risk trans fat
            for moderate_item in trans_fat_moderate_risk:
                if moderate_item.lower() in ingredient.lower():
                    moderate_trans_fat_count += 1
                    print(f"⚠️ Moderate trans fat counted: {ingredient}")
                    break
    
    # Count moderate excitotoxins (not already counted as high risk)  
    moderate_excitotoxin_count = 0
    for ingredient in matches["excitotoxins"]:
        if ingredient not in high_risk_excitotoxin_found:
            # Check if it's a moderate risk excitotoxin
            for moderate_item in excitotoxin_moderate_risk:
                if moderate_item.lower() in ingredient.lower():
                    moderate_excitotoxin_count += 1
                    print(f"⚠️ Moderate excitotoxin counted: {ingredient}")
                    break
            # Also check low risk excitotoxins
            for low_item in excitotoxin_low_risk:
                if low_item.lower() in ingredient.lower():
                    moderate_excitotoxin_count += 1
                    print(f"⚠️ Low risk excitotoxin counted: {ingredient}")
                    break
    
    # Count ALL corn ingredients (as per document: all corn counts)
    corn_count = len(matches["corn"])
    
    # Count ALL sugar ingredients (only high risk sugars count as problematic)  
    sugar_count = len(matches["sugar"])  # Only high risk sugars
    
    # Calculate total problematic count
    total_problematic_count = moderate_trans_fat_count + moderate_excitotoxin_count + corn_count + sugar_count
    
    print(f"⚖️ TOTAL PROBLEMATIC COUNT: {total_problematic_count}")
    print(f"   - Moderate trans fats: {moderate_trans_fat_count}")
    print(f"   - Moderate excitotoxins: {moderate_excitotoxin_count}")
    print(f"   - Corn ingredients: {corn_count}")
    print(f"   - Sugar ingredients: {sugar_count}")
    
    # RULE 4: Apply hierarchy rules per document
    # "Per category: if 1-2 stays Proceed Carefully, if 3-4 in food = Oh NOOO! Danger!"
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
    """Create standardized error result"""
    return {
        "rating": "↪️ TRY AGAIN",
        "matched_ingredients": {
            "trans_fat": [], "excitotoxins": [], "corn": [], 
            "sugar": [], "sugar_safe": [], "gmo": [], "all_detected": []
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
        'sugar_safe': '✅',
        'gmo': '👽',
        'all_detected': '📋'
    }
    return emoji_map.get(category, '📝')

# Additional utility function for backwards compatibility
def analyze_ingredients(text):
    """Wrapper function for backwards compatibility"""
    return match_all_ingredients(text)
