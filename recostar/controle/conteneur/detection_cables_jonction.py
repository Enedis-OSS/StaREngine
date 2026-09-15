"""
Moteur de detection du raccordement d'une RPD_Jonction_Reco a ses cables.

Un seul parcours du jeu de donnees repond a deux questions distinctes, qui
reposent sur la meme geometrie :

    combien de cables sont raccordes a cette jonction ?   -> cardinalite
    ce cable-ci touche-t-il vraiment la jonction ?        -> coincidence

Les controles servis, et le type d'anomalie de chacun :

    E-6201   derivation_cables_insuffisants
    E-6202   jonction_cables_insuffisants
    E-6203   extremite_reseau_sans_cable, extremite_reseau_cables_multiples
    E-6116   cable_telecommunication_absent
    E-9609   raccordement_incoherent
    E-9502   jonction_hors_extremite      (dans `cable/`)

Pourquoi un moteur commun
-------------------------
Les deux familles de regles reposent sur la **meme** coincidence : la jonction
est-elle posee sur une extremite topologique du cable ? Le moteur ne la calcule
qu'une fois, a `TOLERANCE_SUPERPOSITION`, si bien que les controles servis ne
peuvent pas diverger sur sa tolerance.

Deux perimetres, un seul parcours
---------------------------------
Les deux regles ne jugent pas la meme population, et le moteur ne peut donc pas
filtrer en amont :

  - **le compte** (E-6201, E-6202, E-6203, E-6116) ne vaut que pour les quatre
    TypeJonction porteurs
    d'une regle, au Statut UnderCommissionning ;
  - **la coincidence** (E-9502) vaut pour toute jonction, quel que soit son
    type — une remontee aero-souterraine mal posee reste une anomalie — mais ne
    juge que les cables **electriques** au Statut UnderCommissionning, seuls
    cables dont le raccordement geometrique fait foi a ce stade.

Chaque regle pose donc son propre filtre, sur un parcours unique.

Deux granularites
-----------------
Les controles de compte decrivent une **jonction** : son type, sa regle, ses
comptes. E-9502 decrit
un **lien** (jonction, cable) : une jonction liee a deux cables mal raccordes
porte deux anomalies. Le filtrage par type precedant la construction du GeoJSON,
chaque fichier d'ecarts reste homogene et n'herite d'aucune colonne vide.

Un raccordement confirme sur les deux plans
-------------------------------------------
Un cable n'est compte comme raccorde que si le raccordement est etabli des deux
cotes :

  - **attributaire** : l'identifiant du cable figure dans le champ cables_href
    de la jonction, et resout un cable existant ;
  - **geographique** : le point de la jonction coincide avec l'une des
    extremites topologiques du cable.

Compter les seules references de cables_href reviendrait a faire confiance a une
declaration sans la verifier ; compter les seules coincidences geometriques
reviendrait a inventer un lien que la donnee ne declare pas. Le nombre retenu
est celui de l'intersection.

Les deux ensembles sont par ailleurs compares : leur divergence est signalee
pour elle-meme (`raccordement_incoherent`), independamment du compte. Une
jonction peut ainsi etre au bon nombre de raccordements tout en declarant une
reference sans realite geometrique.

`raccordement_incoherent` et `jonction_hors_extremite` ne sont pas exclusifs :
le premier constate qu'une jonction diverge, le second nomme **lequel** de ses
cables. C'est le seul recouvrement assume du moteur, et il reste coherent : une
seule geometrie, une seule tolerance.

Regles de compte, par TypeJonction
----------------------------------
    Derivation       : au moins 3 cables ;
    Jonction         : au moins 2 cables ;
    ExtremiteReseau  : exactement 1 cable ;
    Telecom          : au moins un cable de telecommunication raccorde.

  Source de l'enumeration : les valeurs admises de TypeJonction sont declarees
  par `xsd_structuration/regles_valeurs.py` (_ENUM_TYPE_JONCTION, regle
  E_TYPE_JONCTION, source PDF §10.4.1), qui fait foi pour le projet. « Telecom »
  y figure, aux cotes de Derivation, ExtremiteReseau, Jonction,
  RemonteeAeroSouterraine et EpanouissementHTA. Le XSD V1.1 l'enumere egalement ;
  celui de la V1.0 ne le fait pas, un TypeJonction Telecom sur un jeu V1.0 etant
  alors signale par le controle de structuration, non ici — le moteur reste
  agnostique de version et applique sa regle des que la valeur est presente.

La regle du type Telecom porte sur la **nature** d'au moins un cable rattache,
non sur leur compte : aucun nombre minimal ne lui est impose par ailleurs.

Geometrie des extremites : la decomposition reutilise `extraire_extremites`
(module commun), qui identifie les extremites **topologiques** d'une geometrie
lineaire. Les parties d'un MultiLineString RecoStaR n'etant ni ordonnees ni
orientees, prendre le premier et le dernier sommet apres mise a plat donnerait
des extremites fausses.

Tolerance de coincidence : la comparaison est planimetrique et admet un ecart
de 1 mm — `TOLERANCE_SUPERPOSITION` du module commun, deja partagee par les
controles d'altimetrie. Le contact d'un noeud et d'une extremite est de mesure
nulle :
les coordonnees RecoStaR etant arrondies au millimetre des le GML source, une
egalite exacte se heurte a l'arrondi. La valeur reste tres en deca de toute
precision de leve — un cable reellement ecarte, meme au centimetre, demeure
detecte. Le Z est ecarte, l'ecart altimetrique relevant des controles
altimetriques.

Cables dont les extremites sont indeterminables : une geometrie fermee, ou dont
les parties se neutralisent deux a deux, ne livre aucune extremite. Un tel cable
ne peut etre confirme geographiquement : il n'est donc ni compte comme raccorde,
ni signale comme mal raccorde (E-9502) — la cause tient a la geometrie
du cable, non a la position de la jonction. Leur nombre est reporte au rapport
et a l'anomalie.

Couches de cable analysees : RPD_CableElectrique_Reco, RPD_CableTerre_Reco et
RPD_CableTelecommunication_Reco. Une reference ne resolvant aucune de ces
couches n'est pas un raccordement attributaire valide ; son integrite relevant
d'E-9400, elle n'est ici que comptee.

Versions : jonction et cables ont une structure identique en RecoStaR V1.0 et
V1.1 ; le moteur est agnostique de version.
"""

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.chargement import charger_features
from recostar.controle.fonctions_communes.ecarts import filtrer_par_type
from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_ecarts_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.geometrie import (
    TOLERANCE_SUPERPOSITION,
    extraire_extremites,
    extraire_point_xy,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_CABLES_HREF,
    CHAMP_STATUT,
    CHAMP_TYPE_JONCTION,
    COUCHE_CABLE_ELECTRIQUE,
    COUCHE_CABLE_TELECOM,
    COUCHE_CABLE_TERRE,
    FICHIER_JONCTION,
    STATUT_MISE_EN_SERVICE,
    TYPE_JONCTION_TELECOM,
)

# Couches de cable dont une reference cables_href peut designer une entite
COUCHES_CABLE: tuple[str, ...] = (
    COUCHE_CABLE_ELECTRIQUE,
    COUCHE_CABLE_TERRE,
    COUCHE_CABLE_TELECOM,
)

# Extension des fichiers de couche
EXTENSION: str = ".geojson"

# Statut des entites a controler, jonctions comme cables
STATUT_CONTROLE: str = STATUT_MISE_EN_SERVICE

# Types d'anomalie produits par le moteur, un par code rendu. Le compte de cables
# en produit trois et non un : le verificateur reserve un code a chaque
# TypeJonction, la regle etant la meme mais le seuil — et donc le geste de
# correction — propre a chacun.
TYPE_DERIVATION_INSUFFISANTE: str = "derivation_cables_insuffisants"
TYPE_JONCTION_INSUFFISANTE: str = "jonction_cables_insuffisants"
TYPE_EXTREMITE_SANS_CABLE: str = "extremite_reseau_sans_cable"
TYPE_EXTREMITE_CABLES_MULTIPLES: str = "extremite_reseau_cables_multiples"
TYPE_RACCORDEMENT_INCOHERENT: str = "raccordement_incoherent"
TYPE_CABLE_TELECOM_ABSENT: str = "cable_telecommunication_absent"
TYPE_JONCTION_HORS_EXTREMITE: str = "jonction_hors_extremite"


@dataclass(frozen=True, slots=True)
class RegleJonction:
    """Attendu de raccordement pour un type de jonction, et les codes qui le sanctionnent.

    - `minimum` / `maximum` : nombre de cables raccordes ; `maximum` a None
      signifie « sans plafond », `minimum` a 0 « sans exigence de compte » ;
    - `type_insuffisant` / `type_excessif` : le type d'anomalie — donc le code du
      verificateur — a lever de part et d'autre des bornes. None quand la borne
      n'existe pas : un type sans plafond ne peut pas etre excessif ;
    - `cable_telecom_requis` : au moins un cable de telecommunication doit
      figurer dans cables_href. Contrainte de **nature**, independante du compte.

    Le seuil et le code voyagent ensemble parce qu'ils sont la meme decision
    metier : le verificateur ne dit pas « nombre de cables insuffisant », il dit
    « derivation avec moins de 3 cables » (E-6201) ou « jonction avec moins de 2 »
    (E-6202). Les separer inviterait a les faire diverger.
    """

    minimum: int
    maximum: int | None
    type_insuffisant: str | None = None
    type_excessif: str | None = None
    cable_telecom_requis: bool = False


# Regles par type de jonction. Le dictionnaire tient lieu de filtre de
# perimetre des controles de compte : un type absent n'est pas controle. Il ne
# restreint pas la coincidence, qui vaut pour toute jonction.
REGLES_PAR_TYPE: dict[str, RegleJonction] = {
    "Derivation": RegleJonction(3, None, TYPE_DERIVATION_INSUFFISANTE),
    "Jonction": RegleJonction(2, None, TYPE_JONCTION_INSUFFISANTE),
    # Seul type borne des deux cotes : « liee a un cable et un seul ». Les deux
    # ecarts portent le meme code E-6203, que la fiche enonce dans les deux sens.
    "ExtremiteReseau": RegleJonction(1, 1, TYPE_EXTREMITE_SANS_CABLE, TYPE_EXTREMITE_CABLES_MULTIPLES),
    # Aucun compte impose : seule la nature d'un cable rattache est exigee, d'ou
    # l'absence de type de compte — un minimum a 0 n'est jamais tenu en defaut.
    TYPE_JONCTION_TELECOM: RegleJonction(0, None, cable_telecom_requis=True),
}


@dataclass(frozen=True, slots=True)
class IndexCables:
    """Cables resolvables par cables_href, et les sous-ensembles interroges.

    - `extremites` : {id_cable: extremites planimetriques}, toutes couches ;
    - `telecom` : cables de la couche de telecommunication, pour la regle de
      nature du TypeJonction Telecom ;
    - `electriques_controles` : cables electriques au Statut controle, seul
      perimetre sur lequel la coincidence fait foi (E-9502) ;
    - `couches_absentes` : couches de cable manquantes du jeu, remontees au
      rapport sans bloquer.

    Les trois vues sont construites en une passe : les recalculer a chaque
    jonction serait quadratique, alors qu'un test d'appartenance a un frozenset
    est en O(1).
    """

    extremites: dict[str, frozenset[tuple[float, float]]]
    telecom: frozenset[str]
    electriques_controles: frozenset[str]
    couches_absentes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BilanRaccordement:
    """Confrontation des raccordements attributaires et geographiques.

    - `references` : cables designes par cables_href et resolus dans une couche
      de cable ;
    - `geographiques` : cables dont une extremite coincide avec la jonction ;
    - `raccordes` : intersection des deux, seuls raccordements confirmes ;
    - `references_non_resolues` : references ne designant aucun cable connu ;
    - `sans_extremite` : references dont les extremites sont indeterminables,
      donc non confirmables geographiquement ;
    - `references_telecom` : references resolvant un cable de telecommunication.
    """

    references: frozenset[str]
    geographiques: frozenset[str]
    raccordes: frozenset[str]
    references_non_resolues: frozenset[str]
    sans_extremite: frozenset[str]
    references_telecom: frozenset[str]

    @property
    def references_sans_coincidence(self) -> frozenset[str]:
        """Cables declares par cables_href mais non confirmes geographiquement."""
        return self.references - self.geographiques

    @property
    def coincidences_non_declarees(self) -> frozenset[str]:
        """Cables coincidant avec la jonction mais absents de cables_href."""
        return self.geographiques - self.references

    @property
    def est_coherent(self) -> bool:
        """Indique si les deux sources de raccordement concordent."""
        return not self.references_sans_coincidence and not self.coincidences_non_declarees


# ---------------------------------------------------------------------------
# Chargement des index
# ---------------------------------------------------------------------------


def indexer_cables(repertoire: str) -> IndexCables:
    """Indexe les extremites des trois couches de cable, et leurs sous-ensembles.

    Les extremites sont decomposees une seule fois par cable : elles sont
    ensuite interrogees par toutes les jonctions, en O(1) par test
    d'appartenance.

    Un cable dont les extremites sont indeterminables est conserve avec un
    ensemble vide : il reste une reference resolvable, mais aucune coincidence
    ne pourra l'etablir.
    """
    index: dict[str, frozenset[tuple[float, float]]] = {}
    telecom: set[str] = set()
    electriques: set[str] = set()
    absentes: list[str] = []
    for couche in COUCHES_CABLE:
        features, _, absente = charger_features(repertoire, f"{couche}{EXTENSION}")
        if absente:
            absentes.append(couche)
            continue
        _indexer_couche(couche, features, index, telecom, electriques)
    return IndexCables(index, frozenset(telecom), frozenset(electriques), tuple(absentes))


def _indexer_couche(
    couche: str,
    features: list[dict[str, Any]],
    index: dict[str, frozenset[tuple[float, float]]],
    telecom: set[str],
    electriques: set[str],
) -> None:
    """Verse une couche de cable dans l'index et ses deux sous-ensembles.

    Les trois structures sont enrichies en place : le moteur n'en construit
    qu'un exemplaire, quelle que soit la taille du jeu.
    """
    # Le rattachement d'un cable a sa couche est connu ici et nulle part
    # ailleurs : l'index des extremites ne le conserve pas.
    est_telecom = couche == COUCHE_CABLE_TELECOM
    est_electrique = couche == COUCHE_CABLE_ELECTRIQUE
    for feature in features:
        identifiant = obtenir_id_feature(feature)
        if identifiant is None:
            continue
        index[identifiant] = frozenset(extraire_extremites(feature.get("geometry")))
        if est_telecom:
            telecom.add(identifiant)
        elif est_electrique and (feature.get("properties") or {}).get(CHAMP_STATUT) == STATUT_CONTROLE:
            electriques.add(identifiant)


# ---------------------------------------------------------------------------
# Regles metier (fonctions pures, testables sans I/O)
# ---------------------------------------------------------------------------


def extraire_references(proprietes: Mapping[str, Any]) -> frozenset[str]:
    """Extrait les identifiants de cable declares par cables_href.

    Le champ liste les identifiants separes par des virgules ; les espaces sont
    egalement acceptes, la convention variant selon les couches (meme
    permissivite que `references_cables.extraire_ids_cables_href` du domaine
    cable).
    """
    valeur = proprietes.get(CHAMP_CABLES_HREF)
    if valeur is None:
        return frozenset()
    return frozenset(reference for reference in str(valeur).replace(",", " ").split() if reference)


def coincide(point: tuple[float, float], extremites: frozenset[tuple[float, float]]) -> bool:
    """Indique si le point coincide avec l'une des extremites, a la tolerance pres.

    Le contact d'un noeud et d'une extremite est de mesure nulle : une egalite
    exacte se heurterait a l'arrondi millimetrique des coordonnees RecoStaR.
    L'ecart admis est `TOLERANCE_SUPERPOSITION` (1 mm), la meme valeur que celle
    retenue par les controles d'altimetrie pour les memes raisons.

    Un cable sans extremite exploitable ne coincide avec rien : le court-circuit
    evite d'entrer dans la boucle pour rien.
    """
    if not extremites:
        return False
    distance = math.dist  # alias local (boucle critique)
    return any(distance(point, extremite) <= TOLERANCE_SUPERPOSITION for extremite in extremites)


def distance_extremite_plus_proche(
    point: tuple[float, float],
    extremites: frozenset[tuple[float, float]],
) -> float:
    """Distance planimetrique du point a l'extremite la plus proche.

    Valeur de diagnostic : elle indique l'ampleur du decalage — quelques
    centimetres ou plusieurs dizaines de metres — sans intervenir dans la
    decision de conformite, qui reste le seul fait de `coincide`.
    """
    distance = math.dist  # alias local
    return min(distance(point, extremite) for extremite in extremites)


def regle_applicable(proprietes: Mapping[str, Any]) -> RegleJonction | None:
    """Retourne la regle de compte applicable a la jonction, ou None hors perimetre.

    Filtre et regle en une seule resolution : le compte d'une jonction n'est
    controle que si son Statut est UnderCommissionning et si son TypeJonction
    porte une regle. La coincidence, elle, ne passe pas par ce filtre.
    """
    if proprietes.get(CHAMP_STATUT) != STATUT_CONTROLE:
        return None
    type_jonction = proprietes.get(CHAMP_TYPE_JONCTION)
    if not isinstance(type_jonction, str):
        return None
    return REGLES_PAR_TYPE.get(type_jonction)


def construire_bilan(
    point: tuple[float, float] | None,
    references: frozenset[str],
    extremites_cables: Mapping[str, frozenset[tuple[float, float]]],
    cables_telecom: frozenset[str] = frozenset(),
) -> BilanRaccordement:
    """Confronte les raccordements declares et les coincidences geometriques.

    Le parcours geographique est restreint aux cables **declares** : un cable
    coincidant sans etre declare ne peut de toute facon pas compter comme
    raccorde, et balayer l'ensemble des cables du jeu pour chaque jonction
    serait quadratique. Les coincidences non declarees sont neanmoins
    recherchees par `detecter_coincidences_non_declarees`, sur demande du
    diagnostic d'incoherence.
    """
    resolues = frozenset(reference for reference in references if reference in extremites_cables)
    sans_extremite = frozenset(reference for reference in resolues if not extremites_cables[reference])
    if point is None:
        geographiques: frozenset[str] = frozenset()
    else:
        geographiques = frozenset(reference for reference in resolues if coincide(point, extremites_cables[reference]))
    return BilanRaccordement(
        references=resolues,
        geographiques=geographiques,
        raccordes=resolues & geographiques,
        references_non_resolues=references - resolues,
        sans_extremite=sans_extremite,
        references_telecom=resolues & cables_telecom,
    )


def classifier_bilan(regle: RegleJonction, bilan: BilanRaccordement) -> list[str]:
    """Retourne les codes d'anomalie de compte d'une jonction au regard de sa regle.

    Le compte, la nature des cables et la coherence sont trois constats
    independants : une jonction peut etre au bon nombre de raccordements tout en
    declarant une reference sans realite geometrique. Leurs anomalies cumulent
    donc.

    L'exigence de cable de telecommunication porte sur les seules **references**
    declarees, comme l'enonce la regle : sa confirmation geometrique releve du
    constat de coherence, evalue par ailleurs.
    """
    anomalies: list[str] = []
    nombre = len(bilan.raccordes)
    if nombre < regle.minimum and regle.type_insuffisant is not None:
        anomalies.append(regle.type_insuffisant)
    elif regle.maximum is not None and nombre > regle.maximum and regle.type_excessif is not None:
        anomalies.append(regle.type_excessif)
    if regle.cable_telecom_requis and not bilan.references_telecom:
        anomalies.append(TYPE_CABLE_TELECOM_ABSENT)
    if not bilan.est_coherent:
        anomalies.append(TYPE_RACCORDEMENT_INCOHERENT)
    return anomalies


def detecter_coincidences_non_declarees(
    point: tuple[float, float] | None,
    references: frozenset[str],
    extremites_cables: Mapping[str, frozenset[tuple[float, float]]],
) -> frozenset[str]:
    """Retourne les cables coincidant avec la jonction sans etre declares.

    Balayage complet de l'index, reserve aux jonctions deja identifiees comme
    suspectes : le realiser pour chaque jonction serait quadratique et sans
    objet, un cable non declare ne pouvant jamais compter comme raccorde.
    """
    if point is None:
        return frozenset()
    return frozenset(
        identifiant
        for identifiant, extremites in extremites_cables.items()
        if identifiant not in references and coincide(point, extremites)
    )


def liens_hors_extremite(bilan: BilanRaccordement, electriques_controles: frozenset[str]) -> frozenset[str]:
    """Cables declares par la jonction sans coincider avec elle (perimetre E-9502).

    Deux retraits sur les references non confirmees :
      - les cables sans extremite exploitable, dont la conformite du lien ne
        peut pas etre tranchee — la cause tient a la geometrie du cable ;
      - les cables hors du perimetre electrique controle, dont le raccordement
        geometrique ne fait pas foi a ce stade.
    """
    return (bilan.references_sans_coincidence - bilan.sans_extremite) & electriques_controles


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def _anomalie_jonction(
    type_anomalie: str,
    feature: dict[str, Any],
    proprietes: Mapping[str, Any],
    regle: RegleJonction,
    bilan: BilanRaccordement,
    non_declares: frozenset[str],
) -> dict[str, Any]:
    """Assemble une anomalie de compte ; tous les comptes du bilan sont conserves."""
    return {
        "type_anomalie": type_anomalie,
        "id_jonction": obtenir_id_feature(feature),
        "type_jonction": proprietes.get(CHAMP_TYPE_JONCTION),
        "nombre_minimum": regle.minimum,
        "nombre_maximum": regle.maximum,
        "nombre_cables_raccordes": len(bilan.raccordes),
        "nombre_references": len(bilan.references),
        "nombre_geographiques": len(bilan.geographiques) + len(non_declares),
        "nombre_references_sans_coincidence": len(bilan.references_sans_coincidence),
        "nombre_coincidences_non_declarees": len(non_declares),
        "nombre_references_non_resolues": len(bilan.references_non_resolues),
        "nombre_cables_sans_extremite": len(bilan.sans_extremite),
        "nombre_cables_telecommunication": len(bilan.references_telecom),
        "geometrie": feature.get("geometry"),
    }


def _anomalie_lien(
    feature: dict[str, Any],
    proprietes: Mapping[str, Any],
    point: tuple[float, float],
    id_cable: str,
    extremites: frozenset[tuple[float, float]],
) -> dict[str, Any]:
    """Assemble l'anomalie d'un lien (jonction, cable) sans coincidence.

    Le cable fautif est nomme : l'ecart designerait sinon la jonction sans dire
    quelle reference corriger, alors qu'une jonction en porte souvent plusieurs.
    """
    return {
        "type_anomalie": TYPE_JONCTION_HORS_EXTREMITE,
        "id_jonction": obtenir_id_feature(feature),
        "type_jonction": proprietes.get(CHAMP_TYPE_JONCTION),
        "id_cable": id_cable,
        "distance_extremite": round(distance_extremite_plus_proche(point, extremites), 3),
        "geometrie": feature.get("geometry"),
    }


def _detecter_liens(
    feature: dict[str, Any],
    proprietes: Mapping[str, Any],
    point: tuple[float, float] | None,
    bilan: BilanRaccordement,
    index: IndexCables,
) -> list[dict[str, Any]]:
    """Anomalies de lien d'une jonction : une par cable declare sans coincidence.

    Le tri rend l'ordre des ecarts deterministe, un frozenset n'en garantissant
    aucun.
    """
    if point is None:
        return []
    return [
        _anomalie_lien(feature, proprietes, point, id_cable, index.extremites[id_cable])
        for id_cable in sorted(liens_hors_extremite(bilan, index.electriques_controles))
    ]


def _detecter_compte(
    feature: dict[str, Any],
    proprietes: Mapping[str, Any],
    point: tuple[float, float] | None,
    references: frozenset[str],
    bilan: BilanRaccordement,
    regle: RegleJonction,
    extremites_cables: Mapping[str, frozenset[tuple[float, float]]],
) -> list[dict[str, Any]]:
    """Anomalies de compte d'une jonction : au plus une par constat non tenu."""
    non_declares = detecter_coincidences_non_declarees(point, references, extremites_cables)
    codes = classifier_bilan(regle, bilan)
    if non_declares and TYPE_RACCORDEMENT_INCOHERENT not in codes:
        codes.append(TYPE_RACCORDEMENT_INCOHERENT)
    return [_anomalie_jonction(code, feature, proprietes, regle, bilan, non_declares) for code in codes]


def detecter_anomalies(features_jonction: list[dict[str, Any]], index: IndexCables) -> list[dict[str, Any]]:
    """Detecte les anomalies de raccordement des jonctions, tous codes confondus.

    Un seul parcours, deux perimetres : la coincidence est evaluee sur toute
    jonction, le compte sur les seules jonctions porteuses d'une regle. Une
    jonction peut porter plusieurs anomalies — un compte fautif, une incoherence
    et autant de liens mal raccordes qu'elle en declare.
    """
    anomalies: list[dict[str, Any]] = []
    extremites = index.extremites
    for feature in features_jonction:
        proprietes = feature.get("properties") or {}
        point = extraire_point_xy(feature.get("geometry"))
        references = extraire_references(proprietes)
        bilan = construire_bilan(point, references, extremites, index.telecom)
        anomalies.extend(_detecter_liens(feature, proprietes, point, bilan, index))
        regle = regle_applicable(proprietes)
        if regle is not None:
            anomalies.extend(_detecter_compte(feature, proprietes, point, references, bilan, regle, extremites))
    return anomalies


def compter_jonctions_a_controler(features_jonction: list[dict[str, Any]]) -> int:
    """Compte les jonctions dont le compte de cables entre dans le perimetre."""
    return sum(1 for feature in features_jonction if regle_applicable(feature.get("properties") or {}) is not None)


def compter_jonctions_non_conformes(anomalies: list[dict[str, Any]]) -> int:
    """Compte les jonctions distinctes portant au moins une anomalie."""
    return len({anomalie["id_jonction"] for anomalie in anomalies})


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------

# Champs de comptes repris tels quels dans les proprietes d'un ecart de compte.
_CHAMPS_COMPTE: tuple[str, ...] = (
    "nombre_minimum",
    "nombre_maximum",
    "nombre_cables_raccordes",
    "nombre_references",
    "nombre_geographiques",
    "nombre_references_sans_coincidence",
    "nombre_coincidences_non_declarees",
    "nombre_references_non_resolues",
    "nombre_cables_sans_extremite",
    "nombre_cables_telecommunication",
)


def _proprietes_compte(anomalie: dict[str, Any]) -> dict[str, Any]:
    """Proprietes d'un ecart decrivant une jonction : sa regle et ses comptes.

    Les comptes des deux sources de raccordement sont exposes cote a cote :
    c'est leur confrontation qui explique l'ecart.
    """
    proprietes: dict[str, Any] = {
        "type_anomalie": anomalie["type_anomalie"],
        "fichier_source": FICHIER_JONCTION,
        "id_jonction": anomalie["id_jonction"],
        "type_jonction": anomalie["type_jonction"],
    }
    proprietes.update((champ, anomalie[champ]) for champ in _CHAMPS_COMPTE)
    return proprietes


def _proprietes_lien(anomalie: dict[str, Any]) -> dict[str, Any]:
    """Proprietes d'un ecart decrivant un lien (jonction, cable).

    La distance a l'extremite la plus proche donne l'ampleur du decalage :
    quelques centimetres se corrigent autrement qu'une inversion de reference.
    """
    return {
        "type_anomalie": anomalie["type_anomalie"],
        "fichier_source": FICHIER_JONCTION,
        "id_jonction": anomalie["id_jonction"],
        "type_jonction": anomalie["type_jonction"],
        "id_cable": anomalie["id_cable"],
        "distance_extremite_m": anomalie["distance_extremite"],
    }


# Constructeur de proprietes par type d'anomalie ; les types absents decrivent
# une jonction. Une table plutot qu'une cascade : ajouter un type se voit ici.
_CONSTRUCTEURS_PROPRIETES: dict[str, Any] = {
    TYPE_JONCTION_HORS_EXTREMITE: _proprietes_lien,
}


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    profil: ProfilEcarts,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des jonctions au raccordement non conforme.

    La geometrie de chaque feature est le Point de la jonction concernee : c'est
    l'entite a reprendre, donc le point a localiser dans QGIS. Le crs est
    propage depuis le fichier source des jonctions.
    """
    construire = _CONSTRUCTEURS_PROPRIETES.get  # alias local
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": construire(a["type_anomalie"], _proprietes_compte)(a),
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
    """Execute le controle du raccordement des jonctions en mode CLI.

    Indexe les extremites des cables une seule fois, evalue chaque jonction et
    ecrit le fichier d'ecarts GeoJSON. L'absence d'un fichier source est
    signalee sans bloquer : un jeu ne contient pas necessairement toutes les
    couches de cable.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    index = indexer_cables(repertoire_resolu)
    features, crs, jonction_absente = charger_features(repertoire_resolu, FICHIER_JONCTION)

    # Le moteur releve toutes les anomalies ; le controle appelant ne retient
    # que celles de son code. Les compteurs qui suivent portent donc sur son
    # perimetre, non sur celui du moteur.
    anomalies = filtrer_par_type(detecter_anomalies(features, index), types_retenus)
    geojson_ecarts = construire_geojson_ecarts(anomalies, profil, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, fichier_sortie)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_ecarts_par_type(geojson_ecarts),
        "nombre_jonctions_analysees": len(features),
        "nombre_jonctions_controlees": compter_jonctions_a_controler(features),
        "nombre_jonctions_non_conformes": compter_jonctions_non_conformes(anomalies),
        "nombre_cables_indexes": len(index.extremites),
        "nombre_cables_electriques_controles": len(index.electriques_controles),
        "nombre_cables_telecommunication": len(index.telecom),
        "nombre_cables_sans_extremite": sum(1 for extremites in index.extremites.values() if not extremites),
        "tolerance_coincidence_m": TOLERANCE_SUPERPOSITION,
        "fichier_jonction_absent": jonction_absente,
        "couches_cable_absentes": list(index.couches_absentes),
        "sortie": chemin_ecrit,
    }
