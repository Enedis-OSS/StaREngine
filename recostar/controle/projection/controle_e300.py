"""
Controle de conformite de projection des entites GeoJSON.

Verifie que l'ensemble des fichiers GeoJSON d'un jeu de donnees Recostar
utilisent la projection declaree dans le fichier _metadata.json (champ
Metadata.SRS). Tout fichier dont le champ crs ne correspond pas a la
projection attendue (ou ne possede pas de champ crs) voit l'integralite
de ses entites signalee comme anomalie.

Usage CLI :
    python controle_e300.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e300_projection.geojson
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from utils_geojson import (
    ProfilEcarts,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    lister_fichiers_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Nom du fichier de metadonnees du jeu de donnees
FICHIER_METADATA: str = "_metadata.json"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e300_projection.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E300"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "projection_incorrecte": ("L'entité n'est pas dans la projection attendue du jeu de données."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_entite",),
)


# Niveau de priorite affecte aux entites signalees
PRIORITE_ANOMALIE: str = "bloquant"


def _normaliser_epsg(valeur: str) -> str | None:
    """Normalise un identifiant de projection vers le format canonique EPSG:NNNN.

    Formats pris en charge :
    - URN OGC : urn:ogc:def:crs:EPSG::3947
                urn:ogc:def:crs:EPSG:6.18.3:3947
    - Format direct : EPSG:3947 (insensible a la casse)

    Retourne None si le format n'est pas reconnu ou si le code n'est pas numerique.
    """
    valeur = valeur.strip()
    # Format URN OGC : le code EPSG est le dernier segment non vide apres ':'
    if valeur.lower().startswith("urn:ogc:def:crs:"):
        parties = valeur.split(":")
        code = next((p for p in reversed(parties) if p and p.isdigit()), None)
        return f"EPSG:{code}" if code else None
    # Format EPSG:NNNN direct (insensible a la casse)
    majuscule = valeur.upper()
    if majuscule.startswith("EPSG:"):
        code = majuscule[5:]
        return f"EPSG:{code}" if code.isdigit() else None
    return None


def lire_srs_attendu(repertoire: str) -> tuple[str | None, str | None]:
    """Lit le SRS attendu depuis _metadata.json du repertoire.

    Retourne (epsg_normalise, message_erreur). L'un des deux est toujours None.
    """
    chemin = os.path.join(repertoire, FICHIER_METADATA)
    if not os.path.isfile(chemin):
        return None, f"Fichier {FICHIER_METADATA} introuvable dans {repertoire}"

    try:
        with open(chemin, encoding="utf-8") as fichier:
            metadonnees = json.load(fichier)
    except (json.JSONDecodeError, OSError):
        return None, f"Impossible de lire {FICHIER_METADATA}"

    srs = (metadonnees.get("Metadata") or {}).get("SRS")
    if not srs:
        return None, f"Champ Metadata.SRS absent de {FICHIER_METADATA}"

    epsg = _normaliser_epsg(srs)
    if epsg is None:
        return None, f"Valeur SRS non reconnue : {srs!r}"

    return epsg, None


def extraire_epsg_collection(collection: dict[str, Any]) -> str | None:
    """Extrait et normalise le code EPSG depuis le champ crs d'une FeatureCollection.

    Retourne None si le champ crs est absent ou non reconnu.
    """
    crs = collection.get("crs")
    if crs is None:
        return None
    nom_crs = (crs.get("properties") or {}).get("name", "")
    if not nom_crs:
        return None
    return _normaliser_epsg(nom_crs)


def detecter_entites_projection_incorrecte(
    features: list[dict[str, Any]],
    nom_fichier: str,
    projection_attendue: str,
    projection_detectee: str | None,
) -> list[dict[str, Any]]:
    """Signale toutes les entites d'un fichier dont la projection ne correspond pas.

    Si la projection du fichier est absente (None) ou differente de la projection
    attendue, l'integralite des entites avec geometrie est signalee.
    Les entites sans geometrie sont ignorees.
    """
    if projection_detectee == projection_attendue:
        return []

    projection_signalee = projection_detectee if projection_detectee else "inconnue"
    anomalies: list[dict[str, Any]] = []
    for feature in features:
        geometrie = feature.get("geometry")
        if geometrie is None:
            continue
        anomalies.append(
            {
                "fichier_source": nom_fichier,
                "id_entite": obtenir_id_feature(feature),
                "type_geometrie": geometrie.get("type", "inconnu"),
                "geometrie": geometrie,
                "projection_attendue": projection_attendue,
                "projection_detectee": projection_signalee,
            }
        )
    return anomalies


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des entites en ecart de projection.

    La geometrie originale de chaque entite est conservee pour permettre
    la localisation dans QGIS.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "fichier_source": a["fichier_source"],
                "id_entite": a["id_entite"],
                "type_geometrie": a["type_geometrie"],
                "projection_attendue": a["projection_attendue"],
                "projection_detectee": a["projection_detectee"],
                "type_anomalie": "projection_incorrecte",
                "priorite": PRIORITE_ANOMALIE,
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, PROFIL_ECARTS)


def _construire_crs_depuis_epsg(epsg: str) -> dict[str, Any]:
    """Construit un objet CRS GeoJSON depuis un code EPSG normalise (EPSG:NNNN)."""
    code = epsg[5:]  # Retire le prefixe "EPSG:"
    return {
        "type": "name",
        "properties": {"name": f"urn:ogc:def:crs:EPSG::{code}"},
    }


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de projection en mode CLI.

    Lit la projection attendue depuis _metadata.json, parcourt tous les GeoJSON
    du repertoire, detecte les entites en ecart et ecrit le fichier de sortie.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    projection_attendue, erreur = lire_srs_attendu(repertoire_resolu)
    # Controle explicite sur projection_attendue pour le narrowing de type (Pylance)
    if projection_attendue is None or erreur is not None:
        return {"succes": False, "erreur": erreur}

    fichiers = lister_fichiers_geojson(repertoire_resolu)
    if not fichiers:
        return {"succes": False, "erreur": "Aucun fichier GeoJSON dans le repertoire"}

    toutes_anomalies: list[dict[str, Any]] = []
    fichiers_analyses = 0

    for nom_fichier in fichiers:
        collection = lire_geojson(os.path.join(repertoire_resolu, nom_fichier))
        if collection is None:
            continue
        features = collection.get("features", [])
        projection_detectee = extraire_epsg_collection(collection)
        anomalies = detecter_entites_projection_incorrecte(
            features, nom_fichier, projection_attendue, projection_detectee
        )
        toutes_anomalies.extend(anomalies)
        fichiers_analyses += 1

    # Le CRS de sortie est celui de la projection attendue (reference du controle)
    crs_sortie = _construire_crs_depuis_epsg(projection_attendue)
    geojson_ecarts = construire_geojson_ecarts(toutes_anomalies, crs_sortie)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(toutes_anomalies),
        "fichiers_analyses": fichiers_analyses,
        "projection_attendue": projection_attendue,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle de conformite de projection."""
    parseur = argparse.ArgumentParser(description="Controle de conformite de projection des entites GeoJSON")
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON et le _metadata.json",
    )
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
