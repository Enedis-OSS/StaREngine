"""
Controle E-6209 : Le nœud a une géométrie et est lié a un conteneur

Il releve un noeud qui
decrit sa position deux fois : par une geometrie propre et par un rattachement a
un conteneur. Les deux sources sont libres de diverger, la position devient
ambigue.

Perimetre — arbitrage metier, plus large que celui des regles de chaine :

    RPD_CoupeCircuitAFusibles_Reco   RPD_SupportModules_Reco
    RPD_JeuBarres_Reco               RPD_Terre_Reco
    RPD_ModuleRaccordement_Reco      RPD_PosteElectrique_Reco
    RPD_PointDeComptage_Reco         RPD_OuvrageCollectifBranchement_Reco

Les six premieres n'ont pas le droit de porter une geometrie : toute geometrie
propre y est indue. Les deux dernieres en ont le droit — c'est la premiere voie
de localisation admise par E-6109 — mais pas cumulee avec un conteneur_href.

Le rattachement se lit sur l'attribut, pas sur sa resolution : un conteneur_href
renseigne mais mort compte comme un rattachement. Sans cette lecture, ce cas ne
sortirait nulle part, E-6109 declarant l'ouvrage conforme au titre de sa
geometrie propre.

Aucun filtre de statut : porter une geometrie indue reste indu a l'etat de
projet, et six des huit couches visees ne portent pas de champ Statut.

Le moteur `detection_localisation_noeud` releve toute
la chaine de localisation, ce controle ne retient que ce type. Autres
controles servis par ce moteur : e6105, e6106.

Usage CLI :
    python -m recostar.controle.conteneur.e6209 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e6209_geometrie_directe_du_noeud.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_localisation_noeud import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6209_geometrie_directe_du_noeud.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-6209"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "geometrie_directe_presente",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "geometrie_directe_presente": ("Le nœud porte une géométrie propre alors qu'il est rattaché à un conteneur."),
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
    """Execute le controle E-6209 et ecrit ses ecarts."""
    return executer_analyse(repertoire, TYPES_RETENUS, PROFIL_ECARTS, FICHIER_SORTIE, sortie)


def main() -> None:
    """Point d'entree CLI du controle E-6209."""
    parseur = argparse.ArgumentParser(description="Controle E-6209 : le nœud a une géométrie et est lié a un conteneur")
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
