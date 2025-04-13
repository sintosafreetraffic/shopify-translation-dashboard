# random_name.py
import random
from bs4 import BeautifulSoup # Make sure BeautifulSoup is imported
import re
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FEMALE_KEYWORDS = {
    # English - General & Clothing
    'women', 'woman', 'womens', 'female', 'ladies', 'lady', 'girl', 'girls',
    'she', 'her', 'hers', 'feminine', 'dress', 'skirt', 'blouse', 'gown',
    'tunic', 'leggings', 'jeggings', 'capris', 'pantyhose', 'tights', 'stockings',
    'lingerie', 'bra', 'bralette', 'panty', 'panties', 'chemise', 'camisole',
    'bodysuit', 'nightgown', 'negligee', 'bikini', 'swimsuit', 'one-piece', # Swimwear
    'cardigan', 'shrug', 'bolero', 'peplum', 'romper', 'jumpsuit',

    # English - Shoes & Accessories
    'heels', 'pumps', 'stilettos', 'wedges', 'flats', 'sandals', # Often female styles
    'purse', 'handbag', 'clutch', 'tote', 'satchel', 'jewelry', 'earrings',
    'necklace', 'bracelet', 'pendant', 'locket', 'brooch', 'bangle', 'anklet',
    'ring', 'tiara', 'headband', 'hair clip', 'barrette', 'scrunchie', 'scarf', 'shawl',
    'fascinator',

    # English - Beauty & Care
    'cosmetic', 'makeup', 'lipstick', 'lip gloss', 'eyeliner', 'eyeshadow',
    'mascara', 'foundation', 'concealer', 'blush', 'bronzer', 'nail polish',
    'manicure', 'pedicure', 'perfume', 'fragrance', # Often gendered, lean female if unspecified
    'skincare', 'moisturizer', 'serum', 'cleanser', # Can be neutral, but often marketed to women

    # German - General & Clothing
    'damen', 'frau', 'mädchen', 'weiblich', 'feminin', 'kleid', 'rock',
    'bluse', 'tunika', 'robe', 'mieder', 'strumpfhose', 'strümpfe',
    'nachthemd', 'negligee', 'badeanzug', 'einteiler', # Swimwear
    'strickjacke',

    # German - Shoes & Accessories
    'stiefellette', # Ankle boot often female
    'pumps', 'sandalen', 'ballerinas', 'handtasche', 'umhängetasche', 'schmuck',
    'ohrringe', 'halskette', 'armband', 'anhänger', 'brosche', 'armreif',
    'ring', 'diadem', 'haarband', 'haarspange', 'haargummi', 'tuch', 'schal',

    # German - Beauty & Care
    'kosmetik', 'schminke', 'lippenstift', 'lipgloss', 'wimperntusche',
    'lidschatten', 'rouge', 'nagellack', 'maniküre', 'pediküre', 'parfüm',
    'duft', 'hautpflege', 'feuchtigkeitscreme',
}

MALE_KEYWORDS = {
    # English - General & Clothing
    'men', 'man', 'mens', 'male', 'gentlemen', 'gentleman', 'boy', 'boys',
    'he', 'his', 'masculine', 'suit', 'blazer', 'tuxedo', 'dinner jacket',
    'waistcoat', 'vest', # Often means waistcoat in men's context
    'trousers', 'pants', 'chinos', 'slacks', 'jeans', # Can be neutral, but basic term often defaults male in context
    'shorts', # Can be neutral
    'shirt', 't-shirt', 'polo', # Often neutral, but check context
    'sweater', 'pullover', 'jumper', # Can be neutral
    'boxer', 'briefs', 'trunks', 'underwear', # Men's underwear
    'swim trunks', 'board shorts',

    # English - Shoes & Accessories
    'oxfords', 'brogues', 'loafers', 'derby', # Specific men's shoe types
    'boots', 'sneakers', # Often neutral
    'tie', 'bow tie', 'cufflinks', 'tie clip', 'pocket square', 'belt',
    'wallet', 'briefcase', 'messenger bag', 'watch', 'suspenders',

    # English - Grooming
    'shave', 'shaving', 'razor', 'aftershave', 'cologne', 'beard', 'mustache',
    'trimmer', 'pomade', 'grooming',

    # German - General & Clothing
    'herren', 'herr', 'mann', 'junge', 'knabe', 'männlich', 'maskulin',
    'anzug', 'sakko', 'smoking', 'weste', 'hose', # Often neutral contextually
    'hemd', # Often neutral contextually
    'pullover', 'strickpullover', # Often neutral
    'boxershorts', 'unterhose', 'badehose', 'badeshorts',

    # German - Shoes & Accessories
    'halbschuhe', 'schnürschuhe', # Generic dress shoes
    'stiefel', 'turnschuhe', # Often neutral
    'krawatte', 'fliege', 'manschettenknöpfe', 'krawattennadel', 'einstecktuch',
    'gürtel', 'geldbörse', 'brieftasche', 'aktentasche', 'uhr', 'hosenträger',

    # German - Grooming
    'rasur', 'rasieren', 'rasierer', 'after shave', 'kölnisch wasser', 'bart',
    'schnurrbart', 'trimmer', 'pomade', 'bartpflege',
}

NEUTRAL_KEYWORDS = {
    # English
    'unisex', 'kids', 'children', 'child', 'baby', 'toddler', 'infant', 'junior',
    'youth', 'gender neutral', 'genderless', 'all genders', 'shared',
    'pet', 'dog', 'cat', 'animal',
    'home', 'decor', 'house', 'kitchen', 'cookware', 'tableware', 'cutlery',
    'glassware', 'living', 'room', 'furniture', 'sofa', 'chair', 'table',
    'lamp', 'bedding', 'towel', 'bath', 'garden', 'plant', 'tool',
    'office', 'stationery', 'notebook', 'pen', 'pencil',
    'art', 'print', 'poster', 'book', 'game', 'toy', 'puzzle',
    'electronics', 'gadget', 'computer', 'laptop', 'tablet', 'phone', 'camera',
    'headphones', 'speaker', 'charger', 'cable',
    'food', 'drink', 'beverage', 'coffee', 'tea', 'snack', 'grocery',
    'bag', 'backpack', 'luggage', 'suitcase',
    'bicycle', 'bike', 'car', 'auto', 'vehicle', 'accessory', # Usually neutral unless specified e.g. 'car seat cover for women'
    'travel', 'outdoor', 'camping', 'sport', 'fitness', # Neutral unless qualified
    'hoodie', 'sweatshirt', 'jacket', 'coat', 'beanie', 'cap', 'gloves', 'socks', 'scarf', # Often unisex unless styled/marketed otherwise
    'apron', 'costume', 'uniform', 'pajamas', 'pyjamas', 'robe', # Often neutral

    # German
    'kinder', 'kind', 'baby', 'kleinkind', 'säugling', 'jugend',
    'geschlechtsneutral', 'unisex', 'alle geschlechter',
    'haustier', 'hund', 'katze', 'tier',
    'zuhause', 'heim', 'deko', 'dekoration', 'haus', 'küche', 'kochgeschirr',
    'geschirr', 'besteck', 'glaswaren', 'wohnen', 'zimmer', 'möbel',
    'stuhl', 'tisch', 'lampe', 'bettwäsche', 'handtuch', 'bad', 'garten',
    'pflanze', 'werkzeug',
    'büro', 'schreibwaren', 'notizbuch', 'stift', 'bleistift',
    'kunst', 'druck', 'poster', 'buch', 'spiel', 'spielzeug', 'puzzle',
    'elektronik', 'gerät', 'computer', 'laptop', 'tablet', 'handy', 'kamera',
    'kopfhörer', 'lautsprecher', 'ladegerät', 'kabel',
    'lebensmittel', 'essen', 'getränk', 'kaffee', 'tee', 'snack',
    'tasche', 'rucksack', 'gepäck', 'koffer',
    'fahrrad', 'rad', 'auto', 'fahrzeug', 'zubehör',
    'reise', 'outdoor', 'camping', 'sport', 'fitness',
    'kapuzenpullover', 'sweatshirt', 'jacke', 'mantel', 'mütze', 'kappe', 'handschuhe', 'socken', 'schal',
    'schürze', 'kostüm', 'uniform', 'schlafanzug', 'pyjama', 'bademantel',
}

# --- Paste your full lists here ---
# Using shorter lists for example brevity. Replace these with your 500 names each.
FEMALE_NAMES = [
    "Aaliyah", "Abigail", "Ada", "Adalyn", "Addison", "Adelaide", "Adeline", "Adelyn", "Adriana", "Adrienne",
    "Agatha", "Agnes", "Ainsley", "Aisha", "Alaina", "Alana", "Alanna", "Alani", "Alayna", "Aleah",
    "Alejandra", "Alena", "Alessandra", "Alessia", "Alex", "Alexa", "Alexandra", "Alexandria", "Alexia", "Alexis",
    "Alice", "Alicia", "Alina", "Alisa", "Alisha", "Alison", "Alivia", "Aliya", "Aliyah", "Allison",
    "Allyson", "Alma", "Alondra", "Alyssa", "Amanda", "Amara", "Amari", "Amaya", "Amber", "Amelia",
    "Amelie", "Amina", "Amira", "Amy", "Ana", "Anais", "Anastasia", "Andrea", "Angela", "Angelica",
    "Angelina", "Angeline", "Angelique", "Anika", "Anisa", "Anisha", "Anita", "Aniya", "Aniyah", "Ann",
    "Anna", "Annabel", "Annabella", "Annabelle", "Annalise", "Anne", "Annette", "Annie", "Annika", "Ansley",
    "Antonia", "Anya", "April", "Arabella", "Arden", "Arely", "Aria", "Ariana", "Arianna", "Ariel",
    "Ariella", "Arielle", "Ariyah", "Arlene", "Armani", "Ashley", "Ashlyn", "Ashlynn", "Aspen", "Astrid",
    "Athena", "Aubrey", "Audrey", "Aurora", "Autumn", "Ava", "Avery", "Ayla", "Aylin", "Azalea",
    "Bailey", "Barbara", "Beatrice", "Beatriz", "Becky", "Belinda", "Bella", "Belle", "Berenice", "Bernadette",
    "Bernice", "Bethany", "Betty", "Beverly", "Bianca", "Blair", "Blakely", "Bonnie", "Brenda", "Brenna",
    "Briana", "Brianna", "Bridget", "Brielle", "Briley", "Brinley", "Bristol", "Brittany", "Brooke", "Brooklyn",
    "Brooklynn", "Brylee", "Brynlee", "Brynn", "Cadence", "Caitlin", "Calliope", "Callie", "Cameron", "Camila",
    "Camille", "Candace", "Cara", "Carina", "Carla", "Carlee", "Carley", "Carlie", "Carly", "Carmen",
    "Carol", "Carolina", "Caroline", "Carolyn", "Carrie", "Carson", "Cassandra", "Cassidy", "Catalina", "Catherine",
    "Cathy", "Cecelia", "Cecilia", "Celeste", "Celia", "Celine", "Chandler", "Chanel", "Charlee", "Charleigh",
    "Charley", "Charlie", "Charlotte", "Chaya", "Chelsea", "Cher", "Cheryl", "Cheyenne", "Chiquita", "Chloe",
    "Christina", "Christine", "Claire", "Clara", "Clarice", "Clarissa", "Claudia", "Clementine", "Colette", "Colleen",
    "Collins", "Connie", "Constance", "Cora", "Coraline", "Corey", "Corinne", "Courtney", "Crystal", "Cynthia",
    "Dahlia", "Daisy", "Dakota", "Daleyza", "Dallas", "Dana", "Daniela", "Daniella", "Danielle", "Daphne",
    "Dara", "Darlene", "Davina", "Dawn", "Dayana", "Deanna", "Debbie", "Deborah", "Debra", "Delaney",
    "Delia", "Delilah", "Della", "Denise", "Desiree", "Diana", "Diane", "Dianna", "Dixie", "Dominique",
    "Donna", "Dora", "Doreen", "Doris", "Dorothy", "Dulce", "Dylan", "Eden", "Edith", "Eileen",
    "Elaine", "Eleanor", "Elena", "Eliana", "Elianna", "Elinor", "Elisa", "Elisabeth", "Elise", "Elisha",
    "Eliza", "Elizabeth", "Ella", "Elle", "Ellen", "Ellie", "Elliot", "Ellis", "Elodie", "Eloise",
    "Elsa", "Elsie", "Elyse", "Ember", "Emery", "Emilia", "Emilie", "Emily", "Emma", "Emmaline",
    "Emmalyn", "Emmanuelle", "Emmeline", "Emmie", "Emmy", "Ensley", "Erica", "Erika", "Erin", "Esmeralda",
    "Esperanza", "Estelle", "Esther", "Eugenia", "Eulalia", "Eunice", "Eva", "Evangeline", "Eve", "Evelyn",
    "Everlee", "Everleigh", "Everly", "Evie", "Fabiola", "Faith", "Fallon", "Fatima", "Faye", "Felicia",
    "Felicity", "Fernanda", "Fiona", "Flora", "Florence", "Frances", "Francesca", "Frankie", "Freya", "Frida",
    "Gabrielle", "Gabriella", "Gaby", "Gail", "Galilea", "Gemma", "Gena", "Genesis", "Geneva", "Genevieve",
    "Georgia", "Georgina", "Geraldine", "Gertrude", "Gia", "Giana", "Gianna", "Gigi", "Gillian", "Gina",
    "Ginger", "Ginny", "Gisela", "Gisele", "Giselle", "Gladys", "Gloria", "Grace", "Gracelyn", "Gracie",
    "Graciela", "Greta", "Gretchen", "Guadalupe", "Gwendolyn", "Hadley", "Hailey", "Haleigh", "Haley", "Hali",
    "Hallie", "Halsey", "Hana", "Hanna", "Hannah", "Harley", "Harmony", "Harper", "Harriet", "Hattie",
    "Haven", "Hayden", "Haylee", "Hayley", "Hazel", "Heather", "Heaven", "Heidi", "Helen", "Helena",
    "Helga", "Henley", "Holly", "Hope", "Ida", "Ileana", "Iliana", "Imogen", "India", "Indira",
    "Ingrid", "Irene", "Iris", "Irma", "Isabel", "Isabela", "Isabella", "Isabelle", "Isadora", "Isla",
    "Itzel", "Ivana", "Ivanna", "Ivy", "Izabella", "Jackie", "Jacqueline", "Jada", "Jade", "Jadelyn",
    "Jael", "Jaime", "Jamie", "Jane", "Janelle", "Janet", "Janice", "Janie", "Janine", "Jaqueline",
    "Jasmine", "Jaycee", "Jayda", "Jayde", "Jayla", "Jaylee", "Jayleen", "Jaylene", "Jazlyn", "Jazmin",
    "Jazmine", "Jean", "Jeanette", "Jeanine", "Jeanne", "Jeannette", "Jeannie", "Jemima", "Jenna", "Jennifer",
    "Jenny", "Jessica", "Jessie", "Jewel", "Jill", "Jillian", "Jimena", "Jo", "Joan", "Joann",
    "Joanna", "Joanne", "Jocelyn", "Jodi", "Jodie", "Jody", "Joelle", "Johanna", "Jolene", "Jolie",
    "Jordan", "Jordyn", "Joselyn", "Josephine", "Josie", "Joslyn", "Journey", "Joy", "Joyce", "Judith",
    "Judy", "Julia", "Juliana", "Julianna", "Julianne", "Julie", "Juliet", "Juliette", "June", "Juniper",
    "Juno", "Justice", "Justine", "Kacey", "Kadijah", "Kaelyn", "Kai", "Kaia", "Kailey", "Kailyn",
    "Kairi", "Kaisa", "Kaitlin", "Kaitlyn", "Kaiya", "Kala", "Kalani", "Kali", "Kaliyah", "Kallie",
    "Kamila", "Kamilah", "Kamryn", "Kara", "Karen", "Kari", "Karin", "Karina", "Karissa", "Karla",
    "Karlee", "Karly", "Karma", "Karol", "Karolina", "Kassandra", "Kassidy", "Katalina", "Katarina", "Kate",
    "Katelyn", "Katelynn", "Katherine", "Kathleen", "Kathryn", "Kathy", "Katie", "Katina", "Katrina", "Katy",
    "Kaya", "Kayla", "Kaylee", "Kayleigh", "Kaylie", "Kaylin", "Kehlani", "Keila", "Keira", "Keiry",
    "Kelli", "Kellie", "Kelly", "Kelsey", "Kelsie", "Kendall", "Kendra", "Kenia", "Kenna", "Kennedi",
    "Kennedy", "Kenzie", "Keri", "Kerri", "Kerry", "Keyla", "Khloe", "Kiana", "Kianna", "Kiara",
    "Kiera", "Kierra", "Kiersten", "Kiley", "Kim", "Kimberly", "Kinsley", "Kinsey", "Kinzlee", "Kinzley",
    "Kira", "Kirsten", "Kirstin", "Kirsty", "Kit", "Kitty", "Kora", "Kori", "Kortney", "Kourtney",
    "Krista", "Kristen", "Kristi", "Kristie", "Kristin", "Kristina", "Kristine", "Kristy", "Krystal", "Kyla",
    "Kylee", "Kyleigh", "Kylie", "Kyra", "Lacey", "Laila", "Lailah", "Lainey", "Lana", "Laney",
    "Lara", "Larissa", "Laura", "Laurel", "Lauren", "Laurie", "Layla", "Laylah", "Lea", "Leah",
    "Leanna", "Leanne", "Legacy", "Leia", "Leila", "Leilani", "Leilany", "Lena", "Lenora", "Leona",
    "Leonora", "Leslie", "Lesly", "Leticia", "Lettie", "Lexi", "Lexie", "Leyla", "Lia", "Liana",
    "Liane", "Libby", "Liberty", "Lidia", "Lila", "Lilah", "Liliana", "Lilianna", "Lilianne", "Lilith",
    "Lillian", "Lilliana", "Lillianna", "Lillie", "Lilly", "Lily", "Lina", "Linda", "Lindsay", "Lindsey",
    "Lisa", "Lisette", "Liv", "Livia", "Liz", "Liza", "Lizbeth", "Lizeth", "Lois", "Lola",
    "Lolita", "London", "Londyn", "Lora", "Loraine", "Lorelai", "Lorelei", "Lorena", "Loretta", "Lori",
    "Lorna", "Lorraine", "Lottie", "Louise", "Lourdes", "Lucia", "Lucille", "Lucinda", "Lucy", "Luisa",
    "Lulu", "Luna", "Luz", "Lydia", "Lyla", "Lynda", "Lynn", "Lynne", "Lynnette", "Lyric",
    "Mabel", "Mabelle", "Mable", "Maci", "Macie", "Mackenzie", "Macy", "Madalyn", "Maddie", "Maddison",
    "Madeline", "Madelyn", "Madelynn", "Madilyn", "Madisyn", "Madison", "Mae", "Maeve", "Magdalena", "Maggie",
    "Magnolia", "Maia", "Maisie", "Makayla", "Makenna", "Makenzie", "Malani", "Malaya", "Malayah", "Maleah",
    "Malia", "Maliah", "Malinda", "Mallory", "Mara", "Marcela", "Marceline", "Marcella", "Marcelle", "Marcia",
    "Marcy", "Margaret", "Margarita", "Margo", "Margot", "Mari", "Maria", "Mariah", "Mariam", "Mariana",
    "Marianna", "Marianne", "Maribel", "Maricela", "Marie", "Mariela", "Marilyn", "Marina", "Marion", "Marisa",
    "Marisol", "Marissa", "Maritza", "Marjorie", "Marley", "Marna", "Marnie", "Marsha", "Marta", "Martha",
    "Martina", "Mary", "Maryam", "Maryann", "Maryanne", "Marylou", "Matilda", "Mattie", "Maude", "Maureen",
    "Mavis", "Max", "Maxine", "May", "Maya", "Mayra", "Mazikeen", "Mckenna", "Mckenzie", "Mckinley",
    "Meagan", "Megan", "Meghan", "Megumi", "Mei", "Melanie", "Melany", "Melinda", "Melisa", "Melissa",
    "Melody", "Mercedes", "Meredith", "Mia", "Micaela", "Micah", "Michaela", "Michele", "Michelle", "Mikaela",
    "Mikayla", "Mila", "Milagros", "Milan", "Milana", "Milani", "Mildred", "Milena", "Millie", "Mina",
    "Mindy", "Minerva", "Mira", "Miranda", "Miriam", "Misty", "Miya", "Mollie", "Molly", "Mona",
    "Monica", "Monique", "Montserrat", "Morgan", "Mya", "Myah", "Myla", "Myra", "Myrtle", "Nadia",
    "Nadine", "Nahla", "Nancy", "Naomi", "Natalia", "Natalie", "Natasha", "Nathalie", "Navy", "Nayeli",
    "Nellie", "Nelly", "Neriah", "Nevaeh", "Nia", "Nicole", "Nicolette", "Nikki", "Nina", "Nita",
    "Noa", "Noel", "Noelia", "Noelle", "Noemi", "Nola", "Nora", "Norah", "Noreen", "Norma",
    "Nova", "Nyla", "Nylah", "Oaklee", "Oakleigh", "Oakley", "Oaklyn", "Oaklynn", "Octavia", "Odessa",
    "Odette", "Olga", "Olive", "Olivia", "Opal", "Ophelia", "Ora", "Oriana", "Paola", "Paris",
    "Parker", "Patience", "Patricia", "Patsy", "Patty", "Paula", "Paulette", "Paulina", "Pauline", "Payton",
    "Pearl", "Peggy", "Penelope", "Penny", "Perla", "Persephone", "Petra", "Peyton", "Phoebe", "Phoenix",
    "Phyllis", "Piper", "Pippa", "Polina", "Polly", "Poppy", "Precious", "Presley", "Princess", "Priscilla",
    "Promise", "Prudence", "Quinn", "Rachael", "Rachel", "Rachelle", "Raegan", "Raelyn", "Raina", "Ramona",
    "Ramsey", "Randi", "Raquel", "Raven", "Rayna", "Rayne", "Reagan", "Rebecca", "Rebekah", "Reese",
    "Regina", "Reina", "Remi", "Remington", "Remy", "Renata", "Rene", "Renee", "Reyna", "Rhea",
    "Rhoda", "Rhonda", "Rian", "Ria", "Riley", "Rina", "Rita", "River", "Rivka", "Roberta",
    "Robin", "Robyn", "Rochelle", "Rocky", "Rocio", "Rory", "Rosa", "Rosalie", "Rosalin", "Rosalind",
    "Rosalinda", "Rosalyn", "Rosanna", "Rosanne", "Rose", "Roselyn", "Rosemary", "Rosie", "Roslyn", "Rowan",
    "Roxana", "Roxanne", "Roxie", "Roxy", "Ruby", "Ruth", "Ruthie", "Ryan", "Ryann", "Rylan",
    "Rylee", "Ryleigh", "Rylie", "Sabrina", "Sade", "Sadie", "Sage", "Saige", "Sally", "Salma",
    "Samantha", "Samara", "Samira", "Sandra", "Sandy", "Sanjuana", "Saoirse", "Sara", "Sarah", "Sarai",
    "Sarahi", "Sarina", "Sasha", "Savannah", "Sawyer", "Saylor", "Scarlett", "Scout", "Selah", "Selena",
    "Selene", "Selma", "Serena", "Serenity", "Shaina", "Shakira", "Shana", "Shania", "Shannon", "Shari",
    "Sharon", "Shauna", "Shawn", "Shawna", "Shayla", "Shayna", "Shea", "Sheila", "Shelby", "Shelley",
    "Shelly", "Sheri", "Sherri", "Sherry", "Sheryl", "Shiloh", "Shirley", "Sidney", "Sienna", "Sierra",
    "Silvana", "Silvia", "Simone", "Sky", "Skye", "Skyla", "Skylar", "Skylark", "Sloane", "Sofia",
    "Sofie", "Solana", "Solange", "Sonia", "Sonja", "Sonya", "Sophia", "Sophie", "Soraya", "Spencer",
    "Stacey", "Stacie", "Stacy", "Star", "Starla", "Stella", "Stephanie", "Stevie", "Stormi", "Sue",
    "Susan", "Susanna", "Susannah", "Susie", "Suzanne", "Suzette", "Sutton", "Svetlana", "Sybil", "Sydney",
    "Sylvia", "Sylvie", "Tabitha", "Tahlia", "Talia", "Tamara", "Tamera", "Tami", "Tammy", "Tania",
    "Tanya", "Tara", "Tasha", "Tatiana", "Tatum", "Taylor", "Teagan", "Teresa", "Teri", "Terri",
    "Terry", "Tess", "Tessa", "Thalia", "Thea", "Thelma", "Theodora", "Theresa", "Therese", "Tia",
    "Tiana", "Tianna", "Tiffany", "Tina", "Tinsley", "Toni", "Tonia", "Tonya", "Tori", "Tracey",
    "Traci", "Tracie", "Tracy", "Trinity", "Trisha", "Trudy", "Tuesday", "Turner", "Tyra", "Ursula",
    "Valentina", "Valerie", "Valery", "Vanessa", "Vanna", "Vera", "Veronica", "Vicki", "Vickie", "Vicky",
    "Victoria", "Vienna", "Violet", "Violeta", "Violette", "Virginia", "Vivian", "Viviana", "Vivienne", "Wanda",
    "Wendy", "Whitney", "Willa", "Willie", "Willow", "Wilma", "Winifred", "Winnie", "Wren", "Wynter",
    "Ximena", "Xiomara", "Yael", "Yahaira", "Yana", "Yara", "Yareli", "Yaretzi", "Yasmin", "Yasmine",
    "Yesenia", "Yolanda", "Yvette", "Yvonne", "Zaina", "Zainab", "Zaniyah", "Zara", "Zaria", "Zariyah",
    "Zelda", "Zella", "Zhavia", "Zinnia", "Ziva", "Zoé", "Zoey", "Zoie", "Zola", "Zora",
    "Zoya", "Zuri"
]

# Definition for the list of 500 male names
MALE_NAMES = [
    "Aaron", "Abel", "Abraham", "Abram", "Ace", "Adam", "Adan", "Aden", "Adonis", "Adrian",
    "Adrien", "Agustin", "Ahmed", "Aidan", "Aiden", "Alan", "Albert", "Alberto", "Aldo", "Alec",
    "Alejandro", "Alessandro", "Alex", "Alexander", "Alexzander", "Alfie", "Alfonso", "Alfred", "Alfredo", "Ali",
    "Allan", "Allen", "Alonzo", "Alonso", "Alistair", "Alvaro", "Alvin", "Amari", "Amaru", "Ambrose",
    "Amir", "Amos", "Anders", "Anderson", "Andre", "Andres", "Andrew", "Andy", "Angel", "Angelo",
    "Angus", "Anson", "Anthony", "Anton", "Antonio", "Apollo", "Archer", "Archie", "Arden", "Ares",
    "Ari", "Aris", "Ariel", "Arlo", "Armand", "Armando", "Armani", "Arnold", "Aron", "Arthur",
    "Arturo", "Aryan", "Asa", "Asher", "Ashley", "Ashton", "Atticus", "August", "Augustin", "Augustine",
    "Augustus", "Aurelio", "Austin", "Avery", "Axel", "Ayden", "Aydin", "Baker", "Banks", "Baptiste",
    "Baron", "Barrett", "Barry", "Bart", "Bartholomew", "Basil", "Beau", "Beck", "Beckett", "Beckham",
    "Ben", "Benedict", "Benjamin", "Benji", "Bennett", "Benson", "Bentley", "Bernard", "Bernardo", "Bernie",
    "Bilal", "Bill", "Billy", "Bjorn", "Blaine", "Blair", "Blaise", "Blake", "Blaze", "Bo",
    "Bobby", "Boden", "Bodhi", "Booker", "Boris", "Boston", "Bowen", "Brad", "Braden", "Bradford",
    "Bradley", "Brady", "Braeden", "Brandon", "Brandt", "Brantley", "Braxton", "Brayan", "Brayden", "Braylen",
    "Braylon", "Breck", "Brendan", "Brenden", "Brennan", "Brent", "Brenton", "Brett", "Brian", "Brice",
    "Bridger", "Briggs", "Brighton", "Brixton", "Brock", "Brodie", "Brody", "Bronson", "Brooks", "Bruce",
    "Bruno", "Bryan", "Bryant", "Bryce", "Brycen", "Bryson", "Byron", "Cade", "Caden", "Cael",
    "Cain", "Caius", "Cal", "Caleb", "Callum", "Calvin", "Camden", "Camdyn", "Cameron", "Campbell",
    "Camron", "Camryn", "Cannon", "Carl", "Carlo", "Carlos", "Carlton", "Carmelo", "Carson", "Carter",
    "Case", "Casen", "Casey", "Cash", "Cason", "Caspian", "Cassian", "Cassius", "Castiel", "Castle",
    "Cato", "Cayden", "Cecil", "Cedric", "Cesar", "Chad", "Chance", "Chandler", "Charles", "Charley",
    "Charlie", "Chase", "Chaim", "Chester", "Chet", "Chris", "Christian", "Christopher", "Chuck", "Cillian",
    "Clark", "Claude", "Clay", "Clayton", "Cleo", "Clement", "Clete", "Cleveland", "Cliff", "Clifford",
    "Clint", "Clinton", "Clive", "Clyde", "Cody", "Cohen", "Colby", "Cole", "Coleman", "Colin",
    "Collin", "Colt", "Colter", "Colton", "Conan", "Conner", "Connor", "Conrad", "Cooper", "Corbin",
    "Corey", "Cormac", "Cornelius", "Cory", "Craig", "Crew", "Crispin", "Cristiano", "Cristian", "Crosby",
    "Cruz", "Cullen", "Curtis", "Curt", "Cyrus", "Dale", "Dallas", "Dalton", "Damian", "Damien",
    "Damon", "Dan", "Dane", "Daniel", "Danny", "Dante", "Dario", "Darius", "Darrell", "Darren",
    "Darryl", "Darwin", "Daryl", "Dash", "Dave", "David", "Davian", "Davion", "Davis", "Dawson",
    "Dax", "Daxton", "Dayton", "Dean", "Declan", "Dedric", "Deegan", "Deen", "Dennis", "Denny",
    "Derek", "Derrick", "Desmond", "Devin", "Devon", "Dexter", "Diego", "Dillon", "Dimitri", "Dion",
    "Dirk", "Dominic", "Dominick", "Donald", "Donnie", "Donovan", "Dorian", "Doug", "Douglas", "Drake",
    "Drew", "Duane", "Duke", "Duncan", "Dustin", "Dwayne", "Dwight", "Dylan", "Ean", "Earl",
    "Easton", "Ed", "Eddie", "Eddy", "Edgar", "Edmundo", "Eduardo", "Edward", "Edwin", "Egan",
    "Eitan", "Eli", "Elian", "Elias", "Eliezer", "Elijah", "Elio", "Eliot", "Elisha", "Elliot",
    "Elliott", "Ellis", "Elmer", "Elmo", "Elton", "Elvis", "Emanuel", "Emerson", "Emery", "Emmet",
    "Emmett", "Emmanuel", "Enoch", "Enos", "Enrique", "Enzo", "Ephraim", "Eric", "Erick", "Erik",
    "Ernest", "Ernesto", "Ernie", "Erwin", "Esteban", "Ethan", "Etienne", "Eugene", "Evan", "Evander",
    "Everett", "Ewan", "Ezekiel", "Ezra", "Fabian", "Fabio", "Felipe", "Felix", "Fernando", "Fidel",
    "Finn", "Finnian", "Finnegan", "Finnley", "Fisher", "Fletcher", "Flynn", "Ford", "Forest", "Forrest",
    "Foster", "Fox", "Francis", "Francisco", "Franco", "Frank", "Frankie", "Franklin", "Fraser", "Fred",
    "Freddie", "Freddy", "Frederick", "Gabe", "Gabriel", "Gael", "Gage", "Galen", "Garland", "Garrett",
    "Garrison", "Garth", "Gary", "Gavin", "Gene", "Geoffrey", "George", "Gerald", "Gerard", "Gerardo",
    "German", "Gianni", "Gideon", "Gilbert", "Gilberto", "Gino", "Giovanni", "Glen", "Glenn", "Gordon",
    "Grady", "Graham", "Grant", "Graysen", "Grayson", "Greg", "Gregg", "Gregory", "Greyson", "Griffin",
    "Guadalupe", "Guillermo", "Gunnar", "Gunner", "Gus", "Gustavo", "Guy", "Haden", "Hamza", "Hank",
    "Hans", "Harlan", "Harlem", "Harley", "Harold", "Harris", "Harrison", "Harry", "Harvey", "Hassan",
    "Hayden", "Hayes", "Heath", "Hector", "Hendrix", "Henrik", "Henry", "Herbert", "Herman", "Hezekiah",
    "Holden", "Howard", "Hudson", "Hugh", "Hugo", "Humberto", "Hunter", "Hussein", "Ian", "Ibrahim",
    "Idris", "Ignacio", "Iker", "Immanuel", "Imran", "Indiana", "Ira", "Irvin", "Irving", "Isaac",
    "Isaiah", "Isaias", "Ishaan", "Ismael", "Israel", "Issac", "Ivan", "Izaiah", "Jace", "Jack",
    "Jackson", "Jacob", "Jacoby", "Jaden", "Jadiel", "Jagger", "Jaiden", "Jaime", "Jair", "Jairo",
    "Jake", "Jakob", "Jakobe", "Jalen", "Jamal", "Jamar", "Jamari", "James", "Jameson", "Jamie",
    "Jamir", "Jamison", "Jan", "Jared", "Jaron", "Jarrett", "Jarvis", "Jason", "Jasper", "Javier",
    "Javion", "Jax", "Jaxon", "Jaxson", "Jay", "Jayce", "Jayceon", "Jaycob", "Jayden", "Jaylen",
    "Jaylin", "Jaylon", "Jayson", "Jean", "Jedidiah", "Jeff", "Jefferson", "Jeffery", "Jeffrey", "Jensen",
    "Jeremiah", "Jeremias", "Jeremy", "Jericho", "Jermaine", "Jerome", "Jerry", "Jesse", "Jesus", "Jett",
    "Jevon", "Jim", "Jimmie", "Jimmy", "Joaquin", "Joe", "Joel", "Joey", "Johan", "John",
    "Johnathan", "Johnathon", "Johnny", "Jon", "Jonah", "Jonas", "Jonathan", "Jonathon", "Jordan", "Jorden",
    "Jordi", "Jordon", "Jorge", "Jose", "Joseph", "Josh", "Joshua", "Josiah", "Josue", "Jovan",
    "Jovani", "Jovanni", "Juan", "Judah", "Judd", "Jude", "Julian", "Julien", "Julio", "Julius",
    "Junior", "Justice", "Justin", "Justus", "Kade", "Kaden", "Kai", "Kaiden", "Kaiser", "Kaleb",
    "Kalel", "Kamari", "Kamden", "Kameron", "Kamryn", "Kane", "Kareem", "Karl", "Karson", "Karter",
    "Kasen", "Kash", "Kason", "Kayden", "Kaysen", "Kayson", "Keanu", "Keaton", "Keegan", "Keenan",
    "Keith", "Kellan", "Kellen", "Kelly", "Kelvin", "Ken", "Kendall", "Kendrick", "Kenneth", "Kenny",
    "Kent", "Kenton", "Kenzo", "Kevin", "Khalid", "Khalil", "Kian", "Kieran", "Killian", "King",
    "Kingsley", "Kingston", "Klaus", "Knox", "Kobe", "Kody", "Kohen", "Kolten", "Kolton", "Konnor",
    "Konrad", "Korbyn", "Korey", "Kory", "Kristian", "Kristoff", "Kristopher", "Kurt", "Kurtis", "Kye",
    "Kylan", "Kylar", "Kyle", "Kyler", "Kylian", "Kylo", "Kyree", "Kyrie", "Kyson", "Lamar",
    "Lance", "Landen", "Landon", "Landry", "Landyn", "Lane", "Langston", "Larry", "Lars", "Lawrence",
    "Lawson", "Layne", "Layton", "Leandro", "Lee", "Legend", "Leif", "Leighton", "Leland", "Lennon",
    "Lennox", "Leo", "Leon", "Leonard", "Leonardo", "Leonel", "Leonidas", "Leroy", "Levi", "Lewis",
    "Liam", "Lincoln", "Link", "Lionel", "Lloyd", "Lochlan", "Logan", "London", "Lonnie", "Loren",
    "Lorenzo", "Louis", "Louie", "Lowen", "Luca", "Lucas", "Lucian", "Luciano", "Luis", "Luka",
    "Lukas", "Luke", "Luther", "Lyle", "Lyndon", "Lyric", "Mac", "Mack", "Madden", "Maddox",
    "Magnus", "Major", "Makai", "Makhi", "Malachi", "Malakai", "Malcolm", "Malik", "Manuel", "Marc",
    "Marcel", "Marcellus", "Marcelo", "Marco", "Marcos", "Marcus", "Mario", "Marion", "Mark", "Marlon",
    "Marquis", "Marshall", "Martin", "Marvin", "Mason", "Massimo", "Mateo", "Mathew", "Mathias", "Matias",
    "Matt", "Matteo", "Matthew", "Maurice", "Mauricio", "Maverick", "Max", "Maxim", "Maximilian", "Maximiliano",
    "Maximo", "Maxwell", "Maxton", "Mayson", "Mekhi", "Melvin", "Memphis", "Messiah", "Micah", "Michael",
    "Micheal", "Miguel", "Mike", "Mikael", "Milan", "Miles", "Miller", "Milo", "Misael", "Mitchell",
    "Mohamed", "Mohammad", "Mohammed", "Moises", "Monte", "Morgan", "Moses", "Moshe", "Muhammad", "Mustafa",
    "Myles", "Mylo", "Nash", "Nasir", "Nathan", "Nathanael", "Nathaniel", "Nehemiah", "Neil", "Nelson",
    "Neymar", "Nicholas", "Nick", "Nickolas", "Nico", "Niko", "Nikolai", "Nikolas", "Nixon", "Noah",
    "Noe", "Noel", "Nolan", "Norman", "Odin", "Oliver", "Ollie", "Omar", "Omari", "Orion",
    "Orlando", "Osbaldo", "Oscar", "Osvaldo", "Otis", "Otto", "Owen", "Ozzy", "Pablo", "Parker",
    "Pascal", "Patrick", "Paul", "Paxton", "Payton", "Pedro", "Percy", "Perry", "Peter", "Peyton",
    "Philip", "Phillip", "Phoenix", "Pierce", "Pierre", "Porter", "Preston", "Prince", "Princeton", "Quentin",
    "Quincy", "Quinn", "Quinton", "Rafael", "Raiden", "Ralph", "Ramiro", "Ramon", "Ramsey", "Randall",
    "Randy", "Raphael", "Raul", "Ray", "Rayan", "Raylan", "Raymond", "Reagan", "Reece", "Reed",
    "Reese", "Reginald", "Reid", "Reign", "Remi", "Remington", "Remy", "Renato", "Rene", "Reuben",
    "Rex", "Rey", "Reyansh", "Rhett", "Rhys", "Ricardo", "Richard", "Richie", "Rick", "Rickey",
    "Ricky", "Rico", "Ridge", "Riggs", "Riley", "River", "Robby", "Robert", "Roberto", "Robin",
    "Rocco", "Rocky", "Rodney", "Rodrigo", "Rogelio", "Roger", "Rohan", "Roland", "Rolando", "Roman",
    "Rome", "Romeo", "Ronald", "Ronan", "Ronin", "Ronnie", "Rory", "Rosendo", "Ross", "Rowan",
    "Rowen", "Roy", "Royal", "Royce", "Ruben", "Rudy", "Russell", "Ryan", "Ryder", "Ryker",
    "Rylan", "Ryland", "Sage", "Saint", "Sal", "Salvador", "Salvatore", "Sam", "Samir", "Samson",
    "Samuel", "Santana", "Santiago", "Santino", "Santos", "Saul", "Sawyer", "Scott", "Scottie", "Seamus",
    "Sean", "Sebastian", "Semaj", "Sergio", "Seth", "Shane", "Shaun", "Shawn", "Sheldon", "Shepherd",
    "Sheppard", "Sherman", "Shiloh", "Silas", "Simeon", "Simon", "Sincere", "Skyler", "Solomon", "Sonny",
    "Soren", "Spencer", "Stanley", "Stefan", "Stephan", "Stephen", "Sterling", "Steve", "Steven", "Stetson",
    "Stewart", "Stone", "Stuart", "Sullivan", "Sutton", "Sylas", "Tadeo", "Talon", "Tanner", "Tariq",
    "Tate", "Tatum", "Taylor", "Ted", "Teddy", "Terence", "Terrance", "Terrell", "Terrence", "Terry",
    "Thaddeus", "Theo", "Theodore", "Thiago", "Thomas", "Timothy", "Titan", "Titus", "Tobias", "Toby",
    "Todd", "Tomas", "Tommy", "Tony", "Trace", "Travis", "Trent", "Trenton", "Trevor", "Trey",
    "Tristan", "Tristen", "Tristian", "Troy", "Tru", "Truett", "Tucker", "Turner", "Ty", "Tyler",
    "Tyson", "Ulises", "Uriel", "Uriah", "Valentin", "Valentino", "Van", "Vance", "Vaughn", "Vicente",
    "Victor", "Vihaan", "Vincent", "Vincenzo", "Virgil", "Wade", "Walker", "Wallace", "Walter", "Warren",
    "Watson", "Waylon", "Wayne", "Wells", "Wes", "Wesley", "Wesson", "Westin", "Westley", "Weston",
    "Will", "William", "Willie", "Willis", "Wilson", "Winston", "Wyatt", "Xander", "Xavier", "Xzavier",
    "Yadiel", "Yahir", "Yair", "Yandel", "Yanis", "Yael", "Yosef", "Yousef", "Yusuf", "Zachariah",
    "Zachary", "Zachery", "Zack", "Zackary", "Zackery", "Zaid", "Zain", "Zaire", "Zakai", "Zander",
    "Zane", "Zavier", "Zayden", "Zayn", "Zayne", "Zechariah", "Zeke", "Zion", "Zyan"
]
# --- End of name lists ---


def simple_html_strip(html_content):
    """Basic HTML tag removal for keyword searching."""
    if not html_content:
        return ""
    try:
        # Use BeautifulSoup for more robust stripping
        soup = BeautifulSoup(html_content, "html.parser")
        return soup.get_text(separator=' ', strip=True)
    except Exception:
        # Fallback regex (less reliable)
        return re.sub(r'<[^>]+>', ' ', html_content)

def check_keywords(text, keywords):
    """Check if any keyword exists as a whole word in the text (case-insensitive)."""
    if not text:
        return False
    # Use word boundaries (\b) to match whole words only
    # Join keywords into a regex pattern: \b(word1|word2|...)\b
    pattern = r"\b(" + "|".join(re.escape(k) for k in keywords) + r")\b"
    return bool(re.search(pattern, text, re.IGNORECASE))

def determine_product_gender(product_data):
    """
    Analyzes product data (type, tags, title, description) to determine gender.
    Returns 'female', 'male', or 'neutral'.
    """
    if not product_data:
        return 'neutral' # Default if no data

    # Get fields and convert to lowercase for matching
    p_type = product_data.get('product_type', '').lower()
    # Tags might be a comma-separated string or already a list, handle both
    tags_data = product_data.get('tags', '')
    tags_string = tags_data.lower() if isinstance(tags_data, str) else ' '.join(t.lower() for t in tags_data)
    title = product_data.get('title', '').lower()
    # Strip HTML from description before checking
    description = simple_html_strip(product_data.get('body_html', '')).lower()

    # --- Check Priority: Type & Tags first ---
    if check_keywords(p_type, NEUTRAL_KEYWORDS) or check_keywords(tags_string, NEUTRAL_KEYWORDS):
        logger.info(f"[{product_data.get('id')}] Gender determined as NEUTRAL based on type/tags.")
        return 'neutral'
    if check_keywords(p_type, FEMALE_KEYWORDS) or check_keywords(tags_string, FEMALE_KEYWORDS):
        logger.info(f"[{product_data.get('id')}] Gender determined as FEMALE based on type/tags.")
        return 'female'
    if check_keywords(p_type, MALE_KEYWORDS) or check_keywords(tags_string, MALE_KEYWORDS):
         logger.info(f"[{product_data.get('id')}] Gender determined as MALE based on type/tags.")
         return 'male'

    # --- Check Title ---
    if check_keywords(title, NEUTRAL_KEYWORDS):
        logger.info(f"[{product_data.get('id')}] Gender determined as NEUTRAL based on title.")
        return 'neutral'
    if check_keywords(title, FEMALE_KEYWORDS):
         logger.info(f"[{product_data.get('id')}] Gender determined as FEMALE based on title.")
         return 'female'
    if check_keywords(title, MALE_KEYWORDS):
        logger.info(f"[{product_data.get('id')}] Gender determined as MALE based on title.")
        return 'male'

    # --- Check Description (less reliable, check last) ---
    # Consider limiting description length checked for performance: e.g., description[:500]
    if check_keywords(description, NEUTRAL_KEYWORDS):
        logger.info(f"[{product_data.get('id')}] Gender determined as NEUTRAL based on description.")
        return 'neutral'
    if check_keywords(description, FEMALE_KEYWORDS):
        logger.info(f"[{product_data.get('id')}] Gender determined as FEMALE based on description.")
        return 'female'
    if check_keywords(description, MALE_KEYWORDS):
        logger.info(f"[{product_data.get('id')}] Gender determined as MALE based on description.")
        return 'male'

    # --- Default ---
    logger.info(f"[{product_data.get('id')}] No clear gender keywords found. Defaulting to NEUTRAL.")
    return 'neutral'

ALL_NAMES = FEMALE_NAMES + MALE_NAMES

def get_random_female_name():
  """Returns a randomly selected female name from the list."""
  if not FEMALE_NAMES:
    return "No female names loaded"
  return random.choice(FEMALE_NAMES)

def get_random_male_name():
  """Returns a randomly selected male name from the list."""
  if not MALE_NAMES:
    return "No male names loaded"
  return random.choice(MALE_NAMES)

def get_random_name():
  """Returns a randomly selected name from the combined list of male and female names."""
  if not ALL_NAMES:
    return "No names loaded"
  return random.choice(ALL_NAMES)

# Example of how to use the functions when the script is run directly
if __name__ == "__main__":
  print("Generating random names:")
  print(f"Random Female Name: {get_random_female_name()}")
  print(f"Random Male Name:   {get_random_male_name()}")
  print(f"Random Name (any):  {get_random_name()}")

  print("\nGenerating 5 random names:")
  for _ in range(5):
      print(get_random_name())

