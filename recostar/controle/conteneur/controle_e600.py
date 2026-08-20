"""
Controle E600 : conformite du materiel de jonction au catalogue de reference.

Verifie que le materiel declare pour une jonction electrique correspond bien a
une entree du catalogue de reference des boites de jonction / derivation :

    recostar/referentiels/boites/catalogue-materiel-jonction.json

Chaine de references controlee (deux entites, un catalogue) :

    RPD_Jonction_Reco.materiel_href  ->  RPD_Materiel_Reco.id
    (DomaineTension porte par la jonction) + (Fabricant, Modele portes par le
    materiel)  ->  entree du catalogue

Perimetre : une entite RPD_Jonction_Reco n'est controlee que si elle remplit
les trois conditions cumulatives suivantes :
  - materiel_href est renseigne (la jonction declare un materiel) ;
  - Statut vaut UnderCommissionning ;
  - TypeJonction vaut Derivation ou Jonction.
Toute autre jonction est ignoree. En particulier, une jonction sans
materiel_href est hors perimetre : les ExtremiteReseau n'ont legitimement pas
de materiel (cf. champsFabricantModele dans jonction-mapping.json), et
l'exigence de presence du lien releve du controle de structuration.

Regles de gestion (une anomalie par regle enfreinte, cumul possible) :
  - materiel_introuvable            : materiel_href ne resout aucune entite
                                      RPD_Materiel_Reco ;
  - domaine_tension_hors_catalogue  : le DomaineTension de la jonction n'est
                                      couvert par aucune entree du catalogue
                                      (HTB, valeur absente ou inconnue) ; les
                                      valeurs du materiel ne sont alors pas
                                      evaluables ;
  - fabricant_non_reference         : le Fabricant du materiel n'existe pas
                                      dans le catalogue pour ce domaine ;
  - modele_non_reference            : le Modele du materiel n'existe pas dans
                                      le catalogue pour ce domaine ;
  - couple_fabricant_modele_non_reference : Fabricant et Modele existent
                                      separement, mais leur association n'est
                                      pas repertoriee pour ce domaine.

Un Fabricant ou un Modele non renseigne ne peut correspondre a aucune entree :
il est signale par l'anomalie « non reference » correspondante, la valeur brute
(null) etant reportee dans le fichier d'ecarts.

Normalisation (indispensable) :
  Le catalogue et l'export GeoJSON n'utilisent pas les memes conventions de
  saisie. La comparaison s'effectue sur des chaines normalisees : casse
  ignoree et suites d'espaces blancs repliees en un espace unique (semantique
  « collapse » de XSD). Les valeurs issues du GML portent les sauts de ligne du
  document source — « DDC 240-35 \nv2006 » designe le modele « DDC 240-35
  v2006 » du catalogue — qu'un simple strip laisserait diverger. Meme principe
  que le controle E502, etendu aux espaces internes.

Source de verite du catalogue :
  L'index est construit a partir de la seule liste `entrees`. Les blocs
  `fabricants`, `modeles` et `correspondancesParDomaine` en sont des vues
  derivees : les ignorer supprime tout risque de divergence si le catalogue
  evolue vers des associations non cartesiennes.

Versions : jonction et materiel ont une structure identique en RecoStaR V1.0 et
V1.1 ; le controle est agnostique de version.

Priorite : majeur.

Usage CLI :
    python controle_e600.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e600_materiel_jonction_non_reference.geojson
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils_geojson import (
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Fichiers source
FICHIER_JONCTION: str = "RPD_Jonction_Reco.geojson"
FICHIER_MATERIEL: str = "RPD_Materiel_Reco.geojson"

# Catalogue de reference, resolu depuis la position du module
# (.../recostar/controle/conteneur/ -> .../recostar/referentiels/boites/)
CHEMIN_CATALOGUE: str = str(Path(__file__).parents[2] / "referentiels" / "boites" / "catalogue-materiel-jonction.json")

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e600_materiel_jonction_non_reference.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E600"

# Types d'anomalie produits par ce controle
TYPE_MATERIEL_INTROUVABLE: str = "materiel_introuvable"
TYPE_DOMAINE_HORS_CATALOGUE: str = "domaine_tension_hors_catalogue"
TYPE_FABRICANT_NON_REFERENCE: str = "fabricant_non_reference"
TYPE_MODELE_NON_REFERENCE: str = "modele_non_reference"
TYPE_COUPLE_NON_REFERENCE: str = "couple_fabricant_modele_non_reference"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    TYPE_MATERIEL_INTROUVABLE: ("Le matériel référencé par la jonction n'existe pas dans RPD_Materiel_Reco."),
    TYPE_DOMAINE_HORS_CATALOGUE: ("Le DomaineTension de la jonction n'est couvert par aucune entrée du catalogue."),
    TYPE_FABRICANT_NON_REFERENCE: ("Le Fabricant du matériel n'est pas référencé au catalogue."),
    TYPE_MODELE_NON_REFERENCE: ("Le Modèle du matériel n'est pas référencé au catalogue pour ce domaine."),
    TYPE_COUPLE_NON_REFERENCE: ("L'association Fabricant / Modèle n'est pas référencée au catalogue."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_jonction", "id_materiel"),
)

# Niveau de priorite affecte a toutes les anomalies. Majeur : l'ecart est
# signale et compte dans le rapport, mais ne declasse pas la famille
# (cf. PRIORITES_DECLASSANTES dans synthese_controles).
PRIORITE_ANOMALIE: str = "majeur"

# Noms des champs dans les proprietes des features
CHAMP_STATUT: str = "Statut"
CHAMP_TYPE_JONCTION: str = "TypeJonction"
CHAMP_DOMAINE: str = "DomaineTension"
CHAMP_MATERIEL_HREF: str = "materiel_href"
CHAMP_FABRICANT: str = "Fabricant"
CHAMP_MODELE: str = "Modele"

# Statut des jonctions a controler
STATUT_CONTROLE: str = "UnderCommissionning"

# Types de jonction a controler (frozenset -> appartenance en O(1))
TYPES_JONCTION_CONTROLES: frozenset[str] = frozenset({"Derivation", "Jonction"})

# Cles du catalogue de reference
CLE_ENTREES: str = "entrees"
CLE_DOMAINE_ENTREE: str = "domaineTension"
CLE_FABRICANT_ENTREE: str = "fabricant"
CLE_MODELE_ENTREE: str = "modele"


@dataclass(frozen=True, slots=True)
class CatalogueMateriel:
    """Index normalise du catalogue de materiel de jonction.

    - `entrees` : triplets (domaine, fabricant, modele) valides ;
    - `fabricants_par_domaine` / `modeles_par_domaine` : vues par domaine,
      permettant de distinguer une valeur inconnue d'une association inconnue ;
    - toutes les valeurs sont normalisees (strip + minuscules).

    Les trois structures reposent sur des `frozenset` : le controle effectue un
    test d'appartenance par jonction, en O(1).
    """

    entrees: frozenset[tuple[str, str, str]]
    fabricants_par_domaine: Mapping[str, frozenset[str]]
    modeles_par_domaine: Mapping[str, frozenset[str]]

    @property
    def domaines(self) -> frozenset[str]:
        """Domaines de tension couverts par au moins une entree du catalogue."""
        return frozenset(self.fabricants_par_domaine)


# ---------------------------------------------------------------------------
# Normalisation et chargement du catalogue
# ---------------------------------------------------------------------------


def normaliser_valeur(valeur: Any) -> str | None:
    """Normalise une valeur textuelle pour la comparaison au catalogue.

    Applique la semantique « collapse » de XSD (`xs:token`) : toute suite
    d'espaces, tabulations et sauts de ligne est repliee en un espace unique,
    les bords sont supprimes, la casse est ignoree. Le repliement interne n'est
    pas cosmetique : les valeurs issues du GML portent les sauts de ligne du
    document source (« DDC 240-35 \nv2006 » pour « DDC 240-35 v2006 »), qu'un
    simple strip laisserait diverger du catalogue. Il n'introduit aucun faux
    negatif : les modeles et fabricants du catalogue restent tous distincts
    apres normalisation.

    Retourne None pour une valeur absente ou vide : aucune entree du catalogue
    ne peut lui correspondre, ce que le classement traduit en anomalie.
    """
    if valeur is None:
        return None
    texte = " ".join(str(valeur).split()).lower()
    return texte or None


def _extraire_triplet(entree: Any) -> tuple[str, str, str] | None:
    """Extrait le triplet normalise (domaine, fabricant, modele) d'une entree.

    Retourne None pour une entree malformee ou incomplete : une entree partielle
    ne decrit aucun materiel identifiable, elle est ignoree sans faire echouer
    le chargement du reste du catalogue.
    """
    if not isinstance(entree, dict):
        return None
    domaine = normaliser_valeur(entree.get(CLE_DOMAINE_ENTREE))
    fabricant = normaliser_valeur(entree.get(CLE_FABRICANT_ENTREE))
    modele = normaliser_valeur(entree.get(CLE_MODELE_ENTREE))
    if domaine is None or fabricant is None or modele is None:
        return None
    return domaine, fabricant, modele


def _construire_catalogue(donnees: Any) -> CatalogueMateriel | None:
    """Construit l'index normalise depuis le contenu JSON du catalogue.

    Retourne None si la structure ne fournit aucune entree exploitable :
    fichier vide, cle `entrees` absente ou entrees toutes incompletes.
    """
    if not isinstance(donnees, dict):
        return None
    entrees = donnees.get(CLE_ENTREES)
    if not isinstance(entrees, list):
        return None

    triplets: set[tuple[str, str, str]] = set()
    fabricants: defaultdict[str, set[str]] = defaultdict(set)
    modeles: defaultdict[str, set[str]] = defaultdict(set)
    extraire = _extraire_triplet  # alias local (boucle de chargement)
    for entree in entrees:
        triplet = extraire(entree)
        if triplet is None:
            continue
        domaine, fabricant, modele = triplet
        triplets.add(triplet)
        fabricants[domaine].add(fabricant)
        modeles[domaine].add(modele)

    if not triplets:
        return None
    return CatalogueMateriel(
        entrees=frozenset(triplets),
        fabricants_par_domaine={domaine: frozenset(valeurs) for domaine, valeurs in fabricants.items()},
        modeles_par_domaine={domaine: frozenset(valeurs) for domaine, valeurs in modeles.items()},
    )


def charger_catalogue(chemin: str) -> tuple[CatalogueMateriel | None, str | None]:
    """Charge le catalogue une seule fois et construit son index normalise.

    Retourne (catalogue, erreur). Un catalogue absent, illisible ou vide est
    une erreur bloquante : sans reference, aucune conclusion ne peut etre tiree
    des valeurs du materiel.
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
# Chargement des entites
# ---------------------------------------------------------------------------


def indexer_materiels(features: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Construit l'index {id_materiel: proprietes} des RPD_Materiel_Reco.

    L'identifiant est celui resolu par `materiel_href` cote jonction. Le
    dictionnaire assure la resolution du lien en O(1).
    """
    index: dict[str, dict[str, Any]] = {}
    for feature in features:
        id_materiel = obtenir_id_feature(feature)
        if id_materiel is None:
            continue
        index[id_materiel] = feature.get("properties") or {}
    return index


def _charger_features(repertoire: str, nom_fichier: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None, bool]:
    """Charge les features d'un GeoJSON. Retourne (features, crs, fichier_absent)."""
    chemin = os.path.join(repertoire, nom_fichier)
    collection = lire_geojson(chemin) if os.path.isfile(chemin) else None
    if collection is None:
        return [], None, True
    return collection.get("features", []), collection.get("crs"), False


# ---------------------------------------------------------------------------
# Regles metier (fonctions pures, testables sans I/O)
# ---------------------------------------------------------------------------


def est_a_controler(proprietes: Mapping[str, Any]) -> bool:
    """Indique si une jonction entre dans le perimetre du controle.

    Trois conditions cumulatives : materiel declare, Statut UnderCommissionning
    et TypeJonction parmi Derivation / Jonction.
    """
    if proprietes.get(CHAMP_STATUT) != STATUT_CONTROLE:
        return False
    if proprietes.get(CHAMP_TYPE_JONCTION) not in TYPES_JONCTION_CONTROLES:
        return False
    return normaliser_valeur(proprietes.get(CHAMP_MATERIEL_HREF)) is not None


def classifier_materiel(
    domaine: Any,
    fabricant: Any,
    modele: Any,
    catalogue: CatalogueMateriel,
) -> list[str]:
    """Retourne les codes d'anomalie du materiel au regard du catalogue.

    Un domaine hors catalogue court-circuite les autres regles : le Fabricant et
    le Modele ne sont pas evaluables sans domaine de reference, les signaler
    produirait deux anomalies redondantes et trompeuses.

    Le controle d'association n'est evalue que si Fabricant et Modele sont l'un
    et l'autre reconnus : signaler l'association d'une valeur deja invalide
    n'apporterait aucune information supplementaire.
    """
    cle_domaine = normaliser_valeur(domaine)
    if cle_domaine is None or cle_domaine not in catalogue.fabricants_par_domaine:
        return [TYPE_DOMAINE_HORS_CATALOGUE]

    cle_fabricant = normaliser_valeur(fabricant)
    cle_modele = normaliser_valeur(modele)
    anomalies: list[str] = []
    if cle_fabricant is None or cle_fabricant not in catalogue.fabricants_par_domaine[cle_domaine]:
        anomalies.append(TYPE_FABRICANT_NON_REFERENCE)
    if cle_modele is None or cle_modele not in catalogue.modeles_par_domaine[cle_domaine]:
        anomalies.append(TYPE_MODELE_NON_REFERENCE)
    if anomalies:
        return anomalies

    if (cle_domaine, cle_fabricant, cle_modele) not in catalogue.entrees:
        return [TYPE_COUPLE_NON_REFERENCE]
    return []


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def _construire_anomalie(
    feature: dict[str, Any],
    proprietes: Mapping[str, Any],
    id_materiel: str,
    materiel: Mapping[str, Any] | None,
    type_anomalie: str,
) -> dict[str, Any]:
    """Assemble une anomalie ; les valeurs brutes sont conservees pour diagnostic."""
    return {
        "type_anomalie": type_anomalie,
        "id_jonction": obtenir_id_feature(feature),
        "id_materiel": id_materiel,
        "type_jonction": proprietes.get(CHAMP_TYPE_JONCTION),
        "domaine_tension": proprietes.get(CHAMP_DOMAINE),
        "fabricant": materiel.get(CHAMP_FABRICANT) if materiel is not None else None,
        "modele": materiel.get(CHAMP_MODELE) if materiel is not None else None,
        "geometrie": feature.get("geometry"),
    }


def detecter_anomalies(
    features_jonction: list[dict[str, Any]],
    materiels: dict[str, dict[str, Any]],
    catalogue: CatalogueMateriel,
) -> list[dict[str, Any]]:
    """Detecte les materiels de jonction non conformes au catalogue.

    Seules les jonctions du perimetre sont parcourues. Un lien non resolu est
    signale sans evaluer les valeurs, qui n'existent pas. Une jonction peut
    porter plusieurs anomalies (Fabricant et Modele tous deux inconnus).
    """
    anomalies: list[dict[str, Any]] = []
    classifier = classifier_materiel  # alias local (boucle principale)
    for feature in features_jonction:
        proprietes = feature.get("properties") or {}
        if not est_a_controler(proprietes):
            continue
        id_materiel = str(proprietes[CHAMP_MATERIEL_HREF]).strip()
        materiel = materiels.get(id_materiel)
        if materiel is None:
            anomalies.append(_construire_anomalie(feature, proprietes, id_materiel, None, TYPE_MATERIEL_INTROUVABLE))
            continue
        codes = classifier(
            proprietes.get(CHAMP_DOMAINE),
            materiel.get(CHAMP_FABRICANT),
            materiel.get(CHAMP_MODELE),
            catalogue,
        )
        anomalies.extend(_construire_anomalie(feature, proprietes, id_materiel, materiel, code) for code in codes)
    return anomalies


def compter_jonctions_a_controler(features_jonction: list[dict[str, Any]]) -> int:
    """Compte les jonctions entrant dans le perimetre du controle."""
    return sum(1 for feature in features_jonction if est_a_controler(feature.get("properties") or {}))


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des materiels non conformes au catalogue.

    La geometrie de chaque feature est le Point de la jonction : RPD_Materiel_Reco
    n'a pas de geometrie propre, l'ecart serait sinon inexploitable dans QGIS.
    Le crs est propage depuis le fichier des jonctions.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": FICHIER_JONCTION,
                "id_jonction": a["id_jonction"],
                "id_materiel": a["id_materiel"],
                "type_jonction": a["type_jonction"],
                "domaine_tension": a["domaine_tension"],
                "fabricant": a["fabricant"],
                "modele": a["modele"],
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
    """Execute le controle de conformite du materiel de jonction en mode CLI.

    Charge le catalogue une seule fois, resout le lien materiel de chaque
    jonction du perimetre et ecrit le fichier d'ecarts GeoJSON. Un catalogue
    indisponible est une erreur bloquante ; l'absence d'un fichier source est
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

    features_jonction, crs, jonction_absent = _charger_features(repertoire_resolu, FICHIER_JONCTION)
    features_materiel, _, materiel_absent = _charger_features(repertoire_resolu, FICHIER_MATERIEL)
    materiels = indexer_materiels(features_materiel)

    anomalies = detecter_anomalies(features_jonction, materiels, catalogue)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_anomalies_par_type(anomalies),
        "nombre_jonctions_analysees": len(features_jonction),
        "nombre_jonctions_controlees": compter_jonctions_a_controler(features_jonction),
        "nombre_materiels": len(materiels),
        "nombre_entrees_catalogue": len(catalogue.entrees),
        "fichier_jonction_absent": jonction_absent,
        "fichier_materiel_absent": materiel_absent,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle de conformite du materiel de jonction."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E600 : conformite du materiel des jonctions "
            "(RPD_Jonction_Reco au statut UnderCommissionning, de type Derivation "
            "ou Jonction) au catalogue catalogue-materiel-jonction.json."
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
