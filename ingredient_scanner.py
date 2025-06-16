import re
from scanner_config import *

def extract_ingredients_from_text(ocr_text):
    """Extract actual ingredients from OCR text with exact matching"""
    
    # Clean and normalize the text
    text = ocr_text.lower().strip()
    
    # Remove common OCR errors and noise
    text = re.sub(r'[^\w\s,\.\-\(\)]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    
    # Find ingredients section
    ingredients_pattern = r'ingredient[s]?\s*[:\-]?\s*(.*?)(?:contains\s*[:\-]|nutrition|allergen|warning|$)'
    match = re.search(ingredients_pattern, text, re.IGNORECASE | re.DOTALL)
    
    if match:
        ingredients_text = match.group(1)
    else:
        ingredients_text = text
    
    # Split by commas and clean each ingredient
    raw_ingredients = [item.strip() for item in ingredients_text.split(',')]
    
    # Clean each ingredient
    cleaned_ingredients = []
    for ingredient in raw_ingredients:
        # Remove parenthetical information but keep the main ingredient
        ingredient = re.sub(r'\([^)]*\)', '', ingredient).strip()
        
        # Remove periods, extra spaces
        ingredient = re.sub(r'\.+', '', ingredient).strip()
        ingredient = re.sub(r'\s+', ' ', ingredient).strip()
        
        # Skip very short or invalid ingredients
        if len(ingredient) > 2 and ingredient.replace(' ', '').isalpha():
            cleaned_ingredients.append(ingredient)
    
    return cleaned_ingredients

def exact_match_ingredients(detected_ingredients, keyword_list):
    """Find exact matches only - no partial matching"""
    exact_matches = []
    
    for detected in detected_ingredients:
        detected_lower = detected.lower().strip()
        
        for keyword in keyword_list:
            keyword_lower = keyword.lower().strip()
            
            # Exact match logic
            if detected_lower == keyword_lower:
                exact_matches.append(detected)
                break
            
            # Handle compound words (e.g., "modified cornstarch" should match "modified cornstarch" not "cornstarch")
            elif ' ' in keyword_lower and keyword_lower in detected_lower:
                # Only match if the keyword appears as complete words
                pattern = r'\b' + re.escape(keyword_lower) + r'\b'
                if re.search(pattern, detected_lower):
                    exact_matches.append(detected)
                    break
            
            # Handle single words that appear as complete words
            elif ' ' not in keyword_lower and ' ' not in detected_lower:
                if detected_lower == keyword_lower:
                    exact_matches.append(detected)
                    break
    
    return list(set(exact_matches))  # Remove duplicates

def smart_ingredient_detection(detected_ingredients):
    """
    Smart detection that prioritizes longer, more specific ingredient names
    to avoid false positives like 'cornstarch' when 'modified cornstarch' is present
    """
    
    # Sort ingredients by length (longest first) to prioritize specific matches
    sorted_ingredients = sorted(detected_ingredients, key=len, reverse=True)
    
    # Track what we've already matched to avoid duplicates
    matched_terms = set()
    
    results = {
        "trans_fat": [],
        "excitotoxins": [],
        "corn": [],
        "sugar": [],
        "gmo": [],
        "safe": [],
        "all_detected": detected_ingredients
    }
    
    for ingredient in sorted_ingredients:
        ingredient_lower = ingredient.lower().strip()
        
        # Skip if we've already matched a longer version of this
        if any(ingredient_lower in matched.lower() for matched in matched_terms):
            continue
        
        matched = False
        
        # Check trans fats (prioritize specific matches)
        all_trans_fat = trans_fat_high_risk + trans_fat_moderate_risk + trans_fat_safe
        for tf in sorted(all_trans_fat, key=len, reverse=True):
            if tf.lower() == ingredient_lower or (len(tf.split()) > 1 and tf.lower() in ingredient_lower):
                results["trans_fat"].append(ingredient)
                matched_terms.add(ingredient)
                matched = True
                break
        
        if matched:
            continue
            
        # Check excitotoxins
        all_excitotoxins = excitotoxin_high_risk + excitotoxin_moderate_risk + excitotoxin_low_risk
        for ex in sorted(all_excitotoxins, key=len, reverse=True):
            if ex.lower() == ingredient_lower or (len(ex.split()) > 1 and ex.lower() in ingredient_lower):
                results["excitotoxins"].append(ingredient)
                matched_terms.add(ingredient)
                matched = True
                break
        
        if matched:
            continue
            
        # Check corn ingredients
        all_corn = corn_high_risk + corn_moderate_risk + corn_low_risk
        for corn in sorted(all_corn, key=len, reverse=True):
            if corn.lower() == ingredient_lower or (len(corn.split()) > 1 and corn.lower() in ingredient_lower):
                results["corn"].append(ingredient)
                matched_terms.add(ingredient)
                matched = True
                break
        
        if matched:
            continue
            
        # Check sugar ingredients
        all_sugar = sugar_high_risk + sugar_moderate_risk + sugar_low_risk
        for sugar in sorted(all_sugar, key=len, reverse=True):
            if sugar.lower() == ingredient_lower or (len(sugar.split()) > 1 and sugar.lower() in ingredient_lower):
                results["sugar"].append(ingredient)
                matched_terms.add(ingredient)
                matched = True
                break
        
        if matched:
            continue
            
        # Check GMO ingredients
        for gmo in sorted(gmo_keywords, key=len, reverse=True):
            if gmo.lower() == ingredient_lower or (len(gmo.split()) > 1 and gmo.lower() in ingredient_lower):
                results["gmo"].append(ingredient)
                matched_terms.add(ingredient)
                matched = True
                break
        
        if matched:
            continue
            
        # Check safe ingredients
        for safe in sorted(safe_ingredients, key=len, reverse=True):
            if safe.lower() == ingredient_lower or (len(safe.split()) > 1 and safe.lower() in ingredient_lower):
                results["safe"].append(ingredient)
                matched_terms.add(ingredient)
                matched = True
                break
    
    return results

def analyze_ingredients(ocr_text):
    """Main analysis function with exact matching"""
    
    print("🔍 Starting ingredient analysis...")
    
    # Extract ingredients from OCR text
    detected_ingredients = extract_ingredients_from_text(ocr_text)
    print(f"📝 Detected ingredients: {detected_ingredients}")
    
    if not detected_ingredients:
        print("❌ No ingredients detected")
        return {
            "rating": "↪️ TRY AGAIN",
            "matches": {"trans_fat": [], "excitotoxins": [], "corn": [], "sugar": [], "gmo": [], "safe": [], "all_detected": []},
            "gmo_alert": False,
            "text_quality": "very_poor"
        }
    
    # Smart ingredient detection with exact matching
    matches = smart_ingredient_detection(detected_ingredients)
    
    # Check for GMO alert
    gmo_alert = len(matches["gmo"]) > 0
    
    # Assess text quality based on number of reasonable ingredients detected
    if len(detected_ingredients) >= 8:
        text_quality = "excellent"
    elif len(detected_ingredients) >= 5:
        text_quality = "good"
    elif len(detected_ingredients) >= 3:
        text_quality = "fair"
    else:
        text_quality = "poor"
    
    # Rate according to hierarchy
    rating = rate_ingredients_according_to_hierarchy(matches, text_quality)
    
    print(f"⭐ Final rating: {rating}")
    print(f"📊 Matches found: {matches}")
    print(f"🧬 GMO Alert: {gmo_alert}")
    
    return {
        "rating": rating,
        "matches": matches,
        "gmo_alert": gmo_alert,
        "text_quality": text_quality
    }

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
            if high_risk_item.lower() == ingredient.lower() or high_risk_item.lower() in ingredient.lower():
                high_risk_trans_fat_found.append(ingredient)
                print(f"🚨 HIGH RISK Trans Fat detected: {ingredient}")
                return "🚨 Oh NOOOO! Danger!"
    
    # RULE 2: HIGH RISK EXCITOTOXINS - ANY ONE = immediate danger  
    high_risk_excitotoxin_found = []
    for ingredient in matches["excitotoxins"]:
        # Check against high risk excitotoxin list from scanner_config
        for high_risk_item in excitotoxin_high_risk:
            if high_risk_item.lower() == ingredient.lower() or high_risk_item.lower() in ingredient.lower():
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
                if moderate_item.lower() == ingredient.lower() or moderate_item.lower() in ingredient.lower():
                    moderate_trans_fat_count += 1
                    print(f"⚠️ Moderate trans fat counted: {ingredient}")
                    break
    
    # Count moderate excitotoxins (not already counted as high risk)  
    moderate_excitotoxin_count = 0
    for ingredient in matches["excitotoxins"]:
        if ingredient not in high_risk_excitotoxin_found:
            # Check if it's a moderate risk excitotoxin
            for moderate_item in excitotoxin_moderate_risk:
                if moderate_item.lower() == ingredient.lower() or moderate_item.lower() in ingredient.lower():
                    moderate_excitotoxin_count += 1
                    print(f"⚠️ Moderate excitotoxin counted: {ingredient}")
                    break
            # Also check low risk excitotoxins
            for low_item in excitotoxin_low_risk:
                if low_item.lower() == ingredient.lower() or low_item.lower() in ingredient.lower():
                    moderate_excitotoxin_count += 1
                    print(f"⚠️ Low risk excitotoxin counted: {ingredient}")
                    break
    
    # Count ALL corn ingredients (as per document: all corn counts)
    corn_count = len(matches["corn"])
    
    # Count ALL sugar ingredients (as per document: all sugar counts)  
    sugar_count = len(matches["sugar"])
    
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

# Example usage for testing
if __name__ == "__main__":
    # Test with Campbell's soup ingredients
    test_text = """
    Ingredients: Chicken stock, modified cornstarch, vegetable oil, wheat flour,
    cream, chicken meat, chicken fat, salt, whey, dried chicken, monosodium
    glutamate, soy protein concentrate, water, natural flavoring, yeast extract,
    beta carotene for color, soy protein isolate, sodium phosphate, celery
    extract, onion extract, butter, garlic juice concentrate.
    """
    
    result = analyze_ingredients(test_text)
    print(f"\n🎯 FINAL RESULT:")
    print(f"Rating: {result['rating']}")
    print(f"GMO Alert: {result['gmo_alert']}")
    print(f"Text Quality: {result['text_quality']}")
