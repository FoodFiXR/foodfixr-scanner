# Enhanced ingredient lists with more comprehensive coverage

# TOP 5 MOST DANGEROUS - These trigger immediate danger regardless of count
trans_fat_top5_danger = [
    "partially hydrogenated",
    "hydrogenated oil", 
    "vegetable shortening",
    "shortening",
    "partially hydrog"  # OCR variation
]

excitotoxin_top5_danger = [
    "monosodium glutamate",
    "msg",
    "hydrolyzed vegetable protein",
    "hydrolyzed protein", 
    "autolyzed yeast"
]

gmo_top5_danger = [
    "genetically modified",
    "gmo",
    "bioengineered",
    "genetically engineered",
    "high fructose corn syrup"  # Most common GMO ingredient
]

trans_fat_high_risk = [
    "partially hydrogenated",
    "hydrogenated oil",
    "vegetable shortening",
    "shortening",
    "partially hydrog",  # OCR variation
    "part hydrogenated"
]

trans_fat_moderate_risk = [
    "hydrogenated",
    "margarine",
    "high-stability oil",
    "interesterified fat",
    "emulsifiers",
    "vegetable oil",
    "frying oil",
    "modified fat",
    "synthetic fat",
    "lard substitute",
    "monoglycerides",
    "diglycerides",
    "palm oil",
    "palm kernel oil",
    "coconut oil",
    "butter",
    "ghee"
]

excitotoxin_high_risk = [
    "monosodium glutamate",
    "msg",
    "mono sodium glutamate",
    "hydrolyzed vegetable protein",
    "hydrolyzed protein",
    "hydrolyzed plant protein",
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
    "BHT"
]

excitotoxin_moderate_risk = [
    "soy protein isolate",
    "spice extract",
    "broth",
    "stock",
    "bouillon",
    "seasoning",
    "protein isolate",
    "whey protein",
    "gelatin",
    "modified food starch"
]

corn_high_risk = [
    "corn syrup",
    "high fructose corn syrup",
    "hfcs",
    "cornstarch",
    "corn starch",
    "modified food starch",
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
    "corn bran"
]

corn_moderate_risk = [
    "vegetable oil",
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
    "maltose"
]

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
    "molasses",
    "honey",
    "artificial sweetener",
    "aspartame",
    "sucralose",
    "saccharin",
    "acesulfame potassium",
    "stevia",
    "monk fruit",
    "invert sugar",
    "turbinado sugar",
    "coconut sugar",
    "date sugar",
    "whole wheat flour",
    "whole oat flour"
]

gmo_keywords = [
    "genetically modified",
    "gmo",
    "bioengineered",
    "genetically engineered",
    "modified",
    "engineered",
    "high fructose corn syrup",  # Most common GMO ingredient
    "corn syrup",
    "soybean oil",
    "canola oil",
    "cottonseed oil"
]

# Additional preservatives and additives to watch for
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
    "propyl gallate"
]

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
    "allura red"
]

# Common OCR misreads to watch for
common_ocr_errors = {
    "com syrup": "corn syrup",
    "com starch": "corn starch",
    "hydrog": "hydrogenated",
    "nat flavor": "natural flavor",
    "artif": "artificial",
    "preserv": "preservative",
    "glucos": "glucose",
    "fructos": "fructose",
    "sucros": "sucrose"
}