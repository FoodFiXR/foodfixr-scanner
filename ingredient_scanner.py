# ingredient_scanner.py
import re
import pytesseract
from PIL import Image
import os
from typing import Dict, List, Set

# Risk level constants
DANGER = "Oh NOOOO! Danger!"
PROCEED_CAREFULLY = "Proceed carefully" 
SAFE = "Yay! Safe!"
TRY_AGAIN = "TRY AGAIN"

# Trans Fats Database - High danger (flagged even if 1 is present)
TRANS_FATS = {
    "danger": [
        "partially hydrogenated oil", "partially hydrogenated soybean oil",
        "partially hydrogenated cottonseed oil", "partially hydrogenated palm oil",
        "partially hydrogenated canola oil", "vegetable shortening", "shortening",
        "hydrogenated oil", "interesterified fats", "high-stability oil"
    ],
    "caution": [
        "hydrogenated fat", "margarine", "vegetable oil", "frying oil",
        "modified fat", "synthetic fat", "lard substitute", "monoglycerides",
        "diglycerides"
    ],
    "safe": [
        "fully hydrogenated oil", "palm oil", "coconut oil", "butter",
        "ghee", "cold-pressed oil", "olive oil", "avocado oil"
    ]
}

# Excitotoxins Database - High danger (flagged even if 1 is present)
EXCITOTOXINS = {
    "danger": [
        "monosodium glutamate", "msg", "aspartame", "hydrolyzed vegetable protein",
        "hvp", "hydrolyzed soy protein", "hydrolyzed corn protein", "disodium inosinate",
        "disodium guanylate", "yeast extract", "natural yeast extract", "extract of yeast",
        "autolyzed yeast", "calcium caseinate", "sodium caseinate", "torula yeast"
    ],
    "caution": [
        "natural flavors", "natural flavoring", "spices", "seasoning blends",
        "soy sauce", "non-brewed soy sauce", "hydrolyzed soy sauce", "enzyme modified cheese",
        "whey protein isolate", "whey protein hydrolysate", "bouillon", "broth", "stock",
        "chicken broth", "beef stock", "bouillon flavor"
    ],
    "low": [
        "maltodextrin", "modified food starch", "textured vegetable protein", "tvp",
        "corn syrup solids", "carrageenan"
    ]
}

# Corn Database - Moderate danger (1-2 = proceed carefully, 3-4 = danger)
CORN = {
    "high": [
        "high fructose corn syrup", "hfcs", "corn syrup", "cornstarch", "modified cornstarch",
        "maltodextrin", "dextrose", "fructose", "glucose", "citric acid", "ascorbic acid",
        "erythritol", "sorbitol", "xylitol", "caramel color", "vanillin", "msg",
        "monosodium glutamate"
    ],
    "moderate": [
        "natural flavors", "natural flavoring", "vegetable oil", "vegetable starch",
        "modified food starch", "lactic acid", "xanthan gum", "guar gum", "enzymes",
        "lecithin", "tocopherols", "baking powder", "polydextrose", "inositol",
        "mono- and diglycerides", "calcium stearate", "magnesium stearate"
    ],
    "low": [
        "sodium erythorbate", "ethyl maltol", "sodium citrate", "potassium citrate",
        "cornmeal", "corn flour", "masa harina", "corn oil", "corn alcohol",
        "corn ethanol", "pla", "corn-based vinegars", "sorbitan monooleate",
        "sorbitan tristearate", "zein"
    ],
    "suspected": [
        "food starch", "spices", "flavor enhancer", "fermented sugar", "binder",
        "stabilizer", "anti-caking agent"
    ]
}

# Sugar Database - Low danger (1-2 = proceed carefully, 3-4 = danger)
SUGAR = {
    "high": [
        "high-fructose corn syrup", "corn syrup", "corn syrup solids", "glucose-fructose syrup",
        "crystalline fructose", "anhydrous dextrose", "invert sugar", "maltodextrin",
        "glucose solids", "refiner's syrup", "agave syrup", "agave nectar", "fructose",
        "dextrose", "glucose", "sucrose"
    ],
    "low": [
        "cane sugar", "beet sugar", "brown sugar", "coconut sugar", "date sugar", "palm sugar",
        "evaporated cane juice", "fruit juice concentrate", "apple juice concentrate",
        "grape juice concentrate", "barley malt syrup", "brown rice syrup", "rice syrup",
        "golden syrup", "sorghum syrup", "molasses", "treacle", "carob syrup", "yacon syrup",
        "honey", "maple syrup", "maple sugar", "coconut nectar", "date syrup", "date paste",
        "banana puree", "raisin juice concentrate", "fig paste", "grape must", "apple puree",
        "pineapple juice concentrate", "diastatic malt", "malt syrup", "malt extract", "ethyl maltol"
    ],
    "watch": [
        "organic cane juice", "dehydrated cane juice", "cane juice crystals", "rice sweetener",
        "corn sweetener", "natural sweetener", "all-natural sweetener", "naturally sweetened",
        "naturally flavored", "natural flavor", "sweetened", "no refined sugar", "no added sugar",
        "sugar-free"
    ]
}

# GMO Database - Special category for alerts
GMO_INGREDIENTS = [
    "corn syrup", "high fructose corn syrup", "hfcs", "corn starch", "modified corn starch",
    "soybean oil", "soy lecithin", "soy protein isolate", "canola oil", "cottonseed oil",
    "textured vegetable protein", "tvp", "hydrolyzed soy protein", "hydrolyzed vegetable protein",
    "sugar", "monoglycerides", "diglycerides", "maltodextrin", "dextrose", "glucose",
    "fructose", "ascorbic acid", "citric acid", "xanthan gum", "natural flavors",
    "yeast extract", "heme", "soy leghemoglobin", "enzymes", "glycerin", "glycerol",
    "lactic acid", "sodium lactate", "tocopherols", "vitamin e", "modified food starch",
    "bioengineered food", "contains bioengineered ingredients", "fermentation-derived dairy proteins",
    "synbio vanillin", "vegetable oil", "starch", "modified starch", "lecithin",
    "flavoring", "natural flavor", "artificial flavor", "alcohol", "ethanol", "corn alcohol",
    "fruit juice concentrate", "papaya", "zucchini", "yellow summer squash", "arctic apple",
    "innate potato", "pink pineapple", "genetically engineered", "genetically modified organism",
    "bioengineered", "fermentation-derived proteins", "synthetic biology", "synbio",
    "lab-grown", "precision fermentation"
]

def normalize_text(text: str) -> str:
    """Normalize text for ingredient matching"""
    if not text:
        return ""
    # Remove special characters, convert to lowercase, normalize whitespace
    cleaned = re.sub(r'[^\w\s\-/()]', ' ', text.lower())
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def extract_text_from_image(image_path: str) -> str:
    """Extract text from image using OCR"""
    try:
        # Configure tesseract for better ingredient detection
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789(),-./: '
        
        image = Image.open(image_path)
        
        # Enhance image for better OCR
        image = image.convert('L')  # Convert to grayscale
        
        text = pytesseract.image_to_string(image, config=custom_config)
        return text.strip()
        
    except Exception as e:
        print(f"OCR Error: {e}")
        return ""

def find_ingredients_in_text(text: str, ingredient_list: List[str]) -> List[str]:
    """Find ingredients from a list in the given text"""
    found = []
    normalized_text = normalize_text(text)
    
    for ingredient in ingredient_list:
        normalized_ingredient = normalize_text(ingredient)
        
        # Create pattern for word boundary matching
        pattern = r'\b' + re.escape(normalized_ingredient) + r'\b'
        
        if re.search(pattern, normalized_text):
            found.append(ingredient)
    
    return found

def categorize_ingredients(text: str) -> Dict:
    """Categorize all detected ingredients by type and risk level"""
    
    result = {
        "trans_fat": [],
        "excitotoxins": [], 
        "corn": [],
        "sugar": [],
        "gmo": [],
        "safe_ingredients": []
    }
    
    # Check Trans Fats
    for category, ingredients in TRANS_FATS.items():
        found = find_ingredients_in_text(text, ingredients)
        if found:
            if category == "danger" or category == "caution":
                result["trans_fat"].extend(found)
            elif category == "safe":
                result["safe_ingredients"].extend(found)
    
    # Check Excitotoxins  
    for category, ingredients in EXCITOTOXINS.items():
        found = find_ingredients_in_text(text, ingredients)
        if found:
            if category == "danger" or category == "caution" or category == "low":
                result["excitotoxins"].extend(found)
    
    # Check Corn
    for category, ingredients in CORN.items():
        found = find_ingredients_in_text(text, ingredients)
        if found:
            result["corn"].extend(found)
    
    # Check Sugar
    for category, ingredients in SUGAR.items():
        found = find_ingredients_in_text(text, ingredients)
        if found:
            result["sugar"].extend(found)
    
    # Check GMO
    found_gmo = find_ingredients_in_text(text, GMO_INGREDIENTS)
    if found_gmo:
        result["gmo"].extend(found_gmo)
    
    # Remove duplicates
    for category in result:
        result[category] = list(set(result[category]))
    
    return result

def determine_overall_risk(categorized_ingredients: Dict) -> str:
    """Determine overall risk level based on ingredient hierarchy"""
    
    # 1. Trans Fats: High danger - flagged even if 1 is present
    if categorized_ingredients["trans_fat"]:
        return DANGER
    
    # 2. Excitotoxins: High danger - flagged even if 1 is present  
    if categorized_ingredients["excitotoxins"]:
        return DANGER
    
    # 3. Corn: Moderate Danger - 1-2 = proceed carefully, 3-4 = danger
    corn_count = len(categorized_ingredients["corn"])
    if corn_count >= 3:
        return DANGER
    elif corn_count >= 1:
        return PROCEED_CAREFULLY
    
    # 4. Sugar: Low danger - 1-2 = proceed carefully, 3-4 = danger
    sugar_count = len(categorized_ingredients["sugar"])
    if sugar_count >= 3:
        return DANGER
    elif sugar_count >= 1:
        return PROCEED_CAREFULLY
    
    # 5. Zero danger items = Safe
    return SAFE

def scan_image_for_ingredients(image_path: str) -> Dict:
    """Main function to scan image and return ingredient analysis"""
    
    try:
        # Extract text from image
        extracted_text = extract_text_from_image(image_path)
        
        if not extracted_text or len(extracted_text.strip()) < 10:
            return {
                "rating": TRY_AGAIN,
                "confidence": "low",
                "extracted_text": extracted_text,
                "matched_ingredients": {
                    "trans_fat": [],
                    "excitotoxins": [],
                    "corn": [],
                    "sugar": [],
                    "gmo": [],
                    "safe_ingredients": []
                }
            }
        
        # Categorize ingredients
        matched_ingredients = categorize_ingredients(extracted_text)
        
        # Determine overall risk
        overall_risk = determine_overall_risk(matched_ingredients)
        
        # Calculate confidence based on text quality and matches
        total_matches = sum(len(matches) for matches in matched_ingredients.values())
        confidence = "high" if total_matches > 0 and len(extracted_text) > 50 else "medium"
        
        result = {
            "rating": overall_risk,
            "confidence": confidence,
            "extracted_text": extracted_text,
            "matched_ingredients": matched_ingredients
        }
        
        return result
        
    except Exception as e:
        print(f"Scanning error: {e}")
        return {
            "rating": TRY_AGAIN,
            "confidence": "low",
            "extracted_text": "",
            "matched_ingredients": {
                "trans_fat": [],
                "excitotoxins": [],
                "corn": [],
                "sugar": [],
                "gmo": [],
                "safe_ingredients": []
            },
            "error": str(e)
        }

# Additional utility functions for debugging
def print_ingredient_databases():
    """Print all ingredient databases for verification"""
    print("=== TRANS FATS ===")
    for category, ingredients in TRANS_FATS.items():
        print(f"{category.upper()}: {len(ingredients)} ingredients")
        for ing in ingredients[:5]:  # Show first 5
            print(f"  - {ing}")
        if len(ingredients) > 5:
            print(f"  ... and {len(ingredients) - 5} more")
        print()
    
    print("=== EXCITOTOXINS ===")
    for category, ingredients in EXCITOTOXINS.items():
        print(f"{category.upper()}: {len(ingredients)} ingredients")
        for ing in ingredients[:5]:
            print(f"  - {ing}")
        if len(ingredients) > 5:
            print(f"  ... and {len(ingredients) - 5} more")
        print()
    
    print("=== CORN ===")
    for category, ingredients in CORN.items():
        print(f"{category.upper()}: {len(ingredients)} ingredients")
        for ing in ingredients[:5]:
            print(f"  - {ing}")
        if len(ingredients) > 5:
            print(f"  ... and {len(ingredients) - 5} more")
        print()
    
    print("=== SUGAR ===")
    for category, ingredients in SUGAR.items():
        print(f"{category.upper()}: {len(ingredients)} ingredients")
        for ing in ingredients[:5]:
            print(f"  - {ing}")
        if len(ingredients) > 5:
            print(f"  ... and {len(ingredients) - 5} more")
        print()
    
    print(f"=== GMO === {len(GMO_INGREDIENTS)} ingredients")
    for ing in GMO_INGREDIENTS[:10]:
        print(f"  - {ing}")
    if len(GMO_INGREDIENTS) > 10:
        print(f"  ... and {len(GMO_INGREDIENTS) - 10} more")

if __name__ == "__main__":
    # Test with sample text
    test_text = "Ingredients: water, corn syrup, partially hydrogenated soybean oil, natural flavors, citric acid, msg"
    
    print("Testing ingredient scanner...")
    print(f"Test text: {test_text}")
    print()
    
    categorized = categorize_ingredients(test_text)
    risk = determine_overall_risk(categorized)
    
    print(f"Overall Risk: {risk}")
    print("Categorized ingredients:")
    for category, ingredients in categorized.items():
        if ingredients:
            print(f"  {category}: {ingredients}")
    
    print("\n" + "="*50)
    print_ingredient_databases()
