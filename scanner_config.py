# scanner_config.py - Updated with ChemStuffs category

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
    "magnesium stearate",
    "whole grain corn",
    "masa",
    "organic masa"
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
    "sucrose"
]

# ✅ Safe Sugars - Don't count as problematic (previously moderate risk)
sugar_safe = [
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
    "ethyl maltol",
    "cane sugar"
]

# Combine high risk and safe for easier processing
sugar_keywords = sugar_high_risk + sugar_safe 

# ☢️ CHEMSTUFFS - NEW CATEGORY FOR CHEMICAL ADDITIVES
# 🔴 Red - "Oh nooooo, Danger!" - High-risk chemical ingredients
chemstuffs_high_risk = [
    # Artificial Sweeteners
    "sucralose",
    "aspartame", 
    "acesulfame k",
    "acesulfame potassium",
    
    # Synthetic Caffeine
    "caffeine anhydrous",
    "synthetic caffeine",
    
    # Preservative Combinations
    "sodium benzoate",
    "potassium benzoate",
    
    # Artificial Dyes
    "red 40",
    "yellow 5",
    "blue 1",
    "fd&c red 40",
    "fd&c yellow 5", 
    "fd&c blue 1",
    "allura red ac",
    "tartrazine",
    "brilliant blue fcf",
    
    # Chemical Preservatives
    "bht",
    "butylated hydroxytoluene",
    "bha",
    "butylated hydroxyanisole",
    
    # Industrial Chemicals
    "propylene glycol",
    "ethylene glycol",
    
    # Synthetic Supplements (High Dose)
    "synthetic l-carnitine",
    "synthetic niacin",
    "pyridoxine hcl",
    "cyanocobalamin",
    "folic acid",
    
    # Performance Chemicals
    "glucuronolactone",
    "synthetic taurine",
    "synthetic d-ribose",
    "citicoline",
    "cdp-choline",
    "synthetic theobromine"
]

# 🟡 Yellow - "Proceed with caution" - Moderate chemical risk
chemstuffs_moderate_risk = [
    # Acids
    "phosphoric acid",
    "citric acid",
    "malic acid",
    "tartaric acid",
    
    # Synthetic Vitamins
    "synthetic vitamin b6",
    "synthetic vitamin b12", 
    "synthetic folate",
    
    # Artificial Flavors
    "artificial flavors",
    "artificial flavoring",
    "artificial vanilla",
    "vanillin",
    
    # Carbonation + Alcohol combinations
    "carbonated alcoholic beverage",
    
    # Stabilizers
    "sodium phosphate",
    "potassium phosphate",
    "calcium phosphate",
    
    # Emulsifiers
    "polysorbate 80",
    "polysorbate 60",
    "sorbitan monostearate",
    
    # Synthetic Antioxidants
    "tbhq",
    "tertiary butylhydroquinone",
    
    # Chemical Buffers
    "sodium bicarbonate",
    "potassium bicarbonate"
]

# 🟢 Green - "Yay, safe!" - Natural/safer alternatives
chemstuffs_safe = [
    # Natural Caffeine
    "guarana",
    "yerba mate",
    "green tea extract",
    "coffee extract",
    
    # Natural Electrolytes
    "sea salt",
    "himalayan salt",
    "potassium chloride",
    "magnesium glycinate",
    
    # Natural Calming
    "l-theanine",
    "chamomile",
    
    # Natural Adaptogens
    "panax ginseng",
    "rhodiola",
    "ashwagandha",
    
    # Natural B Vitamins
    "methylcobalamin",
    "p5p",
    "folate",
    "nutritional yeast",
    
    # Whole Food Extracts
    "coconut water powder",
    "beetroot extract",
    "ginger extract",
    "lemon juice",
    "green tea extract",
    "chlorophyll",
    
    # Natural Preservatives
    "vitamin e",
    "rosemary extract",
    "ascorbyl palmitate"
]

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
    "cottonseed",
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
    "modified food starch",
    "bioengineered food",
    "contains bioengineered ingredients",
    "fermentation-derived dairy proteins",
    "synbio vanillin",
    "vegetable oil",
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

# RATING HIERARCHY RULES:
# 1. ANY Trans Fat High Risk = IMMEDIATE "Oh NOOOO! Danger!"
# 2. ANY Excitotoxin High Risk = IMMEDIATE "Oh NOOOO! Danger!"  
# 3. ANY ChemStuffs High Risk = IMMEDIATE "Oh NOOOO! Danger!"
# 4. Count all moderate/low risk items across categories:
#    - 3+ total = "Oh NOOOO! Danger!"
#    - 1-2 total = "Proceed carefully" 
#    - 0 total = "Yay! Safe!"
# 5. Safety labels (non-gmo, no msg) override to "Yay! Safe!"
# 6. GMO = Alert notification but doesn't affect rating
