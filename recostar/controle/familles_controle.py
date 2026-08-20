"""
Registre declaratif des familles de controle.

Ajouter une famille consiste a declarer une entree dans FAMILLES et les libelles
de ses controles dans LIBELLES_CONTROLES : ni l'orchestrateur
(pipeline_globale.py) ni le rapport PDF (rapport_pdf.py) n'ont a etre modifies.

Deux modes d'execution couvrent les pipelines existants :
  - MODE_REPERTOIRE : le pipeline recoit un repertoire de GeoJSON
    (altimetrie, cable, cheminement, conteneur, projection) ;
  - MODE_GML        : le pipeline recoit un fichier GML (xsd_structuration).

Les modules de pipeline sont charges dynamiquement depuis leur sous-dossier :
ils s'importent a plat (`from controle_e200 import ...`) et ne constituent pas
des paquets installables. Le chargement reutilise les pipelines existants tels
quels, sans dupliquer leur logique.
"""

import importlib.util
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import ModuleType

from synthese_controles import PRIORITE_BLOQUANT

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
        # il reste bloquant, la regle generale de la structuration.
        priorite_par_defaut=PRIORITE_BLOQUANT,
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
# projection (requis par E303) et le cable (requis par E508), tous deux
# resolvant l'emprise DR depuis ce numero.
FAMILLES_AVEC_NUMERO_AFFAIRE: frozenset[str] = frozenset({"projection", "cable"})


# Libelles des controles, indexes par la cle utilisee dans le rapport du
# pipeline de la famille ("controle_e200" pour les pipelines GeoJSON, "E110"
# pour le pipeline XSD).
#
# Ces libelles ne sont pas extraits des docstrings des modules de controle :
# leur format n'est pas homogene (seuls 19 des 32 controles suivent la
# convention "Controle EXXX : ..."), une extraction automatique serait donc
# partielle et fragile. Le registre est la source de verite du rapport.
LIBELLES_CONTROLES: dict[str, str] = {
    # Structuration XSD V1.1 (E110-E114)
    "E110": "Ordre de structure des objets RPD",
    "E111": "Règles métier conditionnelles",
    "E112": "Validation XSD native (lxml)",
    "E113": "En-tête, namespaces, métadonnées, unicité gml:id",
    "E114": "Valeurs des champs : énumérations, CodeLists, formats",
    # Structuration XSD V1.0 (E010-E014) : mêmes contrôles appliques au profil
    # de version 1.0. Le pipeline n'expose que la serie correspondant a la
    # version detectee dans le GML.
    "E010": "Ordre de structure des objets RPD",
    "E011": "Règles métier conditionnelles",
    "E012": "Validation XSD native (lxml)",
    "E013": "En-tête, namespaces, métadonnées, unicité gml:id",
    "E014": "Valeurs des champs : énumérations, CodeLists, formats",
    # Projection (E300-E303)
    "controle_e300": "Conformité de projection",
    "controle_e301": "Cohérence spatiale",
    "controle_e302": "Superficie des géométries supplémentaires",
    "controle_e303": "Appartenance à l'emprise DR",
    # Altimetrie (E200-E209)
    "controle_e200": "Conformité 3D",
    "controle_e201": "Coordonnées Z nulles",
    "controle_e202": "Altimétrie des sommets de câbles",
    "controle_e203": "Altimétrie IGN",
    "controle_e204": "Doublons spatiaux",
    "controle_e205": "Point de levé / géométrie supplémentaire de coffret",
    "controle_e206": "Point de levé sur sommets de géométrie de bâtiment",
    "controle_e207": "Point de levé / géométrie supplémentaire de support",
    "controle_e208": "Rattachement des sommets de câbles aux points de levé",
    "controle_e209": "Points de levé orphelins",
    # Cheminement (E400-E404)
    "controle_e400": "Superpositions géométriques entre cheminements",
    "controle_e401": "Intégrité des relations câbles / cheminements",
    "controle_e402": "Cohérence câble de terre / cheminement",
    "controle_e403": "Cohérence d'implantation des câbles électriques",
    "controle_e404": "Profondeur manquante aux charges génératrices",
    # Cable (E500-E509)
    "controle_e500": "Cohérence du DomaineTension jonction / câbles",
    "controle_e501": "Cohérence métier FonctionCable / DomaineTension",
    "controle_e502": "Désignation normalisée des câbles électriques",
    "controle_e503": "Précision des cheminements associés à un câble",
    "controle_e504": "Densité de sommets des câbles électriques",
    "controle_e505": "Cohérence longueur / DomaineTension",
    "controle_e506": "Raccordement des câbles aux nœuds du réseau",
    "controle_e507": "Position des jonctions sur les extrémités des câbles",
    "controle_e508": "Câbles HTB situés en Métropole",
    "controle_e509": "Discrétisation des courbes des câbles électriques",
    # Conteneur (E600-E610)
    "controle_e600": "Conformité du matériel de jonction au catalogue",
    "controle_e601": "Rattachement du matériel à une jonction",
    "controle_e602": "Unicité des identifiants de matériel entre jonctions",
    "controle_e603": "Caractéristiques de poteau conformes au catalogue",
    "controle_e604": "Types de nœuds rattachés aux coffrets",
    "controle_e605": "Chaîne de localisation des nœuds sans géométrie",
    "controle_e606": "Localisation des remontées aéro-souterraines",
    "controle_e607": "Localisation des points de comptage et ouvrages collectifs",
    "controle_e608": "Nombre de câbles raccordés selon le type de jonction",
    "controle_e609": "Rattachement des nœuds du réseau à un câble existant",
    "controle_e610": "Nomenclature de composition des coffrets",
}


def code_controle(cle: str) -> str:
    """Derive le code affichable d'un controle depuis sa cle de rapport.

    "controle_e200" -> "E200" ; "E110" reste inchange (convention du pipeline
    de structuration XSD).
    """
    if cle.startswith("controle_"):
        return cle.removeprefix("controle_").upper()
    return cle


def libelle_controle(cle: str) -> str:
    """Retourne le libelle d'un controle, ou son code si aucun n'est declare."""
    return LIBELLES_CONTROLES.get(cle, code_controle(cle))


@cache
def charger_module_pipeline(cle_famille: str) -> ModuleType:
    """Charge le module de pipeline d'une famille, une seule fois par processus.

    Le sous-dossier de la famille est ajoute a sys.path : les modules de
    controle s'y importent a plat. Le module de pipeline est enregistre sous un
    nom prefixe, les six pipelines exposant tous un `executer_pipeline`.
    """
    famille = famille_par_cle(cle_famille)
    dossier = RACINE_CONTROLE / famille.dossier
    chemin = dossier / f"{famille.module_pipeline}.py"
    if not chemin.is_file():
        raise ImportError(f"Pipeline introuvable : {chemin}")

    dossier_str = str(dossier)
    if dossier_str not in sys.path:
        sys.path.insert(0, dossier_str)

    specification = importlib.util.spec_from_file_location(f"_pipeline_{famille.cle}", chemin)
    if specification is None or specification.loader is None:
        raise ImportError(f"Chargement impossible : {chemin}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@cache
def famille_par_cle(cle: str) -> FamilleControle:
    """Retourne la famille declaree sous cette cle."""
    for famille in FAMILLES:
        if famille.cle == cle:
            return famille
    raise KeyError(f"Famille de controle inconnue : {cle}")
