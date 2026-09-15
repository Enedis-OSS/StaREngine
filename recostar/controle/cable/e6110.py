"""
Controle E-6110 : Le câble n'est pas lié à deux nœuds

Le moteur `detection_raccordement_cable` releve toutes les anomalies de son
domaine ; ce controle ne retient que celles de son code. Autres controles servis
par ce moteur : e6111, e9501.

Usage CLI :
    python -m recostar.controle.cable.e6110 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e6110_cable_sans_deux_noeuds.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.cable.detection_raccordement_cable import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6110_cable_sans_deux_noeuds.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-6110"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "cable_noeud_unique",
        "cable_sans_noeud",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "cable_noeud_unique": ("Le câble n'est raccordé qu'à un seul nœud du réseau."),
    "cable_sans_noeud": ("Le câble n'est raccordé à aucun nœud du réseau."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable",),
    # Couche de l'entite en anomalie, que les ecarts ne nomment pas.
    couche_source="RPD_CableElectrique_Reco",
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-6110 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-6110."""
    parseur = argparse.ArgumentParser(description="Controle E-6110 : Le câble n'est pas lié à deux nœuds")
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
