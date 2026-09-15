"""
Controle E-6113 : Un câble de télécommunication ne doit pas être lié à un Noeud électrique

Un cable de telecommunication ne se raccorde qu'a une RPD_Jonction_Reco dont le
TypeJonction vaut Telecom. Tout autre noeud qui le declare dans son cables_href
melange le reseau electrique et le reseau de telecommunication.

Perimetre : les neuf couches de noeud du moteur, au Statut UnderCommissionning
ou Functional. Le cas vise est donc un cable de telecommunication reference par
un jeu de barres, une terre, un point de comptage, un poste — ou une jonction
d'un autre type que Telecom.

La regle n'est evaluee que sur une reference qui **aboutit** et designe bien un
cable : une reference introuvable (E-9604) ou visant une entite d'une autre
nature (E-9607) releve des controles voisins, et la signaler deux fois
n'apprendrait rien de plus.

Le cas symetrique — un cable electrique sur une jonction de telecommunication —
porte le code E-6115 et son propre fichier, `e6115.py`. Les deux regles sont
exclusives sur une meme reference et partagent le meme discriminant, la nature du
noeud : `classifier_separation_reseaux` les porte ensemble.

Le moteur `detection_references_noeud_cable` releve
toutes les anomalies de son domaine, ce controle ne retenant que celles de son
code. Les autres controles servis par ce moteur : e6115, e6213, e9604, e9605,
e9606, e9607, e9608.

Usage CLI :
    python -m recostar.controle.conteneur.e6113 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e6113_cable_telecom_sur_noeud_electrique.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_references_noeud_cable import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6113_cable_telecom_sur_noeud_electrique.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-6113"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "cable_telecom_sur_noeud_electrique",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "cable_telecom_sur_noeud_electrique": (
        "Le nœud est lié à un câble de télécommunication sans être une jonction de télécommunication."
    ),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_noeud",),
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-6113 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-6113."""
    parseur = argparse.ArgumentParser(
        description="Controle E-6113 : un câble de télécommunication ne doit pas être lié à un nœud électrique"
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
