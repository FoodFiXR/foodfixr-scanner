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

# Professional tier detection
PROFESSIONAL_TIER = os.getenv('RENDER_TIER') == 'professional' or int(os.getenv('WEB_CONCURRENCY', '1')) > 1

if PROFESSIONAL_TIER:
    print("✅ PROFESSIONAL TIER DETECTED in ingredient_scanner - Using enhanced thresholds")
    MEMORY_THRESHOLD = 2000  # 2GB
    COMPRESSION_THRESHOLD = 1000  # 1MB
else:
    print("ℹ️ Free tier detected - Using conservative thresholds")
    MEMORY_THRESHOLD = 120   # 120MB
    COMPRESSION_THRESHOLD = 300  # 300KB

# Enhanced memory monitoring function
def log_memory_usage(stage="", force_gc=False):
    """Enhanced memory monitoring with professional tier support"""
    try:
        if force_gc:
            iterations = 2 if PROFESSIONAL_TIER else 3
            for _ in range(iterations):
                gc.collect()
            time.sleep(0.05 if PROFESSIONAL_TIER else 0.1)
        
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        print(f"DEBUG: Memory usage {stage}: {memory_mb:.1f} MB")
        
        # Use tier-appropriate threshold
        threshold = MEMORY_THRESHOLD
        if memory_mb > threshold:
            print(f"DEBUG: High memory usage! Forcing cleanup...")
            for _ in range(3):
                gc.collect()
            time.sleep(0.1)
            
            memory_mb = process.memory_info().rss / 1024 / 1024
            print(f"DEBUG: Memory after cleanup: {memory_mb:.1f} MB")
            
        return memory_mb
    except Exception as e:
        print(f"DEBUG: Memory monitoring error: {e}")
        return 0

def aggressive_cleanup():
    """Ultra-aggressive memory cleanup"""
    try:
        # Force multiple garbage collection cycles
        iterations = 3 if PROFESSIONAL_TIER else 5
        for _ in range(iterations):
            gc.collect()
        
        # Clear PIL cache
        max_pixels = 50000000 if PROFESSIONAL_TIER else 30000000
        Image.MAX_IMAGE_PIXELS = max_pixels
        
        # Force Python to release memory back to OS (if possible)
        if hasattr(gc, 'set_threshold'):
            gc.set_threshold(0, 0, 0)  # Disable automatic GC temporarily
            gc.collect()
            gc.set_threshold(700, 10, 10)  # Re-enable with aggressive settings
        
        print("DEBUG: Aggressive cleanup completed")
    except Exception as e:
        print(f"DEBUG: Cleanup error: {e}")

def ultra_minimal_compress(image_path, max_size_kb=None):
    """Ultra-minimal compression with tier-appropriate settings"""
    if max_size_kb is None:
        max_size_kb = 500 if PROFESSIONAL_TIER else 60
        
    log_memory_usage("before ultra minimal", force_gc=True)
    
    temp_path = None
    img = None
    
    try:
        current_size_kb = os.path.getsize(image_path) / 1024
        print(f"DEBUG: Ultra minimal - current size: {current_size_kb:.1f} KB")
        
        if current_size_kb <= max_size_kb:
            print("DEBUG: Size OK, no compression needed")
            return image_path
        
        temp_dir = tempfile.gettempdir()
        prefix = "pro_ultra" if PROFESSIONAL_TIER else "ultra"
        temp_path = os.path.join(temp_dir, f"{prefix}_compressed_{int(time.time())}.jpg")
        
        with Image.open(image_path) as img:
            width, height = img.size
            mode = img.mode
            
            print(f"DEBUG: Original: {width}x{height}, mode: {mode}")
            
            # Tier-appropriate downsizing
            if PROFESSIONAL_TIER:
                max_dim = min(600, max(width, height) // 3)
                min_width, min_height = 300, 200
            else:
                max_dim = min(300, max(width, height) // 4)
                min_width, min_height = 150, 100
            
            if width > height:
                new_width = max_dim
                new_height = int(height * max_dim / width)
            else:
                new_height = max_dim
                new_width = int(width * max_dim / height)
            
            new_width = max(new_width, min_width)
            new_height = max(new_height, min_height)
            
            print(f"DEBUG: Target size: {new_width}x{new_height}")
            
            # Convert mode if necessary
            if mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
                log_memory_usage("after mode conversion")
            
            # Single resize operation
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Clear original reference
            img.close()
            del img
            img = None
            gc.collect()
            log_memory_usage("after resize")
            
            # Tier-appropriate quality levels
            if PROFESSIONAL_TIER:
                quality_levels = [25, 20, 15, 12, 10]
            else:
                quality_levels = [15, 12, 10, 8]
            
            for quality in quality_levels:
                img_resized.save(temp_path, 'JPEG', quality=quality, optimize=True, progressive=False)
                
                result_size_kb = os.path.getsize(temp_path) / 1024
                print(f"DEBUG: Ultra quality {quality}: {result_size_kb:.1f} KB")
                
                if result_size_kb <= max_size_kb:
                    print(f"✅ Ultra success at quality {quality}: {result_size_kb:.1f} KB")
                    img_resized.close()
                    del img_resized
                    gc.collect()
                    return temp_path
            
            # Final attempt with lowest quality
            img_resized.save(temp_path, 'JPEG', quality=5, optimize=True, progressive=False)
            result_size_kb = os.path.getsize(temp_path) / 1024
            print(f"DEBUG: Final result: {result_size_kb:.1f} KB")
            
            img_resized.close()
            del img_resized
            gc.collect()
            
            return temp_path
            
    except Exception as e:
        print(f"DEBUG: Ultra minimal compression failed: {e}")
        
        # Emergency cleanup
        if img:
            try:
                img.close()
            except:
                pass
        
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        
        gc.collect()
        return image_path
    
    finally:
        if img:
            try:
                img.close()
            except:
                pass
        gc.collect()
        log_memory_usage("end ultra minimal", force_gc=True)

def compress_image_for_ocr(image_path, max_size_kb=None):
    """Tier-appropriate image compression for OCR"""
    if max_size_kb is None:
        max_size_kb = 500 if PROFESSIONAL_TIER else 80
        
    print(f"DEBUG: {'Professional' if PROFESSIONAL_TIER else 'Standard'} tier compression for {image_path}")
    log_memory_usage("start compression", force_gc=True)
    
    try:
        # Quick size check
        current_size_kb = os.path.getsize(image_path) / 1024
        print(f"DEBUG: Current size: {current_size_kb:.1f} KB, target: {max_size_kb} KB")
        
        if current_size_kb <= max_size_kb:
            print("DEBUG: Size acceptable, no compression needed")
            return image_path
        
        # Tier-appropriate threshold for ultra-minimal compression
        ultra_threshold = COMPRESSION_THRESHOLD
        if current_size_kb > ultra_threshold:
            print(f"DEBUG: Large file detected ({current_size_kb:.1f}KB > {ultra_threshold}KB), using ultra-minimal compression")
            return ultra_minimal_compress(image_path, max_size_kb)
        
        # Standard compression with tier-appropriate settings
        prefix = "pro" if PROFESSIONAL_TIER else "std"
        temp_path = os.path.join(tempfile.gettempdir(), f"{prefix}_compressed_{int(time.time())}.jpg")
        
        try:
            with Image.open(image_path) as original:
                width, height = original.size
                
                # Tier-appropriate scaling
                scale_factor_exp = 0.3 if PROFESSIONAL_TIER else 0.4
                scale_factor = min(1.0, (max_size_kb / current_size_kb) ** scale_factor_exp)
                
                if PROFESSIONAL_TIER:
                    target_width = max(int(width * scale_factor), 400)
                    target_height = max(int(height * scale_factor), 300)
                else:
                    target_width = max(int(width * scale_factor), 200)
                    target_height = max(int(height * scale_factor), 150)
                
                print(f"DEBUG: Scaling {width}x{height} -> {target_width}x{target_height}")
                
                # Convert mode if necessary
                if original.mode in ('RGBA', 'LA', 'P'):
                    original = original.convert('RGB')
                
                # Resize with quality preservation
                resized = original.resize((target_width, target_height), Image.Resampling.LANCZOS)
                
                # Force cleanup
                original.close()
                gc.collect()
                log_memory_usage("after resize")
                
                # Tier-appropriate quality levels
                if PROFESSIONAL_TIER:
                    quality_levels = [70, 60, 50, 40, 30, 25, 20]
                else:
                    quality_levels = [30, 25, 20, 15, 12]
                
                for quality in quality_levels:
                    resized.save(temp_path, 'JPEG', quality=quality, optimize=True)
                    
                    result_size_kb = os.path.getsize(temp_path) / 1024
                    print(f"DEBUG: Quality {quality}: {result_size_kb:.1f} KB")
                    
                    if result_size_kb <= max_size_kb:
                        print(f"✅ Compression success at quality {quality}: {result_size_kb:.1f} KB")
                        resized.close()
                        gc.collect()
                        return temp_path
                
                # If standard compression fails, try ultra-minimal
                resized.close()
                gc.collect()
                
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
                print("DEBUG: Standard compression failed, trying ultra-minimal")
                return ultra_minimal_compress(image_path, max_size_kb)
                
        except Exception as e:
            print(f"DEBUG: Compression error: {e}")
            gc.collect()
            
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            
            return ultra_minimal_compress(image_path, max_size_kb)
    
    except Exception as e:
        print(f"DEBUG: Compression completely failed: {e}")
        gc.collect()
        return image_path
    
    finally:
        gc.collect()
        log_memory_usage("end compression", force_gc=True)

def safe_ocr_with_fallback(image_path, max_attempts=None):
    """Safe OCR with circuit breaker - tier appropriate"""
    if max_attempts is None:
        max_attempts = 3 if PROFESSIONAL_TIER else 2
        
    print(f"DEBUG: Starting {'professional' if PROFESSIONAL_TIER else 'standard'} OCR with {max_attempts} attempts")
    
    for attempt in range(max_attempts):
        try:
            print(f"DEBUG: OCR attempt {attempt + 1}/{max_attempts}")
            
            # Tier-appropriate memory check
            memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
            memory_limit = 1500 if PROFESSIONAL_TIER else 150
            
            if memory_mb > memory_limit:
                print(f"DEBUG: High memory usage ({memory_mb:.1f}MB), forcing cleanup")
                aggressive_cleanup()
                time.sleep(0.5)
                
                # Check again after cleanup
                memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
                critical_limit = 2000 if PROFESSIONAL_TIER else 200
                
                if memory_mb > critical_limit:
                    print(f"DEBUG: Memory still very high ({memory_mb:.1f}MB), skipping attempt")
                    if attempt == max_attempts - 1:
                        return ""
                    continue
            
            # OCR with tier-appropriate timeout
            import signal
            
            def ocr_timeout_handler(signum, frame):
                raise TimeoutError("OCR timeout")
            
            old_handler = signal.signal(signal.SIGALRM, ocr_timeout_handler)
            timeout_seconds = 90 if PROFESSIONAL_TIER else 45
            signal.alarm(timeout_seconds)
            
            try:
                result = extract_text_ocr_space(image_path)
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
                
                if result and len(result.strip()) > 3:
                    print(f"DEBUG: OCR successful on attempt {attempt + 1}")
                    return result
                else:
                    print(f"DEBUG: OCR returned empty result on attempt {attempt + 1}")
                    
            except TimeoutError:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
                print(f"DEBUG: OCR timed out on attempt {attempt + 1}")
                aggressive_cleanup()
                
                if attempt == max_attempts - 1:
                    return ""
                continue
                
        except Exception as e:
            print(f"DEBUG: OCR attempt {attempt + 1} failed: {e}")
            aggressive_cleanup()
            
            if attempt == max_attempts - 1:
                print("DEBUG: All OCR attempts failed")
                return ""
            
            wait_time = 1 if PROFESSIONAL_TIER else 2
            time.sleep(wait_time)
    
    return ""

def extract_text_with_multiple_methods(image_path):
    """Main text extraction with tier-appropriate methods"""
    try:
        print(f"DEBUG: Starting {'professional' if PROFESSIONAL_TIER else 'standard'} OCR text extraction from {image_path}")
        
        # Tier-appropriate cleanup
        aggressive_cleanup()
        
        # Try safe OCR with circuit breaker
        text = safe_ocr_with_fallback(image_path)
        
        if text and len(text.strip()) > 5:
            print(f"DEBUG: OCR successful - extracted {len(text)} characters")
            return text
        
        # If OCR fails, try fallback
        print("DEBUG: OCR failed, trying fallback...")
        return extract_text_pytesseract_fallback(image_path)
        
    except Exception as e:
        print(f"DEBUG: All OCR methods failed: {e}")
        aggressive_cleanup()
        return ""

def extract_text_ocr_space(image_path):
    """OCR.space extraction with tier-appropriate settings"""
    log_memory_usage("start OCR", force_gc=True)
    
    processed_image_path = None
    response = None
    
    try:
        # Use tier-appropriate compression
        max_kb = 500 if PROFESSIONAL_TIER else 80
        processed_image_path = compress_image_for_ocr(image_path, max_size_kb=max_kb)
        log_memory_usage("after compression", force_gc=True)
        
        api_url = 'https://api.ocr.space/parse/image'
        api_key = os.getenv('OCR_SPACE_API_KEY', 'helloworld')
        
        print(f"DEBUG: Using compressed image: {processed_image_path}")
        final_size = os.path.getsize(processed_image_path) / 1024
        print(f"DEBUG: Final size: {final_size:.1f} KB")
        
        # Enhanced request data
        data = {
            'apikey': api_key,
            'language': 'eng',
            'isOverlayRequired': False,
            'detectOrientation': True,
            'scale': True,
            'OCREngine': 2,
            'isTable': False,
            'isSearchablePdfHideTextLayer': False
        }
        
        # Make API request with tier-appropriate timeout
        timeout = 30 if PROFESSIONAL_TIER else 20
        with open(processed_image_path, 'rb') as f:
            files = {'file': f}
            print("DEBUG: Sending to OCR.space API...")
            
            try:
                response = requests.post(api_url, files=files, data=data, timeout=timeout)
                log_memory_usage("after API call")
            except requests.exceptions.Timeout:
                print("DEBUG: OCR API timeout")
                return ""
            except Exception as api_error:
                print(f"DEBUG: OCR API error: {api_error}")
                return ""
        
        # Process response
        if response and response.status_code == 200:
            try:
                result = response.json()
                extracted_text = parse_ocr_space_response(result)
                
                # Clear response
                response.close() if hasattr(response, 'close') else None
                del response
                response = None
                gc.collect()
                
                return extracted_text
                
            except Exception as parse_error:
                print(f"DEBUG: Response parsing error: {parse_error}")
                return ""
        else:
            if response:
                print(f"DEBUG: OCR API returned status {response.status_code}")
            return ""
            
    except Exception as e:
        print(f"DEBUG: OCR extraction failed: {e}")
        return ""
    
    finally:
        # Cleanup
        if response:
            try:
                response.close() if hasattr(response, 'close') else None
                del response
            except:
                pass
        
        # Clean up compressed file
        if processed_image_path and processed_image_path != image_path:
            try:
                os.remove(processed_image_path)
                print("DEBUG: Cleaned up compressed image")
            except Exception as cleanup_error:
                print(f"DEBUG: Cleanup error: {cleanup_error}")
        
        # Force garbage collection
        aggressive_cleanup()
        log_memory_usage("end OCR", force_gc=True)

def extract_text_ocr_space_enhanced(image_path):
    """Enhanced OCR.space with alternative settings"""
    try:
        aggressive_cleanup()
        
        processed_image_path = compress_image_for_ocr(image_path, max_size_kb=80)
        aggressive_cleanup()
        
        api_url = 'https://api.ocr.space/parse/image'
        api_key = os.getenv('OCR_SPACE_API_KEY', 'helloworld')
        
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
                    'OCREngine': 1,  # Try engine 1 for difficult images
                    'isTable': True,
                    'isSearchablePdfHideTextLayer': False
                }
                
                print("DEBUG: Sending to OCR.space API (enhanced)...")
                response = requests.post(api_url, files=files, data=data, timeout=20)
        
        except Exception as e:
            print(f"DEBUG: Enhanced OCR API call failed: {e}")
            return ""
        finally:
            if processed_image_path != image_path:
                try:
                    os.remove(processed_image_path)
                except:
                    pass
            aggressive_cleanup()
        
        if response and response.status_code == 200:
            result = response.json()
            extracted_text = parse_ocr_space_response(result)
            
            response.close() if hasattr(response, 'close') else None
            del response
            aggressive_cleanup()
            
            return extracted_text
        else:
            if response:
                print(f"DEBUG: Enhanced OCR API returned status {response.status_code}")
            return ""
            
    except Exception as e:
        print(f"DEBUG: Enhanced OCR method failed: {e}")
        aggressive_cleanup()
        return ""

def process_request_with_memory_management():
    """Pre-request memory management"""
    try:
        print("DEBUG: Pre-request memory management")
        log_memory_usage("pre-request", force_gc=True)
        
        temp_dir = tempfile.gettempdir()
        current_time = time.time()
        
        cleaned_count = 0
        for filename in os.listdir(temp_dir):
            if ('compressed' in filename or 'ocr_' in filename or 'ultra_' in filename) and filename.endswith('.jpg'):
                filepath = os.path.join(temp_dir, filename)
                try:
                    if os.path.isfile(filepath):
                        max_age = 30 if PROFESSIONAL_TIER else 60
                        file_age = current_time - os.path.getmtime(filepath)
                        if file_age > max_age:
                            os.remove(filepath)
                            cleaned_count += 1
                except Exception as e:
                    print(f"DEBUG: Temp file cleanup error: {e}")
        
        if cleaned_count > 0:
            print(f"DEBUG: Cleaned up {cleaned_count} old temp files")
        
        log_memory_usage("post-cleanup", force_gc=True)
        
    except Exception as e:
        print(f"DEBUG: Request memory management error: {e}")

def before_scan_cleanup():
    """Pre-scan cleanup with tier-appropriate settings"""
    process_request_with_memory_management()
    
    # Set tier-appropriate PIL limits
    max_pixels = 50000000 if PROFESSIONAL_TIER else 30000000
    Image.MAX_IMAGE_PIXELS = max_pixels
    
    # Force Python to be more aggressive with memory
    import sys
    if hasattr(sys, 'setswitchinterval'):
        interval = 0.001 if PROFESSIONAL_TIER else 0.005
        sys.setswitchinterval(interval)
    
    aggressive_cleanup()

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
        
        first_result = parsed_results[0]
        print(f"DEBUG: First result keys: {list(first_result.keys())}")
        
        extracted_text = first_result.get('ParsedText', '')
        
        if extracted_text and len(extracted_text.strip()) > 0:
            cleaned_text = extracted_text.replace('\r', ' ').replace('\n', ' ')
            cleaned_text = ' '.join(cleaned_text.split())
            
            print(f"DEBUG: OCR.space extracted {len(cleaned_text)} characters")
            print(f"DEBUG: Raw text preview: {cleaned_text[:300]}...")
            return cleaned_text
        else:
            print("DEBUG: OCR.space returned empty text")
            if 'ErrorMessage' in first_result:
                print(f"DEBUG: ParsedResult error: {first_result['ErrorMessage']}")
            return ""
            
    except Exception as e:
        print(f"DEBUG: Error parsing OCR.space response: {e}")
        print(f"DEBUG: Raw response: {result}")
        return ""

def extract_text_pytesseract_fallback(image_path):
    """Pytesseract fallback with memory management"""
    try:
        print("DEBUG: Attempting pytesseract fallback...")
        import pytesseract
        from PIL import Image
        
        aggressive_cleanup()
        
        image = Image.open(image_path)
        
        if image.mode != 'L':
            image = image.convert('L')
            
        text = pytesseract.image_to_string(image, config='--psm 6')
        
        image.close()
        del image
        aggressive_cleanup()
        
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
        aggressive_cleanup()
        return ""

def normalize_ingredient_text(text):
    """CONSERVATIVE text normalization - only fix obvious OCR errors"""
    if not text:
        return ""
    
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s\-\(\),.]', ' ', text)
    
    obvious_corrections = {
        'rn': 'm',
        'cornsynup': 'corn syrup',
        'com syrup': 'corn syrup',
        'hfc5': 'hfcs',
        'naturalflavors': 'natural flavors',
        'naturalflavor': 'natural flavor',
        'soylecithin': 'soy lecithin',
        'monosodiumglutamate': 'monosodium glutamate',
        'highfructose': 'high fructose',
        'vegetableoil': 'vegetable oil',
    }
    
    for wrong, correct in obvious_corrections.items():
        text = text.replace(wrong, correct)
    
    return text

def check_for_safety_labels(text):
    """Check for explicit safety labels that override ingredient concerns"""
    if not text:
        return False
    
    normalized_text = normalize_ingredient_text(text)
    print(f"DEBUG: Checking for safety labels in text: {normalized_text[:200]}...")
    
    safety_patterns = [
        r'\bno\s+msg\b', r'\bno\s+msg\s+added\b', r'\bmsg\s+free\b',
        r'\bwithout\s+msg\b', r'\bno\s+artificial\s+msg\b', r'\bno\s+added\s+msg\b',
        r'\bnon\s*gmo\b', r'\bnon\s*-\s*gmo\b', r'\bgmo\s+free\b',
        r'\bwithout\s+gmo\b', r'\bno\s+gmo\b', r'\bnon\s+genetically\s+modified\b',
        r'\bmsg\s*free\b', r'\bgmo\s*free\b', r'\bnon\s*gmo\s+natural\b',
        r'\bnatural\s+non\s*gmo\b', r'\bno\s+monosodium\s+glutamate\b',
    ]
    
    for pattern in safety_patterns:
        matches = re.findall(pattern, normalized_text, re.IGNORECASE)
        if matches:
            print(f"DEBUG: ✅ SAFETY LABEL FOUND: Pattern '{pattern}' matched: {matches}")
            return True
    
    safety_phrases = [
        "no msg added", "msg free", "non gmo", "non-gmo", "gmo free", "no gmo",
        "without msg", "without gmo", "non genetically modified", "no monosodium glutamate"
    ]
    
    for phrase in safety_phrases:
        flexible_text = re.sub(r'[\s\-_]+', '', normalized_text)
        flexible_phrase = re.sub(r'[\s\-_]+', '', phrase)
        
        if flexible_phrase in flexible_text:
            print(f"DEBUG: ✅ SAFETY PHRASE FOUND (flexible): '{phrase}' found in text")
            return True
    
    print("DEBUG: ❌ No safety labels found")
    return False

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
        
        # Strategy 1: EXACT word boundary match
        pattern = r'\b' + re.escape(normalized_ingredient) + r'\b'
        if re.search(pattern, normalized_text):
            matches.append(ingredient)
            print(f"DEBUG: ✅ EXACT WORD MATCH: '{normalized_ingredient}' -> '{ingredient}'")
            continue
        
        # Strategy 2: Multi-word ingredients
        if ' ' in normalized_ingredient:
            words = normalized_ingredient.split()
            if len(words) >= 2:
                all_word_positions = []
                all_words_found = True
                
                for word in words:
                    if len(word) <= 2:
                        continue
                    word_pattern = r'\b' + re.escape(word) + r'\b'
                    matches_found = list(re.finditer(word_pattern, normalized_text))
                    if matches_found:
                        all_word_positions.extend([m.start() for m in matches_found])
                    else:
                        all_words_found = False
                        break
                
                if all_words_found and all_word_positions:
                    min_pos = min(all_word_positions)
                    max_pos = max(all_word_positions)
                    if max_pos - min_pos <= 50:
                        matches.append(ingredient)
                        print(f"DEBUG: ✅ MULTI-WORD MATCH: '{normalized_ingredient}' -> '{ingredient}'")
                        continue
        
        # Strategy 3: Single critical ingredients
        if (' ' not in normalized_ingredient and 
            len(normalized_ingredient) > 5 and
            normalized_ingredient in normalized_text):
            
            for match in re.finditer(re.escape(normalized_ingredient), normalized_text):
                start, end = match.span()
                
                char_before = normalized_text[start-1] if start > 0 else ' '
                char_after = normalized_text[end] if end < len(normalized_text) else ' '
                
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
    
    words = re.findall(r'\b[a-zA-Z]{2,}\b', text)
    
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
            "all_detected": [],
            "has_safety_labels": False
        }
    
    print(f"DEBUG: Matching ingredients in text of {len(text)} characters")
    print(f"DEBUG: Text sample: {text[:200]}...")
    
    has_safety_labels = check_for_safety_labels(text)
    
    trans_fat_matches = precise_ingredient_matching(text, trans_fat_high_risk + trans_fat_moderate_risk, "Trans Fat")
    excitotoxin_matches = precise_ingredient_matching(text, excitotoxin_high_risk + excitotoxin_moderate_risk, "Excitotoxin")
    corn_matches = precise_ingredient_matching(text, corn_high_risk + corn_moderate_risk, "Corn")
    sugar_high_matches = precise_ingredient_matching(text, sugar_high_risk, "High Risk Sugar")
    sugar_safe_matches = precise_ingredient_matching(text, sugar_safe, "Safe Sugar")
    gmo_matches = precise_ingredient_matching(text, gmo_keywords, "GMO")
    
    all_detected = list(set(trans_fat_matches + excitotoxin_matches + corn_matches + 
                           sugar_high_matches + sugar_safe_matches + gmo_matches))
    
    result = {
        "trans_fat": list(set(trans_fat_matches)),
        "excitotoxins": list(set(excitotoxin_matches)),
        "corn": list(set(corn_matches)),
        "sugar": list(set(sugar_high_matches)),
        "sugar_safe": list(set(sugar_safe_matches)),
        "gmo": list(set(gmo_matches)),
        "all_detected": all_detected,
        "has_safety_labels": has_safety_labels
    }
    
    print(f"DEBUG: PRECISE INGREDIENT MATCHING RESULTS:")
    if has_safety_labels:
        print(f"  🛡️ SAFETY LABELS: Found safety labels (no msg, non-gmo, etc.)")
    for category, ingredients in result.items():
        if category == "has_safety_labels":
            continue
        if ingredients:
            print(f"  ✅ {category}: {ingredients}")
        else:
            print(f"  ❌ {category}: No matches")
    
    return result

def rate_ingredients_according_to_hierarchy(matches, text_quality):
    """Rating system with safety label override"""
    
    print(f"DEBUG: Rating ingredients with text quality: {text_quality}")
    
    if text_quality == "very_poor":
        return "↪️ TRY AGAIN"
    
    # SAFETY LABELS OVERRIDE
    if matches.get("has_safety_labels", False):
        print(f"🛡️ SAFETY LABELS DETECTED - OVERRIDING TO SAFE!")
        print(f"   Product explicitly states 'no msg', 'non-gmo', or similar safety claims")
        return "✅ Yay! Safe!"
    
    # HIGH RISK TRANS FATS
    high_risk_trans_fat_found = []
    for ingredient in matches["trans_fat"]:
        for high_risk_item in trans_fat_high_risk:
            if high_risk_item.lower() in ingredient.lower():
                high_risk_trans_fat_found.append(ingredient)
                print(f"🚨 HIGH RISK Trans Fat detected: {ingredient}")
                return "🚨 Oh NOOOO! Danger!"
    
    # HIGH RISK EXCITOTOXINS
    high_risk_excitotoxin_found = []
    for ingredient in matches["excitotoxins"]:
        for high_risk_item in excitotoxin_high_risk:
            if high_risk_item.lower() in ingredient.lower():
                high_risk_excitotoxin_found.append(ingredient)
                print(f"🚨 HIGH RISK Excitotoxin detected: {ingredient}")
                return "🚨 Oh NOOOO! Danger!"
    
    # COUNT PROBLEMATIC INGREDIENTS
    total_problematic_count = 0
    
    moderate_trans_fat_count = 0
    for ingredient in matches["trans_fat"]:
        if ingredient not in high_risk_trans_fat_found:
            for moderate_item in trans_fat_moderate_risk:
                if moderate_item.lower() in ingredient.lower():
                    moderate_trans_fat_count += 1
                    print(f"⚠️ Moderate trans fat counted: {ingredient}")
                    break
    
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
    
    corn_count = len(matches["corn"])
    sugar_count = len(matches["sugar"])
    
    total_problematic_count = moderate_trans_fat_count + moderate_excitotoxin_count + corn_count + sugar_count
    
    print(f"⚖️ TOTAL PROBLEMATIC COUNT: {total_problematic_count}")
    print(f"   - Moderate trans fats: {moderate_trans_fat_count}")
    print(f"   - Moderate excitotoxins: {moderate_excitotoxin_count}")
    print(f"   - Corn ingredients: {corn_count}")
    print(f"   - Sugar ingredients: {sugar_count}")
    
    if total_problematic_count >= 3:
        return "🚨 Oh NOOOO! Danger!"
    elif total_problematic_count >= 1:
        return "⚠️ Proceed carefully"
    
    if len(matches["all_detected"]) > 0:
        return "✅ Yay! Safe!"
    
    if text_quality in ["poor", "fair"]:
        return "↪️ TRY AGAIN"
    
    return "✅ Yay! Safe!"

def scan_image_for_ingredients(image_path):
    """Main scanning function with comprehensive memory management and error handling"""
    try:
        before_scan_cleanup()
        
        print(f"\n{'='*80}")
        print(f"🔬 STARTING {'PROFESSIONAL' if PROFESSIONAL_TIER else 'STANDARD'} TIER SCAN: {image_path}")
        print(f"{'='*80}")
        print(f"DEBUG: File exists: {os.path.exists(image_path)}")
        
        initial_memory = log_memory_usage("scan start", force_gc=True)
        
        memory_warning_threshold = 1500 if PROFESSIONAL_TIER else 150
        if initial_memory > memory_warning_threshold:
            print(f"WARNING: High initial memory {initial_memory:.1f}MB - may cause issues")
            aggressive_cleanup()
            time.sleep(0.5)
        
        print("🔍 Starting tier-appropriate OCR text extraction...")
        text = extract_text_with_multiple_methods(image_path)
        print(f"📝 Extracted text length: {len(text)} characters")
        
        if text:
            print(f"📋 EXTRACTED TEXT:\n{text}")
        else:
            print("❌ No text extracted!")
        
        text_quality = assess_text_quality_enhanced(text)
        print(f"📊 Text quality assessment: {text_quality}")
        
        print("🧬 Starting PRECISE ingredient matching...")
        matches = match_all_ingredients(text)
        
        print("⚖️ Applying hierarchy-based rating with safety label override...")
        rating = rate_ingredients_according_to_hierarchy(matches, text_quality)
        print(f"🏆 Final rating: {rating}")
        
        confidence = determine_confidence(text_quality, text, matches)
        
        gmo_alert = None
        if matches["gmo"] and not matches.get("has_safety_labels", False):
            gmo_alert = "📣 GMO Alert!"
        
        result = {
            "rating": rating,
            "matched_ingredients": matches,
            "confidence": confidence,
            "extracted_text_length": len(text),
            "text_quality": text_quality,
            "extracted_text": text,
            "gmo_alert": gmo_alert,
            "has_safety_labels": matches.get("has_safety_labels", False)
        }
        
        print_scan_summary(result)
        
        aggressive_cleanup()
        final_memory = log_memory_usage("scan end", force_gc=True)
        print(f"DEBUG: Memory change: {initial_memory:.1f}MB -> {final_memory:.1f}MB")
        
        return result
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR in scan_image_for_ingredients: {e}")
        import traceback
        traceback.print_exc()
        
        aggressive_cleanup()
        
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
            "sugar": [], "sugar_safe": [], "gmo": [], "all_detected": [],
            "has_safety_labels": False
        },
        "confidence": "very_low",
        "text_quality": "very_poor",
        "extracted_text_length": 0,
        "gmo_alert": None,
        "has_safety_labels": False,
        "error": error_message
    }

def print_scan_summary(result):
    """Print comprehensive scan summary"""
    print(f"\n{'🎯 SCAN SUMMARY':=^80}")
    print(f"🏆 FINAL RATING: {result['rating']}")
    print(f"🎯 Confidence: {result['confidence']}")
    print(f"📊 Text Quality: {result['text_quality']}")
    print(f"📝 Text Length: {result['extracted_text_length']} characters")
    
    if result.get('has_safety_labels', False):
        print(f"🛡️ SAFETY LABELS DETECTED: Product claims to be safe (no msg, non-gmo, etc.)")
    
    if result['gmo_alert']:
        print(f"📣 {result['gmo_alert']}")
    
    print(f"\n🧬 DETECTED INGREDIENTS BY CATEGORY:")
    for category, ingredients in result['matched_ingredients'].items():
        if category == "has_safety_labels":
            continue
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

# Tier detection and function selection
def get_compression_function():
    """Return appropriate compression function based on tier"""
    return compress_image_for_ocr

def get_ocr_function():
    """Return appropriate OCR function based on tier"""
    return extract_text_with_multiple_methods

# Professional tier function aliases for compatibility
def compress_image_for_ocr_professional(image_path, max_size_kb=500):
    return compress_image_for_ocr(image_path, max_size_kb)

def ultra_minimal_compress_professional(image_path, max_size_kb=500):
    return ultra_minimal_compress(image_path, max_size_kb)

def extract_text_ocr_space_professional(image_path):
    return extract_text_ocr_space(image_path)

def safe_ocr_with_fallback_professional(image_path, max_attempts=3):
    return safe_ocr_with_fallback(image_path, max_attempts)

def extract_text_with_multiple_methods_professional(image_path):
    return extract_text_with_multiple_methods(image_path)

# Logging
if PROFESSIONAL_TIER:
    print("✅ PROFESSIONAL TIER DETECTED - Using enhanced functions")
    print(f"   - Memory threshold: {MEMORY_THRESHOLD}MB")
    print(f"   - Compression threshold: {COMPRESSION_THRESHOLD}KB")
else:
    print("ℹ️ Free tier detected - Using standard functions")
    print(f"   - Memory threshold: {MEMORY_THRESHOLD}MB")
    print(f"   - Compression threshold: {COMPRESSION_THRESHOLD}KB")

# Backwards compatibility
def analyze_ingredients(text):
    """Wrapper function for backwards compatibility"""
    return match_all_ingredients(text)
