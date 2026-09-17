"""
Módulo de Taxonomía Farmacológica, Clases Terapéuticas y Diccionario de Alias/Sinónimos.
Utilizado para el enriquecimiento y propagación de interacciones en el Grafo de Conocimiento.
"""

# Diccionario de Sinónimos y Alias Comunes
SUBSTANCE_ALIASES = {
    "aspirina": "Acetilsalicílico ácido",
    "aas": "Acetilsalicílico ácido",
    "acido acetilsalicilico": "Acetilsalicílico ácido",
    "ácido acetilsalicílico": "Acetilsalicílico ácido",
    "acetilsalicilico": "Acetilsalicílico ácido",
    "acetilsalicílico": "Acetilsalicílico ácido",
    "paracetamol": "Paracetamol",
    "acetaminofeno": "Paracetamol",
    "acetaminofen": "Paracetamol",
    "acido clavulanico": "Clavulánico ácido",
    "ácido clavulánico": "Clavulánico ácido",
    "clavulanato": "Clavulánico ácido",
    "acido valproico": "Valproico ácido",
    "ácido valproico": "Valproico ácido",
    "valproato": "Valproico ácido",
    "valproato de sodio": "Valproico ácido",
    "salbutamol": "Salbutamol",
    "albuterol": "Salbutamol",
    "levotiroxina sodica": "Levotiroxina",
    "levotiroxina": "Levotiroxina",
    "t4": "Levotiroxina",
    "vitamina c": "Ascórbico ácido",
    "acido ascorbico": "Ascórbico ácido",
    "ácido ascórbico": "Ascórbico ácido",
    "vitamina b12": "Cianocobalamina",
    "vitamina d3": "Colecalciferol",
    "vitamina d": "Ergocalciferol",
    "acido folico": "Fólico ácido",
    "ácido fólico": "Fólico ácido",
    "omeprazol sodico": "Omeprazol"
}

# Definición de Clases Farmacológicas y Familias Terapéuticas
PHARMACOLOGICAL_CLASSES = {
    "AINEs (Antiinflamatorios No Esteroideos)": {
        "mention_patterns": [
            r"\baines?\b",
            r"\bantiinflamatorios?\s+no\s+esteroid\w*\b",
            r"\ba\.i\.n\.e\.s?\b",
            r"\bsalicilatos?\b"
        ],
        "core_members": [
            "Ibuprofeno", "Diclofenac", "Naproxeno", "Ketorolac", "Meloxicam",
            "Piroxicam", "Indometacina", "Celecoxib", "Etoricoxib", "Acetilsalicílico ácido",
            "Ketoprofeno", "Dexketoprofeno", "Clonixinato de lisina", "Flurbiprofeno",
            "Tenoxicam", "Aceclofenac", "Nabumetona", "Sulindac", "Mefenámico ácido"
        ],
        "action_patterns": [r"\bantiinflamatorio\b", r"\banalgésico\s+y\s+antiinflamatorio\b"]
    },
    "Anticoagulantes": {
        "mention_patterns": [
            r"\banticoagulantes?(\s+orales?)?\b",
            r"\bantivitamina\s+k\b",
            r"\binhibidores?\s+de\s+la\s+coagulaci[oó]n\b",
            r"\bcumar[ií]nic\w*\b"
        ],
        "core_members": [
            "Warfarina", "Acenocumarol", "Heparina", "Enoxaparina", "Dabigatrán",
            "Rivaroxabán", "Apixabán", "Nadroparina", "Fondaparinux", "Bivalirudina"
        ],
        "action_patterns": [r"\banticoagulante\b", r"\bantotrombótico\b"]
    },
    "Antiagregantes Plaquetarios": {
        "mention_patterns": [
            r"\bantiagregantes?(\s+plaquetarios?)?\b",
            r"\binhibidores?\s+de\s+la\s+agregaci[oó]n\s+plaquetaria\b"
        ],
        "core_members": [
            "Clopidogrel", "Acetilsalicílico ácido", "Prasugrel", "Ticagrelor",
            "Triflusal", "Cilostazol", "Dipiridamol"
        ],
        "action_patterns": [r"\bantiagregante\s+plaquetario\b"]
    },
    "Beta-bloqueantes": {
        "mention_patterns": [
            r"\bbeta[\s-]?bloqueantes?\b",
            r"\bbloqueantes?\s+beta\b",
            r"\bbetabloqueadores?\b",
            r"\bbeta[\s-]?adren[eé]rgic\w*\b"
        ],
        "core_members": [
            "Atenolol", "Bisoprolol", "Carvedilol", "Metoprolol", "Propranolol",
            "Labetalol", "Nebivolol", "Sotalol", "Timolol", "Nadolol", "Esmolol"
        ],
        "action_patterns": [r"\bbeta[\s-]?bloqueante\b", r"\bbloqueante\s+beta\b"]
    },
    "Inhibidores de la ECA (IECA)": {
        "mention_patterns": [
            r"\biecas?\b",
            r"\binhibidores?\s+de\s+la\s+eca\b",
            r"\binhibidores?\s+de\s+la\s+enzima\s+conversora\b"
        ],
        "core_members": [
            "Enalapril", "Captopril", "Ramipril", "Lisinopril", "Perindopril",
            "Benazepril", "Fosinopril", "Quinapril", "Trandolapril"
        ],
        "action_patterns": [r"\binhibidor\s+de\s+la\s+eca\b", r"\binhibidor\s+de\s+la\s+enzima\s+conversora\b"]
    },
    "Antagonistas de Receptores de Angiotensina II (ARA II)": {
        "mention_patterns": [
            r"\bara[\s-]?ii\b",
            r"\bantagonistas?\s+de(l|\s+los)?\s+receptores?\s+de\s+angiotensina\b",
            r"\bsartanes?\b"
        ],
        "core_members": [
            "Losartán", "Valsartán", "Candesartán", "Telmisartán", "Irbesartán",
            "Olmesartán", "Eprosartán"
        ],
        "action_patterns": [r"\bantagonista\s+de(l|\s+los)?\s+receptores?\s+de\s+angiotensina\b", r"\bara[\s-]?ii\b"]
    },
    "Benzodiacepinas": {
        "mention_patterns": [
            r"\bbenzodiacepinas?\b",
            r"\bbenzodiazepinas?\b",
            r"\bansiol[ií]ticos?\s+benzodiacep[ií]nic\w*\b"
        ],
        "core_members": [
            "Clonazepam", "Diazepam", "Lorazepam", "Alprazolam", "Midazolam",
            "Bromazepam", "Clobazam", "Flunitrazepam", "Triazolam", "Clorazepato"
        ],
        "action_patterns": [r"\bbenzodiacepina\b", r"\bbenzodiazepina\b"]
    },
    "Anticonvulsivantes / Antiepilépticos": {
        "mention_patterns": [
            r"\banticonvulsivantes?\b",
            r"\bantiepil[eé]ptic\w*\b",
            r"\banticonvulsivos?\b"
        ],
        "core_members": [
            "Fenitoína", "Carbamazepina", "Valproico ácido",
            "Lamotrigina", "Levetiracetam", "Gabapentina", "Pregabalina",
            "Topiramato", "Oxcarbazepina", "Fenobarbital", "Primidona", "Lacosamida"
        ],
        "action_patterns": [r"\banticonvulsivante\b", r"\bantiepiléptico\b"]
    },
    "Corticoides / Corticosteroides": {
        "mention_patterns": [
            r"\bcorticoides?\b",
            r"\bcorticosteroid\w*\b",
            r"\bglucocorticoid\w*\b",
            r"\bcorticoesteroid\w*\b"
        ],
        "core_members": [
            "Dexametasona", "Betametasona", "Prednisona", "Prednisolona",
            "Hidrocortisona", "Triamcinolona", "Metilprednisolona", "Budesonida",
            "Fluticasona", "Mometasona", "Deflazacort", "Clobetasol"
        ],
        "action_patterns": [r"\bcorticoide\b", r"\bcorticosteroide\b", r"\bglucocorticoide\b"]
    },
    "Diuréticos": {
        "mention_patterns": [
            r"\bdiur[eé]tic\w*(\s+de\s+asa|\s+tiaz[ií]dic\w*|\s+ahorradores\s+de\s+potasio)?\b",
            r"\btiazidas?\b"
        ],
        "core_members": [
            "Furosemida", "Hidroclorotiazida", "Espironolactona", "Clortalidona",
            "Torasemida", "Amilorida", "Indapamida", "Eplerenona", "Acetazolamida"
        ],
        "action_patterns": [r"\bdiurético\b"]
    },
    "Inhibidores de la Bomba de Protones (IBP)": {
        "mention_patterns": [
            r"\bibps?\b",
            r"\binhibidores?\s+de\s+la\s+bomba\s+de\s+protones\b",
            r"\bantiulcerosos?\s+ibp\b"
        ],
        "core_members": [
            "Omeprazol", "Pantoprazol", "Lansoprazol", "Esomeprazol", "Rabeprazol", "Dexlansoprazol"
        ],
        "action_patterns": [r"\binhibidor\s+de\s+la\s+bomba\s+de\s+protones\b"]
    },
    "Macrólidos": {
        "mention_patterns": [
            r"\bmacr[oó]lidos?\b",
            r"\bantibi[oó]ticos?\s+macr[oó]lidos?\b"
        ],
        "core_members": [
            "Azitromicina", "Claritromicina", "Eritromicina", "Espiramicina", "Roxitromicina"
        ],
        "action_patterns": [r"\bmacrólido\b", r"\bantibiótico\s+macrólido\b"]
    },
    "Quinolonas / Fluoroquinolonas": {
        "mention_patterns": [
            r"\bquinolonas?\b",
            r"\bfluoroquinolonas?\b"
        ],
        "core_members": [
            "Ciprofloxacina", "Levofloxacina", "Moxifloxacina", "Norfloxacina", "Ofloxacina"
        ],
        "action_patterns": [r"\bquinolona\b", r"\bfluoroquinolona\b"]
    },
    "Aminoglucósidos": {
        "mention_patterns": [
            r"\baminogluc[oó]sidos?\b",
            r"\baminoglic[oó]sidos?\b"
        ],
        "core_members": [
            "Gentamicina", "Amikacina", "Tobramicina", "Estreptomicina", "Neomicina", "Kanamicina"
        ],
        "action_patterns": [r"\baminoglucósido\b"]
    },
    "Antidepresivos Tricíclicos (ATC)": {
        "mention_patterns": [
            r"\bantidepresivos?\s+tric[ií]clicos?\b",
            r"\batcs?\b",
            r"\btric[ií]clicos?\b"
        ],
        "core_members": [
            "Amitriptilina", "Imipramina", "Clomipramina", "Nortriptilina", "Doxepina", "Trimipramina"
        ],
        "action_patterns": [r"\bantidepresivo\s+tricíclico\b"]
    },
    "ISRS (Inhibidores de Recaptación de Serotonina)": {
        "mention_patterns": [
            r"\bisrs\b",
            r"\binhibidores?\s+(selectivos?\s+)?de\s+la\s+recaptaci[oó]n\s+de\s+serotonina\b"
        ],
        "core_members": [
            "Fluoxetina", "Sertralina", "Paroxetina", "Citalopram", "Escitalopram", "Fluvoxamina"
        ],
        "action_patterns": [r"\binhibidor\s+de\s+la\s+recaptación\s+de\s+serotonina\b", r"\bisrs\b"]
    },
    "IMAO (Inhibidores de Monoaminooxidasa)": {
        "mention_patterns": [
            r"\bimaos?\b",
            r"\binhibidores?\s+de\s+la\s+monoaminooxidasa\b",
            r"\bimao[\s-]?a\b",
            r"\bimao[\s-]?b\b"
        ],
        "core_members": [
            "Moclobemida", "Selegilina", "Tranilcipromina", "Fenelzina", "Rasagilina"
        ],
        "action_patterns": [r"\binhibidor\s+de\s+la\s+monoaminooxidasa\b", r"\bimao\b"]
    },
    "Digitálicos / Glucósidos Cardíacos": {
        "mention_patterns": [
            r"\bdigit[aá]licos?\b",
            r"\bgluc[oó]sidos?\s+card[ií]acos?\b",
            r"\bcardiot[oó]nicos?\b"
        ],
        "core_members": [
            "Digoxina", "Digitoxina", "Deslanósido"
        ],
        "action_patterns": [r"\bcardiotónico\b", r"\bdigitálico\b"]
    },
    "Hipoglucemiantes / Antidiabéticos": {
        "mention_patterns": [
            r"\bhipoglucemiantes?(\s+orales?)?\b",
            r"\bantidiab[eé]ticos?(\s+orales?)?\b",
            r"\bsulfonilureas?\b",
            r"\binsulinas?\b"
        ],
        "core_members": [
            "Metformina", "Glibenclamida", "Glimepirida", "Gliclazida", "Sitagliptina",
            "Empagliflozina", "Dapagliflozina", "Linagliptina", "Vildagliptina", "Pioglitazona"
        ],
        "action_patterns": [r"\bhipoglucemiante\b", r"\bantidiabético\b"]
    },
    "Opioides / Analgésicos Narcóticos": {
        "mention_patterns": [
            r"\bopioides?\b",
            r"\bopi[aá]ceos?\b",
            r"\banalg[eé]sicos?\s+narc[oó]ticos?\b",
            r"\banalg[eé]sicos?\s+mayores?\b"
        ],
        "core_members": [
            "Morfina", "Tramadol", "Fentanilo", "Oxicodona", "Codeína", "Metadona",
            "Buprenorfina", "Remifentanilo", "Petidina", "Dextropropoxifeno"
        ],
        "action_patterns": [r"\bopioide\b", r"\bopiáceo\b", r"\banalgésico\s+narcótico\b"]
    },
    "Estatinas (Inhibidores de HMG-CoA)": {
        "mention_patterns": [
            r"\bestatinas?\b",
            r"\binhibidores?\s+de\s+la\s+hmg[\s-]?coa\b"
        ],
        "core_members": [
            "Atorvastatina", "Rosuvastatina", "Simvastatina", "Pravastatina", "Fluvastatina", "Pitavastatina"
        ],
        "action_patterns": [r"\bestatina\b", r"\bhipolipemiante\b"]
    },
    "Antihistamínicos H1": {
        "mention_patterns": [
            r"\bantihistam[ií]nicos?(\s+h1)?\b",
            r"\bantagonistas?\s+h1\b"
        ],
        "core_members": [
            "Loratadina", "Cetirizina", "Difenhidramina", "Desloratadina",
            "Clorfeniramina", "Fexofenadina", "Levocetirizina", "Hidroxizina", "Ebastina"
        ],
        "action_patterns": [r"\bantihistamínico\b", r"\bantagonista\s+h1\b"]
    },
    "Neurolépticos / Antipsicóticos": {
        "mention_patterns": [
            r"\bneurol[eé]pticos?\b",
            r"\bantipsic[oó]ticos?\b"
        ],
        "core_members": [
            "Haloperidol", "Risperidona", "Quetiapina", "Olanzapina", "Aripiprazol",
            "Clozapina", "Clorpromazina", "Levomepromazina", "Sulpirida", "Ziprasidona"
        ],
        "action_patterns": [r"\bneuroléptico\b", r"\bantipsicótico\b"]
    },
    "Nitratos / Vasodilatadores Coronarios": {
        "mention_patterns": [
            r"\bnitratos?(\s+org[aá]nicos?)?\b",
            r"\bnitritos?\b",
            r"\bvasodilatadores?\s+coronarios?\b",
            r"\bdonantes?\s+de\s+[oó]xido\s+n[ií]trico\b"
        ],
        "core_members": [
            "Nitroglicerina", "Dinitrato de isosorbida", "Mononitrato de isosorbida", "Nitroprusiato de sodio"
        ],
        "action_patterns": [r"\bnitrato\b", r"\bvasodilatador\s+coronario\b", r"\bantianginoso\b"]
    }
}
