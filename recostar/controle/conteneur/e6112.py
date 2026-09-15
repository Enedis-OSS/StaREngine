"""
Controle E-6112 : Ce nœud ne peut pas exister sans conteneur

Six types de noeuds n'ont aucune existence propre : ils sont heberges par un
conteneur, dont ils tiennent leur position, et n'ont pas de raison d'etre hors de
lui. Un noeud de ces couches sans `conteneur_href` decrit un ouvrage qui n'existe
nulle part.

    RPD_CoupeCircuitAFusibles_Reco   RPD_SupportModules_Reco
    RPD_JeuBarres_Reco               RPD_Terre_Reco
    RPD_ModuleRaccordement_Reco      RPD_PosteElectrique_Reco

Ce sont les memes couches qu'E-6105 et E-6106 : aucune ne porte de geometrie au
XSD, toutes tiennent leur position du conteneur.

Frontiere avec E-6105
---------------------
Le libelle d'E-6105 couvre litteralement deux faits — « n'est pas lie a un
conteneur **ou** ce dernier n'est pas identifiable ». Le premier releve de ce
code-ci, plus precis ; les deux sont exclusifs.

    E-6112  aucun conteneur_href n'est renseigne      (ce controle)
    E-6105  il est renseigne mais ne resout rien

Un noeud ne peut relever des deux : soit la reference existe, soit elle n'existe
pas. La distinction n'est pas cosmetique — elle separe un ouvrage orphelin, qu'il
faut rattacher, d'une reference cassee, qu'il faut corriger ou dont la cible est
a retablir.

Le moteur `detection_localisation_noeud` releve toute
la chaine de localisation, ce controle ne retient que ce type. Autres
controles servis par ce moteur : e6105, e6106, e6209.

L'absence de conteneur interrompt la cascade du moteur : sans conteneur, ni la
geometrie ni la suite de la chaine ne sont evaluables. Un noeud signale ici ne
l'est donc jamais par E-6106.

Usage CLI :
    python -m recostar.controle.conteneur.e6112 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e6112_noeud_sans_conteneur.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_localisation_noeud import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6112_noeud_sans_conteneur.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-6112"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "conteneur_absent",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "conteneur_absent": ("Le nœud n'est rattaché à aucun conteneur."),
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
    """Execute le controle E-6112 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(repertoire, TYPES_RETENUS, PROFIL_ECARTS, FICHIER_SORTIE, sortie)


def main() -> None:
    """Point d'entree CLI du controle E-6112."""
    parseur = argparse.ArgumentParser(description="Controle E-6112 : ce nœud ne peut pas exister sans conteneur")
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
