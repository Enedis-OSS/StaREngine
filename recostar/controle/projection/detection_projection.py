"""
Moteur de detection des ecarts de projection d'un jeu GeoJSON RecoStaR.

Le fichier `_metadata.json` declare la projection du jeu (`Metadata.SRS`) ;
chaque GeoJSON porte la sienne dans son champ `crs`. Confronter les deux, et les
fichiers entre eux, repond a trois questions distinctes, auxquelles le
verificateur reserve trois codes :

    le fichier ne declare aucun crs            -> E-2200
    son crs differe du SRS declare             -> E-5105
    les fichiers ne portent pas tous le meme   -> E-9302

Pourquoi trois codes et non un
------------------------------
Un crs **absent** et un crs **different** ne se corrigent pas de la meme facon :
l'un est une declaration manquante, l'autre une reprojection a faire. Le
discriminant est le meme calcul (`projection_detectee` vaut None dans le premier
cas), mais les deux constats ne se confondent pas.

La non-unicite, elle, compare les fichiers entre eux, la ou les deux autres
regles comparent chaque fichier au SRS declare.
Un jeu peut parfaitement etre unanime tout en divergeant du declare — c'est
alors E-5105 seul — ou panache tout en ayant des fichiers conformes.

E-9302 plutot qu'E-0007
-----------------------
Le verificateur nomme ce dernier defaut `E-0007`, « l'information du systeme de
projection portee par les objets du GML n'est pas unique sur l'ensemble du
fichier ». L'arbitrage metier ecarte ce code au profit d'un code local : la
regle s'evalue ici sur les GeoJSON issus de la conversion, ou « le fichier » du
verificateur est devenu un **jeu de fichiers**, chacun portant son propre `crs`.

Granularite : une anomalie par entite, comme les deux autres regles. Sont
signalees les entites des fichiers portant un crs **minoritaire** — ce sont eux
qu'il faut reprendre, et non le jeu entier. A egalite de decompte, le crs le
plus petit dans l'ordre lexicographique fait reference, afin que le verdict ne
depende pas de l'ordre de lecture du repertoire.

Les entites sans geometrie sont ignorees : l'ecart ne serait pas localisable.
"""

import json
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.ecarts import filtrer_par_type
from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_ecarts_par_type,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    lister_fichiers_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.resultats import (
    MOTIF_AUCUN_GEOJSON,
    rapport_sans_objet,
)

# Nom du fichier de metadonnees du jeu de donnees
FICHIER_METADATA: str = "_metadata.json"

# Nombre de crs distincts a partir duquel le jeu cesse d'etre unanime.
SEUIL_NON_UNICITE: int = 2


# Types d'anomalie produits par le moteur, un par code rendu.
TYPE_NON_DEFINIE: str = "projection_non_definie"
TYPE_DIFFERENTE: str = "projection_differente"
TYPE_NON_UNIQUE: str = "projection_non_unique"

# Libelle porte au rapport quand un fichier ne declare aucune projection.
PROJECTION_INCONNUE: str = "inconnue"


def normaliser_epsg(valeur: str) -> str | None:
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

    epsg = normaliser_epsg(srs)
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
    return normaliser_epsg(nom_crs)


def _ecart(
    feature: dict[str, Any], nom_fichier: str, type_anomalie: str, attendue: str, detectee: str | None
) -> dict[str, Any] | None:
    """Assemble l'ecart d'une entite, ou None si elle n'est pas localisable."""
    geometrie = feature.get("geometry")
    if geometrie is None:
        return None
    return {
        "type_anomalie": type_anomalie,
        "fichier_source": nom_fichier,
        "id_entite": obtenir_id_feature(feature),
        "type_geometrie": geometrie.get("type", "inconnu"),
        "geometrie": geometrie,
        "projection_attendue": attendue,
        "projection_detectee": detectee if detectee else PROJECTION_INCONNUE,
    }


def detecter_ecart_au_srs(
    features: list[dict[str, Any]],
    nom_fichier: str,
    projection_attendue: str,
    projection_detectee: str | None,
) -> list[dict[str, Any]]:
    """Confronte la projection d'un fichier au SRS declare par les metadonnees.

    Deux causes, deux codes : un `crs` absent est une declaration manquante
    (E-2200), un `crs` present mais different appelle une reprojection (E-5105).
    Les separer ici evite de redecider plus tard sur une chaine de repli.
    """
    if projection_detectee == projection_attendue:
        return []
    type_anomalie = TYPE_NON_DEFINIE if projection_detectee is None else TYPE_DIFFERENTE
    ecarts = (_ecart(f, nom_fichier, type_anomalie, projection_attendue, projection_detectee) for f in features)
    return [ecart for ecart in ecarts if ecart is not None]


def crs_minoritaires(projections: Mapping[str, str | None]) -> frozenset[str]:
    """Retourne les crs du jeu qui ne sont pas celui de la majorite des fichiers.

    Les fichiers sans `crs` sont ecartes du decompte : leur defaut est nomme par
    E-2200, et les compter ferait d'une declaration manquante une opinion
    divergente. Un jeu unanime — ou reduit a un seul crs — ne rend rien.

    A egalite de decompte, le crs le plus petit dans l'ordre lexicographique fait
    reference : sans ce depart, le verdict dependrait de l'ordre de lecture du
    repertoire.
    """
    declares = [projection for projection in projections.values() if projection is not None]
    if len(set(declares)) < SEUIL_NON_UNICITE:
        return frozenset()
    decompte = Counter(declares)
    majoritaire = min(decompte, key=lambda crs: (-decompte[crs], crs))
    return frozenset(decompte) - {majoritaire}


def detecter_non_unicite(
    features: list[dict[str, Any]],
    nom_fichier: str,
    projection_attendue: str,
    projection_detectee: str | None,
    minoritaires: frozenset[str],
) -> list[dict[str, Any]]:
    """Signale les entites d'un fichier portant un crs minoritaire du jeu."""
    if projection_detectee is None or projection_detectee not in minoritaires:
        return []
    ecarts = (_ecart(f, nom_fichier, TYPE_NON_UNIQUE, projection_attendue, projection_detectee) for f in features)
    return [ecart for ecart in ecarts if ecart is not None]


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    profil: ProfilEcarts,
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
                "type_anomalie": a["type_anomalie"],
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, profil)


def _construire_crs_depuis_epsg(epsg: str) -> dict[str, Any]:
    """Construit un objet CRS GeoJSON depuis un code EPSG normalise (EPSG:NNNN)."""
    code = epsg[5:]  # Retire le prefixe "EPSG:"
    return {
        "type": "name",
        "properties": {"name": f"urn:ogc:def:crs:EPSG::{code}"},
    }


def _lire_jeu(repertoire: str) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str | None]]:
    """Lit une fois chaque GeoJSON du repertoire : ses entites et son crs.

    Deux passes sont necessaires — la non-unicite se juge sur l'ensemble des
    fichiers — mais une seule lecture disque : relire le repertoire pour la
    seconde passe doublerait le cout du controle sur un jeu volumineux.
    """
    entites: dict[str, list[dict[str, Any]]] = {}
    projections: dict[str, str | None] = {}
    for nom_fichier in lister_fichiers_geojson(repertoire):
        collection = lire_geojson(os.path.join(repertoire, nom_fichier))
        if collection is None:
            continue
        entites[nom_fichier] = collection.get("features", [])
        projections[nom_fichier] = extraire_epsg_collection(collection)
    return entites, projections


def detecter_anomalies(
    entites: Mapping[str, list[dict[str, Any]]],
    projections: Mapping[str, str | None],
    projection_attendue: str,
) -> list[dict[str, Any]]:
    """Releve les trois ecarts de projection du jeu, tous codes confondus.

    Un fichier peut en porter deux : un crs minoritaire **et** different du SRS
    declare sont deux constats distincts, l'un envers le jeu, l'autre envers les
    metadonnees.
    """
    minoritaires = crs_minoritaires(projections)
    anomalies: list[dict[str, Any]] = []
    for nom_fichier, features in entites.items():
        detectee = projections[nom_fichier]
        anomalies.extend(detecter_ecart_au_srs(features, nom_fichier, projection_attendue, detectee))
        anomalies.extend(detecter_non_unicite(features, nom_fichier, projection_attendue, detectee, minoritaires))
    return anomalies


def executer_analyse(
    repertoire: str,
    types_retenus: frozenset[str],
    profil: ProfilEcarts,
    fichier_sortie: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute un controle de projection en mode CLI.

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

    entites, projections = _lire_jeu(repertoire_resolu)
    if not entites:
        return rapport_sans_objet(MOTIF_AUCUN_GEOJSON)

    # Le moteur releve les trois ecarts ; le controle appelant ne retient que
    # celui de son code. Les compteurs qui suivent portent sur son perimetre.
    anomalies = filtrer_par_type(detecter_anomalies(entites, projections, projection_attendue), types_retenus)

    # Le CRS de sortie est celui de la projection attendue (reference du controle)
    crs_sortie = _construire_crs_depuis_epsg(projection_attendue)
    geojson_ecarts = construire_geojson_ecarts(anomalies, profil, crs_sortie)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, fichier_sortie)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_ecarts_par_type(geojson_ecarts),
        "fichiers_analyses": len(entites),
        "projection_attendue": projection_attendue,
        "projections_distinctes": sorted({p for p in projections.values() if p is not None}),
        "sortie": chemin_ecrit,
    }
