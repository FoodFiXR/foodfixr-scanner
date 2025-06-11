# Enhanced ingredient lists with improved detection patterns

# TOP 5 MOST DANGEROUS - These trigger immediate danger regardless of count
trans_fat_top5_danger = [
    "partially hydrogenated",
    "hydrogenated oil", 
    "vegetable shortening",
    "shortening",
    "partially hydrog",  # OCR variation
    "trans fat",
    "trans fats"
]

excitotoxin_top5_danger = [
    "monosodium glutamate",
    "msg",
    "hydrolyzed vegetable protein",
    "hydrolyzed protein", 
    "autolyzed yeast",
    "glutamic acid",
    "natural flavor"  # Most common hidden excitotoxin
]

gmo_top5_danger = [
    "genetically modified",
    "gmo",
    "bioengineered", 
    "genetically engineered",
    "high fructose corn syrup",  # Most common GMO ingredient
    "corn syrup",
    "soybean oil"
]

# Enhanced trans fat detection
trans_fat_high_risk = [
    "partially hydrogenated",
    "hydrogenated oil",
    "vegetable shortening", 
    "shortening",
    "partially hydrog",  # OCR variation
    "part hydrogenated",
    "trans fat",
    "trans fats",
    "hydrogenated fat",
    "hydrogenated vegetable oil"
]

trans_fat_moderate_risk = [
    "hydrogenated",
    "margarine",
    "high-stability oil",
    "interesterified fat",
    "emulsifiers",
    "modified fat",
    "synthetic fat",
    "lard substitute",
    "monoglycerides",
    "diglycerides",
    "palm kernel oil"  # Can contain trans fats
]

# Enhanced excitotoxin detection
excitotoxin_high_risk = [
    "monosodium glutamate",
    "msg",
    "mono sodium glutamate",
    "hydrolyzed vegetable protein",
    "hydrolyzed protein",
    "hydrolyzed plant protein",
    "hydrolyzed soy protein",
    "autolyzed yeast",
    "yeast extract",
    "calcium caseinate",
    "sodium caseinate",
    "textured protein",
    "glutamic acid",
    "disodium inosinate",
    "disodium guanylate",
    "natural flavor",
    "natural flavors",
    "natural flavoring",
    "artificial flavor",
    "artificial flavors",
    "flavor enhancer",
    "modified food starch",
    "protein concentrate",
    "soy protein isolate"
]

excitotoxin_moderate_risk = [
    "spice extract",
    "broth",
    "stock",
    "bouillon",
    "seasoning",
    "protein isolate", 
    "whey protein",
    "gelatin",
    "barley malt",
    "malt extract",
    "maltodextrin"
]

# Enhanced corn-based ingredient detection
corn_high_risk = [
    "corn syrup",
    "high fructose corn syrup",
    "hfcs",
    "cornstarch",
    "corn starch", 
    "modified food starch",
    "modified corn starch",
    "corn oil",
    "cornmeal",
    "corn meal",
    "milled corn",
    "dextrose",
    "maltodextrin",
    "citric acid",
    "ascorbic acid",
    "erythritol",
    "sorbitol",
    "xylitol",
    "vanillin",
    "caramel color",
    "caramel coloring",
    "corn flour",
    "corn bran",
    "corn syrup solids",
    "crystalline fructose"
]

corn_moderate_risk = [
    "vegetable oil",  # Often corn-based
    "vegetable starch",
    "glucose",
    "fructose", 
    "xanthan gum",
    "lecithin",
    "enzymes",
    "tocopherols",
    "vitamin c",
    "ascorbic",
    "citric",
    "dextrin",
    "maltose",
    "invert sugar"
]

# Comprehensive sugar detection
sugar_keywords = [
    "sugar",
    "cane sugar",
    "brown sugar",
    "white sugar",
    "raw sugar",
    "glucose",
    "fructose",
    "sucrose",
    "dextrose",
    "maltose",
    "lactose",
    "corn syrup",
    "high fructose corn syrup",
    "maple syrup",
    "agave syrup",
    "agave nectar",
    "molasses",
    "honey",
    "artificial sweetener",
    "aspartame",
    "sucralose",
    "saccharin",
    "acesulfame potassium",
    "ace-k",
    "stevia",
    "monk fruit",
    "invert sugar",
    "turbinado sugar",
    "coconut sugar",
    "date sugar",
    "rice syrup",
    "barley malt syrup",
    "fruit juice concentrate",
    "evaporated cane juice",
    "crystalline fructose",
    "corn syrup solids"
]

# Enhanced GMO detection
gmo_keywords = [
    "genetically modified",
    "gmo",
    "bioengineered",
    "genetically engineered",
    "modified",
    "engineered",
    "high fructose corn syrup",
    "corn syrup",
    "soybean oil",
    "canola oil",
    "cottonseed oil",
    "corn oil",
    "vegetable oil",  # Often GMO
    "modified corn starch",
    "soy lecithin",
    "soy protein",
    "corn starch",
    "maltodextrin",
    "dextrose",
    "citric acid",  # Often from GMO corn
    "ascorbic acid",
    "vitamin c"
]

# Additional harmful preservatives and additives
preservatives_high_risk = [
    "sodium benzoate",
    "potassium benzoate", 
    "sodium nitrite",
    "sodium nitrate",
    "potassium nitrite",
    "potassium nitrate",
    "sulfur dioxide",
    "sodium sulfite",
    "bha",
    "bht",
    "tbhq",
    "propyl gallate",
    "calcium propionate",
    "sodium propionate",
    "potassium sorbate",
    "sodium erythorbate"
]

# Harmful artificial colors
artificial_colors = [
    "red 40",
    "yellow 5", 
    "yellow 6",
    "blue 1",
    "blue 2",
    "red 3",
    "green 3",
    "fd&c",
    "artificial color",
    "artificial coloring",
    "food coloring",
    "lake",
    "tartrazine",
    "sunset yellow",
    "allura red",
    "brilliant blue",
    "erythrosine",
    "fast green"
]

# Common OCR misreads and corrections
common_ocr_corrections = {
    # Spacing fixes
    "com syrup": "corn syrup",
    "com starch": "corn starch", 
    "hydrog": "hydrogenated",
    "nat flavor": "natural flavor",
    "artif": "artificial",
    "preserv": "preservative",
    "glucos": "glucose",
    "fructos": "fructose",
    "sucros": "sucrose",
    
    # Character substitutions
    "monosodium glutarnate": "monosodium glutamate",
    "glutarnate": "glutamate",
    "hydrogenated": "hydrogenated",
    "partiaily": "partially",
    "artifical": "artificial",
    "naturaf": "natural",
    "flavor": "flavor",
    
    # Common ingredient variations
    "corn symp": "corn syrup",
    "high fmctose": "high fructose",
    "vegetabie oil": "vegetable oil",
    "modified starcb": "modified starch",
    "caramel coior": "caramel color"
}

# Ingredient synonyms for better matching
ingredient_synonyms = {
    "msg": ["monosodium glutamate", "mono sodium glutamate"],
    "hfcs": ["high fructose corn syrup"],
    "bha": ["butylated hydroxyanisole"],
    "bht": ["butylated hydroxytoluene"], 
    "tbhq": ["tertiary butylhydroquinone"],
    "natural flavor": ["natural flavoring", "natural flavors"],
    "artificial flavor": ["artificial flavoring", "artificial flavors"],
    "corn syrup": ["corn syrup solids"],
    "modified starch": ["modified food starch", "modified corn starch"],
    "vegetable oil": ["veg oil", "vegetable oils"]
}

# Safe ingredients that should not trigger warnings
safe_ingredients_whitelist = [
    "water", "salt", "sea salt", "flour", "wheat flour", "whole wheat flour", 
    "rice", "brown rice", "wild rice", "oats", "rolled oats", "quinoa", 
    "milk", "organic milk", "eggs", "egg whites", "butter", "olive oil",
    "coconut oil", "avocado oil", "vinegar", "apple cider vinegar",
    "lemon juice", "lime juice", "garlic", "onion", "tomatoes", "potatoes",
    "cheese", "cream", "yogurt", "vanilla", "vanilla extract", "pure vanilla",
    "cinnamon", "black pepper", "white pepper", "herbs", "spices", 
    "oregano", "basil", "thyme", "rosemary", "parsley", "cilantro",
    "almonds", "walnuts", "pecans", "cashews", "peanuts", "sunflower seeds",
    "pumpkin seeds", "chia seeds", "flax seeds", "sesame seeds",
    "cocoa", "dark chocolate", "unsweetened chocolate", "baking soda",
    "baking powder", "yeast", "active dry yeast", "honey", "pure honey",
    "maple syrup", "pure maple syrup", "garlic powder", "onion powder",
    "paprika", "turmeric", "ginger", "cardamom", "nutmeg", "cloves",
    "organic", "natural", "whole grain", "stone ground", "cold pressed",
    "extra virgin", "unrefined", "raw", "sprouted", "fermented"
]

# Weight factors for different risk levels
risk_weights = {
    "trans_fat_top5": 10,      # Immediate danger
    "excitotoxin_top5": 10,    # Immediate danger
    "gmo_top5": 10,            # Immediate danger
    "trans_fat_high": 3,       # High risk
    "excitotoxin_high": 3,     # High risk
    "corn_high": 2,            # Moderate risk
    "sugar": 1,                # Lower risk
    "gmo": 2,                  # Moderate risk
    "preservatives": 2,        # Moderate risk
    "artificial_colors": 2     # Moderate risk
}
