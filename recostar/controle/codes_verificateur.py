"""
Referentiel des codes d'erreur du verificateur RecoStaR et table de correspondance.

Chaque controle porte le code du verificateur qu'il emet : `code_controle` et
`code_erreur` sont un seul et meme code (« E-5107 »).

Un controle releve en revanche plusieurs **types d'anomalie** sous ce code — sous
E-5107, `absence_coordonnee_z` et `z_null`. `CORRESPONDANCES` declare, pour
chaque couple `(code_controle, type_anomalie)`, le code d'erreur rendu : elle
tient lieu de registre des types legitimes de chaque code, que le test
d'exhaustivite confronte aux types reellement emis.

Module pur (aucune E/S, aucun import du reste du projet) : entierement testable
et importable a plat par les modules de controle comme par les tests.

Sources, toutes deux en version 2.14.0 : les fiches
`RecoStaR/Verificateur/Description erreurs verificateur/` — dont le sommaire
donne le statut et la version d'introduction de chaque code, et dont les
sections de niveau (« Erreurs fortes »...) donnent sa gravite — et la matrice de
couverture `correspondance_controles_star-engine_verificateur`, qui rattache
chaque code aux controles star-engine.

Le referentiel couvre les **97 codes en service** ; les 12 codes retires sont
isoles dans `CODES_SUPPRIMES`, que le test d'integrite refuse de voir vises.

Il reproduit la nomenclature du verificateur sans l'interpreter, a **une
exception pres** : le libelle d'E-6213 a ete corrige, celui des fiches 2.14.0
contredisant deux autres codes du meme referentiel. Toute correction de ce genre
porte son motif sur la fiche concernee, faute de quoi l'ecart avec le
verificateur deviendrait invisible — meme exigence que pour
`DEROGATIONS_NIVEAU`.
Les couples dont le code reste a fixer sont declares dans `COUPLES_A_QUALIFIER`
avec leur motif : `resoudre_code_erreur` y retourne `None`, ce qui rend la
migration progressive et non bloquante.
"""

from dataclasses import dataclass
from functools import lru_cache

# Version du referentiel du verificateur reproduite ici. Toute mise a jour des
# fiches doit s'accompagner d'une revision de cette constante : elle rend le
# desalignement visible en revue plutot que silencieux.
VERSION_REFERENTIEL: str = "2.14.0"

# ---------------------------------------------------------------------------
# Echelle de niveaux du verificateur
# ---------------------------------------------------------------------------

# Niveaux du lexique du verificateur, du plus grave au moins grave.
#   - bloquante : interrompt le traitement ;
#   - forte     : n'interrompt pas, mais le certificat n'est pas conforme ;
#   - moyenne   : n'empeche pas la conformite, a corriger ;
#   - basse     : pour information.
NIVEAU_BLOQUANTE: str = "bloquante"
NIVEAU_FORTE: str = "forte"
NIVEAU_MOYENNE: str = "moyenne"
NIVEAU_BASSE: str = "basse"

# Ordre de gravite decroissante, exploite par le lot 2 (echelle de priorites).
ORDRE_NIVEAUX: tuple[str, ...] = (
    NIVEAU_BLOQUANTE,
    NIVEAU_FORTE,
    NIVEAU_MOYENNE,
    NIVEAU_BASSE,
)

# Niveaux qui declassent une livraison. Le lot 2 y alignera
# `PRIORITES_DECLASSANTES` : ce qui declassait sous « bloquant » declasse sous
# « forte ». frozenset : appartenance en O(1) et valeur immuable.
NIVEAUX_DECLASSANTS: frozenset[str] = frozenset({NIVEAU_BLOQUANTE, NIVEAU_FORTE})


# ---------------------------------------------------------------------------
# Referentiel des codes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CodeVerificateur:
    """Fiche d'un code d'erreur du verificateur.

    - `code` : identifiant normalise (« E-5102 ») ;
    - `libelle` : libelle de l'erreur, repris tel quel des fiches — a l'unique
      exception d'E-6213, corrige par arbitrage metier (motif sur sa fiche) ;
    - `niveau` : niveau du verificateur, deduit de la section de la fiche ;
    - `version_introduction` : version du referentiel introduisant le code ;
    - `activation` : fenetre d'activation calendaire, portee par les seuls
      triplets E-71xx / E-72xx / E-73xx, qui declinent la meme regle a trois
      niveaux selon la date. None pour tous les autres codes.
    """

    code: str
    libelle: str
    niveau: str
    version_introduction: str
    activation: str | None = None


# Fiches du referentiel, groupees par serie de codes. Un niveau a None signale
# une donnee non encore relevee dans les fiches, jamais un niveau absent.
_FICHES: tuple[CodeVerificateur, ...] = (
    # --- Erreurs internes ----------------------------------------------
    CodeVerificateur(
        "E-0000",
        "Une erreur est survenue lors du traitement : celui-ci n'a pas abouti. Merci d’envoyer un message via le bouton « Contact » d’Aloé, avec le choix : « Problème de soumission du récolement sur Aloé »",
        NIVEAU_BLOQUANTE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-0001",
        "Anomalie fichier GML (GML manquant, illisible ou plusieurs GML)",
        NIVEAU_BLOQUANTE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-0002",
        "Transformation RecoStaR en DGN avec GML non conforme. Traitement interrompu",
        NIVEAU_BLOQUANTE,
        "2.8.0",
    ),
    # --- Structure du GML ----------------------------------------------
    CodeVerificateur("E-0003", "Le code EPSG de projection n'est pas conforme", NIVEAU_BLOQUANTE, "2.8.0"),
    CodeVerificateur("E-0004", "Le GML ne contient aucune donnée", NIVEAU_BLOQUANTE, "2.8.0"),
    CodeVerificateur(
        "E-0007",
        "L'information du système de projection portée par les objets du GML n'est pas unique sur l'ensemble du fichier",
        NIVEAU_BLOQUANTE,
        "2.8.0",
    ),
    CodeVerificateur("E-0008", "Deux objets possèdent le même gml_id", NIVEAU_BLOQUANTE, "2.8.0"),
    CodeVerificateur(
        "E-0009",
        "Incohérence entre le srsDimension et les coordonnées de l'objet",
        NIVEAU_BLOQUANTE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-0010",
        "Le fichier GML ne contient pas de référence au fichier XSD de spécification RecoStaR",
        NIVEAU_BLOQUANTE,
        "2.10.1",
    ),
    CodeVerificateur(
        "E-0011",
        "Les cheminements d'un même câble sont superposés ou disjoints",
        NIVEAU_BLOQUANTE,
        "2.11.0",
    ),
    CodeVerificateur("E-0012", "Une table de jointure a un doublon", NIVEAU_BLOQUANTE, "2.11.1"),
    CodeVerificateur("E-0013", "Champ manquant sur une table de jointure", NIVEAU_BLOQUANTE, "2.13.0"),
    CodeVerificateur("E-1100", "Objet ou valeur non spécifié dans le standard StaR-Elec (XSD)", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur("E-1101", "Attribut obligatoire manquant (contrôle XSD)", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur(
        "E-1102",
        "Contrôle des géométries et de leur conteneur obligatoires par objet",
        NIVEAU_FORTE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-1103",
        "Le fichier GML ne respecte pas la nomenclature du namespace du XSD",
        NIVEAU_FORTE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-1104",
        "Le XMLValidator (vérificateur de la structure XSD de FME) renvoie un résultat non conforme",
        NIVEAU_MOYENNE,
        "2.8.0",
    ),
    CodeVerificateur("E-1106", "Un champ supplémentaire est présent dans le fichier GML", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur("E-1107", "Le fichier GML ne comprend pas les métadonnées requises", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur("E-1108", "La géométrie n'est pas valide (vertex manquant)", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur("E-1109", "Géométrie supplémentaire sans géométrie", NIVEAU_FORTE, "2.12.0"),
    CodeVerificateur("E-1200", "Erreur inconnue (contrôle XSD)", NIVEAU_MOYENNE, "2.8.0"),
    CodeVerificateur("E-1201", "Absence de srsDimension sur les objets ponctuels", NIVEAU_MOYENNE, "2.8.0"),
    CodeVerificateur("E-1300", "Le srsDimension dans le fichier GML n'est pas correct", NIVEAU_BASSE, "2.8.0"),
    CodeVerificateur("E-2200", "Le système de projection de l'objet n'est pas défini", NIVEAU_MOYENNE, "2.8.0"),
    # --- Domaines de valeurs -------------------------------------------
    CodeVerificateur(
        "E-2100",
        "La valeur énumérée de l'attribut ne correspond pas à une valeur autorisée",
        NIVEAU_FORTE,
        "2.8.0",
    ),
    CodeVerificateur("E-2101", "Câble avec désignation non normalisée", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur("E-2102", "Attributs obligatoires dans la version 1.1", NIVEAU_FORTE, "2.12.1"),
    CodeVerificateur("E-2201", "Les attributs Classe et Effort ne sont pas cohérents", NIVEAU_MOYENNE, "2.8.0"),
    CodeVerificateur(
        "E-7100",
        "Boite de jonction / dérivation sans matériel associé",
        NIVEAU_FORTE,
        "2.8.0",
        "Active au 01/04/2026",
    ),
    CodeVerificateur(
        "E-7101",
        "Boite de jonction / dérivation avec plusieurs matériels associés",
        NIVEAU_FORTE,
        "2.8.0",
        "Active au 01/04/2026",
    ),
    CodeVerificateur(
        "E-7102",
        "Matériel non associé à un objet de type boite de jonction / dérivation",
        NIVEAU_FORTE,
        "2.8.0",
        "Active au 01/01/2027",
    ),
    CodeVerificateur(
        "E-7103",
        "Matériel associé à un objet de type boite de jonction / dérivation qui n'est pas au statut UnderCommissionning",
        NIVEAU_FORTE,
        "2.8.0",
        "Active au 01/01/2027",
    ),
    CodeVerificateur(
        "E-7104",
        "Le couple Fabriquant / modèle ne fait pas parti du catalogue",
        # Les fiches classent ce code en « moyenne » : un materiel hors
        # catalogue est a corriger sans empecher la conformite.
        NIVEAU_MOYENNE,
        "2.8.0",
        "Active au 01/01/2027",
    ),
    CodeVerificateur(
        "E-7200",
        "Boite de jonction / dérivation sans matériel associé",
        NIVEAU_MOYENNE,
        "2.8.0",
        "Active au 01/01/2026 au 01/04/2026",
    ),
    CodeVerificateur(
        "E-7201",
        "Boite de jonction / dérivation avec plusieurs matériels associés",
        NIVEAU_MOYENNE,
        "2.8.0",
        "Active au 01/01/2026 au 01/04/2026",
    ),
    CodeVerificateur(
        "E-7202",
        "Matériel non associé à un objet de type boite de jonction / dérivation",
        NIVEAU_MOYENNE,
        "2.8.0",
        "Active au 01/01/2026 au 01/01/2027",
    ),
    CodeVerificateur(
        "E-7203",
        "Matériel associé à un objet de type boite de jonction / dérivation qui n'est pas au statut UnderCommissionning",
        NIVEAU_MOYENNE,
        "2.8.0",
        "Active au 01/01/2026 au 01/01/2027",
    ),
    CodeVerificateur(
        "E-7204",
        "Le couple Fabriquant / modèle ne fait pas parti du catalogue",
        NIVEAU_MOYENNE,
        "2.8.0",
        "Active au 01/04/2026 au 01/01/2027",
    ),
    CodeVerificateur(
        "E-7300",
        "Boite de jonction / dérivation sans matériel associé",
        NIVEAU_BASSE,
        "2.8.0",
        "Active avant le 01/01/2026",
    ),
    CodeVerificateur(
        "E-7301",
        "Boite de jonction / dérivation avec plusieurs matériels associés",
        NIVEAU_BASSE,
        "2.8.0",
        "Active avant le 01/01/2026",
    ),
    CodeVerificateur(
        "E-7302",
        "Matériel non associé à un objet de type boite de jonction / dérivation",
        NIVEAU_BASSE,
        "2.8.0",
        "Active avant le 01/01/2026",
    ),
    CodeVerificateur(
        "E-7303",
        "Matériel associé à un objet de type boite de jonction / dérivation qui n'est pas au statut UnderCommissionning",
        NIVEAU_BASSE,
        "2.8.0",
        "Active avant le 01/01/2026",
    ),
    CodeVerificateur(
        "E-7304",
        "Le couple Fabriquant / modèle ne fait pas parti du catalogue",
        NIVEAU_BASSE,
        "2.8.0",
        "Active au 01/01/2026 au 01/04/2026",
    ),
    CodeVerificateur("E-7305", "La casse du couple Fabriquant / Modèle n'est pas correcte", NIVEAU_BASSE, "2.10.0"),
    # --- Reference de dossier ------------------------------------------
    CodeVerificateur(
        "E-0005",
        "Le numéro de dossier ne correspond pas aux modèles attendus",
        NIVEAU_BLOQUANTE,
        "2.8.0",
    ),
    CodeVerificateur("E-0006", "Le numéro de dossier ne renvoie pas à une DR connue", NIVEAU_BLOQUANTE, "2.8.0"),
    # --- Typage --------------------------------------------------------
    CodeVerificateur("E-3100", "Les attributs du nœud ne permettent pas de l'identifier", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur("E-3102", "Le câble n'est pas associé à un cheminement", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur("E-3103", "Le cheminement n'a pas le nombre de câble attendu", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur("E-3104", "Les attributs du câble ne permettent pas de l'identifier", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur("E-3106", "Les attributs du conteneur ne permettent pas de l'identifier", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur(
        "E-3109",
        "Un câble de terre est associé à une protection mécanique ou un cheminement aérien",
        NIVEAU_FORTE,
        "2.8.0",
    ),
    CodeVerificateur("E-3110", "L'objet n'a aucune géométrie supplémentaire", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur(
        "E-3111",
        "Le câble est associé à des cheminements de type aériens et souterrains",
        NIVEAU_FORTE,
        "2.11.0",
    ),
    CodeVerificateur("E-3302", "Présence d'une valeur HierarchieBT pour un câble HTA", NIVEAU_BASSE, "2.8.0"),
    CodeVerificateur("E-3304", "Présence de HTB dans le fichier GML en France métropolitaine", NIVEAU_BASSE, "2.8.0"),
    # --- Geographiques -------------------------------------------------
    CodeVerificateur("E-3300", "PLOR superposé avec même type de levé", NIVEAU_BASSE, "2.8.0"),
    CodeVerificateur("E-4200", "La longueur du câble BT est supérieure à 250 m", NIVEAU_MOYENNE, "2.8.0"),
    CodeVerificateur("E-4201", "La longueur du câble HTA est supérieure à 500 m", NIVEAU_MOYENNE, "2.8.0"),
    CodeVerificateur(
        "E-5100",
        "Nombre de points levés insuffisant dans les parties rectilignes",
        NIVEAU_FORTE,
        "2.8.0",
    ),
    CodeVerificateur("E-5101", "Nombre de points levés insuffisant dans les parties courbes", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur("E-5102", "Le sommet n'est pas associé à un PLOR / PTRL", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur("E-5103", "Le Z du sommet n'est pas cohérent avec le Z du PLOR / PTRL", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur(
        "E-5105",
        "Le système de projection du GML n'est pas similaire au système de projection des objets",
        NIVEAU_FORTE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-5106",
        "Les données géographiques du GML ne sont pas dans l'emprise de la DR indiquée par le numéro de dossier",
        NIVEAU_FORTE,
        "2.8.0",
    ),
    CodeVerificateur("E-5107", "Vertex / Point sans Z défini", NIVEAU_BASSE, "2.9.0"),
    CodeVerificateur("E-5108", "Deux cheminements sont superposés", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur("E-5200", "Nombre de points levés insuffisant dans les courbes", NIVEAU_MOYENNE, "2.8.0"),
    CodeVerificateur("E-5201", "Le Z du sommet est incohérent avec les sommets adjacents", NIVEAU_MOYENNE, "2.8.0"),
    CodeVerificateur(
        "E-6103",
        "Merci de vous rapprocher de votre agence carto pour justifier la non classe A",
        NIVEAU_FORTE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-6104",
        "Présence d'un PLOR de type ChargeGeneratrice sans PLOR de type AltitudeGeneratrice superposé (profondeur atypique)",
        NIVEAU_FORTE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-6116",
        "Une jonction de télécommunication doit être à moins de 5cm d'un câble de télécommunication",
        NIVEAU_FORTE,
        "2.14.0",
    ),
    CodeVerificateur(
        "E-6205",
        "Absence d'un PLOR de type ChargeGeneratrice pour un cheminement avec Profondeur Atypique renseignée",
        NIVEAU_MOYENNE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-6206",
        "Le fichier possède des PLOR superposés en X,Y avec un mode de levé identique (Z identique ou différent)",
        NIVEAU_MOYENNE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-6207",
        'PLOR avec valeur de "levé" différente de l\'altitude du PLOR',
        NIVEAU_MOYENNE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-6210",
        "Les sommets du bâtiment technique ou de l'enceinte clôturée n'ont pas tous un PLOR",
        NIVEAU_MOYENNE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-6211",
        "Le PLOR du type ChargeGéneratrice ne se trouve pas à proximité d'un cheminement avec ProfondeurMinNonReg",
        NIVEAU_MOYENNE,
        "2.8.0",
    ),
    # --- Topologiques --------------------------------------------------
    CodeVerificateur("E-6102", "Le câble n'est pas coupé à chaque nœud", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur(
        "E-6105",
        "Le nœud sans géométrie n'est pas lié à un conteneur ou ce dernier n'est pas identifiable",
        NIVEAU_FORTE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-6106",
        "Le nœud est sans géométrie et est lié à un conteneur sans géométrie",
        NIVEAU_FORTE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-6107",
        "Nœud réseau manquant. Coffret n'a pas de nœud réseau conforme identifié",
        NIVEAU_MOYENNE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-6108",
        "Lien erroné : le coffret est lié à un nœud réseau non conforme",
        NIVEAU_MOYENNE,
        "2.8.0",
    ),
    CodeVerificateur(
        "E-6109",
        "Le point de comptage sans géométrie n'est pas dans un coffret ou un bâtiment technique",
        NIVEAU_FORTE,
        "2.8.0",
    ),
    CodeVerificateur("E-6110", "Le câble n'est pas lié à deux nœuds", NIVEAU_FORTE, "2.8.0"),
    CodeVerificateur(
        "E-6111",
        "Les extrémités de câble ne sont pas jointes géométriquement aux nœuds liés",
        NIVEAU_MOYENNE,
        "2.8.0",
    ),
    CodeVerificateur("E-6112", "Ce nœud ne peut pas exister sans conteneur", NIVEAU_FORTE, "2.10.0"),
    CodeVerificateur(
        "E-6113",
        "Un câble de télécommunication ne doit pas être lié à un Noeud électrique",
        NIVEAU_FORTE,
        "2.14.0",
    ),
    CodeVerificateur(
        "E-6114",
        "Un coffret de télécommunication ne doit pas être lié à un nœud éléctrique",
        NIVEAU_FORTE,
        "2.14.0",
    ),
    CodeVerificateur(
        "E-6115",
        "Un câble électrique ne doit pas être lié à un nœud de télécommunication",
        NIVEAU_FORTE,
        "2.14.0",
    ),
    CodeVerificateur("E-6201", "Jonction de type dérivation avec moins de 3 câbles raccordés", NIVEAU_MOYENNE, "2.8.0"),
    CodeVerificateur("E-6202", "Jonction de type jonction avec moins de 2 câbles raccordés", NIVEAU_MOYENNE, "2.8.0"),
    CodeVerificateur(
        "E-6203",
        "Jonction de type extrémité réseau non liée à un câble et un seul",
        NIVEAU_MOYENNE,
        "2.8.0",
    ),
    CodeVerificateur("E-6204", "Jonction de type RAS sans câble raccordé", NIVEAU_MOYENNE, "2.8.0"),
    CodeVerificateur("E-6208", "Aucune cohérence entre coffret et nœud", NIVEAU_MOYENNE, "2.8.0"),
    CodeVerificateur("E-6209", "Le nœud a une géométrie et est lié a un conteneur", NIVEAU_MOYENNE, "2.8.0"),
    # Libelle corrige par arbitrage metier, seule entree du referentiel dans ce
    # cas. Les fiches 2.14.0 portent « Un cable de telecommunication ne doit pas
    # etre lie a un noeud de telecommunication », ce qui contredit E-6116 — lequel
    # exige precisement ce rattachement — et E-6113, qui l'interdit partout
    # ailleurs. Le libelle d'origine est donc tenu pour errone, et le code rendu
    # au seul cas de separation qu'aucun autre ne couvre. A reverifier a la
    # prochaine version des fiches : si le verificateur corrige de son cote, les
    # deux libelles se rejoindront et ce commentaire n'aura plus lieu d'etre.
    CodeVerificateur(
        "E-6213",
        "Un câble de terre ne doit pas être lié à un nœud de télécommunication",
        NIVEAU_MOYENNE,
        "2.14.0",
    ),
)

# Referentiel indexe par code : acces O(1) depuis la resolution et les tests.
# Copie fidele des 97 codes en service du verificateur : rien d'autre n'y entre,
# faute de quoi la comparaison avec les fiches cesserait d'etre mecanique.
REFERENTIEL: dict[str, CodeVerificateur] = {fiche.code: fiche for fiche in _FICHES}

# Codes retires de la nomenclature du verificateur. Les reintroduire par
# inadvertance produirait des rapports pointant des fiches inexistantes : le
# test d'integrite les refuse explicitement.
CODES_SUPPRIMES: frozenset[str] = frozenset(
    {
        "E-115",  # retire en 2.10.1
        "E-311",  # retire en 2.10.0
        "E-315",  # retire en 2.10.0
        "E-317",  # retire en 2.9.0
        "E-318",  # retire en 2.9.0
        "E-321",  # retire en 2.9.0
        "E-333",  # retire en 2.10.0
        "E-610",  # retire en 2.9.0
        "E-620",  # retire en 2.9.0
        "E-632",  # retire en 2.9.0
        "E-633",  # retire en 2.9.0
        "E-735",  # retire en 2.8.0
    }
)


# ---------------------------------------------------------------------------
# Codes locaux star-engine (serie E-9xxx)
# ---------------------------------------------------------------------------

# Prefixe de la serie reservee aux controles que star-engine assure sans qu'ils
# aient d'equivalent dans la nomenclature du verificateur. Le verificateur
# n'utilise que les milliers 0 a 7 : la serie 9000 lui est etrangere et le
# restera, ce qui rend toute collision future improbable et immediatement
# visible.
PREFIXE_CODE_LOCAL: str = "E-9"

# Numerotation `E-9<famille><sequence>`, la famille reprenant le chiffre des
# centaines du code de controle star-engine : 2 altimetrie, 3 projection,
# 4 cheminement, 5 cable, 6 conteneur. Un lecteur situe donc le code sans table.
#
# Le niveau de chaque fiche reprend la priorite de repli de son controle :
# attribuer un code ne change aucun statut de conformite.
# Ces niveaux sont les seuls du referentiel a relever d'une decision interne,
# et non d'une fiche du verificateur.
_FICHES_LOCALES: tuple[CodeVerificateur, ...] = (
    # --- Altimetrie --------------------------------------------------------
    CodeVerificateur(
        "E-9200",
        "L'altitude du sommet s'écarte de l'altitude IGN au-delà du seuil autorisé",
        NIVEAU_BASSE,
        "1.0.3",
    ),
    CodeVerificateur(
        "E-9201",
        "La géométrie supplémentaire de coffret n'est superposée à aucun point levé",
        NIVEAU_FORTE,
        "1.0.3",
    ),
    CodeVerificateur(
        "E-9202",
        "La géométrie supplémentaire de support n'est superposée à aucun point levé",
        NIVEAU_FORTE,
        "1.0.3",
    ),
    # --- Projection --------------------------------------------------------
    CodeVerificateur(
        "E-9300",
        "L'entité appartient à un groupe d'entités détaché du reste du réseau",
        NIVEAU_FORTE,
        "1.0.3",
    ),
    CodeVerificateur(
        "E-9301",
        "La géométrie supplémentaire dépasse la superficie maximale admise",
        NIVEAU_FORTE,
        "1.0.3",
    ),
    # Le verificateur nomme ce defaut E-0007, code que l'arbitrage metier ecarte
    # au profit d'un code local : la regle est evaluee sur les GeoJSON convertis,
    # ou « le fichier » du verificateur est devenu un jeu de fichiers. Le niveau
    # reprend celui d'E-5105, la comparaison voisine.
    CodeVerificateur(
        "E-9302",
        "Les fichiers du jeu ne portent pas tous le même système de projection",
        NIVEAU_FORTE,
        "1.0.4",
    ),
    # --- Cheminement -------------------------------------------------------
    # Le verificateur nomme ce defaut E-0011, « les cheminements d'un meme cable
    # sont superposes ou disjoints ». Son volet « superposes » est deja rendu par
    # E-5108 ; l'arbitrage metier ecarte le code au profit d'un code local, dont
    # le libelle ne retient que le volet restant.
    CodeVerificateur(
        "E-9401",
        "Les cheminements d'un même câble sont disjoints",
        NIVEAU_FORTE,
        "1.0.5",
    ),
    CodeVerificateur(
        "E-9400",
        "Le cheminement référence un câble qui n'existe pas dans le jeu de données",
        NIVEAU_FORTE,
        "1.0.3",
    ),
    # --- Cable -------------------------------------------------------------
    CodeVerificateur(
        "E-9500",
        "Le DomaineTension de la jonction diffère de celui du câble raccordé",
        NIVEAU_FORTE,
        "1.0.3",
    ),
    CodeVerificateur(
        "E-9501",
        "Le câble de terre n'est raccordé à aucun nœud du réseau",
        NIVEAU_MOYENNE,
        "1.0.3",
    ),
    CodeVerificateur(
        "E-9502",
        "La jonction n'est pas positionnée sur une extrémité du câble",
        NIVEAU_FORTE,
        "1.0.3",
    ),
    # --- Conteneur ---------------------------------------------------------
    CodeVerificateur(
        "E-9600",
        "Le matériel référencé par la jonction n'existe pas dans RPD_Materiel_Reco",
        NIVEAU_MOYENNE,
        "1.0.3",
    ),
    CodeVerificateur(
        "E-9601",
        "Le couple NumeroLot / NumeroSerie du matériel est associé à plusieurs jonctions",
        NIVEAU_MOYENNE,
        "1.0.3",
    ),
    CodeVerificateur(
        "E-9602",
        "La Hauteur du support n'est pas référencée au catalogue pour cette matière",
        NIVEAU_MOYENNE,
        "1.0.3",
    ),
    CodeVerificateur(
        "E-9603",
        "La Matiere du support n'est couverte par aucune matière du catalogue",
        NIVEAU_MOYENNE,
        "1.0.3",
    ),
    CodeVerificateur(
        "E-9604",
        "La référence déclarée par cables_href ne correspond à aucune entité du jeu de données",
        NIVEAU_FORTE,
        "1.0.3",
    ),
    CodeVerificateur(
        "E-9605",
        "Le nœud ne déclare aucun rattachement à un câble : cables_href n'est pas renseigné",
        NIVEAU_FORTE,
        "1.0.3",
    ),
    CodeVerificateur(
        "E-9606",
        "Le champ cables_href du nœud est renseigné mais ne porte aucune référence exploitable",
        NIVEAU_FORTE,
        "1.0.3",
    ),
    CodeVerificateur(
        "E-9607",
        "La référence déclarée par cables_href désigne une entité qui n'est pas un câble",
        NIVEAU_FORTE,
        "1.0.3",
    ),
    CodeVerificateur(
        "E-9608",
        "La référence déclarée par cables_href n'a pas la forme d'un identifiant résolvable",
        NIVEAU_FORTE,
        "1.0.3",
    ),
    # Le verificateur code le compte de cables (E-6201 a E-6203) mais ne nomme
    # pas la divergence entre ce que la jonction declare et ce que la geometrie
    # confirme : ce code local la porte.
    CodeVerificateur(
        "E-9609",
        "Les raccordements déclarés par la jonction et ses coïncidences géométriques divergent",
        NIVEAU_MOYENNE,
        "1.0.4",
    ),
    # --- Jeu de donnees ----------------------------------------------------
    # Ces deux codes ne visent aucun objet : ils qualifient la livraison
    # entiere, et sont les seuls a remonter en tete du rapport.
    CodeVerificateur(
        "E-9700",
        "La livraison ne contient aucun ouvrage en attente de mise en service",
        NIVEAU_MOYENNE,
        "1.0.5",
    ),
    CodeVerificateur(
        "E-9701",
        "Le tracé du câble n'est pas altimétré : ses points de levé sont tous à l'altitude nulle",
        NIVEAU_FORTE,
        "1.0.5",
    ),
)

# Referentiel local indexe par code, tenu a part de `REFERENTIEL` pour que ce
# dernier reste comparable ligne a ligne aux fiches du verificateur.
REFERENTIEL_LOCAL: dict[str, CodeVerificateur] = {fiche.code: fiche for fiche in _FICHES_LOCALES}

# Vue de resolution : tout code qu'un rapport peut porter, quelle que soit son
# origine. C'est elle, et non `REFERENTIEL`, que consultent `niveau_code_erreur`
# et `libelle_code_erreur`.
CODES_CONNUS: dict[str, CodeVerificateur] = REFERENTIEL | REFERENTIEL_LOCAL


# ---------------------------------------------------------------------------
# Table de correspondance (code_controle, type_anomalie) -> code_erreur
# ---------------------------------------------------------------------------

# Un couple absent de cette table n'est pas une erreur : `resoudre_code_erreur`
# retourne None, l'ecart reste emis, et le test d'exhaustivite exige seulement
# que le couple soit declare dans `COUPLES_A_QUALIFIER` ci-dessous.
CORRESPONDANCES: dict[tuple[str, str], str] = {
    # --- Altimetrie --------------------------------------------------------
    # Les deux formes du Z non renseigne — coordonnee absente, puis coordonnee
    # a zero — relevent d'un seul code, et donc d'un seul controle depuis leur
    # reunion sous E-5107. Le type d'anomalie conserve la distinction.
    ("E-5107", "absence_coordonnee_z"): "E-5107",
    ("E-5107", "z_null"): "E-5107",
    ("E-5201", "ecart_altimetrique_sommet"): "E-5201",
    ("E-6210", "point_leve_sommet_absent"): "E-6210",
    # Un moteur commun, deux defauts distincts et donc deux codes.
    ("E-5102", "point_leve_absent"): "E-5102",
    ("E-5103", "coordonnees_differentes"): "E-5103",
    ("E-6211", "point_leve_orphelin"): "E-6211",
    # --- Projection --------------------------------------------------------
    # E-0006 (numero de dossier sans DR connue) est porte par le statut du
    # controle, pas par une feature : seul E-5106 qualifie une entite hors
    # emprise.
    ("E-5106", "hors_emprise_dr"): "E-5106",
    # --- Cheminement -------------------------------------------------------
    ("E-5108", "superposition_cheminements"): "E-5108",
    # Le defaut de reference (E-3102) et le defaut de cardinalite (E-3103) sont
    # distincts ; la reference pendante ne releve ni de l'un ni de l'autre.
    ("E-3102", "cable_non_reference"): "E-3102",
    ("E-3103", "cheminement_sans_cable"): "E-3103",
    ("E-3103", "cheminement_multi_cables"): "E-3103",
    # Le fourreau sans cable releve du meme code, sous un type distinct : c'est
    # la seule maille a laquelle sa derogation de niveau se declare
    # (cf. DEROGATIONS_NIVEAU).
    ("E-3103", "fourreau_sans_cable"): "E-3103",
    ("E-3109", "cable_terre_cheminement_incompatible"): "E-3109",
    ("E-3111", "cable_electrique_implantation_incoherente"): "E-3111",
    ("E-6205", "cheminement_sans_profondeur_charge_generatrice"): "E-6205",
    # --- Cable -------------------------------------------------------------
    # E-3302 vise le seul cas HierarchieBT sur cable HTA ; les deux autres
    # incoherences d'attributs relevent du typage du cable (E-3104).
    ("E-3104", "fonction_cable_invalide"): "E-3104",
    ("E-3104", "domaine_tension_fonction_incoherent"): "E-3104",
    ("E-3302", "hierarchie_bt_interdite"): "E-3302",
    ("E-2101", "designation_non_referencee"): "E-2101",
    ("E-6103", "precision_cheminement_non_conforme"): "E-6103",
    ("E-5100", "densite_sommets_insuffisante"): "E-5100",
    # Les deux premiers types relevent du lien relationnel, le troisieme de la
    # coincidence geometrique des extremites.
    ("E-6110", "cable_sans_noeud"): "E-6110",
    ("E-6110", "cable_noeud_unique"): "E-6110",
    ("E-6111", "extremite_non_raccordee"): "E-6111",
    # E-6102 est le complement topologique d'E-6111 : celui-ci part des
    # extremites sans noeud, celui-la des noeuds poses sur le trace sans coupure.
    ("E-6102", "cable_non_coupe_au_noeud"): "E-6102",
    # E-6207 ne vaut qu'en V1.0 : le couple Leve / TypeLeve a disparu en V1.1,
    # ou le controle se declare sans objet plutot que conforme.
    ("E-6207", "leve_different_altitude"): "E-6207",
    # E-6104 lit la meme couche et la meme source GML qu'E-6207, et ne vaut de
    # meme qu'en V1.0 : TypeLeve a disparu du schema en V1.1.
    ("E-6104", "charge_sans_altitude_superposee"): "E-6104",
    # Un moteur, deux mailles de superposition. E-3300 exige
    # la superposition complete X, Y et Z ; E-6206 se contente de la planimetrie
    # (« Z identique ou different ») et **englobe** donc E-3300 — arbitrage
    # metier : deux codes de niveaux differents nomment deux defauts distincts,
    # et un meme groupe peut porter les deux.
    ("E-3300", "plor_superpose_meme_type"): "E-3300",
    ("E-6206", "plor_superpose_xy_meme_type"): "E-6206",
    ("E-3304", "cable_htb_dans_emprise_dr"): "E-3304",
    # Fleche superieure a 40 cm de part et d'autre du sommet : E-5101 ; toute
    # autre courbe insuffisamment decrite : E-5200.
    ("E-5101", "courbe_non_discretisee"): "E-5101",
    ("E-5200", "courbe_mal_discretisee"): "E-5200",
    # --- Conteneur ---------------------------------------------------------
    # E-2201 ne porte que sur le couple Classe / Effort du support.
    ("E-2201", "classe_non_referencee"): "E-2201",
    ("E-2201", "effort_non_reference"): "E-2201",
    ("E-6108", "noeud_non_autorise"): "E-6108",
    # La chaine de localisation se parcourt en deux maillons : le rattachement
    # au conteneur (E-6105), puis la geometrie supplementaire de ce conteneur
    # (E-6106).
    # Le libelle d'E-6105 couvre litteralement l'absence et la reference morte ;
    # le verificateur a detache la premiere en 2.10.0 sous E-6112, plus precis.
    # Arbitrage metier : les deux codes deviennent exclusifs, E-6105 ne jugeant
    # plus que la resolution de la reference.
    ("E-6112", "conteneur_absent"): "E-6112",
    ("E-6105", "conteneur_introuvable"): "E-6105",
    ("E-6106", "geometrie_supplementaire_absente"): "E-6106",
    ("E-6106", "geometrie_supplementaire_introuvable"): "E-6106",
    ("E-6106", "geometrie_supplementaire_invalide"): "E-6106",
    # Rattachement tranche par le metier : E-6209 est retenu et son perimetre
    # etendu au point de comptage et a l'ouvrage collectif, qui peuvent porter
    # une geometrie propre mais pas cumulee avec un conteneur. La matrice de
    # couverture du verificateur, qui declare E-6209 non couvert, est en retard
    # sur cette decision.
    ("E-6209", "geometrie_directe_presente"): "E-6209",
    ("E-6204", "localisation_absente"): "E-6204",
    ("E-6109", "localisation_absente"): "E-6109",
    # Separation electrique / telecommunication. Le moteur des references
    # noeud/cable resout deja la couche de
    # chaque reference cables_href : la nature du cable y est disponible sans
    # second parcours. Les deux regles sont symetriques et exclusives sur une
    # meme reference. E-6114 (coffret telecom) porte sur une autre relation et
    # reste a ecrire ; le cable de terre n'entre dans aucune des deux.
    ("E-6113", "cable_telecom_sur_noeud_electrique"): "E-6113",
    # E-6114 porte sur l'autre relation du bloc, noeud -> conteneur : un coffret
    # de telecommunication n'heberge que des jonctions de telecommunication.
    ("E-6114", "noeud_electrique_sur_coffret_telecom"): "E-6114",
    ("E-6115", "cable_electrique_sur_noeud_telecom"): "E-6115",
    # E-6213 ferme le bloc : le cable de terre sur une jonction de
    # telecommunication. Le libelle de sa fiche a ete corrige, celui des fiches
    # 2.14.0 etant errone — motif porte par la fiche elle-meme.
    ("E-6213", "cable_terre_sur_noeud_telecom"): "E-6213",
    ("E-6116", "cable_telecommunication_absent"): "E-6116",
    # La longueur admise depend du domaine de tension, et le verificateur
    # reserve un code a chacun. Le discriminant est la cle de la table des seuils.
    ("E-4200", "longueur_bt_excessive"): "E-4200",
    ("E-4201", "longueur_hta_excessive"): "E-4201",
    # Le compte de cables porte un code par TypeJonction. Les
    # deux ecarts de l'extremite reseau — aucun cable, ou plusieurs — relevent du
    # meme code, la fiche enoncant la regle dans les deux sens.
    ("E-6201", "derivation_cables_insuffisants"): "E-6201",
    ("E-6202", "jonction_cables_insuffisants"): "E-6202",
    ("E-6203", "extremite_reseau_sans_cable"): "E-6203",
    ("E-6203", "extremite_reseau_cables_multiples"): "E-6203",
    # La divergence entre declaration et geometrie, que le verificateur ne nomme
    # pas.
    ("E-9609", "raccordement_incoherent"): "E-9609",
    ("E-9701", "cable_points_leve_altitude_nulle"): "E-9701",
    # Un crs absent est une declaration manquante (E-2200), un
    # crs different appelle une reprojection (E-5105). La non-unicite du jeu, que
    # le verificateur nomme E-0007, prend un code local par arbitrage metier.
    ("E-2200", "projection_non_definie"): "E-2200",
    ("E-5105", "projection_differente"): "E-5105",
    ("E-9302", "projection_non_unique"): "E-9302",
    # Le numero de dossier, en cascade : la conformite au modele d'abord, la
    # resolution de la direction regionale ensuite. Trois des six modeles ne
    # portent aucune reference DR et sont donc hors du perimetre d'E-0006.
    ("E-0005", "numero_dossier_hors_modele"): "E-0005",
    ("E-0006", "numero_dossier_dr_inconnue"): "E-0006",
    # E-3110 : l'exigence de geometrie supplementaire portee par le conteneur
    # lui-meme. Les trois ruptures de la chaine relevent du meme code — dans les
    # trois cas l'objet n'a, de fait, aucune geometrie supplementaire — mais
    # restent distinguees par leur type, les corrections differant.
    ("E-3110", "geometrie_supplementaire_absente"): "E-3110",
    ("E-3110", "geometrie_supplementaire_introuvable"): "E-3110",
    ("E-3110", "geometrie_supplementaire_invalide"): "E-3110",
    # E-9401 : les cheminements d'un cable laissent un trou. Le code du
    # verificateur, E-0011, couvre aussi la superposition, deja rendue par
    # E-5108 ; le code local ne porte que le volet disjonction.
    ("E-9401", "cheminements_disjoints"): "E-9401",
    # Paliers calendaires du materiel. Les triplets E-71xx / E-72xx / E-73xx
    # sont la meme regle a trois niveaux selon la date d'entree en vigueur
    # (01/01/2026, 01/04/2026, 01/01/2027). L'arbitrage 4 du plan retient le
    # **niveau cible**, c'est-a-dire la serie E-71xx : star-engine annonce des
    # aujourd'hui l'exigence definitive plutot que de voir ses priorites
    # changer d'elles-memes au passage d'une date. Le champ `activation` du
    # referentiel conserve le calendrier pour qui voudrait l'exploiter.
    # Rattachement de la boite a son materiel, les deux sens d'ecart. Le niveau
    # cible est retenu, comme pour E-7102 et E-7104 : les paliers E-72xx et
    # E-73xx de ces memes regles restent volontairement non couverts.
    ("E-7100", "boite_sans_materiel"): "E-7100",
    ("E-7101", "boite_materiels_multiples"): "E-7101",
    ("E-7104", "domaine_tension_hors_catalogue"): "E-7104",
    ("E-7104", "fabricant_non_reference"): "E-7104",
    ("E-7104", "modele_non_reference"): "E-7104",
    # E-7305 n'est pas un palier calendaire : c'est le seul code du bloc sans
    # fenetre d'activation. Il nomme ce qu'E-7104 laisse passer par conception,
    # sa comparaison au catalogue ignorant la casse.
    ("E-7305", "casse_couple_incorrecte"): "E-7305",
    ("E-7104", "couple_fabricant_modele_non_reference"): "E-7104",
    # Un materiel rattache a une jonction dont le TypeJonction n'est ni
    # Derivation ni Jonction n'est, au sens du verificateur, pas associe a une
    # boite : les deux types d'anomalie relevent du meme code.
    ("E-7102", "jonction_absente"): "E-7102",
    ("E-7102", "type_jonction_invalide"): "E-7102",
    # E-7103 complete E-7102 sur le meme moteur : celui-ci juge le type de la
    # jonction portant le materiel, celui-la son statut. Les deux sont evaluees
    # en cascade, un type inadapte court-circuitant la regle de statut.
    ("E-7103", "statut_jonction_invalide"): "E-7103",
    # La composition des coffrets porte deux codes : l'obligation de presence
    # (E-6107) et les bornes de composition par type de noeud (E-6208).
    ("E-6107", "coffret_sans_noeud_autorise"): "E-6107",
    ("E-6208", "nombre_noeuds_excessif"): "E-6208",
    ("E-6208", "noeud_type_non_autorise"): "E-6208",
    # --- Codes locaux star-engine (serie E-9xxx) ---------------------------
    # Anomalies que star-engine detecte sans que le verificateur les nomme.
    # Leur donner un code plutot que de les laisser a `code_erreur` nul rend
    # leur priorite derivable comme celle de toutes les autres : aucun controle
    # n'a plus a declarer de repli.
    ("E-9200", "ecart_altimetrique_ign"): "E-9200",
    ("E-9201", "point_leve_absent"): "E-9201",
    # E-9202 applique aux supports le moteur qu'E-9201 applique aux coffrets :
    # l'objet controle differe, le code aussi, malgre un `type_anomalie` commun.
    ("E-9202", "point_leve_absent"): "E-9202",
    ("E-9300", "groupe_detache_du_reseau"): "E-9300",
    ("E-9301", "aire_excessive"): "E-9301",
    # Reference pendante : ni E-3102 (cable non reference) ni E-3103
    # (cardinalite) ne la couvrent.
    ("E-9400", "reference_orpheline"): "E-9400",
    ("E-9500", "domaine_tension_incoherent"): "E-9500",
    ("E-9501", "cable_terre_non_raccorde"): "E-9501",
    ("E-9502", "jonction_hors_extremite"): "E-9502",
    # Angle mort des deux sens de la relation materiel / jonction : le
    # materiel_href pendant.
    ("E-9600", "materiel_introuvable"): "E-9600",
    ("E-9601", "identifiants_materiel_partages"): "E-9601",
    # E-2201 ne porte que sur le couple Classe / Effort : la hauteur et la
    # matiere du support restent hors nomenclature.
    ("E-9602", "hauteur_non_referencee"): "E-9602",
    ("E-9603", "matiere_hors_catalogue"): "E-9603",
    ("E-9604", "cable_introuvable"): "E-9604",
    ("E-9605", "cables_href_absent"): "E-9605",
    ("E-9605", "cables_href_absent_noeud_terre"): "E-9605",
    ("E-9606", "cables_href_vide"): "E-9606",
    ("E-9607", "reference_hors_couche_cable"): "E-9607",
    ("E-9608", "reference_malformee"): "E-9608",
}


@dataclass(frozen=True, slots=True)
class CoupleAQualifier:
    """Couple emis par un controle dont le code du verificateur reste a fixer.

    Declarer le couple ici est volontaire : le test d'exhaustivite echoue sur
    tout type d'anomalie ni correspondu ni declare, ce qui interdit d'ajouter
    une anomalie sans statuer sur son code.
    """

    code_controle: str
    type_anomalie: str
    motif: str


# Couples en attente, avec le motif qui bloque leur qualification. Le decompte
# de cette table est l'indicateur d'avancement du lot 1.
#
# **La table est vide** : tout type d'anomalie emis par le projet porte un code
# d'erreur. Elle reste declaree pour accueillir un futur couple non encore
# statue, que le test d'exhaustivite tolerera alors.
_COUPLES_A_QUALIFIER: tuple[CoupleAQualifier, ...] = ()

# Index d'appartenance en O(1), consomme par le test d'exhaustivite.
COUPLES_A_QUALIFIER: frozenset[tuple[str, str]] = frozenset(
    (couple.code_controle, couple.type_anomalie) for couple in _COUPLES_A_QUALIFIER
)

# Motif de blocage indexe par couple, affiche par le test en cas d'echec.
MOTIFS_A_QUALIFIER: dict[tuple[str, str], str] = {
    (couple.code_controle, couple.type_anomalie): couple.motif for couple in _COUPLES_A_QUALIFIER
}


# ---------------------------------------------------------------------------
# Derogations de niveau
# ---------------------------------------------------------------------------

# Le niveau d'une anomalie est en regle generale celui de son code d'erreur : le
# referentiel fait foi, et c'est ce qui interdit toute derive entre l'echelle de
# star-engine et celle du verificateur.
#
# Cette table porte les rares exceptions, decidees par le metier, ou une anomalie
# precise merite un niveau different de celui de son code. Elle existe pour que
# ces ecarts soient **explicites** : sans elle, un controle abaisserait sa propre
# priorite dans son coin, et la divergence avec le verificateur serait invisible
# depuis le referentiel.
#
# Toute entree porte son motif. Une derogation sans justification metier ecrite
# n'a pas lieu d'etre : c'est alors le referentiel qu'il faut corriger.
DEROGATIONS_NIVEAU: dict[tuple[str, str], str] = {
    # Le verificateur classe E-3103 en « forte ». Un fourreau pose sans cable
    # associe n'est toutefois pas un defaut de recolement : poser un fourreau en
    # attente de cablage est une pratique courante. L'ecart reste signale — le
    # fourreau devra bien recevoir un cable — mais ne declasse pas la livraison.
    # La derogation ne vise que ce cas : le fourreau porteur de plusieurs cables,
    # comme les autres cheminements sans cable, gardent le niveau du code.
    ("E-3103", "fourreau_sans_cable"): NIVEAU_BASSE,
    # E-9605 est classe « forte » : un noeud du reseau sans rattachement a un
    # cable est un defaut de recolement. Le noeud de terre fait exception : la
    # mise a la terre est une infrastructure partagee, dont le cablage se
    # declare ailleurs que sur le noeud. L'ecart reste signale — le
    # rattachement devra bien etre renseigne — mais ne declasse pas la
    # livraison. La derogation ne vise que ce cas : les huit autres couches de
    # noeud gardent le niveau du code.
    ("E-9605", "cables_href_absent_noeud_terre"): NIVEAU_BASSE,
}


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


# La resolution est appelee une fois par feature d'ecart : le cache evite un
# hachage de tuple repete sur des jeux de plusieurs milliers d'anomalies.
# maxsize borne a la taille de la table, seules ses cles pouvant etre servies.
@lru_cache(maxsize=512)
def resoudre_code_erreur(code_controle: str, type_anomalie: str | None) -> str | None:
    """Retourne le code du verificateur correspondant a une anomalie.

    Retourne None lorsque le couple n'est pas encore qualifie : un code absent
    ne doit jamais empecher l'emission de l'ecart.
    """
    if type_anomalie is None:
        return None
    return CORRESPONDANCES.get((code_controle, type_anomalie))


def niveau_code_erreur(code_erreur: str | None) -> str | None:
    """Retourne le niveau associe a un code d'erreur, local ou non.

    Support du lot 2 : la priorite d'une anomalie devient une propriete de son
    code, non une constante declaree par chaque module de controle.
    """
    if code_erreur is None:
        return None
    fiche = CODES_CONNUS.get(code_erreur)
    return fiche.niveau if fiche is not None else None


def libelle_code_erreur(code_erreur: str | None) -> str | None:
    """Retourne l'intitule du code d'erreur, ou None s'il est inconnu."""
    if code_erreur is None:
        return None
    fiche = CODES_CONNUS.get(code_erreur)
    return fiche.libelle if fiche is not None else None


# Appelee une fois par feature d'ecart et une fois par type d'anomalie a la
# synthese : le cache evite de reparcourir deux tables pour un couple repete.
@lru_cache(maxsize=512)
def niveau_anomalie(code_controle: str, type_anomalie: str | None, defaut: str | None = None) -> str | None:
    """Retourne le niveau du verificateur d'une anomalie, ou `defaut` a defaut.

    C'est le point d'entree du lot 2 : la priorite d'une anomalie n'est plus
    declaree par le module qui la detecte, elle est **une propriete de son code
    d'erreur**, exactement comme chez le verificateur. Toute divergence entre
    les deux echelles est ainsi supprimee par construction.

    `defaut` couvre les couples encore en attente de code (`COUPLES_A_QUALIFIER`)
    : ils conservent la priorite declaree par leur controle tant que leur code
    n'est pas fixe. La migration reste donc progressive et non bloquante.

    Le niveau est ramene a `forte` lorsque le verificateur le classe
    `bloquante` : chez lui, « bloquante » signifie que le traitement s'arrete,
    ce que star-engine exprime deja par le statut de famille « Non execute » et
    non par une anomalie. La distinction n'aurait aucune portee ici — les deux
    niveaux declassent la livraison — et ferait apparaitre dans le rapport une
    colonne que rien n'alimenterait fidelement. `niveau_code_erreur` reste
    disponible pour lire le niveau brut du referentiel.

    Une derogation declaree dans `DEROGATIONS_NIVEAU` prime sur le niveau du
    code : c'est le seul moyen de s'en ecarter, et il laisse une trace au
    referentiel.
    """
    if type_anomalie is not None:
        derogation = DEROGATIONS_NIVEAU.get((code_controle, type_anomalie))
        if derogation is not None:
            return derogation

    niveau = niveau_code_erreur(resoudre_code_erreur(code_controle, type_anomalie))
    if niveau is None:
        return defaut
    return NIVEAU_FORTE if niveau == NIVEAU_BLOQUANTE else niveau
