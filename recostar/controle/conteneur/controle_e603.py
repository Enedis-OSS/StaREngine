"""
Controle E603 : conformite des caracteristiques de poteau au catalogue.

Transpose le principe du controle E600 aux entites RPD_Support_Reco : verifier
que les valeurs saisies forment une combinaison complete et valide du catalogue
de reference des caracteristiques de poteau :

    recostar/referentiels/supports/poteau-catalogue-mapping.json

Correspondance entre les axes du catalogue et les champs du GeoJSON — les noms
different, le mapping est donc explicite :

    catalogue « classes »  <-  RPD_Support_Reco.Classe_href
    catalogue « efforts »  <-  RPD_Support_Reco.Effort      (+ Effort_uom)
    catalogue « hauteurs » <-  RPD_Support_Reco.HauteurPoteau (+ HauteurPoteau_uom)
    discriminant           <-  RPD_Support_Reco.Matiere_href

Filtrage par matiere (cle du controle) :
  Le catalogue ne fournit pas de liste de combinaisons ; il declare, pour chaque
  matiere, les valeurs admises sur chacun des trois axes — c'est le « filtrage
  dynamique par matiere » annonce par sa propre note de version. Une combinaison
  valide est donc un triplet dont les trois valeurs appartiennent aux listes de
  la matiere du poteau. Les listes de premier niveau (`classes`, `efforts`,
  `hauteurs`) sont l'union des trois matieres : les utiliser reviendrait a
  accepter une classe bois sur un poteau beton. Seul `correspondancesParMatiere`
  est indexe.

Perimetre :
  - Entites RPD_Support_Reco au Statut UnderCommissionning, comme E600 pour les
    jonctions.
  - Compatible RecoStaR V1.0 et V1.1 : champs identiques, catalogue independant
    de la version.

Regles de gestion (une anomalie par regle enfreinte, cumul possible) :
  - matiere_hors_catalogue  : la Matiere du support n'est couverte par aucune
                              matiere du catalogue (« Autre », valeur absente ou
                              inconnue). Les trois axes ne sont alors pas
                              evaluables, faute de listes de reference ;
  - classe_non_referencee   : la Classe n'existe pas au catalogue pour cette
                              matiere ;
  - effort_non_reference    : l'Effort n'existe pas au catalogue pour cette
                              matiere ;
  - hauteur_non_referencee  : la Hauteur n'existe pas au catalogue pour cette
                              matiere.

Une valeur non renseignee ne peut correspondre a aucune entree : elle est
signalee par l'anomalie « non reference » correspondante, la valeur brute (null)
etant reportee dans le fichier d'ecarts. C'est ainsi qu'une combinaison
incomplete est signalee, meme convention qu'E600 pour Fabricant et Modele.

Unites (indispensable) :
  Effort et HauteurPoteau sont des `gml:MeasureType` : leur valeur n'a de sens
  qu'accompagnee de son unite, portee par Effort_uom et HauteurPoteau_uom. Le
  catalogue exprime les efforts en kN et les hauteurs en metres. Les mesures
  sont donc converties dans l'unite du catalogue avant comparaison. Une unite
  absente est interpretee comme celle du catalogue (valeur par defaut declaree
  au format GeoJSON) ; une unite inconnue rend la mesure ininterpretable, donc
  non referencee.

Normalisation textuelle :
  Matiere et Classe sont comparees normalisees (casse ignoree, suites d'espaces
  repliees), meme convention qu'E600.

Priorite : majeur.

Usage CLI :
    python controle_e603.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e603_poteau_caracteristiques_non_referencees.geojson
"""

import argparse
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Chargement des sources et normalisation textuelle mutualises avec E600 : les
# deux controles confrontent des saisies GeoJSON a un catalogue de reference.
from controle_e600 import _charger_features, normaliser_valeur
from utils_geojson import (
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Fichier source
FICHIER_SUPPORT: str = "RPD_Support_Reco.geojson"

# Catalogue de reference, resolu depuis la position du module
# (.../recostar/controle/conteneur/ -> .../recostar/referentiels/supports/)
CHEMIN_CATALOGUE: str = str(Path(__file__).parents[2] / "referentiels" / "supports" / "poteau-catalogue-mapping.json")

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e603_poteau_caracteristiques_non_referencees.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E603"

# Types d'anomalie produits par ce controle
TYPE_MATIERE_HORS_CATALOGUE: str = "matiere_hors_catalogue"
TYPE_CLASSE_NON_REFERENCEE: str = "classe_non_referencee"
TYPE_EFFORT_NON_REFERENCE: str = "effort_non_reference"
TYPE_HAUTEUR_NON_REFERENCEE: str = "hauteur_non_referencee"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    TYPE_MATIERE_HORS_CATALOGUE: ("La Matiere du support n'est couverte par aucune matière du catalogue."),
    TYPE_CLASSE_NON_REFERENCEE: ("La Classe du support n'est pas référencée au catalogue pour cette matière."),
    TYPE_EFFORT_NON_REFERENCE: ("L'Effort du support n'est pas référencé au catalogue pour cette matière."),
    TYPE_HAUTEUR_NON_REFERENCEE: ("La Hauteur du support n'est pas référencée au catalogue pour cette matière."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_support",),
)

# Niveau de priorite affecte a toutes les anomalies. Majeur : l'ecart est
# signale et compte dans le rapport, mais ne declasse pas la famille
# (cf. PRIORITES_DECLASSANTES dans synthese_controles).
PRIORITE_ANOMALIE: str = "majeur"

# Noms des champs dans les proprietes des features
CHAMP_STATUT: str = "Statut"
CHAMP_MATIERE: str = "Matiere_href"
CHAMP_CLASSE: str = "Classe_href"
CHAMP_EFFORT: str = "Effort"
CHAMP_EFFORT_UOM: str = "Effort_uom"
CHAMP_HAUTEUR: str = "HauteurPoteau"
CHAMP_HAUTEUR_UOM: str = "HauteurPoteau_uom"

# Statut des entites a controler
STATUT_CONTROLE: str = "UnderCommissionning"

# Cles du catalogue de reference
CLE_CORRESPONDANCES: str = "correspondancesParMatiere"
CLE_CLASSES: str = "classes"
CLE_EFFORTS: str = "efforts"
CLE_HAUTEURS: str = "hauteurs"

# Facteurs de conversion vers l'unite du catalogue, indexes par unite normalisee.
# Le catalogue exprime les efforts en kN et les hauteurs en metres.
UOM_EFFORT_CATALOGUE: str = "kn"
UOM_HAUTEUR_CATALOGUE: str = "m"
FACTEURS_EFFORT: dict[str, float] = {"kn": 1.0, "dan": 0.01, "n": 0.001}
FACTEURS_HAUTEUR: dict[str, float] = {"m": 1.0, "cm": 0.01, "mm": 0.001}

# Nombre de decimales retenues pour comparer une mesure au catalogue. Les
# efforts y sont exprimes a deux decimales ; trois absorbent le bruit de la
# conversion d'unite sans jamais confondre deux valeurs du catalogue, dont le
# plus petit ecart est de 5 centiemes de kN.
PRECISION_MESURE: int = 3


@dataclass(frozen=True, slots=True)
class CataloguePoteau:
    """Index normalise du catalogue des caracteristiques de poteau.

    Les trois axes sont indexes **par matiere** : c'est la matiere qui restreint
    les valeurs admises. Toutes les structures reposent sur des `frozenset`, le
    controle effectuant un test d'appartenance par axe et par support, en O(1).
    """

    classes_par_matiere: Mapping[str, frozenset[str]]
    efforts_par_matiere: Mapping[str, frozenset[float]]
    hauteurs_par_matiere: Mapping[str, frozenset[float]]

    @property
    def matieres(self) -> frozenset[str]:
        """Matieres couvertes par le catalogue."""
        return frozenset(self.classes_par_matiere)


@dataclass(frozen=True, slots=True)
class CaracteristiquesPoteau:
    """Caracteristiques brutes d'un support, telles que saisies.

    Les valeurs ne sont ni converties ni normalisees : le classement s'en charge,
    et le fichier d'ecarts doit restituer ce que la donnee contient reellement.
    """

    matiere: Any
    classe: Any
    effort: Any
    effort_uom: Any
    hauteur: Any
    hauteur_uom: Any


def caracteristiques_depuis_proprietes(proprietes: Mapping[str, Any]) -> CaracteristiquesPoteau:
    """Extrait les caracteristiques controlees des proprietes d'une feature."""
    return CaracteristiquesPoteau(
        proprietes.get(CHAMP_MATIERE),
        proprietes.get(CHAMP_CLASSE),
        proprietes.get(CHAMP_EFFORT),
        proprietes.get(CHAMP_EFFORT_UOM),
        proprietes.get(CHAMP_HAUTEUR),
        proprietes.get(CHAMP_HAUTEUR_UOM),
    )


# ---------------------------------------------------------------------------
# Normalisation des mesures
# ---------------------------------------------------------------------------


def normaliser_mesure(
    valeur: Any,
    uom: Any,
    facteurs: Mapping[str, float],
    uom_par_defaut: str,
) -> float | None:
    """Convertit une mesure dans l'unite du catalogue et l'arrondit.

    Retourne None lorsque la mesure est inexploitable : valeur absente ou non
    numerique, ou unite inconnue. Une unite absente est interpretee comme celle
    du catalogue, valeur par defaut declaree au format GeoJSON (`kN`, `m`).

    L'unite ne peut pas etre ignoree : Effort et HauteurPoteau sont des
    `gml:MeasureType`, dont la valeur n'a de sens qu'accompagnee de son uom.
    """
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    unite = normaliser_valeur(uom) or uom_par_defaut
    facteur = facteurs.get(unite)
    if facteur is None:
        return None
    return round(float(valeur) * facteur, PRECISION_MESURE)


def _normaliser_mesure_referentiel(valeur: Any) -> float | None:
    """Convertit une valeur d'axe du catalogue en mesure comparable.

    Les axes numeriques du catalogue sont serialises en chaines (« 4.00 », « 12 »)
    et deja exprimes dans son unite : seule la conversion en flottant arrondi est
    necessaire.
    """
    try:
        return round(float(str(valeur).strip()), PRECISION_MESURE)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Chargement du catalogue
# ---------------------------------------------------------------------------


def _indexer_axe_textuel(valeurs: Any) -> frozenset[str]:
    """Indexe un axe textuel du catalogue, normalise."""
    if not isinstance(valeurs, list):
        return frozenset()
    return frozenset(normalisee for valeur in valeurs if (normalisee := normaliser_valeur(valeur)) is not None)


def _indexer_axe_mesure(valeurs: Any) -> frozenset[float]:
    """Indexe un axe numerique du catalogue, converti en mesures arrondies."""
    if not isinstance(valeurs, list):
        return frozenset()
    return frozenset(mesure for valeur in valeurs if (mesure := _normaliser_mesure_referentiel(valeur)) is not None)


def _indexer_axes_matiere(axes: Any) -> tuple[frozenset[str], frozenset[float], frozenset[float]] | None:
    """Indexe les trois axes d'une matiere du catalogue.

    Retourne None si la matiere est malformee ou si l'un de ses axes est vide :
    elle ne permettrait alors de valider aucune combinaison complete et rendrait
    tous ses supports non conformes sur cet axe, sans que la donnee soit en cause.
    """
    if not isinstance(axes, dict):
        return None
    classes = _indexer_axe_textuel(axes.get(CLE_CLASSES))
    efforts = _indexer_axe_mesure(axes.get(CLE_EFFORTS))
    hauteurs = _indexer_axe_mesure(axes.get(CLE_HAUTEURS))
    if not (classes and efforts and hauteurs):
        return None
    return classes, efforts, hauteurs


def _construire_catalogue(donnees: Any) -> CataloguePoteau | None:
    """Construit l'index normalise depuis le contenu JSON du catalogue.

    Retourne None si aucune matiere exploitable n'est declaree (voir
    `_indexer_axes_matiere` pour le rejet d'une matiere incomplete).
    """
    if not isinstance(donnees, dict):
        return None
    correspondances = donnees.get(CLE_CORRESPONDANCES)
    if not isinstance(correspondances, dict):
        return None

    classes: dict[str, frozenset[str]] = {}
    efforts: dict[str, frozenset[float]] = {}
    hauteurs: dict[str, frozenset[float]] = {}
    for matiere, axes in correspondances.items():
        cle = normaliser_valeur(matiere)
        indexes = _indexer_axes_matiere(axes)
        if cle is None or indexes is None:
            continue
        classes[cle], efforts[cle], hauteurs[cle] = indexes

    if not classes:
        return None
    return CataloguePoteau(classes, efforts, hauteurs)


def charger_catalogue(chemin: str) -> tuple[CataloguePoteau | None, str | None]:
    """Charge le catalogue une seule fois et construit son index normalise.

    Retourne (catalogue, erreur). Un catalogue absent, illisible ou vide est une
    erreur bloquante : sans reference, aucune conclusion ne peut etre tiree des
    caracteristiques du support. Meme convention qu'E600.
    """
    if not os.path.isfile(chemin):
        return None, f"Catalogue introuvable : {chemin}"
    try:
        with open(chemin, encoding="utf-8") as fichier:
            donnees = json.load(fichier)
    except (json.JSONDecodeError, OSError):
        return None, f"Catalogue illisible : {chemin}"
    catalogue = _construire_catalogue(donnees)
    if catalogue is None:
        return None, f"Catalogue vide ou invalide : {chemin}"
    return catalogue, None


# ---------------------------------------------------------------------------
# Regles metier (fonctions pures, testables sans I/O)
# ---------------------------------------------------------------------------


def est_a_controler(proprietes: Mapping[str, Any]) -> bool:
    """Indique si un support entre dans le perimetre du controle."""
    return proprietes.get(CHAMP_STATUT) == STATUT_CONTROLE


def classifier_support(
    caracteristiques: CaracteristiquesPoteau,
    catalogue: CataloguePoteau,
) -> list[str]:
    """Retourne les codes d'anomalie du support au regard du catalogue.

    Une matiere hors catalogue court-circuite les autres regles : sans listes de
    reference, la classe, l'effort et la hauteur ne sont pas evaluables, et les
    signaler produirait trois anomalies redondantes et trompeuses. Meme parti
    qu'E600 pour un domaine de tension inconnu.

    Les trois axes sont ensuite evalues independamment : ce sont trois valeurs a
    corriger distinctement, elles cumulent donc leurs anomalies.
    """
    matiere = normaliser_valeur(caracteristiques.matiere)
    if matiere is None or matiere not in catalogue.classes_par_matiere:
        return [TYPE_MATIERE_HORS_CATALOGUE]

    anomalies: list[str] = []
    classe = normaliser_valeur(caracteristiques.classe)
    if classe is None or classe not in catalogue.classes_par_matiere[matiere]:
        anomalies.append(TYPE_CLASSE_NON_REFERENCEE)

    effort = normaliser_mesure(
        caracteristiques.effort, caracteristiques.effort_uom, FACTEURS_EFFORT, UOM_EFFORT_CATALOGUE
    )
    if effort is None or effort not in catalogue.efforts_par_matiere[matiere]:
        anomalies.append(TYPE_EFFORT_NON_REFERENCE)

    hauteur = normaliser_mesure(
        caracteristiques.hauteur, caracteristiques.hauteur_uom, FACTEURS_HAUTEUR, UOM_HAUTEUR_CATALOGUE
    )
    if hauteur is None or hauteur not in catalogue.hauteurs_par_matiere[matiere]:
        anomalies.append(TYPE_HAUTEUR_NON_REFERENCEE)

    return anomalies


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies(
    features: list[dict[str, Any]],
    catalogue: CataloguePoteau,
) -> list[dict[str, Any]]:
    """Detecte les supports dont les caracteristiques sortent du catalogue.

    Seuls les supports au statut UnderCommissionning sont controles. Un support
    peut porter plusieurs anomalies : classe, effort et hauteur sont des defauts
    distincts.
    """
    anomalies: list[dict[str, Any]] = []
    classifier = classifier_support  # alias local (boucle principale)
    for feature in features:
        proprietes = feature.get("properties") or {}
        if not est_a_controler(proprietes):
            continue
        caracteristiques = caracteristiques_depuis_proprietes(proprietes)
        geometrie = feature.get("geometry")
        id_support = obtenir_id_feature(feature)
        anomalies.extend(
            {
                "type_anomalie": type_anomalie,
                "id_support": id_support,
                "matiere": caracteristiques.matiere,
                "classe": caracteristiques.classe,
                "effort": caracteristiques.effort,
                "effort_uom": caracteristiques.effort_uom,
                "hauteur": caracteristiques.hauteur,
                "hauteur_uom": caracteristiques.hauteur_uom,
                "geometrie": geometrie,
            }
            for type_anomalie in classifier(caracteristiques, catalogue)
        )
    return anomalies


def compter_supports_a_controler(features: list[dict[str, Any]]) -> int:
    """Compte les supports entrant dans le perimetre du controle."""
    return sum(1 for feature in features if est_a_controler(feature.get("properties") or {}))


def compter_supports_non_conformes(anomalies: list[dict[str, Any]]) -> int:
    """Compte les supports distincts portant au moins une anomalie."""
    return len({anomalie["id_support"] for anomalie in anomalies})


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des caracteristiques non referencees.

    La geometrie de chaque feature est le Point du support concerne. Les unites
    sont exposees a cote des mesures : sans elles, une valeur d'effort n'est pas
    interpretable, et c'est souvent l'unite qui est en cause.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": FICHIER_SUPPORT,
                "id_support": a["id_support"],
                "matiere": a["matiere"],
                "classe": a["classe"],
                "effort": a["effort"],
                "effort_uom": a["effort_uom"],
                "hauteur": a["hauteur"],
                "hauteur_uom": a["hauteur_uom"],
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


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle des caracteristiques de poteau en mode CLI.

    Charge le catalogue une seule fois, controle chaque support au statut
    UnderCommissionning et ecrit le fichier d'ecarts GeoJSON. Un catalogue
    indisponible est une erreur bloquante ; l'absence du fichier support est
    signalee sans bloquer.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    catalogue, erreur = charger_catalogue(CHEMIN_CATALOGUE)
    if catalogue is None:
        return {"succes": False, "erreur": erreur}

    features, crs, support_absent = _charger_features(repertoire_resolu, FICHIER_SUPPORT)

    anomalies = detecter_anomalies(features, catalogue)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_anomalies_par_type(anomalies),
        "nombre_supports_analyses": len(features),
        "nombre_supports_controles": compter_supports_a_controler(features),
        "nombre_supports_non_conformes": compter_supports_non_conformes(anomalies),
        "matieres_catalogue": sorted(catalogue.matieres),
        "fichier_support_absent": support_absent,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle des caracteristiques de poteau."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E603 : conformite des caracteristiques (Classe, Effort, "
            "Hauteur) des RPD_Support_Reco au statut UnderCommissionning avec le "
            "catalogue poteau-catalogue-mapping.json, filtre par matiere."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON",
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
