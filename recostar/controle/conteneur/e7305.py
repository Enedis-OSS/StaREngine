"""
Controle E-7305 : La casse du couple Fabriquant / Modèle n'est pas correcte

Le couple Fabricant / Modele d'un materiel de jonction est bien repertorie au
catalogue, mais n'y est pas ecrit avec la meme capitalisation. La donnee designe
le bon materiel ; son ecriture s'ecarte de la reference.

Pourquoi ce cas echappe a E-7104
--------------------------------
E-7104 confronte le couple au catalogue sur des chaines **normalisees** — casse
ignoree, espaces replies — et c'est ce qui le rend robuste : un ecart de saisie
ne doit pas faire echouer un rattachement legitime. Un « nexans » face a un
catalogue « NEXANS » passe donc E-7104 sans bruit.

E-7305 nomme ce qui reste : le couple est le bon, mais mal orthographie. Les deux
regles sont exclusives — un couple est soit inconnu du catalogue (E-7104,
`forte`), soit connu et eventuellement mal capitalise (E-7305, `basse`).

La casse seule
--------------
Le libelle du code ne vise que la capitalisation. La comparaison est donc faite
apres repliement des espaces des deux cotes (`replier_espaces`) : un
« DDC  240-35 » face a « DDC 240-35 » n'est pas signale, seule une difference de
casse subsistant apres ce repliement peut l'etre.

Une anomalie par couple, non par champ : que le Fabricant, le Modele ou les deux
soient mal capitalises, le defaut est le meme et se corrige d'un geste.

Le moteur `detection_catalogue_materiel` releve toutes
les anomalies de son domaine, ce controle ne retenant que celles de son code. Les
autres controles servis par ce moteur : e7104, e9600.

Usage CLI :
    python -m recostar.controle.conteneur.e7305 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e7305_casse_couple_fabricant_modele.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_catalogue_materiel import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e7305_casse_couple_fabricant_modele.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-7305"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "casse_couple_incorrecte",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "casse_couple_incorrecte": ("La casse du couple Fabricant / Modèle diffère de celle du catalogue."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_jonction", "id_materiel"),
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-7305 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-7305."""
    parseur = argparse.ArgumentParser(
        description="Controle E-7305 : la casse du couple Fabricant / Modèle doit être celle du catalogue"
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
