"""
Pipeline complet RecoStaR.

Orchestre l'enchainement complet des traitements RecoStaR :
    1. Conversion GML vers GeoJSON (recostar_to_geojson.py)
    2. Controles des donnees (altimetrie, noeuds, PLOR, projections)
    3. Conversion GeoJSON vers GML (geojson_to_recostar.py)

Usage CLI :
    python pipeline_recostar_complet_v1.py
        --entree <fichier.gml>
        --sortie-geojson <repertoire>
        --sortie-gml <fichier.gml>
        [--logiciel <nom>] [--producteur <nom>]
        [--responsable <nom>] [--nom <nom>] [--srs <epsg>]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Configuration du logger (logs reduits au strict minimum, sans emoji)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Racine du projet (star_engine)
RACINE_PROJET: Path = Path(__file__).resolve().parents[2]

# Chemins des scripts de conversion (conversion_V1)
SCRIPT_GML_VERS_GEOJSON: Path = (
    RACINE_PROJET
    / "conversion"
    / "recostar"
    / "conversion_V1"
    / "recostar_to_geojson.py"
)
SCRIPT_GEOJSON_VERS_GML: Path = (
    RACINE_PROJET
    / "conversion"
    / "recostar"
    / "conversion_V1"
    / "geojson_to_recostar.py"
)

# Pipelines de controle : nom logique et chemin du script
# L'ordre du tuple definit l'ordre d'execution
PIPELINES_CONTROLES: tuple[tuple[str, Path], ...] = (
    (
        "altimetrie",
        RACINE_PROJET
        / "controles"
        / "recostar"
        / "controles_alti"
        / "pipeline_controle_alti.py",
    ),
    (
        "noeuds",
        RACINE_PROJET
        / "controles"
        / "recostar"
        / "controles_noeuds"
        / "pipeline_controle_noeud.py",
    ),
    (
        "plor",
        RACINE_PROJET
        / "controles"
        / "recostar"
        / "controles_plor"
        / "pipeline_controle_plor.py",
    ),
    (
        "projections",
        RACINE_PROJET
        / "controles"
        / "recostar"
        / "controles_projections"
        / "pipeline_controle_proj.py",
    ),
)


def executer_sous_processus(
    script: Path,
    arguments: list[str],
) -> dict[str, Any]:
    """Execute un script Python en sous-processus.

    Le repertoire de travail est positionne au dossier parent du script
    afin que les imports locaux des modules cibles soient resolus.
    """
    commande = [sys.executable, str(script)] + arguments

    # Execution depuis le dossier du script pour les imports relatifs
    repertoire_travail = str(script.parent)

    try:
        resultat = subprocess.run(
            commande,
            cwd=repertoire_travail,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as erreur:
        return {
            "succes": False,
            "erreur": f"Impossible d'executer {script.name} : {erreur}",
        }

    if resultat.returncode != 0:
        return {
            "succes": False,
            "erreur": resultat.stderr.strip() or f"Code retour {resultat.returncode}",
            "sortie": resultat.stdout.strip(),
        }

    return {"succes": True, "sortie": resultat.stdout.strip()}


def analyser_sortie_json(sortie: str) -> dict[str, Any] | None:
    """Tente de parser une sortie JSON depuis le stdout d'un sous-processus."""
    if not sortie:
        return None
    try:
        return json.loads(sortie)
    except json.JSONDecodeError:
        return None


def convertir_gml_vers_geojson(
    chemin_gml: Path,
    repertoire_sortie: Path,
) -> dict[str, Any]:
    """Etape 1 : conversion du fichier GML source en fichiers GeoJSON."""
    logger.info("Conversion GML vers GeoJSON : %s", chemin_gml.name)

    resultat = executer_sous_processus(
        SCRIPT_GML_VERS_GEOJSON,
        [str(chemin_gml.resolve()), str(repertoire_sortie.resolve())],
    )

    if not resultat["succes"]:
        logger.error("Echec conversion GML vers GeoJSON : %s", resultat.get("erreur"))
    else:
        logger.info("Conversion GML vers GeoJSON terminee")

    return resultat


def executer_controles(
    repertoire_geojson: Path,
    repertoire_sortie: Path,
) -> dict[str, Any]:
    """Etape 2 : execution sequentielle de tous les pipelines de controle.

    Chaque pipeline est execute independamment ; un echec n'empeche pas
    l'execution des suivants. Les resultats JSON sont recuperes et agreges.
    """
    logger.info("Lancement des controles sur %s", repertoire_geojson)

    resultats: dict[str, dict[str, Any]] = {}
    nb_anomalies_total = 0

    for nom, chemin_script in PIPELINES_CONTROLES:
        logger.info("Controle en cours : %s", nom)

        resultat_brut = executer_sous_processus(
            chemin_script,
            [
                "--repertoire",
                str(repertoire_geojson.resolve()),
                "--sortie",
                str(repertoire_sortie.resolve()),
            ],
        )

        if not resultat_brut["succes"]:
            resultats[nom] = resultat_brut
            logger.error("Echec du controle %s : %s", nom, resultat_brut.get("erreur"))
            continue

        # Extraction des resultats JSON produits par le pipeline de controle
        donnees = analyser_sortie_json(resultat_brut.get("sortie", ""))
        if donnees is not None:
            resultats[nom] = donnees
            nb_anomalies_total += donnees.get("nombre_anomalies_total", 0)
        else:
            resultats[nom] = resultat_brut

    logger.info("Controles termines - anomalies totales : %d", nb_anomalies_total)

    return {
        "succes": True,
        "controles": resultats,
        "nombre_anomalies_total": nb_anomalies_total,
    }


def convertir_geojson_vers_gml(
    repertoire_geojson: Path,
    chemin_gml_sortie: Path,
    logiciel: str = "LAZio",
    producteur: str = "TEST",
    responsable: str = "TEST",
    nom: str = "TEST",
    srs: str | None = None,
) -> dict[str, Any]:
    """Etape 3 : reconversion des fichiers GeoJSON en fichier GML final."""
    logger.info("Conversion GeoJSON vers GML : %s", chemin_gml_sortie.name)

    arguments = [
        str(repertoire_geojson.resolve()),
        str(chemin_gml_sortie.resolve()),
        "--logiciel",
        logiciel,
        "--producteur",
        producteur,
        "--responsable",
        responsable,
        "--nom",
        nom,
    ]

    if srs is not None:
        arguments.extend(["--srs", srs])

    resultat = executer_sous_processus(SCRIPT_GEOJSON_VERS_GML, arguments)

    if not resultat["succes"]:
        logger.error("Echec conversion GeoJSON vers GML : %s", resultat.get("erreur"))
    else:
        logger.info("Conversion GeoJSON vers GML terminee")

    return resultat


def executer_pipeline(
    chemin_gml: Path,
    repertoire_geojson: Path,
    chemin_gml_sortie: Path,
    logiciel: str = "LAZio",
    producteur: str = "TEST",
    responsable: str = "TEST",
    nom: str = "TEST",
    srs: str | None = None,
) -> dict[str, Any]:
    """Execute le pipeline complet RecoStaR.

    Enchaine les trois etapes :
        1. Conversion GML vers GeoJSON
        2. Controles des donnees
        3. Conversion GeoJSON vers GML

    Si l'etape 1 echoue, le pipeline s'arrete immediatement.
    Les controles (etape 2) sont informatifs : un echec partiel
    n'empeche pas la reconversion GML finale.
    """
    debut = time.perf_counter()
    resultats: dict[str, Any] = {"etapes": {}}

    # Validation du fichier source
    if not chemin_gml.is_file():
        return {"succes": False, "erreur": f"Fichier GML introuvable : {chemin_gml}"}

    # Creation des repertoires de sortie
    os.makedirs(repertoire_geojson, exist_ok=True)
    os.makedirs(chemin_gml_sortie.parent, exist_ok=True)

    # Etape 1 : GML vers GeoJSON
    resultat_etape_1 = convertir_gml_vers_geojson(chemin_gml, repertoire_geojson)
    resultats["etapes"]["conversion_gml_vers_geojson"] = resultat_etape_1

    if not resultat_etape_1["succes"]:
        resultats["succes"] = False
        resultats["erreur"] = "Echec de la conversion GML vers GeoJSON"
        return resultats

    # Etape 2 : controles des donnees
    resultat_etape_2 = executer_controles(repertoire_geojson, repertoire_geojson)
    resultats["etapes"]["controles"] = resultat_etape_2

    # Etape 3 : GeoJSON vers GML
    resultat_etape_3 = convertir_geojson_vers_gml(
        repertoire_geojson,
        chemin_gml_sortie,
        logiciel=logiciel,
        producteur=producteur,
        responsable=responsable,
        nom=nom,
        srs=srs,
    )
    resultats["etapes"]["conversion_geojson_vers_gml"] = resultat_etape_3

    duree = time.perf_counter() - debut
    resultats["succes"] = resultat_etape_3["succes"]
    resultats["duree_secondes"] = round(duree, 2)

    nb_anomalies = resultat_etape_2.get("nombre_anomalies_total", 0)
    if nb_anomalies > 0:
        resultats["nombre_anomalies_total"] = nb_anomalies

    logger.info("Pipeline termine en %.2f secondes", duree)
    return resultats


def main() -> None:
    """Point d'entree CLI du pipeline complet RecoStaR."""
    parseur = argparse.ArgumentParser(
        description="Pipeline complet RecoStaR : GML -> GeoJSON -> Controles -> GML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemple :
  python pipeline_recostar_complet_v1.py
      --entree recolement.gml
      --sortie-geojson ./geojson_output
      --sortie-gml ./resultat.gml
      --producteur ENEDIS --nom MonReseau
        """,
    )

    parseur.add_argument(
        "--entree",
        required=True,
        type=Path,
        help="Chemin du fichier GML RecoStaR en entree",
    )
    parseur.add_argument(
        "--sortie-geojson",
        required=True,
        type=Path,
        help="Repertoire de sortie des fichiers GeoJSON",
    )
    parseur.add_argument(
        "--sortie-gml",
        required=True,
        type=Path,
        help="Chemin du fichier GML de sortie",
    )
    parseur.add_argument(
        "--logiciel",
        default="LAZio",
        help="Logiciel utilise pour la generation (defaut : LAZio)",
    )
    parseur.add_argument(
        "--producteur",
        default="TEST",
        help="Producteur du recolement (defaut : TEST)",
    )
    parseur.add_argument(
        "--responsable",
        default="TEST",
        help="Responsable du recolement (defaut : TEST)",
    )
    parseur.add_argument(
        "--nom",
        default="TEST",
        help="Nom du reseau (defaut : TEST)",
    )
    parseur.add_argument(
        "--srs",
        default=None,
        help="Forcer le CRS (ex: EPSG:2154). Si absent, detection automatique.",
    )

    arguments = parseur.parse_args()

    resultat = executer_pipeline(
        chemin_gml=arguments.entree,
        repertoire_geojson=arguments.sortie_geojson,
        chemin_gml_sortie=arguments.sortie_gml,
        logiciel=arguments.logiciel,
        producteur=arguments.producteur,
        responsable=arguments.responsable,
        nom=arguments.nom,
        srs=arguments.srs,
    )

    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
