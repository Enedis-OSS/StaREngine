"""
Controle E-2201 : Les attributs Classe et Effort ne sont pas cohérents

Le moteur `detection_catalogue_support` releve toutes les anomalies de son
domaine ; ce controle ne retient que celles de son code. Autres controles servis
par ce moteur : e9602, e9603.

Usage CLI :
    python -m recostar.controle.conteneur.e2201 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e2201_classe_effort_non_references.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_catalogue_support import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e2201_classe_effort_non_references.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-2201"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "classe_non_referencee",
        "effort_non_reference",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "classe_non_referencee": ("La Classe du support n'est pas référencée au catalogue pour cette matière."),
    "effort_non_reference": ("L'Effort du support n'est pas référencé au catalogue pour cette matière."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_support",),
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-2201 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-2201."""
    parseur = argparse.ArgumentParser(
        description="Controle E-2201 : Les attributs Classe et Effort ne sont pas cohérents"
    )
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
