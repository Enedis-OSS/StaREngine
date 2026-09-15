"""
Controle E-6105 : Le nœud sans géométrie n'est pas lié à un conteneur ou ce dernier n'est pas identifiable

**Le cas de l'absence releve d'E-6112.** Le libelle de ce code couvre litterale-
ment deux faits — « n'est pas lie a un conteneur **ou** ce dernier n'est pas
identifiable » —, mais le verificateur a detache le premier en 2.10.0 sous
E-6112, « Ce noeud ne peut pas exister sans conteneur ». Arbitrage metier : le
plus precis l'emporte, et les deux codes deviennent exclusifs. E-6105 ne juge
donc plus que la **resolution** de la reference : un conteneur_href renseigne qui
ne designe aucun conteneur connu.

Le moteur `detection_localisation_noeud` releve toutes
les anomalies de son domaine, ce controle ne retenant que celles de son code. Les
autres controles servis par ce moteur : e6106, e6112, e6209.

Usage CLI :
    python -m recostar.controle.conteneur.e6105 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e6105_conteneur_du_noeud_introuvable.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_localisation_noeud import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6105_conteneur_du_noeud_introuvable.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-6105"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "conteneur_introuvable",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "conteneur_introuvable": ("Le conteneur référencé par le nœud n'existe pas."),
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
    """Execute le controle E-6105 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-6105."""
    parseur = argparse.ArgumentParser(
        description="Controle E-6105 : Le nœud sans géométrie n'est pas lié à un conteneur ou ce dernier n'est pas identifiable"
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
