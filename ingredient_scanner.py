import pytesseract
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import re
from scanner_config import *

def preprocess_image(image):
    """Enhanced image preprocessing for better OCR accuracy"""
    # Convert to grayscale
    if image.mode != 'L':
        image = image.convert('L')
    
    # Resize image if too small - IMPORTANT FOR MOBILE PHOTOS
    width, height = image.size
    if width < 800:  # Upscale small images
        scale_factor = 800 / width
        new_width = int(width * scale_factor)
        new_height = int(height * scale_factor)
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Enhance contrast MORE AGGRESSIVELY
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.5)  # Increased from 2.0
    
    # Enhance sharpness
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(2.5)  # Increased from 2.0
    
    # Apply slight blur to reduce noise
    image = image.filter(ImageFilter.MedianFilter(size=3))
    
    # Auto-level the image
    image = ImageOps.autocontrast(image)
    
    # ADDED: Try to clean up the image more
    image = ImageOps.equalize(image)
    
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
        
        # Try even MORE OCR configurations
        configs = [
            '--oem 3 --psm 6',  # Default: uniform block of text
            '--oem 3 --psm 8',  # Single word
            '--oem 3 --psm 7',  # Single text line
            '--oem 3 --psm 4',  # Single column of text
            '--oem 3 --psm 3',  # Fully automatic page segmentation
            '--oem 3 --psm 11', # Sparse text
            '--oem 3 --psm 12', # Sparse text with OSD
            '--oem 3 --psm 13', # Raw line. Treat as single text line
        ]
        
        texts = []
        for config in configs:
            try:
                text = pytesseract.image_to_string(image, config=config)
                if text.strip():
                    texts.append(text)
                    print(f"OCR Config {config}: Found {len(text)} characters")
            except Exception as e:
                print(f"OCR Config {config} failed: {e}")
                continue
        
        # Combine all extracted texts
        combined_text = ' '.join(texts)
        
        # Clean and normalize the text
        combined_text = re.sub(r'\s+', ' ', combined_text)  # Normalize whitespace
        combined_text = re.sub(r'[^\w\s,.-]', '', combined_text)  # Remove special chars except common punctuation
        
        print(f"TOTAL TEXT EXTRACTED: {len(combined_text)} characters")
        print(f"Extracted text preview: {combined_text[:200]}...")
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
        
        # Handle special cases for variations
        variations = []
        
        # Add base ingredient
        variations.append(normalized_ingredient)
        
        # Handle slash variations (e.g., "monoglycerides/diglycerides")
        if '/' in ingredient:
            parts = ingredient.split('/')
            variations.extend([normalize_text(part.strip()) for part in parts])
        
        # Handle parenthetical variations (e.g., "palm oil (non-hydrogenated)")
        if '(' in ingredient:
            base = ingredient.split('(')[0].strip()
            variations.append(normalize_text(base))
        
        # Check all variations
        for variant in variations:
            # Exact match (must be surrounded by word boundaries)
            if re.search(r'\b' + re.escape(variant) + r'\b', normalized_text):
                matches.append(ingredient)
                break
            
            # For compound ingredients, check if all words are present as separate words
            variant_words = variant.split()
            if len(variant_words) > 1:
                # Check if all words of the ingredient are present as whole words
                if all(re.search(r'\b' + re.escape(word) + r'\b', normalized_text) for word in variant_words):
                    # Additional check: words should be reasonably close to each other
                    positions = []
                    for word in variant_words:
                        match = re.search(r'\b' + re.escape(word) + r'\b', normalized_text)
                        if match:
                            positions.append(match.start())
                    
                    # If words are within 50 characters of each other, consider it a match
                    if positions and max(positions) - min(positions) < 50:
                        matches.append(ingredient)
                        break
        
        # Check for exact abbreviations only
        if ingredient.lower() in ['msg', 'hfcs', 'hvp', 'bha', 'bht', 'tbhq', 'tvp']:
            if re.search(r'\b' + re.escape(ingredient.lower()) + r'\b', normalized_text):
                matches.append(ingredient)
    
    return list(set(matches))  # Remove duplicates

def match_ingredients(text):
    """Enhanced ingredient matching that finds ALL ingredients according to hierarchy"""
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
    Updated ingredient rating following EXACT hierarchy rules from document:
    
    HIERARCHY RULES:
    1. Trans Fats (ranks 1-10): ANY ONE = "Oh NOOOO! Danger!"
    2. Excitotoxins (ranks 1-10): ANY ONE = "Oh NOOOO! Danger!"
    3. For ALL other ingredients (moderate trans fats, moderate excitotoxins, ALL corn, ALL sugar):
       - Count total problematic ingredients
       - 1-2 total = "Proceed carefully"
       - 3-4 total = "Oh NOOOO! Danger!"
    4. GMO is NOT part of ranking, only flagged separately
    """
    
    # If text quality is too poor, suggest trying again
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
        if any(high_risk in ingredient.lower() for high_risk in high_risk_trans_fats):
            print(f"🚨 HIGH RISK Trans Fat found: {ingredient}")
            return "🚨 Oh NOOOO! Danger!"
    
    # RULE 2: Check HIGH RISK Excitotoxins (ranks 1-10) - ANY ONE = immediate danger
    for ingredient in matches["excitotoxins"]:
        if any(high_risk in ingredient.lower() for high_risk in high_risk_excitotoxins):
            print(f"🚨 HIGH RISK Excitotoxin found: {ingredient}")
            return "🚨 Oh NOOOO! Danger!"
    
    # RULE 3: Count ALL problematic ingredients (moderate + low risk)
    # This includes: moderate trans fats (11-18), moderate excitotoxins (11-16), ALL corn, ALL sugar
    total_problematic_count = 0
    problematic_ingredients = []
    
    # Count moderate risk trans fats (ranks 11-18 from document)
    moderate_trans_fats = [
        "hydrogenated fat",
        "margarine",
        "vegetable oil",
        "frying oil",
        "modified fat",
        "synthetic fat",
        "lard substitute",
        "monoglycerides", "diglycerides"
    ]
    
    for ingredient in matches["trans_fat"]:
        if any(moderate in ingredient.lower() for moderate in moderate_trans_fats):
            total_problematic_count += 1
            problematic_ingredients.append(f"Trans Fat (moderate): {ingredient}")
    
    # Count moderate risk excitotoxins (ranks 11-16 from document)
    moderate_excitotoxins = [
        "natural flavors", "natural flavoring",
        "spices", "seasonings",
        "soy sauce",
        "enzyme modified cheese",
        "whey protein isolate", "whey protein hydrolysate",
        "bouillon", "broth", "stock"
    ]
    
    for ingredient in matches["excitotoxins"]:
        if any(moderate in ingredient.lower() for moderate in moderate_excitotoxins):
            total_problematic_count += 1
            problematic_ingredients.append(f"Excitotoxin (moderate): {ingredient}")
    
    # Count ALL corn ingredients (corn is "Moderate Danger" category)
    if matches["corn"]:
        total_problematic_count += len(matches["corn"])
        for ingredient in matches["corn"]:
            problematic_ingredients.append(f"Corn: {ingredient}")
    
    # Count ALL sugar ingredients (sugar is "Low danger" category)
    if matches["sugar"]:
        total_problematic_count += len(matches["sugar"])
        for ingredient in matches["sugar"]:
            problematic_ingredients.append(f"Sugar: {ingredient}")
    
    print(f"⚖️ Total problematic ingredients: {total_problematic_count}")
    if problematic_ingredients:
        print("Problematic ingredients found:")
        for ing in problematic_ingredients:
            print(f"  - {ing}")
    
    # Apply the hierarchy rule: 1-2 = Proceed Carefully, 3-4 = Danger
    if total_problematic_count >= 3:
        return "🚨 Oh NOOOO! Danger!"
    elif total_problematic_count >= 1:
        return "⚠️ Proceed carefully"
    
    # If poor text quality and no clear ingredients detected, suggest trying again
    if text_quality == "poor" and len(matches["all_detected"]) == 0:
        return "✅ Yay! Safe! (No harmful ingredients detected)"
    
    # No dangerous ingredients found
    return "✅ Yay! Safe!"

def assess_text_quality(text):
    """Assess the quality of extracted text - MADE MORE LENIENT"""
    if not text or len(text.strip()) < 3:  # Changed from 5 to 3
        return "very_poor"
    
    # Check for meaningless character sequences - RELAXED
    meaningless_patterns = [
        r'^[^a-zA-Z]*$',  # Only numbers/symbols
        r'^.{1,2}$',      # Changed from 3 to 2 - too short
    ]
    
    for pattern in meaningless_patterns:
        if re.search(pattern, text):
            return "very_poor"
    
    # Check for reasonable word-like content - MORE LENIENT
    words = re.findall(r'\b[a-zA-Z]{1,}\b', text)  # Changed from 2+ to 1+ letters
    if len(words) < 1:  # Changed from 2 to 1
        return "poor"
    
    # Much more lenient text length requirements
    if len(text) < 8 or len(words) / len(text.split()) < 0.2:  # Reduced from 15 and 0.3
        return "poor"
    
    return "good"

def scan_image_for_ingredients(image_path):
    """Main scanning function with enhanced processing and quality assessment"""
    try:
        print(f"DEBUG: Starting scan for {image_path}")
        print(f"DEBUG: File exists: {os.path.exists(image_path)}")
        
        # Check if tesseract is available
        try:
            import pytesseract
            # Test tesseract
            test_img = Image.new('RGB', (100, 30), color='white')
            pytesseract.image_to_string(test_img)
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
        
        text = extract_text_from_image(image_path)
        print(f"DEBUG: Extracted text length: {len(text)}")
        
        text_quality = assess_text_quality(text)
        print(f"DEBUG: Text quality: {text_quality}")
        
        matches = match_ingredients(text)
        rating = rate_ingredients(matches, text_quality)
        
        # Rest of your existing function...
        
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
# Test function for verification
def test_scanner():
    """Test function to verify hierarchy rules"""
    print("Testing hierarchy rules...")
    
    # Test 1: High risk trans fat
    test_matches_1 = {
        "trans_fat": ["partially hydrogenated oil"],
        "excitotoxins": [],
        "corn": [],
        "sugar": [],
        "gmo": [],
        "safe_ingredients": [],
        "all_detected": ["partially hydrogenated oil"]
    }
    result_1 = rate_ingredients(test_matches_1, "good")
    print(f"Test 1 (High risk trans fat): {result_1}")
    assert "Danger" in result_1
    
    # Test 2: High risk excitotoxin
    test_matches_2 = {
        "trans_fat": [],
        "excitotoxins": ["MSG"],
        "corn": [],
        "sugar": [],
        "gmo": [],
        "safe_ingredients": [],
        "all_detected": ["MSG"]
    }
    result_2 = rate_ingredients(test_matches_2, "good")
    print(f"Test 2 (High risk excitotoxin): {result_2}")
    assert "Danger" in result_2
    
    # Test 3: 2 moderate ingredients (should be "Proceed carefully")
    test_matches_3 = {
        "trans_fat": ["vegetable oil"],
        "excitotoxins": [],
        "corn": ["maltodextrin"],
        "sugar": [],
        "gmo": [],
        "safe_ingredients": [],
        "all_detected": ["vegetable oil", "maltodextrin"]
    }
    result_3 = rate_ingredients(test_matches_3, "good")
    print(f"Test 3 (2 moderate ingredients): {result_3}")
    assert "Proceed" in result_3
    
    # Test 4: 3+ moderate ingredients (should be "Danger")
    test_matches_4 = {
        "trans_fat": ["vegetable oil"],
        "excitotoxins": ["natural flavors"],
        "corn": ["corn syrup"],
        "sugar": ["sugar"],
        "gmo": [],
        "safe_ingredients": [],
        "all_detected": ["vegetable oil", "natural flavors", "corn syrup", "sugar"]
    }
    result_4 = rate_ingredients(test_matches_4, "good")
    print(f"Test 4 (4 moderate ingredients): {result_4}")
    assert "Danger" in result_4
    
    print("All tests passed! ✅")

if __name__ == "__main__":
    # Run tests to verify implementation
    test_scanner()
