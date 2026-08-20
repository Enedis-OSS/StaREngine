"""Utilitaires specifiques au domaine cable."""

import importlib.util
from functools import lru_cache
from pathlib import Path
from typing import Any

# Module de conversion detenant la liste de reference des types de noeuds.
# cable/ -> controle/ -> recostar/, puis conversion/conversion_V1_1/.
_CHEMIN_CONVERSION: Path = (
    Path(__file__).resolve().parents[2] / "conversion" / "conversion_V1_1" / "geojson_to_recostar.py"
)

# Nom sous lequel le module de conversion est enregistre lors du chargement
# dynamique. Prefixe distinctif : evite toute collision avec le module homonyme
# de conversion_V1 si les deux venaient a etre importes dans le meme processus.
_NOM_MODULE_CONVERSION: str = "_conversion_v1_1_geojson_to_recostar"


def extraire_ids_cables_href(valeur: Any) -> list[str]:
    """Extrait les identifiants cables depuis le champ cables_href.

    Gere les formes presentes dans les donnees Recostar :
    - chaine unique  : "id<uuid>"
    - chaine multiple separee par virgules : "id<uuid1>,id<uuid2>"
    - chaine multiple separee par espaces  : "id<uuid1> id<uuid2>"
    - liste          : ["id<uuid1>", "id<uuid2>"]
    - null ou absent : liste vide

    Les deux separateurs sont acceptes et normalises : la virgule (serialisation
    GML->GeoJSON, utilisee par les jonctions et cheminements) et l'espace
    (convention du controle aerien E202). Les identifiants (id<uuid>) ne
    contiennent ni virgule ni espace, ce decoupage est donc sans ambiguite.
    """
    if isinstance(valeur, str) and valeur:
        # Uniformise les separateurs puis decoupe (split() ignore les vides)
        return valeur.replace(",", " ").split()
    if isinstance(valeur, list):
        return [str(cid) for cid in valeur if cid is not None]
    return []


@lru_cache(maxsize=1)
def charger_types_noeuds_reseau() -> tuple[str, ...]:
    """Retourne les types d'entites constituant les noeuds du reseau.

    La liste n'est pas redefinie ici : elle est importee depuis le module de
    conversion (constante TYPES_NOEUDS_RESEAU), seule source de verite du
    projet. Ce sont les entites porteuses du champ cables_href qui materialise
    la relation noeud <-> cable.

    La liste est identique en RecoStaR V1.0 et V1.1 ; la V1.1 fait reference.
    Le chargement passe par importlib plutot que par un import classique : le
    module de conversion n'est pas un package installe et porte un nom commun
    aux deux versions. Le resultat est mis en cache (lru_cache) : le module
    n'est charge qu'une seule fois par processus.
    """
    specification = importlib.util.spec_from_file_location(_NOM_MODULE_CONVERSION, _CHEMIN_CONVERSION)
    if specification is None or specification.loader is None:
        raise ImportError(f"Module de conversion introuvable : {_CHEMIN_CONVERSION}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return tuple(module.TYPES_NOEUDS_RESEAU)
