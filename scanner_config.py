# scanner_config.py - Exact hierarchy from document

# TRANS FATS - From hierarchy document
# 🔴 High Risk (ranks 1-10) - ANY ONE = immediate danger
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

# 🟡 Moderate Risk (ranks 11-18) - Count toward total
trans_fat_moderate_risk = [
    "hydrogenated fat",
    "margarine",
    "frying oil", 
    "modified fat",
    "synthetic fat",
    "lard substitute",
    "monoglycerides",
    "diglycerides"
]

# ✅ Safe trans fats (don't count as problematic)
trans_fat_safe = [
    "fully hydrogenated oil",
    "palm oil",
    "coconut oil", 
    "butter",
    "ghee",
    "cold-pressed oil",
    "olive oil",
    "avocado oil"
]

# EXCITOTOXINS - From hierarchy document  
# 🔴 High Risk (ranks 1-10) - ANY ONE = immediate danger
excitotoxin_high_risk = [
    "monosodium glutamate",
    "msg",
    "aspartame", 
    "hydrolyzed vegetable protein",
    "hvp",
    "hydrolyzed soy protein",
    "hydrolyzed corn protein",
    "disodium inosinate",
    "disodium guanylate", 
    "autolyzed yeast",
    "calcium caseinate",
    "sodium caseinate",
    "torula yeast"
]

# 🟡 Moderate Risk (ranks 11-16) - Count toward total
excitotoxin_moderate_risk = [
    "natural flavors",
    "natural flavoring", 
    "non-brewed soy sauce", 
    "hydrolyzed soy sauce",
    "enzyme modified cheese",
    "whey protein isolate",
    "whey protein hydrolysate",
    "bouillon",
    "bouillon flavor"
]

# Low Risk/Ambiguous (ranks 17-21) - Count toward total  
excitotoxin_low_risk = [
    "maltodextrin",
    "modified food starch",
    "textured vegetable protein",
    "tvp",
    "corn syrup solids",
    "carrageenan"
]

# CORN - From hierarchy document
# 🔴 High Risk - Count toward total
corn_high_risk = [
    "high fructose corn syrup",
    "hfcs", 
    "corn syrup",
    "cornstarch",
    "modified cornstarch",
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
    "corn flour",
    "cornmeal",
    "corn oil",
    "corn alcohol",
    "corn ethanol",
    "corn-based vinegars"
]

# 🟡 Moderate Risk - Count toward total
corn_moderate_risk = [
    "modified food starch",
    "lactic acid",
    "xanthan gum",
    "guar gum",
    "lecithin",
    "tocopherols",
    "polydextrose", 
    "inositol",
    "mono- and diglycerides",
    "calcium stearate",
    "magnesium stearate"
]

# Low Risk - Count toward total
corn_low_risk = [
    "sodium erythorbate",
    "ethyl maltol",
    "sodium citrate",
    "potassium citrate",
    "masa harina",
    "sorbitan monooleate",
    "sorbitan tristearate",
    "zein"
]

# SUGAR - From hierarchy document  
# 🔴 High Risk - Count toward total
sugar_high_risk = [
    "high-fructose corn syrup",
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
    "cane sugar"
]

# 🟡 Moderate Risk - Count toward total
sugar_moderate_risk = [
    "beet sugar",
    "brown sugar",
    "coconut sugar",
    "date sugar",
    "palm sugar", 
    "evaporated cane juice",
    "fruit juice concentrates",
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
    "ethyl maltol"
]

# Combine all sugar categories for easier processing
sugar_keywords = sugar_high_risk + sugar_moderate_risk 

# GMO ALERT - From hierarchy document (NOT part of ranking)
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
    "sugar",
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
    "bioengineered",
    "fermentation-derived proteins",
    "synthetic biology",
    "synbio",
    "lab-grown",
    "precision fermentation"
]
 safe_ingredients = [
    "water",
    "salt", 
    "sea salt",
    "black pepper",
    "white pepper",
    "garlic",
    "onion",
    "olive oil",
    "coconut oil",
    "avocado oil",
    "butter",
    "cream",
    "milk",
    "eggs",
    "chicken",
    "beef",
    "pork",
    "fish",
    "salmon",
    "tuna", 
    "turkey",
    "rice",
    "quinoa",
    "oats",
    "wheat",
    "flour",
    "bread",
    "tomato",
    "potato",
    "carrot",
    "celery",
    "spinach",
    "kale",
    "broccoli",
    "apple",
    "banana",
    "orange",
    "lemon",
    "lime",
    "vinegar",
    "apple cider vinegar",
    "baking soda",
    "vanilla extract",
    "cinnamon",
    "paprika",
    "oregano",
    "basil",
    "thyme",
    "rosemary",
    "parsley",
    "bay leaves",
    "turmeric",
    "ginger",
    "mustard seed",
    "fennel",
    "cumin",
    "coriander"
]


