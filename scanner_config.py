# scanner_config.py
# Updated configuration file based on hierarchy document

# ===== TRANS FATS =====
# High Risk (ranks 1-10) - ANY ONE = immediate danger
trans_fat_high_risk = [
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

# Moderate Risk (ranks 11-18) - Count toward total
trans_fat_moderate_risk = [
    "hydrogenated fat",
    "margarine",
    "vegetable oil",
    "blended vegetable oil",
    "frying oil",
    "modified fat",
    "synthetic fat",
    "lard substitute",
    "monoglycerides",
    "diglycerides",
    "monoglycerides/diglycerides",
    "mono- and diglycerides"
]

# Safe (ranks 19-23)
trans_fat_safe = [
    "fully hydrogenated oil",
    "palm oil",
    "palm oil (non-hydrogenated)",
    "coconut oil",
    "butter",
    "ghee",
    "butter/ghee",
    "cold-pressed oil",
    "cold-pressed oils",
    "olive oil",
    "extra virgin olive oil",
    "avocado oil",
    "walnut oil"
]

# ===== EXCITOTOXINS =====
# High Risk (ranks 1-10) - ANY ONE = immediate danger
excitotoxin_high_risk = [
    "monosodium glutamate",
    "msg",
    "aspartame",
    "equal",
    "nutrasweet",
    "hydrolyzed vegetable protein",
    "hvp",
    "hydrolyzed soy protein",
    "hydrolyzed corn protein",
    "hydrolyzed protein",
    "disodium inosinate",
    "disodium guanylate",
    "yeast extract",
    "natural yeast extract",
    "extract of yeast",
    "autolyzed yeast",
    "calcium caseinate",
    "sodium caseinate",
    "torula yeast"
]

# Moderate Risk (ranks 11-16) - Count toward total
excitotoxin_moderate_risk = [
    "natural flavors",
    "natural flavoring",
    "spices",
    "seasonings",
    "spices/seasonings",
    "seasoning blends",
    "soy sauce",
    "non-brewed soy sauce",
    "hydrolyzed soy sauce",
    "enzyme modified cheese",
    "whey protein isolate",
    "whey protein hydrolysate",
    "bouillon",
    "broth",
    "stock",
    "chicken broth",
    "beef stock",
    "bouillon flavor"
]

# Low Risk/Ambiguous (ranks 17-21)
excitotoxin_low_risk = [
    "maltodextrin",
    "modified food starch",
    "textured vegetable protein",
    "tvp",
    "corn syrup solids",
    "carrageenan"
]

# ===== CORN =====
# High Risk (ranks 1-16) - Count toward total
corn_high_risk = [
    "high fructose corn syrup",
    "hfcs",
    "corn syrup",
    "cornstarch",
    "corn starch",
    "modified cornstarch",
    "modified corn starch",
    "maltodextrin",
    "dextrose",
    "fructose",
    "glucose",
    "citric acid",
    "ascorbic acid",
    "erythritol",
    "sorbitol",
    "xylitol",
    "caramel color",
    "vanillin",
    "corn syrup solids",
    "glucose-fructose syrup",
    "crystalline fructose",
    "anhydrous dextrose",
    "glucose solids"
]

# Moderate Risk (ranks 17-30) - Count toward total
corn_moderate_risk = [
    "natural flavors",
    "natural flavoring",
    "vegetable oil",
    "vegetable starch",
    "modified food starch",
    "lactic acid",
    "xanthan gum",
    "guar gum",
    "enzymes",
    "lecithin",
    "tocopherols",
    "vitamin e",
    "baking powder",
    "polydextrose",
    "inositol",
    "mono- and diglycerides",
    "monoglycerides",
    "diglycerides",
    "calcium stearate",
    "magnesium stearate"
]

# Low Risk (ranks 31-39)
corn_low_risk = [
    "sodium erythorbate",
    "ethyl maltol",
    "sodium citrate",
    "potassium citrate",
    "masa harina",
    "corn meal",
    "corn flour",
    "corn oil",
    "corn alcohol",
    "corn ethanol",
    "pla",
    "corn-based vinegars",
    "white vinegar",
    "sorbitan monooleate",
    "sorbitan tristearate",
    "zein"
]

# ===== SUGAR =====
# All sugar ingredients count as problematic according to hierarchy
sugar_keywords = [
    # High Risk Sugars (1-15) - Most dangerous
    "high-fructose corn syrup",
    "high fructose corn syrup",
    "hfcs",
    "corn syrup",
    "corn syrup solids",
    "glucose-fructose syrup",
    "crystalline fructose",
    "anhydrous dextrose",
    "invert sugar",
    "maltodextrin",
    "glucose solids",
    "refiner's syrup",
    "refiners syrup",
    "agave syrup",
    "agave nectar",
    "fructose",
    "dextrose",
    "glucose",
    "sucrose",
    
    # Moderate Risk Sugars (16-48)
    "cane sugar",
    "beet sugar",
    "brown sugar",
    "coconut sugar",
    "date sugar",
    "palm sugar",
    "evaporated cane juice",
    "fruit juice concentrate",
    "fruit juice concentrates",
    "apple juice concentrate",
    "grape juice concentrate",
    "pear juice concentrate",
    "barley malt syrup",
    "brown rice syrup",
    "rice syrup",
    "golden syrup",
    "sorghum syrup",
    "molasses",
    "treacle",
    "carob syrup",
    "yacon syrup",
    "honey",
    "maple syrup",
    "maple sugar",
    "coconut nectar",
    "date syrup",
    "date paste",
    "banana puree",
    "raisin juice concentrate",
    "fig paste",
    "grape must",
    "apple puree",
    "pineapple juice concentrate",
    "diastatic malt",
    "malt syrup",
    "malt extract",
    "ethyl maltol",
    
    # Ambiguous/Marketing terms
    "organic cane juice",
    "dehydrated cane juice",
    "cane juice crystals",
    "rice sweetener",
    "natural sweetener",
    "all-natural sweetener",
    "naturally sweetened",
    "sweetened",
    "sugar"
]

# ===== GMO INGREDIENTS =====
# These trigger GMO Alert but don't count in danger rating
gmo_keywords = [
    "corn syrup",
    "high fructose corn syrup",
    "hfcs",
    "corn starch",
    "cornstarch",
    "modified corn starch",
    "modified cornstarch",
    "soybean oil",
    "soy lecithin",
    "soy protein isolate",
    "canola oil",
    "cottonseed oil",
    "textured vegetable protein",
    "tvp",
    "hydrolyzed soy protein",
    "hydrolyzed vegetable protein",
    "sugar",  # when not specified as cane sugar
    "monoglycerides",
    "diglycerides",
    "mono- and diglycerides",
    "maltodextrin",
    "dextrose",
    "glucose",
    "fructose",
    "ascorbic acid",
    "citric acid",
    "xanthan gum",
    "natural flavors",
    "yeast extract",
    "heme",
    "soy leghemoglobin",
    "enzymes",
    "glycerin",
    "glycerol",
    "lactic acid",
    "sodium lactate",
    "tocopherols",
    "vitamin e",
    "modified food starch",
    "bioengineered food",
    "contains bioengineered ingredients",
    "fermentation-derived dairy proteins",
    "synbio vanillin",
    "vegetable oil",
    "starch",
    "modified starch",
    "lecithin",
    "flavoring",
    "natural flavor",
    "artificial flavor",
    "alcohol",
    "ethanol",
    "corn alcohol",
    "fruit juice concentrate",
    "papaya",
    "zucchini",
    "yellow summer squash",
    "arctic apple",
    "innate potato",
    "pink pineapple",
    "genetically engineered",
    "genetically modified organism",
    "gmo",
    "bioengineered",
    "fermentation-derived proteins",
    "synthetic biology",
    "synbio",
    "lab-grown",
    "precision fermentation"
]

# ===== SAFE INGREDIENTS =====
safe_ingredients = [
    # Safe fats and oils
    "fully hydrogenated oil",
    "palm oil",
    "palm oil (non-hydrogenated)",
    "coconut oil",
    "butter",
    "ghee",
    "butter/ghee",
    "cold-pressed oil",
    "cold-pressed oils",
    "olive oil",
    "extra virgin olive oil",
    "avocado oil",
    "walnut oil",
    "almond oil",
    "sesame oil",
    "sunflower oil",
    "safflower oil",
    
    # Basic ingredients
    "water",
    "salt",
    "sea salt",
    "himalayan salt",
    "black pepper",
    "white pepper",
    "garlic",
    "onion",
    "ginger",
    "turmeric",
    "cinnamon",
    "paprika",
    "cumin",
    "coriander",
    "basil",
    "oregano",
    "thyme",
    "rosemary",
    "sage",
    "parsley",
    "cilantro",
    "mint",
    "dill",
    "bay leaves",
    "vanilla",
    "vanilla bean",
    "cocoa",
    "cacao",
    "coffee",
    "tea",
    
    # Safe additives and vitamins
    "vitamin d",
    "vitamin d3",
    "vitamin c",
    "vitamin b12",
    "calcium carbonate",
    "iron",
    "zinc",
    "magnesium",
    "potassium",
    "sodium bicarbonate",
    "baking soda",
    "cream of tartar",
    "pectin",
    "gelatin",
    "agar",
    "psyllium",
    "flax",
    "chia",
    
    # Whole grains and seeds
    "oats",
    "quinoa",
    "brown rice",
    "wild rice",
    "millet",
    "buckwheat",
    "amaranth",
    "teff",
    "sorghum",
    "barley",
    "rye",
    "spelt",
    "kamut",
    "wheat",
    "whole wheat",
    
    # Nuts and seeds
    "almonds",
    "walnuts",
    "pecans",
    "cashews",
    "pistachios",
    "macadamia",
    "hazelnuts",
    "brazil nuts",
    "pine nuts",
    "pumpkin seeds",
    "sunflower seeds",
    "sesame seeds",
    "flax seeds",
    "chia seeds",
    "hemp seeds",
    
    # Dairy
    "milk",
    "cream",
    "yogurt",
    "cheese",
    "cottage cheese",
    "ricotta",
    "mozzarella",
    "cheddar",
    "parmesan",
    "feta",
    
    # Proteins
    "eggs",
    "egg whites",
    "chicken",
    "turkey",
    "beef",
    "pork",
    "lamb",
    "fish",
    "salmon",
    "tuna",
    "shrimp",
    "crab",
    "lobster",
    
    # Vegetables
    "spinach",
    "kale",
    "lettuce",
    "arugula",
    "broccoli",
    "cauliflower",
    "cabbage",
    "brussels sprouts",
    "carrots",
    "celery",
    "cucumber",
    "tomatoes",
    "bell peppers",
    "mushrooms",
    "asparagus",
    "green beans",
    "peas",
    "corn",  # whole corn
    "potatoes",
    "sweet potatoes",
    "squash",
    "pumpkin",
    "eggplant",
    "beets",
    "radishes",
    "turnips",
    
    # Fruits
    "apples",
    "bananas",
    "oranges",
    "lemons",
    "limes",
    "grapefruit",
    "berries",
    "strawberries",
    "blueberries",
    "raspberries",
    "blackberries",
    "grapes",
    "melons",
    "watermelon",
    "cantaloupe",
    "honeydew",
    "pineapple",
    "mango",
    "papaya",
    "kiwi",
    "peaches",
    "plums",
    "apricots",
    "cherries",
    "pears",
    "figs",
    "dates",
    "raisins",
    "cranberries",
    "pomegranate",
    "avocado",
    
    # Legumes
    "beans",
    "black beans",
    "pinto beans",
    "kidney beans",
    "navy beans",
    "chickpeas",
    "lentils",
    "split peas",
    "soybeans",
    "edamame",
    "tofu",
    "tempeh"
]

# ===== COMMON OCR ERROR CORRECTIONS =====
common_ocr_errors = {
    # Corn syrup variations
    "corn5yrup": "corn syrup",
    "cornsynup": "corn syrup", 
    "com syrup": "corn syrup",
    "cornsyrup": "corn syrup",
    "corn synup": "corn syrup",
    
    # HFCS variations
    "hfc5": "hfcs",
    "hfc3": "hfcs",
    "high fructose com syrup": "high fructose corn syrup",
    "highfructosecornsyrup": "high fructose corn syrup",
    
    # MSG variations
    "m5g": "msg",
    "ms9": "msg",
    "rns9": "msg",
    "monosodiumglutamate": "monosodium glutamate",
    "mono sodium glutamate": "monosodium glutamate",
    
    # Aspartame variations
    "aspertame": "aspartame",
    "aspartarne": "aspartame",
    "asparteme": "aspartame",
    
    # Natural flavors variations
    "naturalflavors": "natural flavors",
    "naturalflavor": "natural flavor",
    "naturalflavoring": "natural flavoring",
    "natural flavonng": "natural flavoring",
    
    # Hydrogenated oil variations
    "partiallyhydrogenated": "partially hydrogenated",
    "hydrogenatedoil": "hydrogenated oil",
    "partially hydrogenated oil": "partially hydrogenated oil",
    
    # Starch variations
    "modifiedstarch": "modified starch",
    "modifiedcornstarch": "modified corn starch",
    "modified com starch": "modified corn starch",
    
    # Lecithin variations
    "soylecithin": "soy lecithin",
    "soy lecrthin": "soy lecithin",
    
    # Oil variations
    "canolaoil": "canola oil",
    "cottonseedoil": "cottonseed oil",
    "vegetableoil": "vegetable oil",
    
    # Protein variations
    "texturedvegetableprotein": "textured vegetable protein",
    "hydrolyzedprotein": "hydrolyzed protein",
    "hydrolyzedvegetableprotein": "hydrolyzed vegetable protein",
    "vegetableprotein": "vegetable protein",
    
    # Yeast extract variations
    "yeastextract": "yeast extract",
    "yeast extract": "yeast extract",
    "autolyzedyeast": "autolyzed yeast",
    
    # Disodium variations
    "disodiuminosinate": "disodium inosinate",
    "disodiumguanylate": "disodium guanylate",
    "disodium inosmate": "disodium inosinate",
    
    # Caseinate variations
    "calciumcaseinate": "calcium caseinate",
    "sodiumcaseinate": "sodium caseinate",
    
    # Maltodextrin variations
    "maltodextnn": "maltodextrin",
    "maltodextrin": "maltodextrin",
    "malto dextrin": "maltodextrin",
    
    # Common character replacements
    "rn": "m",
    "vv": "w", 
    "ii": "ll",
    "cl": "d"
}
