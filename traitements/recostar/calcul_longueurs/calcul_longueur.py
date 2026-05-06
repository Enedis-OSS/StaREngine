"""
Calcul des longueurs geographiques (3D) et electriques des cables.

Exploite les GeoJSON du dossier recolement pour calculer la longueur 3D
de chaque cable electrique, puis applique les corrections de longueur
electrique selon le domaine de tension (HTA/BT) et les entites connectees
aux extremites (remontee aero-souterraine, poste electrique, coffret).

Usage : python calcul_longueur.py --chemin-projet <chemin>
Sortie : fichier JSON dans le dossier rapport/ du projet.
"""

import argparse
import json
import math
import os
import sys
from typing import Any

# --- Fonctions utilitaires ---


def lire_geojson(chemin: str) -> dict[str, Any] | None:
    """Lit un fichier GeoJSON et retourne la collection, ou None si inaccessible."""
    if not os.path.isfile(chemin):
        return None
    with open(chemin, encoding="utf-8") as fichier:
        return json.load(fichier)


def obtenir_chemin_recolement(chemin_projet: str) -> str:
    """Retourne le chemin du dossier recolement/ d'un projet."""
    return os.path.join(chemin_projet, "recolement")


def obtenir_id_feature(feature: dict[str, Any]) -> str | None:
    """Extrait l'identifiant d'une feature GeoJSON depuis ses proprietes."""
    id_val = feature.get("properties", {}).get("id")
    if id_val is None or (isinstance(id_val, str) and not id_val.strip()):
        return None
    return str(id_val)


def extraire_ids_cables_href(feature: dict[str, Any]) -> set[str]:
    """Extrait les identifiants de cables depuis le champ cables_href (separes par virgule)."""
    href = feature.get("properties", {}).get("cables_href")
    if not isinstance(href, str) or not href.strip():
        return set()
    return {cid.strip() for cid in href.split(",") if cid.strip()}


# --- Constantes fichiers ---

FICHIER_CABLES: str = "RPD_CableElectrique_Reco.geojson"
FICHIER_JONCTIONS: str = "RPD_Jonction_Reco.geojson"
FICHIER_POSTES: str = "RPD_PosteElectrique_Reco.geojson"
FICHIER_AERIEN: str = "RPD_Aerien_Reco.geojson"

# Chemin par defaut du referentiel (relatif a la racine du depot)
CHEMIN_REFERENTIEL_RELATIF: tuple[str, ...] = (
    "referentiels",
    "recostar",
    "recostar_referentiels_V1_1.json",
)

# Nom du type enumeratif decrivant le statut dans le referentiel
TYPE_STATUT_REFERENTIEL: str = "ConditionOfFacilityValueReco"

# Fichiers contenant les noeuds rattaches aux coffrets
FICHIERS_NOEUDS_COFFRETS: tuple[str, ...] = (
    "RPD_PointDeComptage_Reco.geojson",
    "RPD_CoupeCircuitAFusibles_Reco.geojson",
    "RPD_JeuBarres_Reco.geojson",
    "RPD_SupportModules_Reco.geojson",
    "RPD_ModuleRaccordement_Reco.geojson",
    "RPD_OuvrageCollectifBranchement_Reco.geojson",
    "RPD_Terre_Reco.geojson",
)

# --- Constantes metier ---

# Valeur du champ TypeJonction pour une remontee aero-souterraine
TYPE_JONCTION_RAS: str = "RemonteeAeroSouterraine"

# Types d'entites pour le calcul des corrections
TYPE_RAS: str = "remontee_aero_souterraine"
TYPE_POSTE: str = "poste"
TYPE_COFFRET: str = "coffret"

# Corrections de longueur electrique par domaine de tension (metres)
CORRECTIONS: dict[str, dict[str, float]] = {
    "HTA": {
        TYPE_RAS: 11.0,
        TYPE_POSTE: 5.0,
    },
    "BT": {
        TYPE_RAS: 11.0,
        TYPE_POSTE: 3.0,
        TYPE_COFFRET: 1.0,
    },
}

# Isolants declenchant une correction aerienne par taux
ISOLANTS_NU: frozenset[str] = frozenset({"Nu"})
ISOLANTS_ISOLES: frozenset[str] = frozenset({"Reticulee", "Thermodurcissable"})

# Taux de correction aerienne (pourcentage de la longueur geographique)
# par domaine de tension et categorie d'isolant
CORRECTIONS_AERIEN: dict[str, dict[str, float]] = {
    "BT": {
        "Nu": 0.04,
        "Isole": 0.05,
    },
    "HTA": {
        "Nu": 0.03,
        "Isole": 0.05,
    },
}


class EntiteReferencee:
    """Entite du reseau referencant un cable via cables_href."""

    __slots__ = ("coordonnees", "type_entite")

    def __init__(self, coordonnees: list[float], type_entite: str) -> None:
        self.coordonnees = coordonnees
        self.type_entite = type_entite


# --- Fonctions de chargement du referentiel ---


def _resoudre_chemin_referentiel(chemin_explicite: str | None = None) -> str:
    """Resout le chemin du referentiel : argument explicite ou chemin par defaut.

    Le chemin par defaut remonte depuis le repertoire du script courant
    jusqu'a la racine du depot pour trouver le fichier referentiel.
    """
    if chemin_explicite is not None:
        return chemin_explicite
    racine = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        candidat = os.path.join(racine, *CHEMIN_REFERENTIEL_RELATIF)
        if os.path.isfile(candidat):
            return candidat
        racine = os.path.dirname(racine)
    return os.path.join(*CHEMIN_REFERENTIEL_RELATIF)


def construire_index_statuts(
    chemin_referentiel: str | None = None,
) -> dict[str, str]:
    """Construit un dictionnaire valeur -> alias pour les statuts de cable.

    Lit le type ConditionOfFacilityValueReco dans l'objet Cable du referentiel.
    Retourne un dict vide si le fichier ou la structure est absente.
    """
    chemin = _resoudre_chemin_referentiel(chemin_referentiel)
    if not os.path.isfile(chemin):
        return {}

    with open(chemin, encoding="utf-8") as fichier:
        referentiel = json.load(fichier)

    cable_types = (
        referentiel.get("objets", {})
        .get("Câble", {})
        .get("types", {})
        .get(TYPE_STATUT_REFERENTIEL, {})
    )

    return {
        entree["valeur"]: entree["alias"]
        for entree in cable_types.get("valeurs", [])
        if "valeur" in entree and "alias" in entree
    }


# --- Fonctions de calcul geometrique ---

# Tolerance absolue pour considerer une coordonnee Z comme nulle (marqueur Z=0.0)
_TOLERANCE_Z: float = 1e-9


def _est_valeur_nulle(valeur: float) -> bool:
    """Verifie si une valeur flottante est consideree comme nulle (Z=0.0)."""
    return abs(valeur) < _TOLERANCE_Z


def _corriger_z_nuls(coordonnees: list[list[float]]) -> list[float]:
    """Corrige les valeurs Z nulles en les remplacant par le Z valide le plus proche.

    Parcours avant puis arriere pour propager les valeurs Z valides (non nulles)
    vers les sommets dont Z vaut 0.0. Si aucun Z valide n'est trouve, la valeur
    reste a 0.0.
    """
    nb = len(coordonnees)
    z_corrige = [coord[2] if len(coord) > 2 else 0.0 for coord in coordonnees]

    _est_z_nul = _est_valeur_nulle

    # Propagation avant : remplacer Z=0.0 par le dernier Z valide rencontre
    dernier_z_valide = 0.0
    for i in range(nb):
        if not _est_z_nul(z_corrige[i]):
            dernier_z_valide = z_corrige[i]
        elif not _est_z_nul(dernier_z_valide):
            z_corrige[i] = dernier_z_valide

    # Propagation arriere : combler les Z=0.0 restants en debut de polyligne
    dernier_z_valide = 0.0
    for i in range(nb - 1, -1, -1):
        if not _est_z_nul(z_corrige[i]):
            dernier_z_valide = z_corrige[i]
        elif not _est_z_nul(dernier_z_valide):
            z_corrige[i] = dernier_z_valide

    return z_corrige


def _calculer_longueur_3d(coordonnees: list[list[float]]) -> float:
    """Calcule la longueur 3D d'une polyligne en sommant les distances entre sommets.

    Les sommets dont la coordonnee Z vaut 0.0 voient leur Z corrige par
    propagation du Z valide le plus proche (precedent ou suivant) afin
    d'eviter les longueurs aberrantes causees par des valeurs Z manquantes.
    """
    longueur = 0.0
    sqrt = math.sqrt
    nb_sommets = len(coordonnees)
    z_corrige = _corriger_z_nuls(coordonnees)

    for i in range(1, nb_sommets):
        precedent = coordonnees[i - 1]
        courant = coordonnees[i]
        dx = courant[0] - precedent[0]
        dy = courant[1] - precedent[1]
        dz = z_corrige[i] - z_corrige[i - 1]
        longueur += sqrt(dx * dx + dy * dy + dz * dz)

    return longueur


def _calculer_centroide(anneau: list[list[float]]) -> list[float]:
    """Calcule le centroide d'un anneau de polygone par moyenne des sommets."""
    nb_points = len(anneau)
    if nb_points == 0:
        return [0.0, 0.0]

    somme_x = 0.0
    somme_y = 0.0
    for point in anneau:
        somme_x += point[0]
        somme_y += point[1]

    return [somme_x / nb_points, somme_y / nb_points]


# --- Fonctions d'extraction ---


def _extraire_coordonnees_cable(
    geometrie: dict[str, Any],
) -> list[list[list[float]]] | None:
    """Extrait les coordonnees d'un cable depuis sa geometrie.

    Gere les types LineString et MultiLineString. Retourne une liste de
    polylignes (chaque polyligne etant une liste de sommets). Pour un
    LineString, retourne une liste contenant une seule polyligne.
    Retourne None si le type de geometrie n'est pas supporte ou si les
    coordonnees sont insuffisantes.
    """
    type_geo = geometrie.get("type")
    coordonnees_brutes = geometrie.get("coordinates", [])

    if type_geo == "LineString":
        polylignes = [coordonnees_brutes]
    elif type_geo == "MultiLineString":
        polylignes = coordonnees_brutes
    else:
        return None

    # Filtrer les polylignes avec au moins 2 sommets
    polylignes_valides = [p for p in polylignes if len(p) >= 2]
    if not polylignes_valides:
        return None

    return polylignes_valides


def _extraire_position_entite(feature: dict[str, Any]) -> list[float] | None:
    """Extrait la position d'une entite (coordonnees directes ou centroide)."""
    geometrie = feature.get("geometry")
    if geometrie is None:
        return None

    type_geo = geometrie.get("type")
    coordonnees = geometrie.get("coordinates")
    if coordonnees is None:
        return None

    if type_geo == "Point":
        return coordonnees

    if type_geo == "Polygon" and len(coordonnees) > 0:
        return _calculer_centroide(coordonnees[0])

    return None


def _extraire_ids_cables(feature: dict[str, Any]) -> set[str]:
    """Extrait les identifiants de cables depuis le champ cables_href."""
    return extraire_ids_cables_href(feature)


# --- Construction de l'index des entites ---


def _ajouter_entite_a_index(
    index: dict[str, list[EntiteReferencee]],
    ids_cables: set[str],
    entite: EntiteReferencee,
) -> None:
    """Ajoute une entite a l'index pour chaque cable reference."""
    for id_cable in ids_cables:
        if id_cable not in index:
            index[id_cable] = []
        index[id_cable].append(entite)


def _indexer_jonctions_ras(
    chemin_recolement: str,
    index: dict[str, list[EntiteReferencee]],
) -> None:
    """Indexe les jonctions de type remontee aero-souterraine par cable."""
    chemin = os.path.join(chemin_recolement, FICHIER_JONCTIONS)
    collection = lire_geojson(chemin)
    if collection is None:
        return

    for feature in collection.get("features", []):
        proprietes = feature.get("properties", {})
        if proprietes.get("TypeJonction") != TYPE_JONCTION_RAS:
            continue

        coordonnees = _extraire_position_entite(feature)
        if coordonnees is None:
            continue

        ids_cables = _extraire_ids_cables(feature)
        entite = EntiteReferencee(coordonnees, TYPE_RAS)
        _ajouter_entite_a_index(index, ids_cables, entite)


def _indexer_postes(
    chemin_recolement: str,
    index: dict[str, list[EntiteReferencee]],
) -> None:
    """Indexe les postes electriques par cable."""
    chemin = os.path.join(chemin_recolement, FICHIER_POSTES)
    collection = lire_geojson(chemin)
    if collection is None:
        return

    for feature in collection.get("features", []):
        coordonnees = _extraire_position_entite(feature)
        if coordonnees is None:
            continue

        ids_cables = _extraire_ids_cables(feature)
        entite = EntiteReferencee(coordonnees, TYPE_POSTE)
        _ajouter_entite_a_index(index, ids_cables, entite)


def _indexer_noeuds_coffrets(
    chemin_recolement: str,
    index: dict[str, list[EntiteReferencee]],
) -> None:
    """Indexe les noeuds rattaches aux coffrets par cable."""
    for nom_fichier in FICHIERS_NOEUDS_COFFRETS:
        chemin = os.path.join(chemin_recolement, nom_fichier)
        collection = lire_geojson(chemin)
        if collection is None:
            continue

        for feature in collection.get("features", []):
            # Seuls les noeuds avec conteneur_href (rattaches a un coffret)
            if not feature.get("properties", {}).get("conteneur_href"):
                continue

            coordonnees = _extraire_position_entite(feature)
            if coordonnees is None:
                continue

            ids_cables = _extraire_ids_cables(feature)
            entite = EntiteReferencee(coordonnees, TYPE_COFFRET)
            _ajouter_entite_a_index(index, ids_cables, entite)


def construire_index_entites(
    chemin_recolement: str,
) -> dict[str, list[EntiteReferencee]]:
    """Construit l'index global des entites referencant chaque cable.

    Retourne un dictionnaire {id_cable: [EntiteReferencee, ...]}
    regroupant les jonctions RAS, postes et noeuds de coffrets.
    """
    index: dict[str, list[EntiteReferencee]] = {}
    _indexer_jonctions_ras(chemin_recolement, index)
    _indexer_postes(chemin_recolement, index)
    _indexer_noeuds_coffrets(chemin_recolement, index)
    return index


# --- Construction de l'ensemble des cables aeriens ---


def construire_ensemble_cables_aeriens(chemin_recolement: str) -> set[str]:
    """Construit l'ensemble des identifiants de cables associes a un cheminement aerien."""
    chemin = os.path.join(chemin_recolement, FICHIER_AERIEN)
    collection = lire_geojson(chemin)
    if collection is None:
        return set()

    ids_cables: set[str] = set()
    for feature in collection.get("features", []):
        ids_cables.update(extraire_ids_cables_href(feature))

    return ids_cables


def _obtenir_taux_correction_aerien(domaine_tension: str, isolant: str) -> float:
    """Retourne le taux de correction aerienne selon le domaine de tension et l'isolant.

    Retourne 0.0 si aucune correction ne s'applique.
    """
    corrections_domaine = CORRECTIONS_AERIEN.get(domaine_tension)
    if corrections_domaine is None:
        return 0.0

    if isolant in ISOLANTS_NU:
        return corrections_domaine.get("Nu", 0.0)

    if isolant in ISOLANTS_ISOLES:
        return corrections_domaine.get("Isole", 0.0)

    return 0.0


# --- Calcul des corrections electriques ---


def _obtenir_correction(type_entite: str, domaine_tension: str) -> float:
    """Retourne la correction en metres pour un type d'entite et un domaine de tension."""
    corrections_domaine = CORRECTIONS.get(domaine_tension)
    if corrections_domaine is None:
        return 0.0
    return corrections_domaine.get(type_entite, 0.0)


class ResultatCorrections:
    """Resultat du calcul des corrections pour les deux extremites d'un cable."""

    __slots__ = (
        "correction_depart",
        "correction_arrivee",
        "type_entite_depart",
        "type_entite_arrivee",
    )

    def __init__(self) -> None:
        self.correction_depart: float = 0.0
        self.correction_arrivee: float = 0.0
        self.type_entite_depart: str = ""
        self.type_entite_arrivee: str = ""


def calculer_corrections_cable(
    coords_depart: list[float],
    coords_arrivee: list[float],
    entites: list[EntiteReferencee],
    domaine_tension: str,
) -> ResultatCorrections:
    """Calcule les corrections electriques pour les deux extremites d'un cable.

    Chaque entite est assignee a l'extremite la plus proche.
    En cas de conflit sur une meme extremite, la correction maximale est retenue.
    Retourne egalement le type d'entite associe a chaque extremite.
    """
    resultat = ResultatCorrections()

    hypot = math.hypot
    obtenir = _obtenir_correction

    for entite in entites:
        cx, cy = entite.coordonnees[0], entite.coordonnees[1]

        dist_depart = hypot(coords_depart[0] - cx, coords_depart[1] - cy)
        dist_arrivee = hypot(coords_arrivee[0] - cx, coords_arrivee[1] - cy)

        correction = obtenir(entite.type_entite, domaine_tension)

        if dist_depart <= dist_arrivee:
            if correction > resultat.correction_depart:
                resultat.correction_depart = correction
                resultat.type_entite_depart = entite.type_entite
        else:
            if correction > resultat.correction_arrivee:
                resultat.correction_arrivee = correction
                resultat.type_entite_arrivee = entite.type_entite

    return resultat


# --- Analyse par cable ---


def analyser_cable(
    cable: dict[str, Any],
    index_entites: dict[str, list[EntiteReferencee]],
    cables_aeriens: set[str] | None = None,
    index_statuts: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Analyse un cable et calcule ses longueurs geographique et electrique.

    Retourne None si le cable n'a pas de geometrie LineString ou MultiLineString
    valide. Le champ statut est traduit en alias via index_statuts.
    """
    id_cable = obtenir_id_feature(cable)
    if id_cable is None:
        return None

    geometrie = cable.get("geometry", {})
    polylignes = _extraire_coordonnees_cable(geometrie)
    if polylignes is None:
        return None

    # Longueur geographique 3D (somme des sous-lignes)
    longueur_geo = sum(_calculer_longueur_3d(pl) for pl in polylignes)

    # Extremites globales du cable (premier sommet / dernier sommet)
    premier_sommet = polylignes[0][0]
    dernier_sommet = polylignes[-1][-1]

    # Domaine de tension du cable
    proprietes = cable.get("properties", {})
    domaine_tension = proprietes.get("DomaineTension", "")

    # Hierarchie BT (uniquement pour les cables BT)
    hierarchie_bt = proprietes.get("HierarchieBT", "")

    # Detection du caractere aerien du cable
    ensemble_aeriens = cables_aeriens if cables_aeriens is not None else set()
    est_aerien = str(id_cable) in ensemble_aeriens

    # Corrections aux extremites (Poste, Coffret, RAS) : exclues pour les cables aeriens
    corrections = ResultatCorrections()
    if not est_aerien:
        entites_liees = index_entites.get(str(id_cable), [])
        corrections = calculer_corrections_cable(
            premier_sommet, dernier_sommet, entites_liees, domaine_tension
        )

    # Correction aerienne (pourcentage de la longueur geographique)
    correction_aerien = 0.0
    taux_aerien = 0.0

    if est_aerien:
        isolant = proprietes.get("Isolant", "")
        taux_aerien = _obtenir_taux_correction_aerien(domaine_tension, isolant)
        correction_aerien = longueur_geo * taux_aerien

    # Statut du cable (alias depuis le referentiel)
    statut_brut = proprietes.get("Statut", "")
    aliases = index_statuts if index_statuts is not None else {}
    statut = aliases.get(statut_brut, statut_brut)

    longueur_electrique = (
        longueur_geo
        + corrections.correction_depart
        + corrections.correction_arrivee
        + correction_aerien
    )

    ceil = math.ceil
    return {
        "id": id_cable,
        "domaine_tension": domaine_tension,
        "hierarchie_bt": hierarchie_bt,
        "statut": statut,
        "longueur_geographique": round(longueur_geo, 1),
        "longueur_electrique": ceil(longueur_electrique),
        "correction_depart": corrections.correction_depart,
        "correction_arrivee": corrections.correction_arrivee,
        "type_entite_depart": corrections.type_entite_depart,
        "type_entite_arrivee": corrections.type_entite_arrivee,
        "correction_aerien": round(correction_aerien, 2),
        "taux_aerien": taux_aerien,
    }


# --- Point d'entree ---


def executer_calcul(
    chemin_projet: str,
    chemin_recolement: str | None = None,
    chemin_referentiel: str | None = None,
) -> dict[str, Any]:
    """Execute le calcul des longueurs sur tous les cables du projet.

    Si chemin_recolement est fourni, il est utilise directement comme repertoire
    contenant les fichiers GeoJSON. Sinon, le sous-dossier recolement/ du projet
    est utilise par defaut.
    """
    recolement = (
        chemin_recolement
        if chemin_recolement is not None
        else obtenir_chemin_recolement(chemin_projet)
    )
    chemin_cables = os.path.join(recolement, FICHIER_CABLES)

    collection = lire_geojson(chemin_cables)
    if collection is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_CABLES} introuvable ou invalide",
            "resultats": [],
        }

    cables = collection.get("features", [])

    # Construction de l'index des entites une seule fois
    index_entites = construire_index_entites(recolement)

    # Construction de l'ensemble des cables aeriens
    cables_aeriens = construire_ensemble_cables_aeriens(recolement)

    # Construction de l'index des alias de statuts
    index_statuts = construire_index_statuts(chemin_referentiel)

    resultats: list[dict[str, Any]] = []
    for cable in cables:
        resultat = analyser_cable(
            cable,
            index_entites,
            cables_aeriens,
            index_statuts,
        )
        if resultat is not None:
            resultats.append(resultat)

    return {"succes": True, "resultats": resultats}


def _ecrire_fichier_sortie(chemin_projet: str, donnees: dict[str, Any]) -> str:
    """Ecrit les resultats dans un fichier JSON dans le dossier rapport/."""
    dossier_rapport = os.path.join(chemin_projet, "rapport")
    os.makedirs(dossier_rapport, exist_ok=True)

    chemin_sortie = os.path.join(dossier_rapport, "resultats_longueurs.json")
    with open(chemin_sortie, "w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2)

    return chemin_sortie


def main() -> None:
    """Point d'entree du script de calcul des longueurs."""
    parseur = argparse.ArgumentParser(
        description="Calcul des longueurs geographiques et electriques des cables"
    )
    parseur.add_argument(
        "--chemin-projet", required=True, help="Chemin du projet RecoStaR"
    )
    arguments = parseur.parse_args()

    resultats = executer_calcul(arguments.chemin_projet)

    if resultats["succes"]:
        chemin_sortie = _ecrire_fichier_sortie(arguments.chemin_projet, resultats)
        print(f"Resultats ecrits dans {chemin_sortie}", file=sys.stderr)

    json.dump(resultats, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
