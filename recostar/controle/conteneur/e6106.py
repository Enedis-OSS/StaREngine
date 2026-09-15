"""
Controle E-6106 : Le nœud est sans géométrie et est lié à un conteneur sans géométrie

Le moteur `detection_localisation_noeud` releve toutes les anomalies de son
domaine ; ce controle ne retient que celles de son code. Autres controles servis
par ce moteur : e6105.

Usage CLI :
    python -m recostar.controle.conteneur.e6106 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e6106_geometrie_supplementaire_du_conteneur.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_localisation_noeud import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6106_geometrie_supplementaire_du_conteneur.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-6106"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "geometrie_supplementaire_absente",
        "geometrie_supplementaire_introuvable",
        "geometrie_supplementaire_invalide",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "geometrie_supplementaire_absente": ("Le conteneur du nœud ne référence aucune géométrie supplémentaire."),
    "geometrie_supplementaire_introuvable": ("La géométrie supplémentaire référencée par le conteneur n'existe pas."),
    "geometrie_supplementaire_invalide": (
        "La géométrie supplémentaire référencée existe mais ne porte pas de géométrie valide."
    ),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_noeud", "id_conteneur"),
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-6106 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-6106."""
    parseur = argparse.ArgumentParser(
        description="Controle E-6106 : Le nœud est sans géométrie et est lié à un conteneur sans géométrie"
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
