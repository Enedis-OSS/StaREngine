"""
Lecture des relations vers les cables du reseau.

Le champ `cables_href` porte la relation noeud -> cable. Sa serialisation depuis
le GML n'est pas homogene, et trois implementations d'extraction coexistaient,
chacune ne connaissant qu'un separateur :

- `cheminement.utils_cheminement` decoupait sur la virgule ;
- `cable.utils_cable` sur la virgule **et** l'espace ;
- `altimetrie.e5201._normaliser_reference_cables` sur l'espace.

Les trois sont ici fondues dans la version la plus large. Ce n'est pas un
arbitrage entre trois comportements : un identifiant `id<uuid>` ne contient ni
virgule ni espace, les trois s'accordent donc sur toute donnee conforme a la
convention que chacune documentait. Elles ne divergeaient que sur une entree que
leur propre domaine declarait ne pas produire — cas ou la variante etroite
renvoyait un identifiant concatene, c'est-a-dire faux.
"""

import importlib.util
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.geojson import lire_geojson
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_CABLES_HREF,
    CHAMP_STATUT,
    FICHIER_AERIEN,
    FICHIERS_CABLES_PAR_VERSION,
    STATUT_MISE_EN_SERVICE,
)

# Module de conversion detenant la liste de reference des types de noeuds.
# fonctions_communes/ -> controle/ -> recostar/, puis conversion/conversion_V1_1/.
_CHEMIN_CONVERSION: Path = (
    Path(__file__).resolve().parents[2] / "conversion" / "conversion_V1_1" / "geojson_to_recostar.py"
)

# Nom sous lequel le module de conversion est enregistre lors du chargement
# dynamique. Prefixe distinctif : evite toute collision avec le module homonyme
# de conversion_V1 si les deux venaient a etre importes dans le meme processus.
_NOM_MODULE_CONVERSION: str = "_conversion_v1_1_geojson_to_recostar"


def extraire_ids_cables_href(valeur: Any) -> list[str]:
    """Extrait les identifiants de cables portes par un champ `cables_href`.

    Formes admises :
    - chaine unique                        : "id<uuid>"
    - chaine multiple separee par virgules : "id<uuid1>,id<uuid2>"
    - chaine multiple separee par espaces  : "id<uuid1> id<uuid2>"
    - liste                                : ["id<uuid1>", "id<uuid2>"]
    - absente, vide ou d'un autre type     : liste vide

    Les deux separateurs sont normalises : la virgule (serialisation GML ->
    GeoJSON des jonctions et cheminements) et l'espace (convention des couches
    aeriennes). Les identifiants n'en contenant aucun, le decoupage est sans
    ambiguite.
    """
    if isinstance(valeur, str) and valeur:
        # Uniformise les separateurs puis decoupe (split() ignore les vides)
        return valeur.replace(",", " ").split()
    if isinstance(valeur, list):
        return [str(identifiant) for identifiant in valeur if identifiant is not None]
    return []


def collecter_ids_cables_aeriens(features: list[dict[str, Any]]) -> set[str]:
    """Rassemble les identifiants de cables references par des entites aeriennes.

    Le set garantit un test d'appartenance en O(1) : les controles s'en servent
    pour exclure, cable par cable, ceux qui sont poses en aerien.
    """
    ids_cables: set[str] = set()
    for feature in features:
        proprietes = feature.get("properties") or {}
        ids_cables.update(extraire_ids_cables_href(proprietes.get(CHAMP_CABLES_HREF)))
    return ids_cables


def charger_ids_cables_aeriens(repertoire: str) -> set[str]:
    """Charge depuis la couche aerienne les identifiants de cables qu'elle porte.

    L'absence de la couche aerienne n'est pas bloquante : aucune exclusion n'est
    alors appliquee, ce qui revient a controler tous les cables.
    """
    collection = lire_geojson(os.path.join(repertoire, FICHIER_AERIEN))
    features = collection.get("features", []) if collection else []
    return collecter_ids_cables_aeriens(features)


@lru_cache(maxsize=1)
def charger_types_noeuds_reseau() -> tuple[str, ...]:
    """Retourne les types d'entites constituant les noeuds du reseau.

    La liste n'est pas redefinie ici : elle est importee depuis le module de
    conversion (constante TYPES_NOEUDS_RESEAU), seule source de verite du
    projet. Ce sont les entites porteuses du champ cables_href qui materialise
    la relation noeud <-> cable.

    La liste est identique en RecoStaR V1.0 et V1.1 ; la V1.1 fait reference.
    Le chargement passe par importlib plutot que par un import classique : le
    module de conversion n'est pas un paquet installe et porte un nom commun
    aux deux versions. Le resultat est mis en cache (lru_cache) : le module
    n'est charge qu'une seule fois par processus.
    """
    specification = importlib.util.spec_from_file_location(_NOM_MODULE_CONVERSION, _CHEMIN_CONVERSION)
    if specification is None or specification.loader is None:
        raise ImportError(f"Module de conversion introuvable : {_CHEMIN_CONVERSION}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return tuple(module.TYPES_NOEUDS_RESEAU)


def resoudre_fichiers_cables(version: str) -> tuple[str, ...]:
    """Retourne les couches de cables a lire pour la version donnee.

    Une version inconnue se replie sur le jeu de couches le plus complet, par
    coherence avec le repli de version de `fonctions_communes.version_recostar` :
    mieux vaut chercher une couche absente que d'en ignorer une presente.
    """
    return FICHIERS_CABLES_PAR_VERSION.get(version, FICHIERS_CABLES_PAR_VERSION["1.1"])


def filtrer_cables_a_controler(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Restreint les entites a celles en cours de mise en service.

    Ce filtrage vaut dans toutes les versions : un recolement ne porte que sur
    les ouvrages qu'il declare poser.
    """
    return [
        feature for feature in features if (feature.get("properties") or {}).get(CHAMP_STATUT) == STATUT_MISE_EN_SERVICE
    ]
