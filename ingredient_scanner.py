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

# Enhanced memory monitoring function
def log_memory_usage(stage="", force_gc=False):
    """Enhanced memory monitoring with optional garbage collection"""
    try:
        if force_gc:
            # Force multiple GC cycles before measuring
            for _ in range(3):
                gc.collect()
            time.sleep(0.1)  # Allow cleanup to complete
        
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        print(f"DEBUG: Memory usage {stage}: {memory_mb:.1f} MB")
        
        # Critical memory threshold - force cleanup if too high
        if memory_mb > 120:  # Lowered threshold for memory-constrained environments
            print(f"DEBUG: CRITICAL memory usage! Forcing aggressive cleanup...")
            for _ in range(5):
                gc.collect()
            time.sleep(0.2)
            
            # Re-measure after cleanup
            memory_mb = process.memory_info().rss / 1024 / 1024
            print(f"DEBUG: Memory after emergency cleanup: {memory_mb:.1f} MB")
            
        return memory_mb
    except Exception as e:
        print(f"DEBUG: Memory monitoring error: {e}")
        return 0

def aggressive_cleanup():
    """Ultra-aggressive memory cleanup"""
    try:
        # Force multiple garbage collection cycles
        for _ in range(5):  # Increased from 3
            gc.collect()
        
        # Clear PIL cache
        Image.MAX_IMAGE_PIXELS = 30000000  # Set conservative limit
        
        # Force Python to release memory back to OS (if possible)
        if hasattr(gc, 'set_threshold'):
            gc.set_threshold(0, 0, 0)  # Disable automatic GC temporarily
            gc.collect()
            gc.set_threshold(700, 10, 10)  # Re-enable with aggressive settings
        
        print("DEBUG: Aggressive cleanup completed")
    except Exception as e:
        print(f"DEBUG: Cleanup error: {e}")

def ultra_minimal_compress(image_path, max_size_kb=60):
    """Ultra-minimal memory footprint compression for emergency situations"""
    log_memory_usage("before ultra minimal", force_gc=True)
    
    temp_path = None
    img = None
    
    try:
        # Check if compression is even needed
        current_size_kb = os.path.getsize(image_path) / 1024
        print(f"DEBUG: Ultra minimal - current size: {current_size_kb:.1f} KB")
        
        if current_size_kb <= max_size_kb:
            print("DEBUG: Size OK, no compression needed")
            return image_path
        
        # Create temp file
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"ultra_compressed_{int(time.time())}.jpg")
        
        # Single-pass processing with minimal memory
        with Image.open(image_path) as img:
            # Get dimensions without loading full image into memory
            width, height = img.size
            mode = img.mode
            
            print(f"DEBUG: Original: {width}x{height}, mode: {mode}")
            
            # Calculate target size very aggressively for memory-constrained environments
            max_dim = min(300, max(width, height) // 4)  # Very aggressive downsizing
            if width > height:
                new_width = max_dim
                new_height = int(height * max_dim / width)
            else:
                new_height = max_dim
                new_width = int(width * max_dim / height)
            
            # Ensure minimum readable size for OCR
            new_width = max(new_width, 150)
            new_height = max(new_height, 100)
            
            print(f"DEBUG: Target size: {new_width}x{new_height}")
            
            # Convert mode if necessary (in-place)
            if mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
                log_memory_usage("after mode conversion")
            
            # Single resize operation
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Clear original reference immediately
            img.close()
            del img
            img = None
            gc.collect()
            log_memory_usage("after resize")
            
            # Save with minimal quality
            img_resized.save(temp_path, 'JPEG', quality=10, optimize=True, progressive=False)
            
            # Check result
            result_size_kb = os.path.getsize(temp_path) / 1024
            print(f"DEBUG: Ultra minimal result: {result_size_kb:.1f} KB")
            
            # Clean up resized image
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
        # Final cleanup
        if img:
            try:
                img.close()
            except:
                pass
        gc.collect()
        log_memory_usage("end ultra minimal", force_gc=True)

def compress_image_for_ocr(image_path, max_size_kb=80):  # Reduced from 100KB
    """Memory-efficient compression specifically optimized for OCR"""
    print(f"DEBUG: Starting memory-efficient compression for {image_path}")
    log_memory_usage("start compression", force_gc=True)
    
    try:
        # Quick size check
        current_size_kb = os.path.getsize(image_path) / 1024
        print(f"DEBUG: Current size: {current_size_kb:.1f} KB, target: {max_size_kb} KB")
        
        if current_size_kb <= max_size_kb:
            print("DEBUG: Size acceptable, no compression needed")
            return image_path
        
        # If file is very large, use ultra-minimal compression immediately
        if current_size_kb > 300:  # Lowered threshold from 400KB
            print("DEBUG: Large file detected, using ultra-minimal compression")
            return ultra_minimal_compress(image_path, max_size_kb)
        
        # For moderate sizes, try standard compression
        temp_path = os.path.join(tempfile.gettempdir(), f"ocr_compressed_{int(time.time())}.jpg")
        
        # Memory-conscious processing
        img = None
        try:
            # Open and process in single operation
            with Image.open(image_path) as original:
                width, height = original.size
                
                # Calculate reasonable target dimensions
                scale_factor = min(1.0, (max_size_kb / current_size_kb) ** 0.4)
                target_width = max(int(width * scale_factor), 200)  # Reduced minimums
                target_height = max(int(height * scale_factor), 150)
                
                print(f"DEBUG: Scaling {width}x{height} -> {target_width}x{target_height}")
                
                # Convert and resize in one step
                if original.mode in ('RGBA', 'LA', 'P'):
                    original = original.convert('RGB')
                
                # Resize
                resized = original.resize((target_width, target_height), Image.Resampling.LANCZOS)
                
                # Force cleanup of original
                original.close()
                gc.collect()
                log_memory_usage("after resize")
                
                # Try different quality levels (more aggressive)
                for quality in [30, 20, 15, 10, 8]:  # Lower quality range
                    resized.save(temp_path, 'JPEG', quality=quality, optimize=True)
                    
                    result_size_kb = os.path.getsize(temp_path) / 1024
                    print(f"DEBUG: Quality {quality}: {result_size_kb:.1f} KB")
                    
                    if result_size_kb <= max_size_kb:
                        print(f"✅ Success at quality {quality}: {result_size_kb:.1f} KB")
                        resized.close()
                        gc.collect()
                        return temp_path
                
                # If still too large, fall back to ultra-minimal
                resized.close()
                gc.collect()
                
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
                print("DEBUG: Standard compression failed, falling back to ultra-minimal")
                return ultra_minimal_compress(image_path, max_size_kb)
                
        except Exception as e:
            print(f"DEBUG: Standard compression error: {e}")
            if img:
                try:
                    img.close()
                except:
                    pass
            gc.collect()
            
            # Clean up temp file
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            
            # Fall back to ultra-minimal
            return ultra_minimal_compress(image_path, max_size_kb)
    
    except Exception as e:
        print(f"DEBUG: Compression completely failed: {e}")
        gc.collect()
        return image_path
    
    finally:
        gc.collect()
        log_memory_usage("end compression", force_gc=True)

# CRITICAL: New safe OCR function with circuit breaker
def safe_ocr_with_fallback(image_path, max_attempts=2):
    """OCR with circuit breaker to prevent 502 errors"""
    print(f"DEBUG: Starting safe OCR with circuit breaker")
    
    for attempt in range(max_attempts):
        try:
            print(f"DEBUG: OCR attempt {attempt + 1}/{max_attempts}")
            
            # Check memory before each attempt
            memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
            if memory_mb > 150:  # Conservative threshold
                print(f"DEBUG: Memory too high ({memory_mb:.1f}MB), forcing cleanup")
                aggressive_cleanup()
                time.sleep(1)
                
                # Check again after cleanup
                memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
                if memory_mb > 200:  # Still too high
                    print(f"DEBUG: Memory still high after cleanup ({memory_mb:.1f}MB), skipping attempt")
                    if attempt == max_attempts - 1:
                        return ""
                    continue
            
            # Try OCR with timeout protection
            import signal
            
            def ocr_timeout_handler(signum, frame):
                raise TimeoutError("OCR timeout")
            
            old_handler = signal.signal(signal.SIGALRM, ocr_timeout_handler)
            signal.alarm(45)  # 45 second timeout for OCR
            
            try:
                result = extract_text_ocr_space(image_path)
                signal.alarm(0)  # Cancel alarm
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
                # Last attempt failed, return minimal response
                print("DEBUG: All OCR attempts failed, returning empty result")
                return ""
            
            time.sleep(2)  # Wait before retry
    
    return ""

def extract_text_with_multiple_methods(image_path):
    """Extract text using safe OCR with fallback options"""
    try:
        print(f"DEBUG: Starting safe OCR text extraction from {image_path}")
        
        # Force garbage collection before starting
        aggressive_cleanup()
        
        # Try safe OCR with circuit breaker
        text = safe_ocr_with_fallback(image_path)
        
        if text and len(text.strip()) > 5:
            print(f"DEBUG: Safe OCR successful - extracted {len(text)} characters")
            return text
        
        # If safe OCR fails, try basic pytesseract fallback (if available)
        print("DEBUG: Safe OCR failed, trying basic pytesseract fallback...")
        return extract_text_pytesseract_fallback(image_path)
        
    except Exception as e:
        print(f"DEBUG: All OCR methods failed: {e}")
        # Force cleanup on error
        aggressive_cleanup()
        return ""

def extract_text_ocr_space(image_path):
    """Memory-safe OCR.space extraction with aggressive cleanup"""
    log_memory_usage("start OCR", force_gc=True)
    
    processed_image_path = None
    response = None
    
    try:
        # Pre-compress with very conservative limits
        processed_image_path = compress_image_for_ocr(image_path, max_size_kb=80)
        log_memory_usage("after compression", force_gc=True)
        
        api_url = 'https://api.ocr.space/parse/image'
        api_key = os.getenv('OCR_SPACE_API_KEY', 'helloworld')
        
        print(f"DEBUG: Using compressed image: {processed_image_path}")
        final_size = os.path.getsize(processed_image_path) / 1024
        print(f"DEBUG: Final size: {final_size:.1f} KB")
        
        # Prepare request data
        data = {
            'apikey': api_key,
            'language': 'eng',
            'isOverlayRequired': False,
            'detectOrientation': True,
            'scale': True,
            'OCREngine': 2,
            'isTable': False
        }
        
        # Make API request with file context manager
        with open(processed_image_path, 'rb') as f:
            files = {'file': f}
            print("DEBUG: Sending to OCR.space API...")
            
            try:
                response = requests.post(api_url, files=files, data=data, timeout=20)
                log_memory_usage("after API call")
            except requests.exceptions.Timeout:
                print("DEBUG: OCR API timeout - file might be too large")
                return ""
            except Exception as api_error:
                print(f"DEBUG: OCR API error: {api_error}")
                return ""
        
        # Process response immediately
        if response and response.status_code == 200:
            try:
                result = response.json()
                extracted_text = parse_ocr_space_response(result)
                
                # Clear response immediately
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
                try:
                    error_info = response.text[:200] if response.text else "No error details"
                    print(f"DEBUG: Error details: {error_info}")
                except:
                    pass
            return ""
            
    except Exception as e:
        print(f"DEBUG: OCR extraction failed: {e}")
        return ""
    
    finally:
        # Aggressive cleanup
        if response:
            try:
                response.close() if hasattr(response, 'close') else None
                del response
            except:
                pass
        
        # Clean up compressed file immediately
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
    """Extract text using OCR.space API - enhanced settings with aggressive memory management"""
    try:
        # Force garbage collection
        aggressive_cleanup()
        
        # Compress image with conservative limit
        processed_image_path = compress_image_for_ocr(image_path, max_size_kb=80)
        
        # Force garbage collection
        aggressive_cleanup()
        
        api_url = 'https://api.ocr.space/parse/image'
        api_key = os.getenv('OCR_SPACE_API_KEY', 'helloworld')
        
        response = None
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
                response = requests.post(api_url, files=files, data=data, timeout=20)
        
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
            aggressive_cleanup()
        
        if response and response.status_code == 200:
            result = response.json()
            extracted_text = parse_ocr_space_response(result)
            
            # Clean up response
            response.close() if hasattr(response, 'close') else None
            del response
            aggressive_cleanup()
            
            return extracted_text
        else:
            if response:
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
        aggressive_cleanup()
        return ""

def process_request_with_memory_management():
    """Call this at the start of each request in your Flask app"""
    try:
        print("DEBUG: Pre-request memory management")
        log_memory_usage("pre-request", force_gc=True)
        
        # Clear any lingering temp files
        temp_dir = tempfile.gettempdir()
        current_time = time.time()
        
        cleaned_count = 0
        for filename in os.listdir(temp_dir):
            if ('compressed' in filename or 'ocr_' in filename or 'ultra_' in filename) and filename.endswith('.jpg'):
                filepath = os.path.join(temp_dir, filename)
                try:
                    if os.path.isfile(filepath):
                        file_age = current_time - os.path.getmtime(filepath)
                        if file_age > 30:  # 30 seconds (very aggressive cleanup)
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
    """Call this before processing each image scan"""
    process_request_with_memory_management()
    
    # Set aggressive PIL limits
    Image.MAX_IMAGE_PIXELS = 30000000  # Reduced from default for memory-constrained environments
    
    # Force Python to be more aggressive with memory
    import sys
    if hasattr(sys, 'setswitchinterval'):
        sys.setswitchinterval(0.001)  # More frequent GC checks
    
    # One final aggressive cleanup
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
    """Fallback to pytesseract if available - with memory management"""
    try:
        print("DEBUG: Attempting pytesseract fallback...")
        import pytesseract
        from PIL import Image
        
        # Force garbage collection before loading image
        aggressive_cleanup()
        
        image = Image.open(image_path)
        
        # Simple preprocessing
        if image.mode != 'L':
            image = image.convert('L')
            
        # Try basic OCR
        text = pytesseract.image_to_string(image, config='--psm 6')
        
        # Clean up image from memory
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
        # Force cleanup on error
        aggressive_cleanup()
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

def check_for_safety_labels(text):
    """Check for explicit safety labels that override ingredient concerns"""
    if not text:
        return False
    
    normalized_text = normalize_ingredient_text(text)
    print(f"DEBUG: Checking for safety labels in text: {normalized_text[:200]}...")
    print(f"DEBUG: Full normalized text: {normalized_text}")
    
    # Define safety label patterns (made more flexible and comprehensive)
    safety_patterns = [
        r'\bno\s+msg\b',              # "no msg"
        r'\bno\s+msg\s+added\b',      # "no msg added"
        r'\bmsg\s+free\b',            # "msg free"
        r'\bwithout\s+msg\b',         # "without msg"
        r'\bno\s+artificial\s+msg\b', # "no artificial msg"
        r'\bno\s+added\s+msg\b',      # "no added msg"
        
        r'\bnon\s*gmo\b',             # "non gmo" or "nongmo"
        r'\bnon\s*-\s*gmo\b',         # "non-gmo" with hyphen
        r'\bgmo\s+free\b',            # "gmo free"
        r'\bwithout\s+gmo\b',         # "without gmo"
        r'\bno\s+gmo\b',              # "no gmo"
        r'\bnon\s+genetically\s+modified\b',  # "non genetically modified"
        
        # Additional patterns for common variations
        r'\bmsg\s*free\b',            # "msgfree"
        r'\bgmo\s*free\b',            # "gmofree" 
        r'\bnon\s*gmo\s+natural\b',   # "non-gmo natural" or "nongmo natural"
        r'\bnatural\s+non\s*gmo\b',   # "natural non-gmo"
        r'\bno\s+monosodium\s+glutamate\b',  # "no monosodium glutamate"
    ]
    
    # Check each pattern
    for pattern in safety_patterns:
        matches = re.findall(pattern, normalized_text, re.IGNORECASE)
        if matches:
            print(f"DEBUG: ✅ SAFETY LABEL FOUND: Pattern '{pattern}' matched: {matches}")
            return True
    
    # Also check for common phrases that might be split across words
    safety_phrases = [
        "no msg added",
        "msg free", 
        "non gmo",
        "non-gmo",
        "gmo free",
        "no gmo",
        "without msg",
        "without gmo",
        "non genetically modified",
        "no monosodium glutamate"
    ]
    
    for phrase in safety_phrases:
        # Remove spaces and hyphens for flexible matching
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
            "all_detected": [],
            "has_safety_labels": False  # NEW: Track safety labels
        }
    
    print(f"DEBUG: Matching ingredients in text of {len(text)} characters")
    print(f"DEBUG: Text sample: {text[:200]}...")
    
    # Check for safety labels FIRST
    has_safety_labels = check_for_safety_labels(text)
    
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
        "all_detected": all_detected,
        "has_safety_labels": has_safety_labels  # NEW: Include safety label status
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
    
    # If text quality is very poor, suggest trying again
    if text_quality == "very_poor":
        return "↪️ TRY AGAIN"
    
    # NEW RULE 0: SAFETY LABELS OVERRIDE - If safety labels found, it's SAFE
    if matches.get("has_safety_labels", False):
        print(f"🛡️ SAFETY LABELS DETECTED - OVERRIDING TO SAFE!")
        print(f"   Product explicitly states 'no msg', 'non-gmo', or similar safety claims")
        return "✅ Yay! Safe!"
    
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
    """Main scanning function with comprehensive memory management and error handling"""
    try:
        # CRITICAL: Clean up before starting any processing
        before_scan_cleanup()
        
        print(f"\n{'='*80}")
        print(f"🔬 STARTING MEMORY-OPTIMIZED SCAN: {image_path}")
        print(f"{'='*80}")
        print(f"DEBUG: File exists: {os.path.exists(image_path)}")
        
        # Check initial memory state
        initial_memory = log_memory_usage("scan start", force_gc=True)
        
        if initial_memory > 150:  # Conservative threshold
            print(f"WARNING: High initial memory {initial_memory:.1f}MB - may cause issues")
            aggressive_cleanup()
            time.sleep(0.5)
        
        # Extract text using safe OCR with circuit breaker
        print("🔍 Starting safe OCR text extraction...")
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
        
        # Rate ingredients according to hierarchy (now with safety label override)
        print("⚖️ Applying hierarchy-based rating with safety label override...")
        rating = rate_ingredients_according_to_hierarchy(matches, text_quality)
        print(f"🏆 Final rating: {rating}")
        
        # Determine confidence
        confidence = determine_confidence(text_quality, text, matches)
        
        # Check for GMO Alert (but don't show if safety labels found)
        gmo_alert = None
        if matches["gmo"] and not matches.get("has_safety_labels", False):
            gmo_alert = "📣 GMO Alert!"
        
        # Create comprehensive result
        result = {
            "rating": rating,
            "matched_ingredients": matches,
            "confidence": confidence,
            "extracted_text_length": len(text),
            "text_quality": text_quality,
            "extracted_text": text,
            "gmo_alert": gmo_alert,
            "has_safety_labels": matches.get("has_safety_labels", False)  # NEW: Include in result
        }
        
        # Print comprehensive summary
        print_scan_summary(result)
        
        # Final cleanup
        aggressive_cleanup()
        final_memory = log_memory_usage("scan end", force_gc=True)
        print(f"DEBUG: Memory change: {initial_memory:.1f}MB -> {final_memory:.1f}MB")
        
        return result
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR in scan_image_for_ingredients: {e}")
        import traceback
        traceback.print_exc()
        
        # Force cleanup on error
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

# Additional utility function for backwards compatibility
def analyze_ingredients(text):
    """Wrapper function for backwards compatibility"""
    return match_all_ingredients(text)
