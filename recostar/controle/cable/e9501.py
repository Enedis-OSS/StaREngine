"""
Controle E-9501 : Le câble de terre n'est raccordé à aucun nœud du réseau

Le moteur `detection_raccordement_cable` releve toutes les anomalies de son
domaine ; ce controle ne retient que celles de son code. Autres controles servis
par ce moteur : e6110, e6111.

Usage CLI :
    python -m recostar.controle.cable.e9501 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e9501_cable_terre_non_raccorde.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.cable.detection_raccordement_cable import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e9501_cable_terre_non_raccorde.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-9501"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "cable_terre_non_raccorde",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "cable_terre_non_raccorde": ("Le câble de terre n'est raccordé à aucun nœud du réseau."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable",),
    # Couche de l'entite en anomalie, que les ecarts ne nomment pas.
    couche_source="RPD_CableTerre_Reco",
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-9501 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-9501."""
    parseur = argparse.ArgumentParser(
        description="Controle E-9501 : Le câble de terre n'est raccordé à aucun nœud du réseau"
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
