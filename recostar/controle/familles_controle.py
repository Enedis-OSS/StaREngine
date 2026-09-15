"""
Registre declaratif des familles de controle.

Ajouter une famille consiste a declarer une entree dans FAMILLES et les libelles
de ses controles dans LIBELLES_CONTROLES : ni l'orchestrateur
(pipeline_globale.py) ni le rapport PDF (rapport_pdf.py) n'ont a etre modifies.

Deux modes d'execution couvrent les pipelines existants :
  - MODE_REPERTOIRE : le pipeline recoit un repertoire de GeoJSON
    (altimetrie, cable, cheminement, conteneur, projection) ;
  - MODE_GML        : le pipeline recoit un fichier GML (xsd_structuration).

Les modules de pipeline sont importes dynamiquement depuis le paquet de leur
famille (`recostar.controle.<dossier>.<module_pipeline>`) : declarer une famille
suffit a la rendre executable, sans toucher a l'orchestrateur. Le chargement
reutilise les pipelines existants tels quels, sans dupliquer leur logique.
"""

import importlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import ModuleType

from recostar.controle.synthese_controles import PRIORITE_FORTE

# Racine du paquet de controle (repertoire de ce module).
RACINE_CONTROLE: Path = Path(__file__).resolve().parent

# Modes d'execution d'un pipeline de famille.
MODE_REPERTOIRE: str = "repertoire"
MODE_GML: str = "gml"


@dataclass(frozen=True, slots=True)
class FamilleControle:
    """Declaration d'une famille de controles.

    - `dossier` : sous-dossier source contenant le pipeline ;
    - `sortie` : sous-dossier produit dans l'arborescence controle/ ;
    - `priorite_par_defaut` : priorite attribuee aux anomalies d'un pipeline qui
      n'en declare pas ; filet de securite, pas source de verite.
    """

    cle: str
    libelle: str
    dossier: str
    module_pipeline: str
    sortie: str
    mode: str
    priorite_par_defaut: str | None = None


# Registre des familles, dans l'ordre d'execution et d'affichage du rapport.
FAMILLES: tuple[FamilleControle, ...] = (
    FamilleControle(
        cle="structuration",
        libelle="Structuration",
        dossier="xsd_structuration",
        module_pipeline="pipeline_controle_xsd",
        sortie="structuration",
        mode=MODE_GML,
        # Le pipeline XSD ventile lui-meme ses anomalies par priorite : chaque
        # erreur porte la sienne (cf. xsd_structuration/priorites_structuration).
        # Ce defaut ne sert donc que de repli si la ventilation etait absente ;
        # il vaut « forte », regle generale de la structuration et defaut du
        # dossier (PRIORITE_PAR_DEFAUT).
        priorite_par_defaut=PRIORITE_FORTE,
    ),
    FamilleControle(
        cle="projection",
        libelle="Projection",
        dossier="projection",
        module_pipeline="pipeline_controle_projection",
        sortie="projection",
        mode=MODE_REPERTOIRE,
    ),
    FamilleControle(
        cle="altimetrie",
        libelle="Altimétrie",
        dossier="altimetrie",
        module_pipeline="pipeline_controle_alti",
        sortie="altimetrie",
        mode=MODE_REPERTOIRE,
    ),
    FamilleControle(
        cle="cheminement",
        libelle="Cheminement",
        dossier="cheminement",
        module_pipeline="pipeline_controle_cheminement",
        sortie="cheminement",
        mode=MODE_REPERTOIRE,
    ),
    FamilleControle(
        cle="cable",
        libelle="Câble",
        dossier="cable",
        module_pipeline="pipeline_controle_cable",
        sortie="cable",
        mode=MODE_REPERTOIRE,
    ),
    FamilleControle(
        cle="conteneur",
        libelle="Conteneur",
        dossier="conteneur",
        module_pipeline="pipeline_controle_conteneur",
        sortie="conteneur",
        mode=MODE_REPERTOIRE,
    ),
)


# Familles dont le pipeline accepte un numero d'affaire supplementaire : la
# projection (requis par E-5106) et le cable (requis par E-3304), tous deux
# resolvant l'emprise DR depuis ce numero.
FAMILLES_AVEC_NUMERO_AFFAIRE: frozenset[str] = frozenset({"projection", "cable"})


# Familles dont le pipeline accepte le chemin du GML source : l'altimetrie, dont
# E-3300, E-6104, E-6206 et E-6207 lisent le couple `Leve` / `TypeLeve`, et le
# conteneur, dont E-7100 et E-7101 comptent les relations `Ouvrage_Materiel`. La
# conversion ne conserve ni les premiers ni le decompte des secondes ; le GML
# reste la seule source. Meme mecanique que FAMILLES_AVEC_NUMERO_AFFAIRE : la
# famille declare ce dont elle a besoin, l'orchestrateur n'a aucun cas
# particulier a connaitre.
FAMILLES_AVEC_GML: frozenset[str] = frozenset({"altimetrie", "conteneur"})


# Libelles des controles, indexes par leur code affichable. La cle de rapport
# des pipelines ("e5107" en GeoJSON, "E0110" en structuration) s'y ramene par
# `code_controle`, les deux conventions ne differant que par la casse.
#
# Ces libelles ne sont pas extraits des docstrings des modules de controle :
# leur format n'est pas homogene, une extraction automatique serait donc
# partielle et fragile. Le registre est la source de verite du rapport.
LIBELLES_CONTROLES: dict[str, str] = {
    "E-2201": "Les attributs Classe et Effort ne sont pas cohérents",
    "E-3300": "PLOR superposé avec même type de levé",
    "E-3102": "Le câble n'est pas associé à un cheminement",
    "E-3103": "Le cheminement n'a pas le nombre de câble attendu",
    "E-3104": "Les attributs du câble ne permettent pas de l'identifier",
    "E-3302": "Présence d'une valeur HierarchieBT pour un câble HTA",
    "E-5101": "Nombre de points levés insuffisant dans les parties courbes",
    "E-5102": "Le sommet n'est pas associé à un PLOR / PTRL",
    "E-5103": "Le Z du sommet n'est pas cohérent avec le Z du PLOR / PTRL",
    "E-5200": "Nombre de points levés insuffisant dans les courbes",
    "E-6102": "Le câble n'est pas coupé à chaque nœud",
    "E-6104": "PLOR de type ChargeGeneratrice sans PLOR de type AltitudeGeneratrice superposé",
    "E-9701": "Câble non altimétré",
    "E-3110": "Conteneur sans géométrie supplémentaire",
    "E-6105": "Le conteneur référencé par le nœud n'est pas identifiable",
    "E-6106": "Le nœud est sans géométrie et est lié à un conteneur sans géométrie",
    "E-6112": "Ce nœud ne peut pas exister sans conteneur",
    "E-6107": "Nœud réseau manquant. Coffret n'a pas de nœud réseau conforme identifié",
    "E-6110": "Le câble n'est pas lié à deux nœuds",
    "E-6111": "Les extrémités de câble ne sont pas jointes géométriquement aux nœuds liés",
    "E-6113": "Un câble de télécommunication ne doit pas être lié à un Noeud électrique",
    "E-6114": "Un coffret de télécommunication ne doit pas être lié à un nœud électrique",
    "E-6115": "Un câble électrique ne doit pas être lié à un nœud de télécommunication",
    "E-6208": "Aucune cohérence entre coffret et nœud",
    "E-6206": "PLOR superposés en X,Y avec un mode de levé identique",
    "E-6207": "PLOR avec valeur de « levé » différente de l'altitude du PLOR",
    "E-6209": "Le nœud a une géométrie et est lié a un conteneur",
    "E-6213": "Un câble de terre ne doit pas être lié à un nœud de télécommunication",
    "E-7103": "Matériel associé à une boîte qui n'est pas au statut UnderCommissionning",
    "E-7100": "Boîte de jonction / dérivation sans matériel associé",
    "E-7101": "Boîte de jonction / dérivation avec plusieurs matériels associés",
    "E-7104": "Le couple Fabriquant / modèle ne fait pas parti du catalogue",
    "E-7305": "La casse du couple Fabriquant / Modèle n'est pas correcte",
    "E-9401": "Cheminements d'un même câble disjoints",
    "E-9400": "Le cheminement référence un câble qui n'existe pas dans le jeu de données",
    "E-9501": "Le câble de terre n'est raccordé à aucun nœud du réseau",
    "E-9600": "Le matériel référencé par la jonction n'existe pas dans RPD_Materiel_Reco",
    "E-9602": "La Hauteur du support n'est pas référencée au catalogue pour cette matière",
    "E-9603": "La Matiere du support n'est couverte par aucune matière du catalogue",
    "E-9604": "La référence déclarée par cables_href ne correspond à aucune entité du jeu de données",
    "E-9605": "Le nœud ne déclare aucun rattachement à un câble : cables_href n'est pas renseigné",
    "E-9606": "Le champ cables_href du nœud est renseigné mais ne porte aucune référence exploitable",
    "E-9607": "La référence déclarée par cables_href désigne une entité qui n'est pas un câble",
    "E-9608": "La référence déclarée par cables_href n'a pas la forme d'un identifiant résolvable",
    # Structuration XSD V1.1 (E0110-E0115)
    "E0110": "Ordre de structure des objets RPD",
    "E0111": "Règles métier conditionnelles",
    "E0112": "Validation XSD native (lxml)",
    "E0113": "En-tête, namespaces, métadonnées, unicité gml:id",
    "E0114": "Valeurs des champs : énumérations, CodeLists, formats",
    "E0115": "Validité des géométries : positions manquantes",
    "E0116": "Doublons dans les tables de jointure",
    "E0117": "Champ manquant sur une table de jointure",
    "E0118": "Exploitabilité du document GML",
    "E0119": "Cohérence de l'attribut srsDimension",
    "E0120": "Ouvrages en attente de mise en service",
    # Structuration XSD V1.0 (E0010-E0014) : mêmes contrôles appliques au profil
    # de version 1.0. Le pipeline n'expose que la serie correspondant a la
    # version detectee dans le GML.
    "E0010": "Ordre de structure des objets RPD",
    "E0011": "Règles métier conditionnelles",
    "E0012": "Validation XSD native (lxml)",
    "E0013": "En-tête, namespaces, métadonnées, unicité gml:id",
    "E0014": "Valeurs des champs : énumérations, CodeLists, formats",
    "E0015": "Validité des géométries : positions manquantes",
    "E0016": "Doublons dans les tables de jointure",
    "E0017": "Champ manquant sur une table de jointure",
    "E0018": "Exploitabilité du document GML",
    "E0019": "Cohérence de l'attribut srsDimension",
    "E0020": "Ouvrages en attente de mise en service",
    # Projection
    "E-0005": "Numéro de dossier hors des modèles attendus",
    "E-0006": "Numéro de dossier sans direction régionale connue",
    "E-2200": "Système de projection non défini",
    "E-5105": "Projection différente de celle des métadonnées",
    "E-9302": "Projection non unique sur le jeu",
    "E-9300": "Cohérence spatiale",
    "E-9301": "Superficie des géométries supplémentaires",
    "E-5106": "Appartenance à l'emprise DR",
    # Altimetrie
    "E-5107": "Altitude Z non renseignée",
    "E-5201": "Altimétrie des sommets de câbles",
    "E-9200": "Altimétrie IGN",
    "E-9201": "Point de levé / géométrie supplémentaire de coffret",
    "E-6210": "Point de levé sur sommets de géométrie de bâtiment",
    "E-9202": "Point de levé / géométrie supplémentaire de support",
    "E-6211": "Points de levé orphelins",
    # Cheminement
    "E-5108": "Superpositions géométriques entre cheminements",
    "E-3109": "Cohérence câble de terre / cheminement",
    "E-3111": "Cohérence d'implantation des câbles électriques",
    "E-6205": "Profondeur manquante aux charges génératrices",
    # Cable
    "E-9500": "Cohérence du DomaineTension jonction / câbles",
    "E-2101": "Désignation normalisée des câbles électriques",
    "E-6103": "Précision des cheminements associés à un câble",
    "E-5100": "Densité de sommets des câbles électriques",
    "E-4200": "Longueur du câble BT supérieure à 250 m",
    "E-4201": "Longueur du câble HTA supérieure à 500 m",
    "E-9502": "Position des jonctions sur les extrémités des câbles",
    "E-3304": "Câbles HTB situés en Métropole",
    # Conteneur
    "E-7102": "Rattachement du matériel à une jonction",
    "E-9601": "Unicité des identifiants de matériel entre jonctions",
    "E-6108": "Types de nœuds rattachés aux coffrets",
    "E-6204": "Localisation des remontées aéro-souterraines",
    "E-6109": "Localisation des points de comptage et ouvrages collectifs",
    "E-6201": "Dérivation raccordant moins de 3 câbles",
    "E-6202": "Jonction raccordant moins de 2 câbles",
    "E-6203": "Extrémité réseau non liée à un câble et un seul",
    "E-6116": "Jonction Telecom sans câble de télécommunication",
    "E-9609": "Raccordements déclarés et géométriques divergents",
}


def code_controle(cle: str) -> str:
    """Derive le code affichable d'un controle depuis sa cle de rapport.

    "e5107" -> "E5107" ; "E0110" reste inchange. Les pipelines GeoJSON indexent
    leur rapport par nom de module et celui de structuration par code ; les deux
    conventions ne different que par la casse.
    """
    return cle.upper()


def libelle_controle(cle: str) -> str:
    """Retourne le libelle d'un controle, ou son code si aucun n'est declare."""
    return LIBELLES_CONTROLES.get(code_controle(cle), code_controle(cle))


@cache
def charger_module_pipeline(cle_famille: str) -> ModuleType:
    """Charge le module de pipeline d'une famille, une seule fois par processus.

    Le pipeline est un module du paquet de sa famille : un import ordinaire
    suffit, sans manipulation de sys.path ni chargement par chemin. Les six
    pipelines exposent tous un `executer_pipeline`.

    Le `cache` evite de repayer la resolution d'import a chaque appel ; la
    reexecution du module est de toute facon deja evitee par sys.modules.
    """
    famille = famille_par_cle(cle_famille)
    return importlib.import_module(f"{__package__}.{famille.dossier}.{famille.module_pipeline}")


@cache
def famille_par_cle(cle: str) -> FamilleControle:
    """Retourne la famille declaree sous cette cle."""
    for famille in FAMILLES:
        if famille.cle == cle:
            return famille
    raise KeyError(f"Famille de controle inconnue : {cle}")
