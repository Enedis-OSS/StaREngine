"""
Controle E-6208 : Aucune cohérence entre coffret et nœud

Le moteur `detection_composition_coffret` releve toutes les anomalies de son
domaine ; ce controle ne retient que celles de son code. Autres controles servis
par ce moteur : e6107.

Usage CLI :
    python -m recostar.controle.conteneur.e6208 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e6208_composition_coffret_non_conforme.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_composition_coffret import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6208_composition_coffret_non_conforme.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-6208"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "noeud_type_non_autorise",
        "nombre_noeuds_excessif",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "noeud_type_non_autorise": (
        "Le type de nœud rattaché au coffret n'est pas prévu par la nomenclature de son TypeCoffret."
    ),
    "nombre_noeuds_excessif": ("Le coffret contient plus de nœuds de ce type que sa nomenclature n'en admet."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_coffret",),
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-6208 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(
        repertoire,
        TYPES_RETENUS,
        PROFIL_ECARTS,
        FICHIER_SORTIE,
        sortie,
    )


def main() -> None:
    """Point d'entree CLI du controle E-6208."""
    parseur = argparse.ArgumentParser(description="Controle E-6208 : Aucune cohérence entre coffret et nœud")
    parseur.add_argument("--repertoire", required=True, help="Repertoire contenant les GeoJSON a analyser")
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
