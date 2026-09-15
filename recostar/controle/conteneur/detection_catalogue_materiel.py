"""
Moteur de detection : conformite du materiel de jonction au catalogue de reference.

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
  que le controle E-2101, etendu aux espaces internes.

Source de verite du catalogue :
  L'index est construit a partir de la seule liste `entrees`. Les blocs
  `fabricants`, `modeles` et `correspondancesParDomaine` en sont des vues
  derivees : les ignorer supprime tout risque de divergence si le catalogue
  evolue vers des associations non cartesiennes.

Versions : jonction et materiel ont une structure identique en RecoStaR V1.0 et
V1.1 ; le controle est agnostique de version.

Priorite : majeur.

"""

import json
import os
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.chargement import charger_features
from recostar.controle.fonctions_communes.ecarts import filtrer_par_type
from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_DOMAINE_TENSION,
    CHAMP_MATERIEL_HREF,
    CHAMP_STATUT,
    CHAMP_TYPE_JONCTION,
    FICHIER_JONCTION,
    FICHIER_MATERIEL,
    STATUT_MISE_EN_SERVICE,
    TYPES_JONCTION_AVEC_MATERIEL,
)
from recostar.controle.fonctions_communes.proprietes import normaliser_valeur, replier_espaces

# Catalogue de reference, resolu depuis la position du module
# (.../recostar/controle/conteneur/ -> .../recostar/referentiels/boites/)
CHEMIN_CATALOGUE: str = str(Path(__file__).parents[2] / "referentiels" / "boites" / "catalogue-materiel-jonction.json")


# Types d'anomalie produits par ce controle
TYPE_MATERIEL_INTROUVABLE: str = "materiel_introuvable"
TYPE_DOMAINE_HORS_CATALOGUE: str = "domaine_tension_hors_catalogue"
TYPE_FABRICANT_NON_REFERENCE: str = "fabricant_non_reference"
TYPE_MODELE_NON_REFERENCE: str = "modele_non_reference"
TYPE_COUPLE_NON_REFERENCE: str = "couple_fabricant_modele_non_reference"
TYPE_CASSE_INCORRECTE: str = "casse_couple_incorrecte"

# Noms des champs dans les proprietes des features
CHAMP_FABRICANT: str = "Fabricant"
CHAMP_MODELE: str = "Modele"

# Statut des jonctions a controler
STATUT_CONTROLE: str = STATUT_MISE_EN_SERVICE

# Types de jonction a controler. Nom local du sous-ensemble declare par le
# modele : les controles de rattachement du materiel jugent la meme relation en
# sens inverse et s'y referent aussi.
TYPES_JONCTION_CONTROLES: frozenset[str] = TYPES_JONCTION_AVEC_MATERIEL

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
    # Ecriture de reference du couple, indexee par son triplet normalise. Le
    # reste de l'index ne retient que des valeurs normalisees, qui ont perdu
    # leur casse : sans cette table, E-7305 n'aurait rien a quoi comparer.
    ecriture_par_entree: Mapping[tuple[str, str, str], tuple[str, str]]

    @property
    def domaines(self) -> frozenset[str]:
        """Domaines de tension couverts par au moins une entree du catalogue."""
        return frozenset(self.fabricants_par_domaine)


# ---------------------------------------------------------------------------
# Normalisation et chargement du catalogue
# ---------------------------------------------------------------------------


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


def _extraire_ecriture(entree: Any) -> tuple[str, str] | None:
    """Extrait l'ecriture de reference (fabricant, modele) d'une entree.

    Les espaces sont replies, la casse conservee : c'est exactement la forme a
    laquelle E-7305 confronte la valeur du materiel. Les deux valeurs sont
    presentes des lors que `_extraire_triplet` a abouti.
    """
    if not isinstance(entree, dict):
        return None
    fabricant = replier_espaces(entree.get(CLE_FABRICANT_ENTREE))
    modele = replier_espaces(entree.get(CLE_MODELE_ENTREE))
    if fabricant is None or modele is None:
        return None
    return fabricant, modele


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
    ecritures: dict[tuple[str, str, str], tuple[str, str]] = {}
    extraire = _extraire_triplet  # alias local (boucle de chargement)
    for entree in entrees:
        triplet = extraire(entree)
        if triplet is None:
            continue
        domaine, fabricant, modele = triplet
        triplets.add(triplet)
        fabricants[domaine].add(fabricant)
        modeles[domaine].add(modele)
        ecriture = _extraire_ecriture(entree)
        if ecriture is not None:
            # Premiere ecriture rencontree : le catalogue est la reference, deux
            # entrees normalisees identiques y decrivent le meme couple.
            ecritures.setdefault(triplet, ecriture)

    if not triplets:
        return None
    return CatalogueMateriel(
        entrees=frozenset(triplets),
        fabricants_par_domaine={domaine: frozenset(valeurs) for domaine, valeurs in fabricants.items()},
        modeles_par_domaine={domaine: frozenset(valeurs) for domaine, valeurs in modeles.items()},
        ecriture_par_entree=dict(ecritures),
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


def casse_incorrecte(
    fabricant: Any,
    modele: Any,
    ecriture_catalogue: tuple[str, str] | None,
) -> bool:
    """Indique si le couple differe du catalogue par sa seule casse.

    N'a de sens que sur un couple **deja reconnu** : les deux valeurs sont alors
    egales a celles du catalogue apres normalisation, casse comprise. Si elles
    different une fois les seuls espaces replies, la difference restante ne peut
    etre que de capitalisation — c'est la regle d'E-7305.

    Un ecart d'espacement seul n'est donc pas signale : `replier_espaces` l'a
    neutralise des deux cotes avant la comparaison. Le libelle du code ne vise
    que la casse.

    Une ecriture de reference absente rend la comparaison impossible : le couple
    est tenu pour conforme plutot que signale sur une supposition.
    """
    if ecriture_catalogue is None:
        return False
    return (replier_espaces(fabricant), replier_espaces(modele)) != ecriture_catalogue


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
    # Une cle absente a deja produit son anomalie ci-dessus : les deux tests sur
    # None ne changent aucun resultat, ils enoncent que le triplet ci-dessous est
    # complet.
    if anomalies or cle_fabricant is None or cle_modele is None:
        return anomalies

    triplet = (cle_domaine, cle_fabricant, cle_modele)
    if triplet not in catalogue.entrees:
        return [TYPE_COUPLE_NON_REFERENCE]
    if casse_incorrecte(fabricant, modele, catalogue.ecriture_par_entree.get(triplet)):
        return [TYPE_CASSE_INCORRECTE]
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
        "domaine_tension": proprietes.get(CHAMP_DOMAINE_TENSION),
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
            proprietes.get(CHAMP_DOMAINE_TENSION),
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
    profil: ProfilEcarts,
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
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, profil)


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def executer_analyse(
    repertoire: str,
    types_retenus: frozenset[str],
    profil: ProfilEcarts,
    fichier_sortie: str,
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

    features_jonction, crs, jonction_absent = charger_features(repertoire_resolu, FICHIER_JONCTION)
    features_materiel, _, materiel_absent = charger_features(repertoire_resolu, FICHIER_MATERIEL)
    materiels = indexer_materiels(features_materiel)

    anomalies = detecter_anomalies(features_jonction, materiels, catalogue)
    # Le moteur a releve toutes les anomalies ; le controle appelant ne
    # retient que celles de son code. Les compteurs qui suivent portent donc
    # sur son perimetre, non sur celui du moteur.
    anomalies = filtrer_par_type(anomalies, types_retenus)
    geojson_ecarts = construire_geojson_ecarts(anomalies, profil, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, fichier_sortie)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
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
