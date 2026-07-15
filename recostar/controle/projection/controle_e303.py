"""
Controle d'appartenance a l'emprise geographique de la direction regionale.

Verifie que les entites presentes dans les GeoJSON analyses se situent
a l'interieur de l'emprise DR correspondant au numero d'affaire fourni.

Formats acceptes pour le numero d'affaire :
  RAC : RAC-CVL-25-007998  -> trigramme CVL recherche dans trigramme_racing
  DA  : DA21/256553        -> prefixe DA21 recherche dans ref_dossier

La reference DR est resolue via fichiers_dr/reference_dr.json.
L'emprise spatiale est chargee depuis fichiers_dr/emprise_dr.geojson (EPSG:2154).
Si les GeoJSON analyses sont dans un autre CRS projete, les coordonnees sont
reprojetees vers EPSG:2154 via pyproj avant le test de containment.

Un seul numero d'affaire est accepte. Les cas situes a la frontiere entre
plusieurs DR sont geres par la resolution multi-repertoire : si un trigramme
ou une reference correspond a plusieurs codes DR, toutes les emprises associees
sont considerees comme autorisees.

Usage CLI :
    python controle_e303.py --repertoire <chemin> --numero_affaire <numero>
                            [--sortie <chemin>]

Sortie : ecarts_emprise_dr.geojson
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from pyproj import CRS, Transformer
from utils_geojson import (
    ecrire_geojson,
    lire_geojson,
    lister_fichiers_geojson,
    obtenir_id_feature,
)

# Chemins absolus des fichiers de reference, calcules depuis la position du module
_REPERTOIRE_MODULE: str = str(Path(__file__).parent)
CHEMIN_REFERENCE_DR: str = os.path.join(_REPERTOIRE_MODULE, "fichiers_dr", "reference_dr.json")
CHEMIN_EMPRISE_DR: str = os.path.join(_REPERTOIRE_MODULE, "fichiers_dr", "emprise_dr.geojson")

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_emprise_dr.geojson"

# Niveau de priorite affecte aux entites hors emprise
PRIORITE_ANOMALIE: str = "bloquant"

# CRS de reference de l'emprise (Lambert 93)
CRS_EMPRISE: str = "EPSG:2154"

# Exceptions metier : numeros d'affaire pour lesquels E303 est entierement ignore
# (aucune verification, aucune anomalie). Le numero d'affaire ci-dessous exclut
# le controle par egalite exacte ; les prefixes par debut de chaine.
NUMERO_AFFAIRE_EXCLU: str = "12345678"
PREFIXES_AFFAIRE_EXCLUS: tuple[str, ...] = ("OSR", "osr")


def affaire_exclue_du_controle(numero_affaire: str) -> bool:
    """Determine si le numero d'affaire exclut totalement le controle E303.

    Regle de gestion : E303 est entierement ignore (aucune verification,
    aucune anomalie generee) dans l'un des cas suivants :
    - le numero d'affaire est exactement egal a NUMERO_AFFAIRE_EXCLU (12345678) ;
    - le numero d'affaire commence par l'un des PREFIXES_AFFAIRE_EXCLUS (OSR / osr).

    Dans tous les autres cas, retourne False (comportement E303 inchange).
    """
    # Normalise les espaces de bord, coherent avec _extraire_prefixe.
    valeur = numero_affaire.strip()
    if valeur == NUMERO_AFFAIRE_EXCLU:
        return True
    # str.startswith accepte un tuple : OSR et osr sont testes en un seul appel.
    return valeur.startswith(PREFIXES_AFFAIRE_EXCLUS)


# Extracteurs de paires (x, y) par type de geometrie
_EXTRACTEURS_XY: dict[str, Any] = {
    "Point": lambda c: [(c[0], c[1])],
    "LineString": lambda c: [(pt[0], pt[1]) for pt in c],
    "MultiPoint": lambda c: [(pt[0], pt[1]) for pt in c],
    "Polygon": lambda c: [(pt[0], pt[1]) for pt in c[0]],
    "MultiLineString": lambda c: [(pt[0], pt[1]) for ligne in c for pt in ligne],
    "MultiPolygon": lambda c: [(pt[0], pt[1]) for poly in c for pt in poly[0]],
}


def _extraire_prefixe(
    numero: str,
) -> tuple[str | None, str | None, str | None]:
    """Extrait le prefixe et le champ de recherche d'un numero d'affaire.

    Retourne (prefixe, champ_recherche, erreur).
    Formats :
    - RAC : RAC-CVL-25-007998 -> ("CVL", "trigramme_racing", None)
    - DA  : DA21/256553       -> ("DA21", "ref_dossier", None)
    """
    valeur = numero.strip()
    if valeur.upper().startswith("RAC-"):
        parties = valeur.split("-", 3)
        if len(parties) >= 2 and parties[1]:
            return parties[1].upper(), "trigramme_racing", None
        return None, None, f"Format RAC invalide : {numero!r}"
    if "/" in valeur:
        prefixe = valeur.split("/")[0].strip().upper()
        if prefixe:
            return prefixe, "ref_dossier", None
        return None, None, f"Format DA invalide : {numero!r}"
    return None, None, f"Format de numero d'affaire non reconnu : {numero!r}"


def _construire_index(
    references: list[dict[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Construit les index de recherche depuis la liste des references DR.

    - index_trigramme : trigramme_racing -> set de repertoires (plusieurs possibles)
    - index_dossier   : ref_dossier      -> repertoire (unique par cle)

    Les cles sont normalisees en majuscule pour une comparaison insensible a la casse.
    """
    index_trigramme: dict[str, set[str]] = {}
    index_dossier: dict[str, str] = {}
    for entree in references:
        trigramme = entree.get("trigramme_racing", "").upper()
        ref = entree.get("ref_dossier", "").upper()
        repertoire = entree.get("repertoire", "")
        if trigramme:
            index_trigramme.setdefault(trigramme, set()).add(repertoire)
        if ref:
            index_dossier[ref] = repertoire
    return index_trigramme, index_dossier


def resoudre_repertoires(
    numero: str,
    index_trigramme: dict[str, set[str]],
    index_dossier: dict[str, str],
) -> tuple[set[str] | None, str | None]:
    """Resout un numero d'affaire vers le(s) code(s) repertoire DR.

    Retourne (repertoires, erreur). Un trigramme peut resoudre vers plusieurs
    repertoires (cas de DR a cheval sur des zones frontalieres dans le referentiel).
    """
    prefixe, champ, erreur = _extraire_prefixe(numero)
    if prefixe is None or champ is None or erreur is not None:
        return None, erreur
    if champ == "trigramme_racing":
        repertoires = index_trigramme.get(prefixe)
        if not repertoires:
            return None, f"Trigramme '{prefixe}' introuvable dans reference_dr.json"
        return repertoires, None
    # Format DA : recherche par ref_dossier (unique)
    repertoire = index_dossier.get(prefixe)
    if not repertoire:
        return None, f"Ref. dossier '{prefixe}' introuvable dans reference_dr.json"
    return {repertoire}, None


def _charger_references(
    chemin: str,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Charge la liste des references DR depuis reference_dr.json."""
    if not os.path.isfile(chemin):
        return None, f"Fichier de references introuvable : {chemin}"
    try:
        with open(chemin, encoding="utf-8") as fichier:
            return json.load(fichier), None
    except (json.JSONDecodeError, OSError):
        return None, f"Impossible de lire le fichier de references : {chemin}"


def _calculer_bbox(
    anneau: list[list[float]],
) -> tuple[float, float, float, float]:
    """Calcule la bounding box d'un anneau pour le filtrage spatial rapide."""
    xs = [p[0] for p in anneau]
    ys = [p[1] for p in anneau]
    return min(xs), min(ys), max(xs), max(ys)


def _charger_emprises_dr(
    chemin: str,
    repertoires: set[str],
) -> tuple[list[dict[str, Any]], str | None]:
    """Charge les emprises DR correspondant aux codes repertoire demandes.

    Chaque emprise est enrichie de sa bbox precalculee pour optimiser les
    tests de containment (filtrage rapide avant le Ray Casting complet).
    La comparaison des codes DR est insensible a la casse.
    """
    if not os.path.isfile(chemin):
        return [], f"Fichier d'emprises introuvable : {chemin}"
    try:
        with open(chemin, encoding="utf-8") as fichier:
            collection = json.load(fichier)
    except (json.JSONDecodeError, OSError):
        return [], "Impossible de lire le fichier d'emprises"

    repertoires_norm = {r.upper() for r in repertoires}
    emprises: list[dict[str, Any]] = []

    for feature in collection.get("features", []):
        props = feature.get("properties") or {}
        code = (props.get("code_dr_oa") or "").upper()
        if code not in repertoires_norm:
            continue
        geom = feature.get("geometry")
        if geom is None or geom.get("type") != "Polygon":
            continue
        anneau = geom["coordinates"][0]
        emprises.append(
            {
                "code": props.get("code_dr_oa"),
                "coordonnees": geom["coordinates"],
                "bbox": _calculer_bbox(anneau),
            }
        )

    if not emprises:
        codes = ", ".join(sorted(repertoires))
        return [], f"Aucune emprise trouvee pour les codes DR : {codes}"

    return emprises, None


def _point_dans_anneau(x: float, y: float, anneau: list[list[float]]) -> bool:
    """Teste si (x, y) est a l'interieur d'un anneau via le Ray Casting.

    Le denominateur (yj - yi) est garanti non nul par la condition
    (yi > y) != (yj > y), qui implique yi != yj.
    """
    dans = False
    j = len(anneau) - 1
    for i in range(len(anneau)):
        xi, yi = anneau[i][0], anneau[i][1]
        xj, yj = anneau[j][0], anneau[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dans = not dans
        j = i
    return dans


def _point_dans_polygon(x: float, y: float, coordonnees: list[list[list[float]]]) -> bool:
    """Teste si (x, y) est dans un Polygon (anneau exterieur moins les trous)."""
    if not _point_dans_anneau(x, y, coordonnees[0]):
        return False
    return all(not _point_dans_anneau(x, y, trou) for trou in coordonnees[1:])


def _point_dans_emprise(x: float, y: float, emprise: dict[str, Any]) -> bool:
    """Teste si (x, y) est dans une emprise DR, avec filtrage bbox preliminaire."""
    xmin, ymin, xmax, ymax = emprise["bbox"]
    if x < xmin or x > xmax or y < ymin or y > ymax:
        return False
    return _point_dans_polygon(x, y, emprise["coordonnees"])


def point_dans_emprises(x: float, y: float, emprises: list[dict[str, Any]]) -> bool:
    """Retourne True si (x, y) est dans au moins une des emprises autorisees."""
    return any(_point_dans_emprise(x, y, e) for e in emprises)


def _extraire_nom_crs(collection: dict[str, Any]) -> str | None:
    """Extrait le nom textuel du CRS depuis une FeatureCollection."""
    crs = collection.get("crs")
    if crs is None:
        return None
    return (crs.get("properties") or {}).get("name") or None


def _creer_transformateur(nom_crs: str | None) -> Transformer | None:
    """Cree un Transformer pyproj vers EPSG:2154 depuis le CRS source.

    Retourne None si le CRS source est identique a EPSG:2154, inconnu ou invalide.
    """
    if nom_crs is None:
        return None
    try:
        crs_source = CRS(nom_crs)
        if crs_source == CRS(CRS_EMPRISE):
            return None
        return Transformer.from_crs(crs_source, CRS(CRS_EMPRISE), always_xy=True)
    except Exception:
        return None


def _extraire_point_representatif(
    geometrie: dict[str, Any],
) -> tuple[float, float] | None:
    """Calcule le centroide d'une geometrie comme point representatif.

    Retourne None si la geometrie est vide ou de type non reconnu.
    """
    coordonnees = geometrie.get("coordinates")
    if coordonnees is None:
        return None
    extracteur = _EXTRACTEURS_XY.get(geometrie.get("type", ""))
    if extracteur is None:
        return None
    points: list[tuple[float, float]] = extracteur(coordonnees)
    if not points:
        return None
    n = len(points)
    return sum(p[0] for p in points) / n, sum(p[1] for p in points) / n


def _appliquer_transformation(
    x: float,
    y: float,
    transformateur: Transformer | None,
) -> tuple[float, float]:
    """Applique la reprojection vers EPSG:2154 si un transformateur est fourni."""
    if transformateur is None:
        return x, y
    xt, yt = transformateur.transform(x, y)
    return float(xt), float(yt)


def detecter_entites_hors_emprise(
    features: list[dict[str, Any]],
    nom_fichier: str,
    emprises: list[dict[str, Any]],
    transformateur: Transformer | None,
) -> tuple[list[dict[str, Any]], int]:
    """Detecte les entites situees hors des emprises DR autorisees.

    Le transformateur est applique une fois par entite pour reprojeter son
    centroide vers EPSG:2154 avant le test de containment.
    Retourne (anomalies, nb_entites_analysees).
    """
    anomalies: list[dict[str, Any]] = []
    nb_analysees = 0
    for feature in features:
        geometrie = feature.get("geometry")
        if geometrie is None:
            continue
        point = _extraire_point_representatif(geometrie)
        if point is None:
            continue
        nb_analysees += 1
        x, y = _appliquer_transformation(point[0], point[1], transformateur)
        if not point_dans_emprises(x, y, emprises):
            anomalies.append(
                {
                    "fichier_source": nom_fichier,
                    "id_entite": obtenir_id_feature(feature),
                    "type_geometrie": geometrie.get("type", "inconnu"),
                    "geometrie": geometrie,
                }
            )
    return anomalies, nb_analysees


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    codes_dr: str,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des entites situees hors emprise DR."""
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "fichier_source": a["fichier_source"],
                "id_entite": a["id_entite"],
                "type_geometrie": a["type_geometrie"],
                "codes_dr_autorises": codes_dr,
                "type_anomalie": "hors_emprise_dr",
                "priorite": PRIORITE_ANOMALIE,
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return resultat


def executer_controle_cli(
    repertoire: str,
    numero_affaire: str | None = None,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle d'appartenance a l'emprise DR.

    Resout le numero d'affaire vers un ou plusieurs codes DR, charge les emprises
    correspondantes et verifie que chaque entite GeoJSON s'y trouve bien incluse.
    """
    if not numero_affaire:
        return {"succes": False, "erreur": "Parametre --numero_affaire requis"}

    # Exception metier : certains numeros d'affaire desactivent entierement E303.
    # Verifie avant tout traitement (repertoire, references, emprises) afin
    # qu'aucune verification ne soit effectuee ni aucune anomalie generee.
    if affaire_exclue_du_controle(numero_affaire):
        return {
            "succes": True,
            "controle_ignore": True,
            "motif": "numero d'affaire exclu du controle E303",
            "priorite": PRIORITE_ANOMALIE,
            "nombre_anomalies": 0,
            "numero_affaire": numero_affaire,
        }

    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    references, erreur = _charger_references(CHEMIN_REFERENCE_DR)
    if references is None or erreur is not None:
        return {"succes": False, "erreur": erreur}

    index_trigramme, index_dossier = _construire_index(references)

    repertoires, erreur = resoudre_repertoires(numero_affaire, index_trigramme, index_dossier)
    if repertoires is None or erreur is not None:
        return {"succes": False, "erreur": erreur}

    emprises, erreur = _charger_emprises_dr(CHEMIN_EMPRISE_DR, repertoires)
    if erreur is not None:
        return {"succes": False, "erreur": erreur}

    fichiers = lister_fichiers_geojson(repertoire_resolu)
    if not fichiers:
        return {"succes": False, "erreur": "Aucun fichier GeoJSON dans le repertoire"}

    toutes_anomalies: list[dict[str, Any]] = []
    nb_entites_total = 0
    fichiers_analyses = 0
    crs_sortie: dict[str, Any] | None = None
    codes_dr_str = ", ".join(sorted(repertoires))

    for nom_fichier in fichiers:
        collection = lire_geojson(os.path.join(repertoire_resolu, nom_fichier))
        if collection is None:
            continue
        # Le transformateur est cree une seule fois par fichier, hors boucle entite
        nom_crs = _extraire_nom_crs(collection)
        transformateur = _creer_transformateur(nom_crs)
        if crs_sortie is None:
            crs_sortie = collection.get("crs")
        features = collection.get("features", [])
        anomalies, nb = detecter_entites_hors_emprise(features, nom_fichier, emprises, transformateur)
        toutes_anomalies.extend(anomalies)
        nb_entites_total += nb
        fichiers_analyses += 1

    geojson_ecarts = construire_geojson_ecarts(toutes_anomalies, codes_dr_str, crs_sortie)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(toutes_anomalies),
        "entites_analysees": nb_entites_total,
        "fichiers_analyses": fichiers_analyses,
        "numero_affaire": numero_affaire,
        "codes_dr": codes_dr_str,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle d'appartenance a l'emprise DR."""
    parseur = argparse.ArgumentParser(description="Controle d'appartenance des entites a l'emprise DR")
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON a analyser",
    )
    parseur.add_argument(
        "--numero_affaire",
        required=True,
        help="Numero d'affaire (format RAC-XXX-YY-NNNNNN ou XXNN/NNNNNN)",
    )
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(
        arguments.repertoire,
        arguments.numero_affaire,
        arguments.sortie,
    )
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
