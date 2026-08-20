"""
Utilitaires communs d'appartenance a l'emprise geographique d'une DR.

Regroupe la resolution du referentiel DR (numero d'affaire -> code repertoire
-> emprise geographique) et le test de containment planimetrique. Ces fonctions
etaient initialement portees par le controle E303 (projection) ; elles sont
mutualisees ici car plusieurs familles de controles en dependent desormais
(E303 pour les entites hors emprise, E508 pour les cables HTB dans l'emprise).

Les fichiers de reference restent stockes dans projection/fichiers_dr :
  - reference_dr.json    : correspondance numero d'affaire -> code repertoire ;
  - emprise_dr.geojson   : emprises geographiques des DR (EPSG:2154).

Formats de numero d'affaire acceptes :
  RAC : RAC-CVL-25-007998  -> trigramme CVL recherche dans trigramme_racing
  DA  : DA21/256553        -> prefixe DA21 recherche dans ref_dossier
"""

import json
import os
from pathlib import Path
from typing import Any

from pyproj import CRS, Transformer

# Chemins absolus des fichiers de reference, calcules depuis la position du module
_REPERTOIRE_CONTROLE: str = str(Path(__file__).resolve().parent)
CHEMIN_REFERENCE_DR: str = os.path.join(_REPERTOIRE_CONTROLE, "projection", "fichiers_dr", "reference_dr.json")
CHEMIN_EMPRISE_DR: str = os.path.join(_REPERTOIRE_CONTROLE, "projection", "fichiers_dr", "emprise_dr.geojson")

# CRS de reference des emprises (Lambert 93)
CRS_EMPRISE: str = "EPSG:2154"

# Extracteurs de paires (x, y) par type de geometrie
EXTRACTEURS_XY: dict[str, Any] = {
    "Point": lambda c: [(c[0], c[1])],
    "LineString": lambda c: [(pt[0], pt[1]) for pt in c],
    "MultiPoint": lambda c: [(pt[0], pt[1]) for pt in c],
    "Polygon": lambda c: [(pt[0], pt[1]) for pt in c[0]],
    "MultiLineString": lambda c: [(pt[0], pt[1]) for ligne in c for pt in ligne],
    "MultiPolygon": lambda c: [(pt[0], pt[1]) for poly in c for pt in poly[0]],
}


# Exceptions metier : numeros d'affaire pour lesquels les controles d'emprise DR
# sont entierement ignores (aucune verification, aucune anomalie). Le numero
# ci-dessous exclut par egalite exacte ; les prefixes par debut de chaine.
NUMERO_AFFAIRE_EXCLU: str = "12345678"
PREFIXES_AFFAIRE_EXCLUS: tuple[str, ...] = ("OSR", "osr")


# ---------------------------------------------------------------------------
# Referentiel DR
# ---------------------------------------------------------------------------


def affaire_exclue_du_controle(numero_affaire: str) -> bool:
    """Determine si le numero d'affaire exclut totalement les controles d'emprise.

    Regle de gestion : le controle appelant est entierement ignore (aucune
    verification, aucune anomalie generee) dans l'un des cas suivants :
    - le numero d'affaire est exactement egal a NUMERO_AFFAIRE_EXCLU (12345678) ;
    - le numero d'affaire commence par l'un des PREFIXES_AFFAIRE_EXCLUS (OSR / osr).

    Ces numeros ne sont pas resolvables dans le referentiel DR : les traiter
    normalement produirait une erreur de format plutot qu'un controle ignore.

    Dans tous les autres cas, retourne False.
    """
    # Normalise les espaces de bord, coherent avec extraire_prefixe.
    valeur = numero_affaire.strip()
    if valeur == NUMERO_AFFAIRE_EXCLU:
        return True
    # str.startswith accepte un tuple : OSR et osr sont testes en un seul appel.
    return valeur.startswith(PREFIXES_AFFAIRE_EXCLUS)


def extraire_prefixe(numero: str) -> tuple[str | None, str | None, str | None]:
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


def construire_index(
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
    prefixe, champ, erreur = extraire_prefixe(numero)
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


def charger_references(chemin: str) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Charge la liste des references DR depuis reference_dr.json."""
    if not os.path.isfile(chemin):
        return None, f"Fichier de references introuvable : {chemin}"
    try:
        with open(chemin, encoding="utf-8") as fichier:
            return json.load(fichier), None
    except (json.JSONDecodeError, OSError):
        return None, f"Impossible de lire le fichier de references : {chemin}"


# ---------------------------------------------------------------------------
# Emprises geographiques
# ---------------------------------------------------------------------------


def calculer_bbox(anneau: list[list[float]]) -> tuple[float, float, float, float]:
    """Calcule la bounding box d'un anneau pour le filtrage spatial rapide."""
    xs = [p[0] for p in anneau]
    ys = [p[1] for p in anneau]
    return min(xs), min(ys), max(xs), max(ys)


def _polygones_de_geometrie(geometrie: dict[str, Any] | None) -> list[list[list[list[float]]]]:
    """Retourne la liste des polygones d'une geometrie d'emprise.

    Un Polygon donne un seul element, un MultiPolygon autant que de parties.
    Les DR insulaires ou discontinues (Alpes, Auvergne...) sont stockees en
    MultiPolygon : les ignorer priverait le controle de leur emprise.
    """
    if geometrie is None:
        return []
    type_geometrie = geometrie.get("type")
    coordonnees = geometrie.get("coordinates")
    if not coordonnees:
        return []
    if type_geometrie == "Polygon":
        return [coordonnees]
    if type_geometrie == "MultiPolygon":
        return list(coordonnees)
    return []


def charger_emprises_dr(
    chemin: str,
    repertoires: set[str],
) -> tuple[list[dict[str, Any]], str | None]:
    """Charge les emprises DR correspondant aux codes repertoire demandes.

    Chaque polygone donne une entree {code, coordonnees, bbox} : la bbox
    precalculee optimise les tests de containment (filtrage rapide avant le Ray
    Casting complet). La comparaison des codes DR est insensible a la casse.
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
        for polygone in _polygones_de_geometrie(feature.get("geometry")):
            emprises.append(
                {
                    "code": props.get("code_dr_oa"),
                    "coordonnees": polygone,
                    "bbox": calculer_bbox(polygone[0]),
                }
            )

    if not emprises:
        codes = ", ".join(sorted(repertoires))
        return [], f"Aucune emprise trouvee pour les codes DR : {codes}"

    return emprises, None


def resoudre_emprises_affaire(numero_affaire: str) -> tuple[list[dict[str, Any]], str, str | None]:
    """Resout un numero d'affaire vers les emprises DR a controler.

    Enchaine les trois etapes du referentiel : chargement de reference_dr.json,
    resolution du numero vers un ou plusieurs codes repertoire, puis chargement
    des emprises geographiques correspondantes.

    Retourne (emprises, codes_dr, erreur). En cas d'echec de l'une des etapes,
    les emprises sont vides et le message d'erreur est renseigne.
    """
    references, erreur = charger_references(CHEMIN_REFERENCE_DR)
    if references is None or erreur is not None:
        return [], "", erreur

    index_trigramme, index_dossier = construire_index(references)

    repertoires, erreur = resoudre_repertoires(numero_affaire, index_trigramme, index_dossier)
    if repertoires is None or erreur is not None:
        return [], "", erreur

    emprises, erreur = charger_emprises_dr(CHEMIN_EMPRISE_DR, repertoires)
    if erreur is not None:
        return [], "", erreur

    return emprises, ", ".join(sorted(repertoires)), None


# ---------------------------------------------------------------------------
# Test de containment planimetrique
# ---------------------------------------------------------------------------


def point_dans_anneau(x: float, y: float, anneau: list[list[float]]) -> bool:
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


def point_dans_polygon(x: float, y: float, coordonnees: list[list[list[float]]]) -> bool:
    """Teste si (x, y) est dans un Polygon (anneau exterieur moins les trous)."""
    if not point_dans_anneau(x, y, coordonnees[0]):
        return False
    return all(not point_dans_anneau(x, y, trou) for trou in coordonnees[1:])


def point_dans_emprise(x: float, y: float, emprise: dict[str, Any]) -> bool:
    """Teste si (x, y) est dans une emprise DR, avec filtrage bbox preliminaire."""
    xmin, ymin, xmax, ymax = emprise["bbox"]
    if x < xmin or x > xmax or y < ymin or y > ymax:
        return False
    return point_dans_polygon(x, y, emprise["coordonnees"])


def point_dans_emprises(x: float, y: float, emprises: list[dict[str, Any]]) -> bool:
    """Retourne True si (x, y) est dans au moins une des emprises autorisees."""
    return any(point_dans_emprise(x, y, e) for e in emprises)


# ---------------------------------------------------------------------------
# Reprojection et point representatif
# ---------------------------------------------------------------------------


def extraire_nom_crs(collection: dict[str, Any]) -> str | None:
    """Extrait le nom textuel du CRS depuis une FeatureCollection."""
    crs = collection.get("crs")
    if crs is None:
        return None
    return (crs.get("properties") or {}).get("name") or None


def creer_transformateur(nom_crs: str | None) -> Transformer | None:
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


def extraire_point_representatif(geometrie: dict[str, Any]) -> tuple[float, float] | None:
    """Calcule le centroide d'une geometrie comme point representatif.

    Retourne None si la geometrie est vide ou de type non reconnu.
    """
    coordonnees = geometrie.get("coordinates")
    if coordonnees is None:
        return None
    extracteur = EXTRACTEURS_XY.get(geometrie.get("type", ""))
    if extracteur is None:
        return None
    points: list[tuple[float, float]] = extracteur(coordonnees)
    if not points:
        return None
    n = len(points)
    return sum(p[0] for p in points) / n, sum(p[1] for p in points) / n


def appliquer_transformation(
    x: float,
    y: float,
    transformateur: Transformer | None,
) -> tuple[float, float]:
    """Applique la reprojection vers EPSG:2154 si un transformateur est fourni."""
    if transformateur is None:
        return x, y
    xt, yt = transformateur.transform(x, y)
    return float(xt), float(yt)
