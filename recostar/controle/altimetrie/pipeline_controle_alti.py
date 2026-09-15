"""
Pipeline de controle altimetrique des GeoJSON.

Orchestre l'execution sequentielle de l'ensemble des controles altimetriques.
Chaque controle est execute via sa fonction `executer_controle_cli` et les
resultats sont centralises. Un echec de controle n'empeche pas les suivants.

Controles enchaines :
    1. Altitude Z non renseignee : entite 2D ou sommet a Z nul (e5107)
    3. Altimetrie des sommets (e5201)
    4. Altimetrie IGN (e9200)
    5. PLOR superposes de meme type de leve (e3300)
    6. Point de leve / geometrie supplementaire de coffret (e9201)
    7. Point de leve sur sommets de geometrie supplementaire de batiment (e6210)
    8. Point de leve / geometrie supplementaire de support, v1.1 (e9202)
    9. Rattachement des sommets de cables aux points de leve (detection_sommets_cables)
    10. Points de leve orphelins (e6211)

Usage CLI :
    python -m recostar.controle.altimetrie.pipeline_controle_alti --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from recostar.controle.altimetrie.e3300 import executer_controle_cli as executer_3300
from recostar.controle.altimetrie.e5102 import executer_controle_cli as executer_5102
from recostar.controle.altimetrie.e5103 import executer_controle_cli as executer_5103
from recostar.controle.altimetrie.e5107 import executer_controle_cli as executer_controle_z_non_renseigne
from recostar.controle.altimetrie.e5201 import executer_controle_cli as executer_controle_sommets
from recostar.controle.altimetrie.e6104 import executer_controle_cli as executer_6104
from recostar.controle.altimetrie.e6206 import executer_controle_cli as executer_6206
from recostar.controle.altimetrie.e6207 import executer_controle_cli as executer_6207
from recostar.controle.altimetrie.e6210 import (
    executer_controle_cli as executer_controle_point_leve_sommets_geom_supp,
)
from recostar.controle.altimetrie.e6211 import (
    executer_controle_cli as executer_controle_points_leve_orphelins,
)
from recostar.controle.altimetrie.e9200 import executer_controle_cli as executer_controle_ign
from recostar.controle.altimetrie.e9201 import (
    executer_controle_cli as executer_controle_point_leve_geom_supp,
)
from recostar.controle.altimetrie.e9202 import (
    executer_controle_cli as executer_controle_point_leve_geom_supp_support,
)
from recostar.controle.altimetrie.e9701 import executer_controle_cli as executer_9701
from recostar.controle.fonctions_communes.sortie_famille import agreger_ecarts_famille

# Noms des controles dans l'ordre d'execution
NOMS_CONTROLES: tuple[str, ...] = (
    "E-5107",
    "E-5201",
    "E-9200",
    "E-3300",
    "E-6206",
    "E-9201",
    "E-6210",
    "E-9202",
    "E-5102",
    "E-5103",
    "E-6211",
    "E-6207",
    "E-6104",
    "E-9701",
)


# Cle de la famille, reportee dans le champ FAMILLE_CONTROLE de chaque ecart.
FAMILLE: str = "altimetrie"


def executer_pipeline(
    repertoire: str,
    sortie: str | None = None,
    chemin_gml: Path | None = None,
) -> dict[str, Any]:
    """Execute l'ensemble des controles altimetriques.

    Chaque controle est execute independamment ; un echec n'empeche pas
    l'execution des controles suivants. Les resultats sont centralises
    avec le nombre total d'anomalies detectees.

    `chemin_gml` n'est utile qu'a E-6207, qui lit un attribut que la conversion
    ne conserve pas. A None, ce controle se replie sur le GeoJSON, ou localise
    lui-meme un GML present dans le repertoire.
    """
    repertoire_resolu = Path(repertoire).resolve()
    if not repertoire_resolu.is_dir():
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = Path(sortie).resolve() if sortie is not None else repertoire_resolu
    os.makedirs(dossier_sortie, exist_ok=True)

    resultats_controles: dict[str, dict[str, Any]] = {
        "E-5107": executer_controle_z_non_renseigne(str(repertoire_resolu), str(dossier_sortie)),
        "E-5201": executer_controle_sommets(str(repertoire_resolu), str(dossier_sortie)),
        "E-9200": executer_controle_ign(str(repertoire_resolu), str(dossier_sortie)),
        "E-3300": executer_3300(str(repertoire_resolu), str(dossier_sortie), chemin_gml=chemin_gml),
        "E-6206": executer_6206(str(repertoire_resolu), str(dossier_sortie), chemin_gml=chemin_gml),
        "E-9701": executer_9701(str(repertoire_resolu), str(dossier_sortie)),
        "E-9201": executer_controle_point_leve_geom_supp(str(repertoire_resolu), str(dossier_sortie)),
        "E-6210": executer_controle_point_leve_sommets_geom_supp(str(repertoire_resolu), str(dossier_sortie)),
        "E-9202": executer_controle_point_leve_geom_supp_support(str(repertoire_resolu), str(dossier_sortie)),
        "E-5102": executer_5102(str(repertoire_resolu), str(dossier_sortie)),
        "E-5103": executer_5103(str(repertoire_resolu), str(dossier_sortie)),
        "E-6211": executer_controle_points_leve_orphelins(str(repertoire_resolu), str(dossier_sortie)),
        "E-6207": executer_6207(str(repertoire_resolu), str(dossier_sortie), chemin_gml=chemin_gml),
        "E-6104": executer_6104(str(repertoire_resolu), str(dossier_sortie), chemin_gml=chemin_gml),
    }

    nb_anomalies_total = sum(r.get("nombre_anomalies", 0) for r in resultats_controles.values() if r.get("succes"))

    return {
        "succes": True,
        "controles": resultats_controles,
        "nombre_anomalies_total": nb_anomalies_total,
        # Les ecarts des controles sont refondus en un fichier unique, aux
        # champs communs a toutes les familles : c'est la sortie que lisent les
        # trois modes d'execution.
        "ecarts_famille": agreger_ecarts_famille(
            (resultat.get("sortie") for resultat in resultats_controles.values()),
            str(dossier_sortie),
            FAMILLE,
        ),
    }


def main() -> None:
    """Point d'entree CLI du pipeline de controles altimetriques."""
    parseur = argparse.ArgumentParser(description="Pipeline de controle altimetrique des GeoJSON")
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON a analyser",
    )
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    arguments = parseur.parse_args()
    resultat = executer_pipeline(arguments.repertoire, arguments.sortie)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
