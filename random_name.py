# random_name.py
import random
from bs4 import BeautifulSoup # Make sure BeautifulSoup is imported
import re
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Gender Keyword Sets (Expanded)

FEMALE_KEYWORDS = {
    # --- English (EN) ---
    # General & Identity
    'women', 'woman', 'womens', 'female', 'ladies', 'lady', 'girl', 'girls',
    'she', 'her', 'hers', 'feminine', 'gal', 'miss', 'ms', 'mrs', 'maiden', 'diva',
    'mother', 'mom', 'mum', 'mummy', 'mommy', 'sister', 'daughter', 'aunt', 'grandmother', # Relational, often used in gifting context
    'bride', 'bridesmaid', 'bachelorette', 'hen party', # Event specific

    # Clothing - Tops & Dresses
    'dress', 'gown', 'frock', 'sundress', 'maxi dress', 'midi dress', 'mini dress', 'shift dress', 'wrap dress', 'sheath dress', 'cocktail dress', 'evening dress', 'ballgown', 'tea dress', 'fit and flare', 'empire waist',
    'skirt', 'maxi skirt', 'midi skirt', 'mini skirt', 'pencil skirt', 'a-line skirt', 'pleated skirt', 'wrap skirt', 'skort',
    'blouse', 'chemise', 'camisole', 'cami', 'tunic', 'peplum', 'halter top', 'crop top', 'tank top', 'tube top', 'shell top', 'womens top', 'ladies top',
    'bodysuit', 'leotard',

    # Clothing - Bottoms
    'leggings', 'jeggings', 'capris', 'culottes', 'palazzo pants', 'womens trousers', 'womens pants', # Qualified

    # Clothing - Outerwear & Layers
    'cardigan', 'shrug', 'bolero', 'kimono', 'poncho', 'shawl', 'wrap', 'cape', 'stole', 'pashmina', 'womens jacket', 'ladies coat', 'womens blazer', 'trench coat women', # Qualified or typically female styles

    # Clothing - Lingerie & Sleepwear
    'lingerie', 'bra', 'bralette', 'push-up', 'bandeau', 'sports bra', 'underwire', 'non-wired',
    'panty', 'panties', 'thong', 'g-string', 'briefs', # Often female context unless specified 'mens briefs'
    'knickers', 'hipster', 'boyshorts', # Typically female underwear styles despite name
    'shapewear', 'bodyshaper', 'waist cincher', 'corselet', 'girdle', 'control brief',
    'nightgown', 'nightie', 'chemise', 'babydoll', 'negligee', 'sleepshirt', 'teddy', 'sleepwear', 'loungewear', # Often female styled
    'petticoat', 'hoopskirt', 'bustier', 'corset', 'garter', 'garter belt', 'suspenders', # Often lingerie context

    # Clothing - Swim & Activewear
    'bikini', 'tankini', 'monokini', 'swimsuit', 'bathing suit', 'swim dress', 'one-piece', 'cover-up', 'beachwear',
    'sports bra', 'yoga pants', 'activewear', 'sportswear', 'athletic wear', # Often neutral but heavily marketed to women

    # Clothing - Other
    'romper', 'jumpsuit', 'playsuit', 'maternity wear', 'nursing top', 'nursing bra', 'plus size', 'petite', 'womens fashion', # Size/Fit/General specific

    # Shoes
    'heels', 'pumps', 'stilettos', 'kitten heels', 'slingbacks', 'court shoes',
    'wedges', 'espadrilles', 'platforms',
    'flats', 'ballet flats', 'ballerinas', 'loafers', 'mules', 'd\'orsay', # Can be female styled
    'sandals', 'gladiators', 'thong sandals', 'flip-flops', # Flip-flops neutral, but styled sandals often female
    'booties', 'ankle boots', 'knee-high boots', 'over-the-knee boots', 'womens boots', # Often female styles

    # Accessories - Bags
    'purse', 'handbag', 'clutch', 'tote', 'satchel', 'crossbody bag', 'shoulder bag', 'wristlet', 'evening bag', 'hobo bag', 'bucket bag', 'minaudiere', 'womens bag',

    # Accessories - Jewelry
    'jewelry', 'jewellery', 'earrings', 'studs', 'hoops', 'dangles', 'drop earrings', 'ear cuffs',
    'necklace', 'pendant', 'locket', 'choker', 'chain', # Often female context
    'bracelet', 'bangle', 'charm bracelet', 'cuff bracelet', 'anklet',
    'ring', 'engagement ring', 'wedding band', 'eternity ring', # Often context specific
    'brooch', 'pin', 'lapel pin', # Sometimes female

    # Accessories - Hair & Headwear
    'tiara', 'diadem', 'headband', 'hairband', 'hair clip', 'barrette', 'hair pin', 'bobby pin', 'comb', 'hair accessory',
    'scrunchie', 'hair tie', 'ponytail holder', 'fascinator', 'millinery', 'sun hat', 'cloche', 'beret', 'beanie', # Hat styles often female
    'veil', 'headscarf',

    # Accessories - Other
    'scarf', 'pashmina', 'neckerchief', 'ascot', # Female styled ascot
    'gloves', 'mittens', 'opera gloves', # Often female styled versions
    'belt', 'waist belt', 'obi belt', # Often female styled versions
    'sunglasses', 'eyewear', 'cat eye glasses', # Often female styled versions
    'tights', 'pantyhose', 'stockings', 'fishnets', 'hosiery', 'thigh-highs', 'hold-ups', 'leg warmers',
    'compact mirror', 'fan', # Hand fan

    # Beauty & Care
    'cosmetic', 'cosmetics', 'makeup', 'beauty', 'vanity case',
    'lipstick', 'lip gloss', 'lip balm', 'lip stain', 'lipliner',
    'eyeliner', 'kohl', 'eyeshadow', 'mascara', 'eyebrow pencil', 'brow gel', 'false eyelashes', 'lash curler',
    'foundation', 'concealer', 'bb cream', 'cc cream', 'primer', 'setting spray', 'setting powder', 'face powder',
    'blush', 'blusher', 'rouge', 'bronzer', 'highlighter', 'illuminator', 'contour',
    'nail polish', 'nail lacquer', 'nail varnish', 'manicure', 'pedicure', 'nail art', 'false nails', 'nail file', 'cuticle oil',
    'perfume', 'fragrance', 'eau de parfum', 'edp', 'eau de toilette', 'edt', 'body spray', 'scent', 'atomizer', # Often gendered
    'skincare', 'moisturizer', 'serum', 'cleanser', 'toner', 'face wash', 'face mask', 'eye cream', 'anti-aging', 'anti-wrinkle', 'exfoliant', 'scrub', 'peel', 'sunscreen', 'spf', # SPF is neutral but common in female marketed products
    'hair removal', 'waxing', 'epilator', 'depilatory', 'threading', 'laser hair removal',
    'feminine hygiene', 'menstrual', 'tampon', 'sanitary pad', 'panty liner', 'menstrual cup',

    # --- German (DE) ---
    # General & Identity
    'damen', 'frau', 'frauen', 'mädchen', 'weiblich', 'feminin', 'fräulein', 'maid', 'sie', 'ihr', 'ihre',
    'mutter', 'mutti', 'mama', 'schwester', 'tochter', 'tante', 'großmutter', 'oma',
    'braut', 'brautjungfer', 'polterabend', 'junggesellinnenabschied',

    # Clothing - Tops & Dresses
    'kleid', 'abendkleid', 'ballkleid', 'cocktailkleid', 'sommerkleid', 'maxikleid', 'midikleid', 'minikleid', 'etuikleid', 'wickelkleid', 'hosenkleid', 'strandkleid', 'dirndl',
    'rock', 'maxirock', 'midirock', 'minirock', 'bleistiftrock', 'faltenrock', 'wickelrock', 'hosenrock',
    'bluse', 'hemdbluse', 'damenhemd', 'tunika', 'top', 'damenshirt', 'tanktop', 'trägertop', 'neckholder', 'bauchfrei', 'oberteil',
    'body', 'overall', 'mieder',

    # Clothing - Bottoms
    'damenhose', 'stoffhose', 'leggings', 'jeggings', 'caprihose', 'culotte', 'palazzo hose', 'damenjeans',

    # Clothing - Outerwear & Layers
    'strickjacke', 'cardigan', 'bolero', 'jäckchen', 'kimono', 'poncho', 'stola', 'umhang', 'damenjacke', 'damenmantel', 'damenblazer', 'trenchcoat', # Female styled

    # Clothing - Lingerie & Sleepwear
    'damenwäsche', 'reizwäsche', 'unterwäsche', 'dessous', 'büstenhalter', 'bh', 'bralette', 'push-up-bh', 'bügel-bh', 'sport-bh',
    'slip', 'damenslip', 'panty', 'hüftslip', 'string', 'tanga', 'unterhose',
    'shapewear', 'formwäsche', 'miederhose', 'taillenformer', 'korsett', 'corsage',
    'nachthemd', 'schlafshirt', 'negligee', 'babydoll', 'morgenmantel', 'schlafanzug', 'pyjama', # Female styled
    'unterrock', 'reifrock', 'strapse', 'strumpfhalter',

    # Clothing - Swim & Activewear
    'badeanzug', 'bikini', 'tankini', 'monokini', 'badekleid', 'einteiler', 'strandmode', 'pareo', 'sarong',
    'sport-bh', 'yogahose', 'sportbekleidung', 'fitnessbekleidung',

    # Clothing - Other
    'jumpsuit', 'overall', 'damenoverall', 'playsuit', 'umstandsmode', 'stillmode', 'stilltop', 'still-bh', 'große größen', 'kurzgrößen', 'damenmode',

    # Shoes
    'damenschuhe', 'pumps', 'stiletto', 'high heels', 'absatzschuhe', 'kitten heels', 'spangenpumps',
    'keilabsatz', 'plateauschuhe', 'wedges', 'espadrilles',
    'ballerinas', 'flache schuhe', 'slipper', 'damenmokassin', 'mules', 'pantoletten',
    'sandalen', 'sandalette', 'riemchensandalette', 'zehentrenner', # Female styled
    'stiefellette', 'damenstiefel', 'overknee-stiefel', 'damenboots',

    # Accessories - Bags
    'handtasche', 'damenhandtasche', 'umhängetasche', 'schultertasche', 'clutch', 'abendtasche', 'shopper', 'beuteltasche', 'kosmetiktasche', 'kulturtasche', # Female context

    # Accessories - Jewelry
    'schmuck', 'damenschmuck', 'modeschmuck', 'ohrringe', 'ohrstecker', 'creolen', 'ohrclip', 'ohrgehänge',
    'halskette', 'kette', 'collier', 'anhänger', 'medaillon', 'halsreif',
    'armband', 'armreif', 'bettlerarmband', 'fußkette', 'fußkettchen',
    'ring', 'verlobungsring', 'ehering', 'damenring',
    'brosche', 'anstecknadel',

    # Accessories - Hair & Headwear
    'diadem', 'tiara', 'haarreif', 'haarband', 'haarspange', 'haarklammer', 'haarnadel', 'haarschmuck',
    'haargummi', 'zopfgummi', 'scrunchie', 'fascinator', 'damenhut', 'sonnenhut', 'schlapphut', 'barett',
    'schleier', 'kopftuch',

    # Accessories - Other
    'tuch', 'halstuch', 'schal', 'pashmina', 'damenhandschuhe', 'fäustlinge',
    'damengürtel', 'taillengürtel',
    'damensonnenbrille',
    'strumpfhose', 'feinstrumpfhose', 'strümpfe', 'halterlose strümpfe', 'netzstrumpfhose', 'leggins', # Note: Leggins also under clothing
    'taschenspiegel', 'fächer',

    # Beauty & Care
    'kosmetik', 'damenkosmetik', 'schminke', 'makeup', 'beauty', 'schönheit', 'kosmetiktasche',
    'lippenstift', 'lipgloss', 'lippenbalsam', 'lipstain', 'lipliner', 'konturenstift',
    'eyeliner', 'kajal', 'lidschatten', 'wimperntusche', 'mascara', 'augenbrauenstift', 'augenbrauengel', 'falsche wimpern', 'wimpernzange',
    'grundierung', 'foundation', 'concealer', 'abdeckstift', 'make-up-basis', 'bb cream', 'cc cream', 'primer', 'fixierspray', 'puder', 'gesichtspuder',
    'rouge', 'bronzer', 'highlighter', 'contouring',
    'nagellack', 'maniküre', 'pediküre', 'nageldesign', 'kunstnägel', 'nagelfeile', 'nagelöl',
    'parfüm', 'parfum', 'damenduft', 'duft', 'duftwasser', 'eau de parfum', 'eau de toilette', 'körperspray', 'zerstäuber',
    'hautpflege', 'gesichtspflege', 'feuchtigkeitscreme', 'gesichtscreme', 'serum', 'gesichtsreinigung', 'reinigungsmilch', 'gesichtswasser', 'toner', 'gesichtsmaske', 'augencreme', 'anti-aging', 'antifaltencreme', 'peeling', 'scrub', 'sonnenschutz', 'lsf',
    'haarentfernung', 'wachsstreifen', 'kaltwachsstreifen', 'warmwachs', 'epilierer', 'enthaarungscreme', 'damenrasierer',
    'damenhygiene', 'intimpflege', 'menstruation', 'tampon', 'binde', 'damenbinde', 'slipeinlage', 'menstruationstasse',

    # --- French (FR) ---
    # General & Identity
    'femme', 'femmes', 'dame', 'dames', 'fille', 'filles', 'madame', 'mademoiselle', 'féminin', 'féminine', 'elle', 'sa', 'ses',
    'mère', 'maman', 'soeur', 'fille', 'tante', 'grand-mère', 'mamie',
    'mariée', 'demoiselle d\'honneur', 'enterrement de vie de jeune fille', 'evjf',

    # Clothing - Tops & Dresses
    'robe', 'robe de soirée', 'robe de cocktail', 'robe longue', 'robe midi', 'mini-robe', 'robe droite', 'robe portefeuille', 'robe fourreau', 'robe empire', 'robe bustier', 'robe d\'été',
    'jupe', 'jupe longue', 'jupe midi', 'mini-jupe', 'jupe crayon', 'jupe plissée', 'jupe portefeuille', 'jupe-culotte',
    'chemisier', 'blouse', 'tunique', 'caraco', 'camisole', 'top', 'débardeur', 'haut', 'haut court', 'dos nu', 'bustier',
    'body', 'léotard', 'justaucorps',

    # Clothing - Bottoms
    'legging', 'jegging', 'pantacourt', 'pantalon femme', # Qualified

    # Clothing - Outerwear & Layers
    'cardigan', 'gilet', 'boléro', 'kimono', 'poncho', 'châle', 'étole', 'cape', 'veste femme', 'manteau femme', 'blazer femme', 'trench femme',

    # Clothing - Lingerie & Sleepwear
    'lingerie', 'sous-vêtement femme', 'soutien-gorge', 'brassière', 'balconnet', 'corbeille', 'push-up', 'bandeau', 'armature', 'sans armature', 'soutien-gorge de sport',
    'culotte', 'slip', 'tanga', 'string', 'shorty', 'boxer femme', 'culotte taille haute',
    'gaine', 'shapewear', 'body gainant', 'corset', 'guêpière',
    'nuisette', 'chemise de nuit', 'pyjama femme', 'babydoll', 'déshabillé', 'robe de chambre femme', 'peignoir femme', # Qualifed/styled
    'jupon', 'porte-jarretelles', 'jarretelles',

    # Clothing - Swim & Activewear
    'maillot de bain', 'bikini', 'tankini', 'monokini', 'une-pièce', 'trikini', 'robe de plage', 'tunique de plage', 'paréo', 'sarong',
    'brassière de sport', 'legging de sport', 'pantalon de yoga', 'tenue de sport', 'vêtement de fitness',

    # Clothing - Other
    'combinaison', 'jumpsuit', 'combishort', 'playsuit', 'vêtements de grossesse', 'vêtements de maternité', 'haut d\'allaitement', 'soutien-gorge d\'allaitement', 'grande taille', 'petite taille', 'mode femme',

    # Shoes
    'chaussures femme', 'talons', 'talons hauts', 'escarpins', 'stilettos', 'talons aiguilles', 'petits talons',
    'compensées', 'plateformes', 'espadrilles',
    'ballerines', 'mocassins femme', 'mules', 'babouches', 'sabo',
    'sandales', 'spartiates', 'nu-pieds', 'tongs', # Often female styled
    'bottines', 'boots femme', 'bottes femme', 'cuissardes',

    # Accessories - Bags
    'sac à main', 'sacoche femme', 'pochette', 'clutch', 'sac bandoulière', 'sac porté épaule', 'cabas', 'fourre-tout', 'sac seau', 'minaudière', 'sac de soirée', 'trousse de toilette', # Female context

    # Accessories - Jewelry
    'bijoux', 'joaillerie', 'bijouterie fantaisie', 'boucles d\'oreilles', 'clous d\'oreilles', 'créoles', 'pendantes', 'dormeuses',
    'collier', 'pendentif', 'ras-de-cou', 'sautoir', 'chaîne',
    'bracelet', 'jonc', 'gourmette', 'bracelet de cheville', 'chaîne de cheville',
    'bague', 'alliance', 'solitaire', 'chevalière', # Context specific
    'broche', 'épingle',

    # Accessories - Hair & Headwear
    'diadème', 'tiare', 'serre-tête', 'bandeau', 'barrette', 'pince à cheveux', 'épingle à cheveux', 'pique à chignon', 'peigne',
    'chouchou', 'élastique cheveux', 'accessoire cheveux', 'bibi', 'capeline', 'chapeau femme', 'chapeau de paille', 'béret',
    'voile', 'voilette', 'foulard', # Headscarf

    # Accessories - Other
    'foulard', 'carré de soie', 'écharpe', 'pashmina', 'étole', 'gants femme', 'mitaines',
    'ceinture femme', 'ceinture fine', 'ceinture large',
    'lunettes de soleil femme',
    'collants', 'bas', 'bas autofixants', 'bas résille', 'guêtres',
    'miroir de poche', 'éventail',

    # Beauty & Care
    'cosmétique', 'maquillage', 'produit de beauté', 'trousse de maquillage', 'vanity',
    'rouge à lèvres', 'gloss', 'baume à lèvres', 'crayon à lèvres', 'encre à lèvres',
    'eyeliner', 'crayon khôl', 'fard à paupières', 'ombre à paupières', 'mascara', 'crayon sourcils', 'gel sourcils', 'faux cils', 'recourbe-cils',
    'fond de teint', 'anticernes', 'correcteur', 'bb crème', 'cc crème', 'base de teint', 'fixateur de maquillage', 'poudre libre', 'poudre compacte',
    'blush', 'fard à joues', 'poudre bronzante', 'terre de soleil', 'enlumineur', 'illuminateur', 'contouring',
    'vernis à ongles', 'manucure', 'pédicure', 'nail art', 'faux ongles', 'lime à ongles', 'huile cuticules',
    'parfum', 'eau de parfum', 'eau de toilette', 'brume parfumée', 'fragrance', 'extrait de parfum', 'vaporisateur',
    'soin de la peau', 'soin visage', 'soin corps', 'crème hydratante', 'sérum', 'nettoyant visage', 'démaquillant', 'lotion tonique', 'masque visage', 'crème contour des yeux', 'soin anti-âge', 'gommage', 'exfoliant', 'protection solaire', 'spf',
    'épilation', 'cire à épiler', 'bande de cire', 'épilateur électrique', 'crème dépilatoire', 'rasoir femme',
    'hygiène féminine', 'hygiène intime', 'protection hygiénique', 'tampon', 'serviette hygiénique', 'protège-slip', 'coupe menstruelle',

    # --- Spanish (ES) ---
    # General & Identity
    'mujer', 'mujeres', 'dama', 'damas', 'chica', 'chicas', 'señora', 'señorita', 'femenino', 'femenina', 'ella', 'su', 'sus',
    'madre', 'mamá', 'hermana', 'hija', 'tía', 'abuela',
    'novia', 'dama de honor', 'despedida de soltera',

    # Clothing - Tops & Dresses
    'vestido', 'vestido de noche', 'vestido de fiesta', 'vestido de cóctel', 'vestido largo', 'vestido midi', 'minivestido', 'vestido recto', 'vestido cruzado', 'vestido tubo', 'vestido imperio', 'vestido de verano',
    'falda', 'falda larga', 'falda midi', 'minifalda', 'falda lápiz', 'falda plisada', 'falda cruzada', 'falda pantalón',
    'blusa', 'camisa mujer', 'túnica', 'top', 'camiseta', 'camiseta sin mangas', 'crop top', 'halter', 'palabra de honor',
    'body', 'leotardo', 'maillot',

    # Clothing - Bottoms
    'leggings', 'jeggings', 'pantalón capri', 'pantalón pirata', 'culotte', 'pantalón palazzo', 'pantalones de mujer',

    # Clothing - Outerwear & Layers
    'cárdigan', 'rebeca', 'chaqueta de punto', 'bolero', 'kimono', 'poncho', 'chal', 'echarpe', 'capa', 'estola', 'chaqueta mujer', 'abrigo mujer', 'blazer mujer', 'gabardina mujer',

    # Clothing - Lingerie & Sleepwear
    'lencería', 'ropa interior femenina', 'sujetador', 'brasier', 'bralette', 'push-up', 'balconet', 'bandeau', 'sujetador deportivo', 'con aros', 'sin aros',
    'braga', 'braguita', 'tanga', 'culotte', 'hipster', 'braga alta',
    'faja', 'ropa moldeadora', 'body reductor', 'corsé', 'bustier',
    'camisón', 'pijama mujer', 'babydoll', 'negligé', 'bata mujer', 'albornoz mujer', # Qualified/styled
    'enagua', 'mirriñaque', 'cancán', 'portaligas', 'liguero', 'ligas',

    # Clothing - Swim & Activewear
    'traje de baño', 'bañador', 'bikini', 'trikini', 'tankini', 'monokini', 'vestido de baño', 'ropa de playa', 'salida de baño', 'pareo', 'sarong', 'caftán',
    'sujetador deportivo', 'top deportivo', 'mallas deportivas', 'mallas de yoga', 'ropa deportiva', 'ropa de fitness',

    # Clothing - Other
    'mono', 'jumpsuit', 'peto', 'ropa premamá', 'ropa de maternidad', 'ropa de lactancia', 'sujetador de lactancia', 'talla grande', 'talla especial', 'moda mujer',

    # Shoes
    'zapatos de mujer', 'tacones', 'tacón', 'zapatos de tacón', 'salones', 'stilettos', 'aguja',
    'plataformas', 'cuñas', 'alpargatas',
    'bailarinas', 'manoletinas', 'mocasines mujer', 'mules', 'zuecos', 'sabrinas',
    'sandalias', 'cangrejeras', 'chanclas', # Often female styled
    'botines', 'botas mujer', 'botas altas', 'mosqueteras',

    # Accessories - Bags
    'bolso', 'cartera', 'bolso de mano', 'clutch', 'bolso tote', 'shopping bag', 'bandolera', 'bolso de hombro', 'bombonera', 'bolso de fiesta', 'neceser', # Female context

    # Accessories - Jewelry
    'joyas', 'joyería', 'bisutería', 'pendientes', 'aretes', 'zarcillos', 'argollas', 'dormilonas',
    'collar', 'gargantilla', 'colgante', 'medalla', 'camafeo', 'cadena',
    'pulsera', 'brazalete', 'esclava', 'tobillera',
    'anillo', 'sortija', 'alianza', 'anillo de compromiso', 'sello', # Context specific
    'broche', 'prendedor', 'alfiler', 'imperdible', # Decorative

    # Accessories - Hair & Headwear
    'diadema', 'tiara', 'banda para el pelo', 'cinta para el pelo', 'pasador', 'hebilla', 'pinza', 'horquilla', 'peineta', 'accesorio para el pelo',
    'coletero', 'goma del pelo', 'scrunchie', 'tocado', 'pamela', 'sombrero mujer', 'sombrero de paja', 'boina',
    'velo', 'mantilla', 'pañuelo cabeza',

    # Accessories - Other
    'pañuelo', 'pañoleta', 'fular', 'bufanda', 'echarpe', 'pashmina', 'chalina', 'guantes mujer', 'manoplas',
    'cinturón mujer', 'cinto', 'fajín',
    'gafas de sol mujer', 'lentes de sol mujer',
    'medias', 'pantimedias', 'pantys', 'leotardos', 'medias de rejilla', 'ligas', 'calentadores',
    'espejo de bolsillo', 'abanico',

    # Beauty & Care
    'cosmético', 'maquillaje', 'belleza', 'neceser de maquillaje',
    'pintalabios', 'lápiz labial', 'barra de labios', 'brillo de labios', 'gloss', 'bálsamo labial', 'tinte labial', 'perfilador de labios',
    'delineador de ojos', 'eyeliner', 'lápiz de ojos', 'kohl', 'sombra de ojos', 'rímel', 'máscara de pestañas', 'lápiz de cejas', 'gel de cejas', 'pestañas postizas', 'rizador de pestañas',
    'base de maquillaje', 'fondo de maquillaje', 'corrector', 'antiojeras', 'bb cream', 'cc cream', 'prebase', 'fijador de maquillaje', 'polvos sueltos', 'polvos compactos',
    'colorete', 'rubor', 'polvos bronceadores', 'iluminador', 'contouring',
    'esmalte de uñas', 'laca de uñas', 'pintauñas', 'manicura', 'pedicura', 'nail art', 'uñas postizas', 'lima de uñas', 'aceite para cutículas',
    'perfume', 'fragancia', 'colonia', 'agua de perfume', 'agua de colonia', 'bruma corporal', 'aroma', 'vaporizador',
    'cuidado de la piel', 'cuidado facial', 'cuidado corporal', 'crema hidratante', 'loción corporal', 'sérum', 'suero', 'limpiador facial', 'desmaquillante', 'agua micelar', 'tónico', 'mascarilla facial', 'crema contorno de ojos', 'crema antiarrugas', 'crema antiedad', 'exfoliante', 'protector solar', 'spf', 'autobronceador',
    'depilación', 'cera depilatoria', 'bandas de cera', 'depiladora eléctrica', 'crema depilatoria', 'maquinilla mujer',
    'higiene íntima', 'higiene femenina', 'tampón', 'compresa', 'protegeslip', 'salvaslip', 'copa menstrual',

    # --- Italian (IT) ---
    # General & Identity
    'donna', 'donne', 'signora', 'signore', 'ragazza', 'ragazze', 'femmina', 'femminile', 'lei', 'sua', 'sue', 'suoi',
    'madre', 'mamma', 'sorella', 'figlia', 'zia', 'nonna',
    'sposa', 'damigella', 'addio al nubilato',

    # Clothing - Tops & Dresses
    'vestito', 'abito', 'vestito da sera', 'vestito da cocktail', 'abito lungo', 'abito midi', 'minigonna', 'tubino', 'abito a portafoglio', 'prendisole',
    'gonna', 'gonna lunga', 'gonna midi', 'minigonna', 'gonna a tubino', 'gonna a pieghe', 'gonna a portafoglio', 'pareo',
    'camicetta', 'blusa', 'camicia donna', 'tunica', 'top', 'canotta', 'canottiera', 'crop top',
    'body', 'tutina', 'salopette', 'jumpsuit',

    # Clothing - Bottoms
    'leggings', 'jeggings', 'pinocchietto', 'pantalone capri', 'culotte', 'pantaloni palazzo', 'pantaloni donna',

    # Clothing - Outerwear & Layers
    'cardigan', 'golfino', 'bolero', 'coprispalle', 'kimono', 'poncho', 'scialle', 'stola', 'mantella', 'cappa', 'giacca donna', 'cappotto donna', 'blazer donna', 'trench',

    # Clothing - Lingerie & Sleepwear
    'lingerie', 'intimo donna', 'biancheria intima', 'reggiseno', 'bralette', 'push-up', 'balconcino', 'fascia', 'reggiseno sportivo', 'con ferretto', 'senza ferretto',
    'mutandine', 'slip donna', 'tanga', 'perizoma', 'culotte', 'brasiliana',
    'guaina', 'intimo modellante', 'body modellante', 'corsetto', 'bustier', 'guepiere',
    'camicia da notte', 'sottoveste', 'pigiama donna', 'babydoll', 'vestaglia', 'accappatoio donna', # Qualified/styled
    'sottogonna', 'crinolina', 'giarrettiera', 'reggicalze',

    # Clothing - Swim & Activewear
    'costume da bagno', 'bikini', 'trikini', 'tankini', 'monokini', 'intero', 'copricostume', 'pareo', 'caftano', 'prendisole',
    'top sportivo', 'reggiseno sportivo', 'pantaloni yoga', 'leggings sportivi', 'abbigliamento sportivo', 'abbigliamento fitness',

    # Clothing - Other
    'tuta', 'abbigliamento premaman', 'maglia allattamento', 'reggiseno allattamento', 'taglie forti', 'taglie comode', 'petite', 'moda donna',

    # Shoes
    'scarpe donna', 'tacchi', 'tacco', 'scarpe col tacco', 'décolleté', 'stiletto', 'tacco a spillo', 'tacco gattino',
    'zeppe', 'platform', 'espadrillas',
    'ballerine', 'mocassini donna', 'mules', 'sabot', 'ciabatte', # Often female styled
    'sandali', 'infradito', # Often female styled
    'stivaletti', 'tronchetti', 'stivali donna', 'stivali alti', 'cuissardes',

    # Accessories - Bags
    'borsa', 'borsetta', 'pochette', 'clutch', 'borsa a tracolla', 'borsa a spalla', 'tote bag', 'shopper', 'secchiello', 'borsa da sera', 'beauty case', # Female context

    # Accessories - Jewelry
    'gioielli', 'bigiotteria', 'orecchini', 'pendenti', 'a lobo', 'a cerchio', 'a clip',
    'collana', 'girocollo', 'pendente', 'ciondolo', 'medaglione', 'catenina',
    'bracciale', 'braccialetto', 'bangle', 'cavigliera',
    'anello', 'fedina', 'anello di fidanzamento', 'fede nuziale', 'solitario',
    'spilla', 'fermaglio', 'pin',

    # Accessories - Hair & Headwear
    'diadema', 'tiara', 'cerchietto', 'fascia per capelli', 'fermaglio', 'molletta', 'forcina', 'pettinino', 'accessori per capelli',
    'elastico per capelli', 'scrunchie', 'fermacoda', 'cappello donna', 'cappello da sole', 'cloche', 'berretto', # Female styled
    'velo', 'veletta',

    # Accessories - Other
    'foulard', 'sciarpa', 'pashmina', 'stola', 'guanti donna', 'manopole',
    'cintura donna', 'cintura vita alta', 'fusciacca',
    'occhiali da sole donna',
    'collant', 'calze', 'autoreggenti', 'calze a rete', 'gambaletti', 'scaldamuscoli',
    'specchietto', 'ventaglio',

    # Beauty & Care
    'cosmetico', 'cosmetici', 'trucco', 'make-up', 'bellezza', 'beauty case', 'trousse',
    'rossetto', 'lucidalabbra', 'gloss', 'balsamo labbra', 'tinta labbra', 'matita labbra',
    'eyeliner', 'matita occhi', 'kajal', 'ombretto', 'mascara', 'matita sopracciglia', 'gel sopracciglia', 'ciglia finte', 'piegaciglia',
    'fondotinta', 'correttore', 'bb cream', 'cc cream', 'primer', 'cipria', 'fissatore trucco',
    'fard', 'blush', 'terra abbronzante', 'bronzer', 'illuminante', 'contouring',
    'smalto per unghie', 'manicure', 'pedicure', 'nail art', 'unghie finte', 'lima per unghie', 'olio per cuticole',
    'profumo', 'fragranza', 'eau de parfum', 'eau de toilette', 'acqua profumata', 'essenza', 'atomizzatore', 'vaporizzatore',
    'cura della pelle', 'skincare', 'cura del viso', 'cura del corpo', 'crema idratante', 'crema viso', 'crema corpo', 'siero', 'detergente viso', 'struccante', 'latte detergente', 'acqua micellare', 'tonico', 'maschera viso', 'crema contorno occhi', 'crema antirughe', 'crema antietà', 'esfoliante', 'scrub', 'peeling', 'protezione solare', 'spf', 'autoabbronzante',
    'depilazione', 'ceretta', 'strisce depilatorie', 'epilatore', 'crema depilatoria', 'rasoio donna',
    'igiene intima', 'assorbente', 'tampone', 'salvaslip', 'coppetta mestruale',

    # --- Dutch (NL) ---
    # General & Identity
    'vrouw', 'vrouwen', 'dame', 'dames', 'meisje', 'meisjes', 'vrouwelijk', 'vrouwelijke', 'zij', 'haar', 'mevrouw',
    'moeder', 'mama', 'zus', 'dochter', 'tante', 'grootmoeder', 'oma',
    'bruid', 'bruidsmeisje', 'vrijgezellenfeest',

    # Clothing - Tops & Dresses
    'jurk', 'japon', 'avondjurk', 'cocktailjurk', 'maxi-jurk', 'midi-jurk', 'mini-jurk', 'tuniekjurk', 'wikkeljurk', 'zomerjurk',
    'rok', 'maxi-rok', 'midi-rok', 'mini-rok', 'kokerrok', 'plooirok', 'wikkelrok',
    'blouse', 'top', 'topje', 'hemdje', 'tuniek', 'haltertop', 'crop top', 'tanktop', 'damesshirt',
    'body', 'turnpakje', 'jumpsuit', 'playsuit',

    # Clothing - Bottoms
    'legging', 'jegging', 'capri broek', 'culotte', 'palazzo broek', 'damesbroek', # Qualified

    # Clothing - Outerwear & Layers
    'vest', 'vestje', 'cardigan', 'bolero', 'omslagdoek', 'kimono', 'poncho', 'sjaal', 'stola', 'cape', 'damesjas', 'damesmantel', 'damesblazer', 'trenchcoat',

    # Clothing - Lingerie & Sleepwear
    'lingerie', 'damesondergoed', 'beha', 'bh', 'bralette', 'push-up bh', 'sportbeha', 'beugelbh', 'zonder beugel',
    'slip', 'slipje', 'damesslip', 'string', 'tanga', 'hipster', 'shorty', 'onderbroek',
    'shapewear', 'corrigerend ondergoed', 'korset', 'bustier', 'torselet',
    'nachthemd', 'nachtjapon', 'pyjama', 'babydoll', 'negligé', 'damespyjama', 'ochtendjas', # Female styled
    'onderrok', 'petticoat', 'jarretelgordel', 'jarretels',

    # Clothing - Swim & Activewear
    'badpak', 'bikini', 'tankini', 'monokini', 'eendelig', 'strandjurk', 'strandtuniek', 'pareo', 'sarong', 'kaftan',
    'sportbeha', 'yogabroek', 'sportlegging', 'sportkleding', 'fitnesskleding',

    # Clothing - Other
    'zwangerschapskleding', 'voedingskleding', 'voedingstop', 'voedingsbeha', 'grote maten', 'kleine maten', 'damesmode',

    # Shoes
    'damesschoenen', 'hakken', 'pumps', 'naaldhakken', 'stilettos',
    'sleehakken', 'espadrilles', 'plateauzolen',
    'ballerina\'s', 'instappers', 'loafers', 'muiltjes', 'sandalen', 'sandaaltjes', 'teenslippers', # Female styled
    'enkellaarsjes', 'laarzen', 'overknee laarzen', 'dameslaarzen',

    # Accessories - Bags
    'handtas', 'damestas', 'schoudertas', 'crossbodytas', 'clutch', 'avondtasje', 'shopper', 'buideltas', 'toilettas', # Female context

    # Accessories - Jewelry
    'sieraden', 'juwelen', 'bijouterie', 'oorbellen', 'oorstekers', 'oorringen', 'oorhangers',
    'ketting', 'halsketting', 'collier', 'hanger', 'medaillon',
    'armband', 'bangle', 'bedelarmband', 'enkelbandje',
    'ring', 'verlovingsring', 'trouwring', 'damesring',
    'broche', 'speld', 'sierspeld',

    # Accessories - Hair & Headwear
    'diadeem', 'tiara', 'haarband', 'haarreep', 'haarspeld', 'haarklem', 'schuifspeldje', 'haarpin', 'kam', 'haaraccessoire',
    'haarelastiek', 'scrunchie', 'paardenstaarthouder', 'fascinator', 'dameshoed', 'zonnehoed', 'baret',
    'sluier', 'hoofddoek',

    # Accessories - Other
    'sjaal', 'shawl', 'pashmina', 'foulard', 'halsdoek', 'handschoenen', 'wanten', # Female styled
    'riem', 'ceintuur', 'tailleriem', # Female styled
    'zonnebril', # Female styled
    'panty', 'maillot', 'kousen', 'nylonkousen', 'netkousen', 'hold-ups', 'jarretelkousen', 'beenwarmers',
    'zakspiegel', 'waaier',

    # Beauty & Care
    'cosmetica', 'make-up', 'beautyproducten', 'make-uptasje',
    'lippenstift', 'lipgloss', 'lippenbalsem', 'lipliner',
    'eyeliner', 'oogpotlood', 'kohlpotlood', 'oogschaduw', 'mascara', 'wenkbrauwpotlood', 'wenkbrauwgel', 'valse wimpers', 'wimperkruller',
    'foundation', 'concealer', 'bb cream', 'cc cream', 'primer', 'setting spray', 'poeder', 'gezichtspoeder',
    'blush', 'rouge', 'bronzer', 'highlighter', 'contouring',
    'nagellak', 'manicure', 'pedicure', 'nail art', 'kunstnagels', 'nagelvijl', 'nagelriemolie',
    'parfum', 'geurtje', 'eau de parfum', 'eau de toilette', 'bodymist', 'parfumverstuiver',
    'huidverzorging', 'gezichtsverzorging', 'lichaamsverzorging', 'dagcrème', 'nachtcrème', 'vochtinbrengende crème', 'serum', 'reiniger', 'gezichtsreiniger', 'make-up remover', 'toner', 'gezichtsmasker', 'oogcrème', 'anti-aging', 'anti-rimpel', 'scrub', 'peeling', 'zonnebrandcrème', 'spf', 'zelfbruiner',
    'ontharing', 'harsen', 'waxen', 'waxstrips', 'epilator', 'ontharingscrème', 'damesscheermesje',
    'maandverband', 'tampon', 'inlegkruisje', 'menstruatiecup',

    # --- Portuguese (PT) ---
    # General & Clothing
    'mulher', 'mulheres', 'senhora', 'senhoras', 'menina', 'meninas', 'rapariga', 'feminino', 'feminina', 'ela', 'dela',
    'vestido', 'saia', 'blusa', 'túnica', 'sutiã', 'lingerie', 'calcinha', 'calcinhas',
    'camisola de dormir', 'body', 'fato de banho', 'maiô', 'biquíni', 'cardigã', 'bolero', 'jumpsuit', 'kaftan', 'sarongue', 'canga',

    # Shoes & Accessories
    'saltos', 'salto alto', 'sapatos de salto', 'plataformas', 'anabela', 'sabrinas', 'sandálias',
    'bolsa', 'mala', 'carteira', 'clutch', 'joias', 'brincos', 'colar', 'pulseira', 'pingente', 'broche', 'anel',
    'bandolete', 'gancho', 'travessa', 'elástico de cabelo', 'lenço', 'echarpe', 'xale',

    # Beauty & Care
    'cosmético', 'maquilhagem', 'maquiagem', 'batom', 'gloss', 'brilho labial', 'delineador', 'sombra',
    'rímel', 'máscara de cílios', 'base', 'corretivo', 'blush', 'bronzeador', 'verniz', 'esmalte', 'manicura', 'pedicura',
    'perfume', 'fragrância', 'cuidado da pele', 'hidratante', 'sérum', 'limpeza de pele', 'desmaquilhante', 'tónico', 'protetor solar',
    'depilação', 'cera', 'pensos higiénicos', 'tampões',

    # --- Polish (PL) ---
    # General & Clothing
    'kobieta', 'kobiety', 'pani', 'panie', 'dziewczyna', 'dziewczyny', 'damski', 'kobiecy', 'ona', 'jej',
    'sukienka', 'suknia', 'spódnica', 'spódniczka', 'bluzka', 'tunika', 'bielizna', 'biustonosz', 'stanik', 'majtki', 'figi',
    'koszula nocna', 'halka', 'body', 'strój kąpielowy', 'kostium kąpielowy', 'bikini', 'jednoczęściowy', 'kardigan', 'sweter rozpinany', 'bolerko', 'kombinezon', 'kaftan', 'pareo',

    # Shoes & Accessories
    'szpilki', 'obcasy', 'buty na obcasie', 'czółenka', 'koturny', 'baleriny', 'sandały',
    'torebka', 'kopertówka', 'torba na ramię', 'biżuteria', 'kolczyki', 'naszyjnik', 'łańcuszek', 'bransoletka', 'wisiorek', 'broszka', 'pierścionek', 'obrączka',
    'opaska', 'spinka do włosów', 'gumka do włosów', 'szalik', 'apaszka', 'chusta',

    # Beauty & Care
    'kosmetyk', 'kosmetyki', 'makijaż', 'szminka', 'pomadka', 'błyszczyk', 'konturówka', 'eyeliner', 'kredka do oczu', 'cień do powiek',
    'tusz do rzęs', 'maskara', 'podkład', 'fluid', 'korektor', 'róż', 'bronzer', 'rozświetlacz', 'lakier do paznokci',
    'manicure', 'pedicure', 'perfumy', 'zapach', 'woda perfumowana', 'woda toaletowa', 'pielęgnacja skóry', 'krem nawilżający', 'serum', 'żel do mycia twarzy', 'płyn micelarny', 'tonik', 'maseczka', 'krem pod oczy', 'przeciwzmarszczkowy', 'peeling',
    'depilacja', 'wosk', 'plastry do depilacji', 'depilator', 'krem do depilacji', 'maszynka damska',
    'higiena intymna', 'podpaski', 'tampony', 'wkładki higieniczne',

    # --- Swedish (SV) ---
    # General & Clothing
    'kvinna', 'kvinnor', 'dam', 'damer', 'flicka', 'flickor', 'tjej', 'kvinnlig', 'feminin', 'hon', 'hennes',
    'klänning', 'aftonklänning', 'cocktailklänning', 'maxiklänning', 'sommarklänning',
    'kjol', 'maxikjol', 'midikjol', 'minikjol', 'pennkjol', 'veckad kjol',
    'blus', 'tunika', 'topp', 'linne', 'crop top',
    'body', 'jumpsuit', 'byxdress',

    # Clothing - Bottoms
    'dambyxor', 'leggings', 'jeggings', 'capribyxor', 'culottes',

    # Clothing - Outerwear & Layers
    'kofta', 'cardigan', 'bolero', 'kimono', 'poncho', 'sjal', 'halsduk', 'damjacka', 'damkappa', 'damkavaj', 'trenchcoat',

    # Clothing - Lingerie & Sleepwear
    'underkläder', 'damunderkläder', 'lingerie', 'behå', 'bh', 'bralette', 'push-up bh', 'sport-bh', 'bygel-bh',
    'trosor', 'stringtrosor', 'hipsters', 'boxertrosor',
    'shapewear', 'formande underkläder', 'korsett', 'bustier',
    'nattlinne', 'pyjamas', 'sovplagg', 'babydoll', 'negligé', 'morgonrock', # Female styled
    'underkjol', 'strumpebandshållare', 'strumpeband',

    # Clothing - Swim & Activewear
    'baddräkt', 'bikini', 'tankini', 'monokini', 'strandkläder', 'sarong', 'pareo', 'kaftan',
    'sport-bh', 'yogabyxor', 'träningskläder',

    # Clothing - Other
    'mammaläder', 'amningstopp', 'amnings-bh', 'plus size', 'stora storlekar', 'petite', 'damkläder', 'dammode',

    # Shoes
    'damskor', 'klackar', 'högklackat', 'pumps', 'stiletter', 'klackskor',
    'kilklackar', 'espadriller', 'platåskor',
    'ballerinaskor', 'loafers', 'mules',
    'sandaler', 'sandaletter',
    'stövletter', 'ankelboots', 'stövlar', 'overkneestövlar', # Often female styles

    # Accessories - Bags
    'handväska', 'damväska', 'axelremsväska', 'crossbodyväska', 'clutch', 'kuvertväska', 'aftonväska', 'tygkasse', 'necessär', # Female context

    # Accessories - Jewelry
    'smycken', 'bijouterier', 'örhängen', 'stiftörhängen', 'ringar', 'hängen',
    'halsband', 'kedja', 'berlock', 'medaljong',
    'armband', 'armring', 'berlockarmband', 'fotlänk', 'vristlänk',
    'ring', 'förlovningsring', 'vigselring',
    'brosch', 'nål',

    # Accessories - Hair & Headwear
    'diadem', 'tiara', 'hårband', 'hårspänne', 'hårklämma', 'hårnål', 'kam', 'håraccessoar',
    'hårsnodd', 'scrunchie', 'hårtofs', 'fascinator', 'damhatt', 'solhatt', 'basker',
    'slöja', 'huvudduk',

    # Accessories - Other
    'scarf', 'sjal', 'pashmina', 'halsduk', 'damhandskar', 'vantar',
    'dambälte', 'midjebälte', 'skärp',
    'damsolglasögon',
    'strumpbyxor', 'tights', 'stay-ups', 'knästrumpor', 'nätstrumpbyxor', 'benvärmare',
    'fickspegel', 'solfjäder',

    # Beauty & Care
    'kosmetika', 'smink', 'makeup', 'skönhet', 'necessär',
    'läppstift', 'läppglans', 'läppbalsam', 'läppenna',
    'eyeliner', 'kajalpenna', 'ögonskugga', 'mascara', 'ögonbrynspenna', 'ögonbrynsgel', 'lösögonfransar', 'ögonfransböjare',
    'foundation', 'concealer', 'täckstift', 'bb cream', 'cc cream', 'primer', 'settingspray', 'puder', 'ansiktspuder',
    'rouge', 'bronzer', 'highlighter', 'contouring',
    'nagellack', 'manikyr', 'pedikyr', 'nagelkonst', 'lösnaglar', 'nagelfil', 'nagelbandsolja',
    'parfym', 'doft', 'eau de parfum', 'eau de toilette', 'kroppsspray',
    'hudvård', 'ansiktsvård', 'kroppsvård', 'fuktkräm', 'ansiktskräm', 'kroppslotion', 'serum', 'ansiktsrengöring', 'sminkborttagning', 'ansiktsvatten', 'toner', 'ansiktsmask', 'ögonkräm', 'anti-age', 'rynkkräm', 'peeling', 'scrubb', 'solskyddsfaktor', 'spf', 'brun utan sol',
    'hårborttagning', 'vaxning', 'vaxremsor', 'epilator', 'hårborttagningskräm', 'rakhyvel för kvinnor',
    'intimhygien', 'mensskydd', 'binda', 'tampong', 'trosskydd', 'menskopp',

    # --- Polish (PL) ---
    # Ogólne i Odzież (General & Clothing)
    'kobieta', 'kobiety', 'pani', 'panie', 'dziewczyna', 'dziewczyny', 'dziewczę', 'kobiecy', 'żeński', 'ona', 'jej',
    'sukienka', 'suknia wieczorowa', 'sukienka koktajlowa', 'sukienka maxi', 'sukienka letnia',
    'spódnica', 'spódnica maxi', 'spódnica midi', 'spódniczka mini', 'spódnica ołówkowa', 'spódnica plisowana',
    'bluzka', 'tunika', 'top', 'koszulka bez rękawów', 'crop top',
    'body', 'kombinezon', 'pajac',

    # Odzież - Dolne części garderoby (Clothing - Bottoms)
    'spodnie damskie', 'legginsy', 'jegginsy', 'spodnie capri', 'kuloty',

    # Odzież - Okrycia wierzchnie i warstwy (Clothing - Outerwear & Layers)
    'kardigan', 'sweter rozpinany', 'bolerko', 'kimono', 'ponczo', 'szal', 'chusta', 'kurtka damska', 'płaszcz damski', 'żakiet damski', 'trencz',

    # Odzież - Bielizna i Odzież nocna (Clothing - Lingerie & Sleepwear)
    'bielizna', 'bielizna damska', 'lingerie', 'biustonosz', 'stanik', 'braletka', 'biustonosz push-up', 'stanik sportowy', 'biustonosz z fiszbinami',
    'majtki', 'stringi', 'figi', 'hipsterki', 'bokserki damskie',
    'bielizna modelująca', 'gorset', 'biustonosz-gorset',
    'koszula nocna', 'piżama', 'bielizna nocna', 'babydoll', 'peniuar', 'szlafrok',
    'halka', 'pas do pończoch', 'podwiązka',

    # Odzież - Stroje kąpielowe i Sportowe (Clothing - Swim & Activewear)
    'strój kąpielowy', 'bikini', 'tankini', 'monokini', 'odzież plażowa', 'sarong', 'pareo', 'kaftan',
    'stanik sportowy', 'spodnie do jogi', 'odzież sportowa',

    # Odzież - Inne (Clothing - Other)
    'odzież ciążowa', 'top do karmienia', 'biustonosz do karmienia', 'plus size', 'duże rozmiary', 'petite', 'odzież damska', 'moda damska',

    # Buty (Shoes)
    'buty damskie', 'obcasy', 'wysokie obcasy', 'szpilki', 'czółenka',
    'buty na koturnie', 'espadryle', 'buty na platformie',
    'baleriny', 'mokasyny', 'mules',
    'sandały', 'sandały na obcasie',
    'botki', 'botki do kostki', 'kozaki', 'kozaki za kolano',

    # Akcesoria - Torebki (Accessories - Bags)
    'torebka', 'torebka damska', 'torebka na ramię', 'torebka crossbody', 'kopertówka', 'torebka wieczorowa', 'torba płócienna', 'kosmetyczka',

    # Akcesoria - Biżuteria (Accessories - Jewelry)
    'biżuteria', 'sztuczna biżuteria', 'kolczyki', 'kolczyki sztyfty', 'kolczyki wiszące',
    'naszyjnik', 'łańcuszek', 'wisiorek', 'zawieszka', 'medalion',
    'bransoletka', 'bransoleta', 'bransoletka z zawieszkami', 'bransoletka na kostkę',
    'pierścionek', 'pierścionek zaręczynowy', 'obrączka ślubna',
    'broszka', 'przypinka',

    # Akcesoria - Do włosów i Nakrycia głowy (Accessories - Hair & Headwear)
    'diadem', 'tiara', 'opaska na włosy', 'spinka do włosów', 'klamra do włosów', 'wsuwka do włosów', 'grzebień', 'ozdoba do włosów',
    'gumka do włosów', 'scrunchie', 'frotka', 'fascynator', 'kapelusz damski', 'kapelusz przeciwsłoneczny', 'beret',
    'welon', 'chusta na głowę',

    # Akcesoria - Inne (Accessories - Other)
    'szalik', 'apaszka', 'szal', 'pashmina', 'chusta', 'rękawiczki damskie', 'mitenki',
    'pasek damski', 'pasek do talii', 'pasek',
    'okulary przeciwsłoneczne damskie',
    'rajstopy', 'tights', 'pończochy samonośne', 'podkolanówki', 'kabaretki', 'getry', 'ocieplacze na nogi',
    'lusterko kieszonkowe', 'wachlarz',

    # Uroda i Pielęgnacja (Beauty & Care)
    'kosmetyki', 'makijaż', 'makeup', 'uroda', 'kosmetyczka',
    'szminka', 'pomadka', 'błyszczyk', 'balsam do ust', 'konturówka do ust',
    'eyeliner', 'kredka do oczu', 'kajal', 'cień do powiek', 'tusz do rzęs', 'mascara', 'kredka do brwi', 'żel do brwi', 'sztuczne rzęsy', 'zalotka',
    'podkład', 'korektor', 'kamuflaż', 'krem BB', 'krem CC', 'baza pod makijaż', 'primer', 'spray utrwalający', 'puder', 'puder do twarzy',
    'róż do policzków', 'bronzer', 'rozświetlacz', 'konturowanie',
    'lakier do paznokci', 'manicure', 'pedicure', 'zdobienie paznokci', 'sztuczne paznokcie', 'pilnik do paznokci', 'oliwka do skórek',
    'perfumy', 'zapach', 'woda perfumowana', 'eau de parfum', 'woda toaletowa', 'eau de toilette', 'mgiełka do ciała',
    'pielęgnacja skóry', 'pielęgnacja twarzy', 'pielęgnacja ciała', 'krem nawilżający', 'krem do twarzy', 'balsam do ciała', 'serum', 'płyn do mycia twarzy', 'demakijaż', 'płyn do demakijażu', 'tonik', 'tonik do twarzy', 'maseczka do twarzy', 'krem pod oczy', 'anti-age', 'krem przeciwzmarszczkowy', 'peeling', 'scrub', 'ochrona przeciwsłoneczna', 'filtr SPF', 'samoopalacz',
    'depilacja', 'woskowanie', 'plastry z woskiem', 'depilator', 'krem do depilacji', 'maszynka do golenia dla kobiet',
    'higiena intymna', 'środki higieniczne', 'podpaska', 'tampon', 'wkładka higieniczna', 'kubeczek menstruacyjny',


# --- Czech (CS) ---
    # Obecné a Oblečení (General & Clothing)
    'žena', 'ženy', 'dáma', 'dámy', 'dívka', 'dívky', 'holka', 'holky', 'ženský', 'ženská', 'feminní', 'ona', 'její',
    'šaty', 'večerní šaty', 'koktejlové šaty', 'koktejlky', 'maxi šaty', 'letní šaty',
    'sukně', 'maxi sukně', 'midi sukně', 'minisukně', 'pouzdrová sukně', 'plisovaná sukně',
    'halenka', 'tunika', 'top', 'tílko', 'crop top',
    'body', 'overal', 'kombinéza',

    # Oblečení - Spodní díly (Clothing - Bottoms)
    'dámské kalhoty', 'legíny', 'jegíny', 'jeggingy', 'capri kalhoty', 'kalhotová sukně', 'culottes',

    # Oblečení - Svrchní oděvy a vrstvy (Clothing - Outerwear & Layers)
    'kardigan', 'propínací svetr', 'bolerko', 'kimono', 'pončo', 'šál', 'šátek', 'dámská bunda', 'dámský kabát', 'dámské sako', 'trenčkot',

    # Oblečení - Spodní prádlo a Noční prádlo (Clothing - Lingerie & Sleepwear)
    'spodní prádlo', 'dámské spodní prádlo', 'lingerie', 'podprsenka', 'braletka', 'push-up podprsenka', 'sportovní podprsenka', 'podprsenka s kosticemi',
    'kalhotky', 'tanga', 'hipsterky', 'boxerky dámské',
    'stahovací prádlo', 'shapewear', 'korzet', 'bustier',
    'noční košile', 'pyžamo', 'noční prádlo', 'babydoll', 'negližé', 'župan',
    'spodnička', 'podvazkový pás', 'podvazek',

    # Oblečení - Plavky a Sportovní oblečení (Clothing - Swim & Activewear)
    'plavky', 'jednodílné plavky', 'bikiny', 'tankiny', 'monokiny', 'plážové oblečení', 'sarong', 'pareo', 'kaftan',
    'sportovní podprsenka', 'kalhoty na jógu', 'sportovní oblečení', 'fitness oblečení',

    # Oblečení - Ostatní (Clothing - Other)
    'těhotenské oblečení', 'kojící top', 'kojící podprsenka', 'plus size', 'nadměrné velikosti', 'petite', 'pro drobnou postavu', 'dámské oblečení', 'dámská móda',

    # Boty (Shoes)
    'dámské boty', 'podpatky', 'vysoké podpatky', 'lodičky', 'jehlové podpatky', 'boty na podpatku',
    'boty na klínku', 'espadrilky', 'boty na platformě',
    'baleríny', 'mokasíny', 'mules', 'pantofle', 'nazouváky',
    'sandály', 'sandály na podpatku',
    'kotníkové boty', 'kozačky', 'kozačky nad kolena',

    # Doplňky - Kabelky (Accessories - Bags)
    'kabelka', 'dámská kabelka', 'kabelka přes rameno', 'crossbody kabelka', 'psaníčko', 'večerní kabelka', 'látková taška', 'kosmetická taštička', 'necessér',

    # Doplňky - Šperky (Accessories - Jewelry)
    'šperky', 'bižuterie', 'náušnice', 'pecky', 'visací náušnice',
    'náhrdelník', 'řetízek', 'přívěsek', 'medailon',
    'náramek', 'pevný náramek', 'náramek s přívěsky', 'náramek na kotník',
    'prsten', 'zásnubní prsten', 'snubní prsten',
    'brož', 'odznak', 'připínací odznak',

    # Doplňky - Vlasové a Pokrývky hlavy (Accessories - Hair & Headwear)
    'diadém', 'tiára', 'čelenka', 'čelenka do vlasů', 'sponka do vlasů', 'skřipec do vlasů', 'pinetka', 'hřeben do vlasů', 'vlasové doplňky',
    'gumička do vlasů', 'scrunchie', 'ozdoba do culíku', 'fascinátor', 'dámský klobouk', 'klobouk proti slunci', 'baret',
    'závoj', 'šátek na hlavu',

    # Doplňky - Ostatní (Accessories - Other)
    'šátek', 'šál', 'pašmína', 'nákrčník', 'dámské rukavice', 'palčáky',
    'dámský pásek', 'pásek do pasu', 'opasek',
    'dámské sluneční brýle',
    'punčocháče', 'punčochy', 'legíny', 'samodržící punčochy', 'podkolenky', 'síťované punčocháče', 'návleky na nohy',
    'kapesní zrcátko', 'vějíř',

    # Krása a Péče (Beauty & Care)
    'kosmetika', 'líčení', 'makeup', 'krása', 'kosmetická taštička',
    'rtěnka', 'lesk na rty', 'balzám na rty', 'konturovací tužka na rty',
    'oční linky', 'tužka na oči', 'kajalová tužka', 'oční stíny', 'řasenka', 'maskara', 'tužka na obočí', 'gel na obočí', 'umělé řasy', 'kleštičky na řasy',
    'make-up', 'podkladový krém', 'korektor', 'krycí tyčinka', 'BB krém', 'CC krém', 'podkladová báze', 'primer', 'fixační sprej', 'pudr', 'pudr na obličej',
    'tvářenka', 'bronzer', 'rozjasňovač', 'konturování',
    'lak na nehty', 'manikúra', 'pedikúra', 'nehtové umění', 'nail art', 'umělé nehty', 'pilník na nehty', 'olejíček na nehtovou kůžičku',
    'parfém', 'vůně', 'parfémová voda', 'eau de parfum', 'toaletní voda', 'eau de toilette', 'tělový sprej',
    'péče o pleť', 'péče o obličej', 'péče o tělo', 'hydratační krém', 'pleťový krém', 'tělové mléko', 'sérum', 'čisticí přípravek na obličej', 'odličovač', 'odličovací přípravek', 'pleťová voda', 'tonikum', 'pleťová maska', 'oční krém', 'anti-age', 'krém proti vráskám', 'peeling', 'scrub', 'ochrana proti slunci', 'SPF', 'samoopalovací přípravek',
    'odstraňování chloupků', 'depilace', 'depilace voskem', 'voskové pásky', 'epilátor', 'depilační krém', 'dámský holicí strojek',
    'intimní hygiena', 'menstruační potřeby', 'vložka', 'tampon', 'slipová vložka', 'menstruační kalíšek',
}

MALE_KEYWORDS = {
    # --- English ---
    # General & Clothing
    'men', 'man', 'mens', 'male', 'gentlemen', 'gentleman', 'boy', 'boys', 'guy', 'fella', 'chap',
    'he', 'his', 'masculine',
    'suit', 'blazer', 'tuxedo', 'dinner jacket', 'formal wear',
    'waistcoat', 'vest', # 'vest' often means waistcoat in men's formal context
    'trousers', 'pants', 'chinos', 'slacks', 'jeans', 'joggers', # Jeans/joggers often neutral
    'shorts', # Often neutral
    'shirt', 'dress shirt', 'button-down', 't-shirt', 'polo', # T-shirt/polo often neutral
    'sweater', 'pullover', 'jumper', 'hoodie', 'sweatshirt', # Often neutral
    'boxer', 'briefs', 'trunks', 'underwear', 'underpants', # Men's underwear
    'swim trunks', 'board shorts', 'swim briefs', 'swimwear',
    'tracksuit',

    # Shoes & Accessories
    'shoes', 'mens shoes', 'formal shoes', 'dress shoes', 'oxfords', 'brogues', 'loafers', 'derby', # Specific men's shoe types
    'boots', 'sneakers', 'trainers', # Often neutral
    'tie', 'bow tie', 'cufflinks', 'tie clip', 'tie bar', 'pocket square', 'belt',
    'wallet', 'briefcase', 'messenger bag', 'bag', 'watch', 'watch strap', 'suspenders', 'braces',
    'sunglasses', 'hat', 'cap', 'beanie', 'scarf', 'gloves',

    # Grooming
    'shave', 'shaving', 'razor', 'aftershave', 'cologne', 'eau de toilette', 'fragrance', 'perfume', 'scent',
    'beard', 'mustache', 'stubble',
    'trimmer', 'clippers', 'shaver', 'pomade', 'hair gel', 'hair wax', 'hair styling',
    'grooming', 'men\'s grooming', 'barber', 'skincare', 'moisturizer', 'face wash', 'deodorant', 'antiperspirant',

    # --- German ---
    # General & Clothing
    'herren', 'herr', 'mann', 'männer', 'junge', 'jungen', 'knabe', 'kerl', 'typ', 'männlich', 'maskulin',
    'anzug', 'sakko', 'blazer', 'smoking', 'formelle kleidung', 'weste',
    'hose', 'herrenhose', 'chino', 'jeans', 'jogginghose', # Jeans/Jogginghose often neutral
    'shorts', # Often neutral
    'hemd', 'herrenhemd', 'businesshemd', 'freizeithemd', 't-shirt', 'polohemd', # T-shirt/Polohemd often neutral
    'pullover', 'strickpullover', 'pulli', 'kapuzenpullover', 'hoodie', 'sweatshirt', # Often neutral
    'boxershorts', 'unterhose', 'slip', 'herrenunterwäsche', # Herrenunterwäsche
    'badehose', 'badeshorts', 'schwimmhose',
    'trainingsanzug',

    # Shoes & Accessories
    'schuhe', 'herrenschuhe', 'halbschuhe', 'schnürschuhe', 'business-schuhe', # Herrenschuhe
    'stiefel', 'sneakers', 'turnschuhe', # Often neutral
    'krawatte', 'fliege', 'manschettenknöpfe', 'krawattennadel', 'einstecktuch',
    'gürtel', 'geldbörse', 'portemonnaie', 'brieftasche', 'aktentasche', 'umhängetasche', 'tasche',
    'uhr', 'armbanduhr', 'herrenuhr', 'uhrenarmband', 'hosenträger',
    'sonnenbrille', 'hut', 'mütze', 'kappe', 'schal', 'handschuhe',

    # Grooming
    'rasur', 'rasieren', 'rasierer', 'rasiermesser', 'after shave', 'rasierwasser', 'eau de cologne', 'kölnisch wasser', 'parfum', 'duft',
    'bart', 'schnurrbart', 'schnauzbart', 'stoppeln',
    'trimmer', 'haarschneider', 'rasierapparat', 'pomade', 'haargel', 'haarwachs', 'haarstyling',
    'körperpflege', 'männerpflege', 'herrenpflege', 'bartpflege', 'friseur', 'barbier', 'hautpflege', 'feuchtigkeitscreme', 'gesichtsreinigung', 'deo', 'deodorant',

    # --- French ---
    # General & Clothing
    'homme', 'hommes', 'garçon', 'garçons', 'monsieur', 'messieurs', 'mec', 'type', 'gars', 'masculin',
    'costume', 'complet', 'veste', 'blazer', 'smoking', 'tenue de soirée', 'gilet',
    'pantalon', 'pantalons', 'chino', 'jean', 'pantalon de jogging', # Jean/Jogging often neutral
    'short', # Often neutral
    'chemise', 'chemise habillée', 'chemisette', 't-shirt', 'polo', # T-shirt/Polo often neutral
    'pull', 'pull-over', 'chandail', 'sweat', 'sweat à capuche', 'hoodie', # Often neutral
    'boxer', 'caleçon', 'slip', 'sous-vêtement', 'sous-vêtements homme', # Masculine underwear
    'maillot de bain', 'short de bain', 'caleçon de bain',
    'survêtement',

    # Shoes & Accessories
    'chaussures', 'chaussures homme', 'chaussures de ville', 'richelieu', 'mocassin', # Men's shoes
    'bottes', 'bottines', 'baskets', 'sneakers', # Often neutral
    'cravate', 'nœud papillon', 'boutons de manchette', 'pince à cravate', 'pochette', 'mouchoir de poche',
    'ceinture', 'portefeuille', 'porte-documents', 'sacoche', 'sac', 'montre', 'bracelet de montre', 'bretelles',
    'lunettes de soleil', 'chapeau', 'casquette', 'bonnet', 'écharpe', 'gants',

    # Grooming
    'rasage', 'raser', 'se raser', 'rasoir', 'après-rasage', 'lotion après-rasage', 'eau de cologne', 'parfum',
    'barbe', 'moustache',
    'tondeuse', 'tondeuse à barbe', 'tondeuse à cheveux', 'pommade', 'gel coiffant', 'cire coiffante', 'coiffure',
    'soins homme', 'soins pour homme', 'coiffeur', 'barbier', 'soin de la peau', 'crème hydratante', 'nettoyant visage', 'déo', 'déodorant',

    # --- Spanish ---
    # General & Clothing
    'hombre', 'hombres', 'chico', 'chicos', 'señor', 'señores', 'caballero', 'caballeros', 'tío', 'tipo', 'masculino',
    'traje', 'americana', 'chaqueta', 'saco', 'esmoquin', 'traje de etiqueta', 'chaleco',
    'pantalón', 'pantalones', 'chino', 'vaqueros', 'jeans', 'pantalones de chándal', 'joggers', # Jeans/Joggers often neutral
    'pantalón corto', 'shorts', # Often neutral
    'camisa', 'camisa de vestir', 'polo', 'camiseta', # Camiseta/Polo often neutral
    'suéter', 'jersey', 'pulóver', 'sudadera', 'sudadera con capucha', # Often neutral
    'boxer', 'calzoncillo', 'slip', 'ropa interior', 'ropa interior masculina', # Masculine underwear
    'bañador', 'traje de baño', 'pantalón corto de baño',
    'chándal',

    # Shoes & Accessories
    'zapatos', 'zapatos hombre', 'zapatos de vestir', 'zapatos formales', 'mocasín', # Men's shoes
    'botas', 'botines', 'zapatillas', 'tenis', 'sneakers', # Often neutral
    'corbata', 'pajarita', 'moño', 'gemelos', 'pisacorbatas', 'pañuelo de bolsillo',
    'cinturón', 'correa', 'cartera', 'billetera', 'maletín', 'portafolio', 'bolso', 'reloj', 'correa de reloj', 'tirantes',
    'gafas de sol', 'lentes de sol', 'sombrero', 'gorra', 'gorro', 'bufanda', 'guantes',

    # Grooming
    'afeitado', 'afeitar', 'rasurar', 'maquinilla de afeitar', 'cuchilla', 'navaja', 'loción para después del afeitado', 'aftershave', 'colonia', 'agua de colonia', 'perfume', 'fragancia',
    'barba', 'bigote',
    'recortadora', 'maquinilla', 'afeitadora', 'pomada', 'gomina', 'gel fijador', 'cera para el pelo', 'peinado',
    'cuidado masculino', 'aseo masculino', 'peluquero', 'barbero', 'cuidado de la piel', 'crema hidratante', 'limpiador facial', 'desodorante', 'antitranspirante',

    # --- Italian ---
    # General & Clothing
    'uomo', 'uomini', 'ragazzo', 'ragazzi', 'signore', 'signori', 'tipo', 'maschile',
    'abito', 'completo', 'giacca', 'blazer', 'smoking', 'abito da sera', 'gilet', 'panciotto',
    'pantaloni', 'chino', 'jeans', 'pantaloni della tuta', # Jeans/Tuta often neutral
    'pantaloncini', 'shorts', # Often neutral
    'camicia', 'camicia elegante', 'polo', 'maglietta', 't-shirt', # T-shirt/Polo often neutral
    'maglione', 'pullover', 'felpa', 'felpa con cappuccio', # Often neutral
    'boxer', 'slip', 'mutande', 'biancheria intima', 'intimo uomo', # Masculine underwear
    'costume da bagno', 'pantaloncini da bagno', 'slip da bagno',
    'tuta',

    # Shoes & Accessories
    'scarpe', 'scarpe uomo', 'scarpe eleganti', 'scarpe formali', 'mocassino', # Men's shoes
    'stivali', 'stivaletti', 'sneakers', # Often neutral
    'cravatta', 'papillon', 'farfallino', 'gemelli', 'fermacravatta', 'fazzoletto da taschino', 'pochette',
    'cintura', 'portafoglio', 'ventiquattrore', 'cartella', 'borsa', 'orologio', 'cinturino', 'bretelle',
    'occhiali da sole', 'cappello', 'berretto', 'cuffia', 'sciarpa', 'guanti',

    # Grooming
    'rasatura', 'radersi', 'rasoio', 'lametta', 'dopobarba', 'lozione dopobarba', 'colonia', 'acqua di colonia', 'profumo', 'fragranza',
    'barba', 'baffi',
    'tagliacapelli', 'regolabarba', 'rasoio elettrico', 'pomata', 'gel per capelli', 'cera per capelli', 'styling capelli',
    'cura uomo', 'grooming maschile', 'barbiere', 'parrucchiere', 'cura della pelle', 'crema idratante', 'detergente viso', 'deodorante', 'antitraspirante',

    # --- Dutch ---
    # General & Clothing
    'heren', 'heer', 'man', 'mannen', 'jongen', 'jongens', 'kerel', 'gast', 'mannelijk', 'mannelijke',
    'pak', 'kostuum', 'colbert', 'blazer', 'smoking', 'formele kleding', 'gilet',
    'broek', 'pantalon', 'chino', 'spijkerbroek', 'jeans', 'joggingbroek', # Jeans/Joggingbroek often neutral
    'short', 'korte broek', # Often neutral
    'overhemd', 'hemd', 'gekleed overhemd', 'polo', 't-shirt', # T-shirt/Polo often neutral
    'trui', 'pullover', 'sweater', 'hoodie', 'sweatshirt', # Often neutral
    'boxershort', 'onderbroek', 'slip', 'herenondergoed', # Herenondergoed
    'zwembroek', 'zwemshort',
    'trainingspak',

    # Shoes & Accessories
    'schoenen', 'herenschoenen', 'nette schoenen', 'geklede schoenen', 'instapper', 'loafers', # Men's shoes
    'laarzen', 'boots', 'sneakers', 'sportschoenen', # Often neutral
    'stropdas', 'das', 'vlinderdas', 'vlinderstrik', 'manchetknopen', 'dasspeld', 'pochet',
    'riem', 'gordel', 'portemonnee', 'portefeuille', 'aktetas', 'attachékoffer', 'tas', 'horloge', 'horlogebandje', 'bretels',
    'zonnebril', 'hoed', 'pet', 'muts', 'sjaal', 'handschoenen',

    # Grooming
    'scheren', 'scheermes', 'scheerapparaat', 'aftershave', 'eau de cologne', 'parfum', 'geurtje',
    'baard', 'snor',
    'trimmer', 'tondeuse', 'pommade', 'haargel', 'haarwax', 'haarstyling',
    'verzorging', 'verzorging voor mannen', 'kapper', 'barbier', 'huidverzorging', 'vochtinbrengende crème', 'gezichtsreiniger', 'deo', 'deodorant',

    # --- Polish (PL) ---
    # General & Clothing
    'mężczyzna', 'mężczyźni', 'chłopak', 'chłopcy', 'pan', 'panowie', 'facet', 'gość', 'męski',
    'garnitur', 'komplet', 'marynarka', 'marynarka sportowa', 'blazer', 'smoking', 'strój formalny', 'kamizelka',
    'spodnie', 'chinosy', 'jeansy', 'dżinsy', 'spodnie dresowe', 'joggery', # Jeansy/Dresy często neutralne
    'szorty', 'krótkie spodenki', # Często neutralne
    'koszula', 'koszula wizytowa', 'koszulka polo', 'polo', 't-shirt', 'koszulka', # T-shirt/Polo często neutralne
    'sweter', 'pulower', 'bluza', 'bluza z kapturem', 'hoodie', # Często neutralne
    'bokserki', 'slipy', 'majtki męskie', 'bielizna męska', # Męska bielizna
    'kąpielówki', 'szorty kąpielowe', 'slipki kąpielowe',
    'dres',

    # Shoes & Accessories
    'buty', 'buty męskie', 'eleganckie buty', 'półbuty', 'buty wizytowe', 'mokasyny', # Buty męskie
    'trzewiki', 'botki', 'sneakersy', 'adidasy', 'trampki', # Często neutralne
    'krawat', 'mucha', 'muszka', 'spinki do mankietów', 'spinka do krawata', 'poszetka',
    'pasek', 'portfel', 'aktówka', 'teczka', 'torba', 'zegarek', 'pasek do zegarka', 'szelki',
    'okulary przeciwsłoneczne', 'kapelusz', 'czapka', 'czapka zimowa', 'szalik', 'rękawiczki',

    # Grooming
    'golenie', 'golić się', 'maszynka do golenia', 'brzytwa', 'płyn po goleniu', 'woda po goleniu', 'woda kolońska', 'perfumy', 'zapach',
    'broda', 'wąsy',
    'maszynka do strzyżenia', 'trymer', 'trymer do brody', 'pomada', 'żel do włosów', 'wosk do włosów', 'stylizacja włosów',
    'pielęgnacja', 'pielęgnacja dla mężczyzn', 'fryzjer', 'barber', 'pielęgnacja skóry', 'krem nawilżający', 'żel do mycia twarzy', 'dezodorant', 'antyperspirant',

    # --- Czech (CS) ---
    # General & Clothing
    'muž', 'muži', 'chlap', 'kluk', 'chlapec', 'chlapci', 'pán', 'pánové', 'chlápek', 'týpek', 'mužský', 'pánský',
    'oblek', 'komplet', 'sako', 'blejzr', 'smoking', 'formální oblečení', 'vesta',
    'kalhoty', 'chinos', 'kalhoty chino', 'džíny', 'rifle', 'tepláky', 'joggery', # Džíny/Tepláky často neutrální
    'kraťasy', 'šortky', # Často neutrální
    'košile', 'společenská košile', 'polokošile', 'polo tričko', 'tričko', # Tričko/Polokošile často neutrální
    'svetr', 'pulovr', 'mikina', 'mikina s kapucí', # Často neutrální
    'boxerky', 'slipy', 'trenýrky', 'pánské spodní prádlo', # Pánské spodní prádlo
    'plavky', 'pánské plavky', 'koupací šortky',
    'tepláková souprava',

    # Shoes & Accessories
    'boty', 'pánské boty', 'společenské boty', 'polobotky', 'mokasíny', # Pánské boty
    'kotníkové boty', 'tenisky', 'sneakers', 'kecky', # Často neutrální
    'kravata', 'motýlek', 'manžetové knoflíčky', 'kravatová spona', 'kapesníček do saka', 'pochette',
    'pásek', 'opasek', 'peněženka', 'portmonka', 'aktovka', 'diplomatka', 'taška', 'hodinky', 'řemínek k hodinkám', 'šle', 'kšandy',
    'sluneční brýle', 'klobouk', 'čepice', 'kulich', 'šála', 'rukavice',

    # Grooming
    'holení', 'holit se', 'holicí strojek', 'břitva', 'voda po holení', 'aftershave', 'kolínská voda', 'parfém', 'vůně',
    'vousy', 'knír', 'knírek', 'strniště',
    'zastřihovač', 'strojek na vlasy', 'zastřihovač vousů', 'holicí strojek elektrický', 'pomáda', 'gel na vlasy', 'vosk na vlasy', 'styling vlasů',
    'péče', 'pánská péče', 'pánská kosmetika', 'holič', 'kadeřník', 'barber', 'péče o pleť', 'hydratační krém', 'čisticí gel na obličej', 'deodorant', 'antiperspirant',

    # --- Portuguese (PT) ---
    # General & Clothing
    'homem', 'homens', 'rapaz', 'rapazes', 'moço', 'senhor', 'senhores', 'cara', 'tipo', 'masculino',
    'fato', 'terno', 'blazer', 'casaco', 'smoking', 'traje formal', 'traje a rigor', 'colete',
    'calças', 'calça', 'chino', 'jeans', 'calça de moletom', 'joggers', # Jeans/Moletom often neutral
    'calções', 'bermudas', 'shorts', # Often neutral
    'camisa', 'camisa social', 'polo', 't-shirt', 'camiseta', # T-shirt/Polo often neutral
    'camisola', 'suéter', 'pulôver', 'malha', 'moletom', 'moletom com capuz', 'hoodie', # Often neutral
    'boxer', 'cueca', 'samba-canção', 'roupa íntima', 'roupa interior masculina', # Masculine underwear
    'calção de banho', 'sunga', 'short de praia',
    'fato de treino', 'agasalho',

    # Shoes & Accessories
    'sapatos', 'sapatos homem', 'sapatos sociais', 'sapato formal', 'mocassim', # Men's shoes
    'botas', 'botins', 'ténis', 'sapatilhas', 'sneakers', # Often neutral
    'gravata', 'laço', 'gravata borboleta', 'botões de punho', 'abotoaduras', 'prendedor de gravata', 'mola de gravata', 'lenço de bolso', 'pochette',
    'cinto', 'carteira', 'porta-moedas', 'pasta', 'mala', 'mala executiva', 'bolsa', 'relógio', 'pulseira de relógio', 'suspensórios',
    'óculos de sol', 'chapéu', 'boné', 'gorro', 'cachecol', 'luvas',

    # Grooming
    'barbear', 'fazer a barba', 'barbear-se', 'máquina de barbear', 'lâmina', 'navalha', 'aftershave', 'loção pós-barba', 'colónia', 'água de colónia', 'perfume', 'fragrância',
    'barba', 'bigode',
    'aparador', 'máquina de cortar cabelo', 'barbeador elétrico', 'pomada', 'gel de cabelo', 'cera de cabelo', 'styling',
    'cuidados masculinos', 'produtos para homem', 'barbeiro', 'cabeleireiro', 'cuidados com a pele', 'hidratante', 'creme hidratante', 'limpeza de rosto', 'desodorizante', 'desodorante', 'antitranspirante',

    # --- Swedish (SV) ---
    # General & Clothing
    'herrar', 'herr', 'man', 'män', 'pojke', 'pojkar', 'kille', 'gubbe', 'typ', 'manlig', 'maskulin',
    'kostym', 'kavaj', 'blazer', 'smoking', 'formell klädsel', 'väst',
    'byxor', 'herrbyxor', 'chinos', 'jeans', 'joggingbyxor', 'mjukisbyxor', # Jeans/Joggingbyxor often neutral
    'shorts', # Often neutral
    'skjorta', 'kostymskjorta', 'pikétröja', 'polo', 't-shirt', 'tröja', # T-shirt/Polo often neutral
    'tröja', 'pullover', 'jumper', 'stickad tröja', 'sweatshirt', 'munkjacka', 'hoodie', # Often neutral
    'boxershorts', 'kalsonger', 'boxer', 'briefs', 'underkläder', 'herruderkläder', # Herruderkläder
    'badbyxor', 'boardshorts', 'badshorts',
    'träningsoverall',

    # Shoes & Accessories
    'skor', 'herrskor', 'finskor', 'kostymskor', 'loafers', 'lågskor', # Herrskor
    'stövlar', 'kängor', 'sneakers', 'gympaskor', 'sportskor', # Often neutral
    'slips', 'fluga', 'manschettknappar', 'slipsklämma', 'näsduk', 'bröstnäsduk', 'pochette',
    'bälte', 'skärp', 'plånbok', 'portmonnä', 'portfölj', 'attachéväska', 'väska', 'klocka', 'armbandsur', 'klockarmband', 'hängslen',
    'solglasögon', 'hatt', 'keps', 'mössa', 'halsduk', 'scarf', 'handskar', 'vantar',

    # Grooming
    'rakning', 'raka sig', 'rakhyvel', 'rakkniv', 'rakapparat', 'after shave', 'rakvatten', 'cologne', 'eau de cologne', 'parfym', 'doft',
    'skägg', 'mustasch',
    'trimmer', 'skäggtrimmer', 'hårtrimmer', 'pomada', 'hårgelé', 'hårvax', 'hårstyling',
    'grooming', 'hudvård för män', 'herrprodukter', 'frisör', 'barberare', 'hudvård', 'fuktighetskräm', 'ansiktsrengöring', 'deodorant', 'deo', 'antiperspirant',
}

NEUTRAL_KEYWORDS = {
    
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

