"""
Controle E-9602 : La Hauteur du support n'est pas référencée au catalogue pour cette matière

Le moteur `detection_catalogue_support` releve toutes les anomalies de son
domaine ; ce controle ne retient que celles de son code. Autres controles servis
par ce moteur : e2201, e9603.

Usage CLI :
    python -m recostar.controle.conteneur.e9602 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e9602_hauteur_poteau_non_referencee.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_catalogue_support import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e9602_hauteur_poteau_non_referencee.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-9602"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "hauteur_non_referencee",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "hauteur_non_referencee": ("La Hauteur du support n'est pas référencée au catalogue pour cette matière."),
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
    """Execute le controle E-9602 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-9602."""
    parseur = argparse.ArgumentParser(
        description="Controle E-9602 : La Hauteur du support n'est pas référencée au catalogue pour cette matière"
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
