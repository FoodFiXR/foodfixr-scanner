# scanner_config.py
# Complete ingredient database following the hierarchy from requirements

# TRANS FATS - High danger (even 1 = danger)
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

trans_fat_moderate_risk = [
    "hydrogenated fat",
    "margarine",
    "vegetable oil",
    "frying oil",
    "modified fat",
    "synthetic fat",
    "lard substitute",
    "monoglycerides",
    "diglycerides"
]

# Top 5 most dangerous trans fats for immediate danger trigger
trans_fat_top5_danger = [
    "partially hydrogenated oil",
    "partially hydrogenated soybean oil",
    "partially hydrogenated cottonseed oil",
    "partially hydrogenated palm oil",
    "partially hydrogenated canola oil"
]

# EXCITOTOXINS - High danger (even 1 = danger)
excitotoxin_high_risk = [
    "monosodium glutamate",
    "msg",
    "aspartame",
    "hydrolyzed vegetable protein",
    "hvp",
    "disodium inosinate",
    "disodium guanylate",
    "yeast extract",
    "autolyzed yeast",
    "calcium caseinate",
    "sodium caseinate",
    "torula yeast"
]

excitotoxin_moderate_risk = [
    "natural flavors",
    "spices",
    "seasonings",
    "soy sauce",
    "enzyme modified cheese",
    "whey protein isolate",
    "whey protein hydrolysate",
    "broth",
    "stock",
    "bouillon"
]

# Top 5 most dangerous excitotoxins for immediate danger trigger
excitotoxin_top5_danger = [
    "monosodium glutamate",
    "msg",
    "aspartame",
    "hydrolyzed vegetable protein",
    "hvp"
]

# CORN - Moderate danger
corn_high_risk = [
    "high fructose corn syrup",
    "hfcs",
    "corn syrup",
    "corn syrup solids",
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
    "msg",
    "monosodium glutamate"
]

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
    "baking powder",
    "polydextrose",
    "inositol",
    "mono- and diglycerides",
    "calcium stearate",
    "magnesium stearate"
]

# SUGAR - Low danger
sugar_keywords = [
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
    "agave syrup",
    "agave nectar",
    "fructose",
    "dextrose",
    "glucose",
    "sucrose",
    "cane sugar",
    "beet sugar",
    "brown sugar",
    "coconut sugar",
    "date sugar",
    "palm sugar",
    "evaporated cane juice",
    "fruit juice concentrate",
    "apple juice concentrate",
    "grape juice concentrate",
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
    "date paste"
]

# GMO - Not part of ranking but flagged as "GMO Alert!"
gmo_keywords = [
    "corn syrup",
    "high fructose corn syrup",
    "hfcs",
    "corn starch",
    "modified corn starch",
    "soybean oil",
    "soy lecithin",
    "soy protein isolate",
    "canola oil",
    "cottonseed oil",
    "textured vegetable protein",
    "tvp",
    "hydrolyzed soy protein",
    "hydrolyzed vegetable protein",
    "sugar",  # when not labeled as "cane sugar"
    "monoglycerides",
    "diglycerides",
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
    "genetically engineered",
    "genetically modified organism",
    "bioengineered",
    "fermentation-derived proteins",
    "synthetic biology",
    "synbio",
    "lab-grown",
    "precision fermentation"
]

# Top 5 most dangerous GMO ingredients
gmo_top5_danger = [
    "high fructose corn syrup",
    "soybean oil",
    "canola oil",
    "corn starch",
    "cottonseed oil"
]

# Safe ingredients list
safe_ingredients = [
    "water",
    "salt",
    "flour",
    "wheat flour",
    "rice",
    "oats",
    "milk",
    "eggs",
    "butter",
    "olive oil",
    "vinegar",
    "lemon juice",
    "garlic",
    "onion",
    "tomatoes",
    "cheese",
    "cream",
    "vanilla",
    "cinnamon",
    "pepper",
    "herbs",
    "spices",
    "whole wheat",
    "brown rice",
    "quinoa",
    "almonds",
    "nuts",
    "coconut",
    "cocoa",
    "chocolate",
    "vanilla extract",
    "baking soda",
    "baking powder",
    "yeast",
    "honey",
    "maple syrup",
    "sea salt",
    "iodized salt",
    "garlic powder",
    "onion powder",
    "paprika",
    "oregano",
    "basil",
    "fully hydrogenated oil",
    "palm oil",  # non-hydrogenated
    "coconut oil",
    "butter",
    "ghee",
    "cold-pressed oils",
    "olive oil",
    "avocado oil",
    "walnut oil"
]
