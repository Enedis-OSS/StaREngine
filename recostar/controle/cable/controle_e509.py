"""
Controle E509 : discretisation des courbes des cables electriques.

Verifie qu'une courbe portee par un cable electrique en cours de mise en service
est decrite par suffisamment de sommets pour rester fidele a son trace reel. Une
courbe rendue par trop peu de segments est remplacee par une ligne brisee dont
chaque corde s'ecarte de l'arc veritable : c'est cet ecart qui est mesure.

Regle de gestion, en deux temps :

  1. Les sommets dont l'angle de changement de direction est inferieur a
     3 degres sont ignores : le trace y est droit a la precision du leve, il n'y
     a pas d'arc a controler.
  2. Sur les sommets restants, on reconstruit l'arc localement puis on mesure la
     fleche. Un sommet dont la fleche atteint ou depasse 40 cm est non conforme :
     le trace s'ecarte trop de la courbe reelle, il manque des sommets.

Echantillonnage dissymetrique (garde-fou) :
  Un sommet encadre par une micro-corde et une corde longue n'est pas retenu
  comme sommet manquant. Le defaut recherche est un *manque* de sommets ; deux
  sommets distants de quelques centimetres etablissent le contraire. Sur un tel
  triangle, le cercle reconstruit est dicte par l'orientation du micro-segment
  — la mesure la plus bruitee du jeu — et la fleche pretee a la longue corde est
  extrapolee depuis un troncon ou aucun sommet n'atteste de courbure. Les cables
  RecoStaR portent regulierement de tels micro-segments : ce sont leurs raccords
  terminaux dans les boites. Les deux cordes encadrant le sommet doivent donc
  atteindre SEUIL_CORDE_COURTE pour que le declencheur B s'applique (voir
  `classer_sommet`).

Methode de mesure — rayon, corde, fleche
----------------------------------------

Trois sommets consecutifs A, B, C definissent un cercle unique (cercle
circonscrit au triangle ABC). Son rayon donne la courbure locale du cable :

    R = (|AB| . |BC| . |AC|) / (2 . |AB ^ BC|)

Le rayon est une grandeur **intrinseque a la courbe** : il ne depend pas de la
finesse du decoupage, contrairement a la distance d'un sommet a la corde de ses
voisins, qui diminue mecaniquement lorsqu'on rapproche les sommets. C'est ce qui
permet de comparer un ecart au sol a un seuil fixe, quelle que soit l'echelle du
trace.

De ce rayon et de la longueur d'une corde tracee, on tire la fleche de l'arc,
c'est-a-dire l'ecart maximal entre le segment dessine et la courbe reelle :

    f = R - racine(R^2 - c^2 / 4)      relation equivalente : R = (c^2 + 4 f^2) / (8 f)

Chaque sommet est evalue sur ses **deux cordes adjacentes** (le segment qui y
arrive et celui qui en repart) ; la plus grande des deux fleches est retenue.

References : « Calcul Rayon-Fleche-corde d'un arc » (metabricoleur.com/t13942)
et « Cercle 3 pts » (fr.scribd.com/document/340858108).

Geometries multi-parties : les troncons d'un MultiLineString sont recolles en
polylignes continues avant analyse (utils_geometrie.recoller_parties_lineaires),
comme le fait E202. Les parties d'un MultiLineString RecoStaR n'etant ni
ordonnees ni orientees, les analyser separement laisserait echapper les sommets
de raccord, qui ne sont jamais des sommets intermediaires.

Comparaison planimetrique (XY) : la fleche est mesuree sur X et Y. Le Z est
ecarte, comme dans E506 et E507 : un ecart altimetrique ne traduit pas un defaut
de discretisation et releve des controles E200 a E209.

Perimetre :
  - Entites RPD_CableElectrique_Reco au Statut UnderCommissionning.
  - Les cables references par un cheminement aerien (RPD_Aerien_Reco.cables_href)
    sont exclus, via le meme mecanisme que les controles E202 / E208 / E504 /
    E505 : la geometrie d'un cable aerien suit une portee entre supports, dont
    la courbure ne releve pas de la discretisation d'un trace au sol.
  - Compatible RecoStaR V1.0 et V1.1 : geometries identiques, controle
    agnostique de version.

Usage CLI :
    python controle_e509.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e509_discretisation_courbe_cable.geojson — une entite par portion de
courbe fautive, restreinte aux seuls sommets concernes.
"""

import argparse
import json
import math
import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from typing import Any

# Mecanisme d'exclusion aerienne reutilise d'E504
from controle_e504 import (
    FICHIER_CABLE_ELECTRIQUE,
    charger_ids_cables_aeriens,
)
from utils_geojson import (
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from utils_geometrie import recoller_parties_lineaires

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e509_discretisation_courbe_cable.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E509"

# Types d'anomalie. Ils decrivent deux defauts distincts et non deux gravites :
# toutes les anomalies du controle partagent la meme priorite (voir
# PRIORITE_ANOMALIE). Le type sert au diagnostic et au libelle du rapport.
TYPE_COURBE_NON_DISCRETISEE: str = "courbe_non_discretisee"
TYPE_COURBE_MAL_DISCRETISEE: str = "courbe_mal_discretisee"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    TYPE_COURBE_NON_DISCRETISEE: (
        "Les deux cordes encadrant le sommet s'écartent de l'arc réel d'au moins 40 cm : la courbe n'est pas décrite."
    ),
    TYPE_COURBE_MAL_DISCRETISEE: ("La portion courbe du câble n'est pas suffisamment discrétisée."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable",),
)


# Niveau de priorite affecte a toutes les anomalies du controle. Bloquant : une
# courbe insuffisamment discretisee decrit le cable ailleurs qu'ou il se trouve,
# le recolement ne peut pas etre exploite en l'etat (cf. PRIORITES_DECLASSANTES
# dans synthese_controles). Les deux types d'anomalie restent distingues pour le
# diagnostic, mais ne se distinguent plus par leur gravite : le controle suit donc
# la convention scalaire majoritaire (E500 a E508) et non la convention
# multi-priorites d'E506.
PRIORITE_ANOMALIE: str = "bloquant"

# Statut des cables a controler
CHAMP_STATUT: str = "Statut"
STATUT_CONTROLE: str = "UnderCommissionning"

# Fleche a partir de laquelle un ecart est tenu pour fort (metres). Une seule
# corde l'atteignant suffit a declencher le controle sur un virage serre ; les
# deux l'atteignant qualifient une courbe qui n'est pas decrite du tout.
SEUIL_FLECHE_FORTE: float = 0.40

# Fleche en deca de laquelle l'ecart est tenu pour negligeable (metres). C'est
# le seuil d'entree du controle : sous cette valeur des deux cotes, le sommet
# est conforme.
SEUIL_FLECHE_NEGLIGEABLE: float = 0.10

# Longueur de corde (metres) en deca de laquelle un ecart significatif isole est
# tolere : un virage serre decrit sur un segment tres court est un detail de
# trace, pas un defaut de discretisation.
SEUIL_CORDE_COURTE: float = 1.00

# Rayon de courbure (metres) au-dela duquel un ecart porte par une seule corde
# n'est plus signale. Sur une courbe tres ample, une corde longue s'ecarte
# arithmetiquement de l'arc sans que le trace en devienne infidele : le cable
# reste a sa place, seule la forme est lissee. En deca, le virage est assez
# serre pour qu'un sommet manquant deplace reellement le trace.
SEUIL_RAYON_ARC_SERRE: float = 15.0

# Angle de changement de direction (degres) en deca duquel un sommet est ignore.
# Sous 3 degres, le trace est droit a la precision du leve : il n'y a pas d'arc,
# et reconstruire un cercle sur des points quasi alignes donnerait un rayon
# enorme, donc une mesure sans signification physique.
SEUIL_ANGLE: float = 3.0

# Ecart (metres) en deca duquel un sommet est juge colineaire a ses voisins et
# retire du trace : il n'apporte aucune information geometrique et fausserait le
# cercle reconstruit sur ses voisins.
TOLERANCE_COLINEARITE: float = 0.001

# Tolerance de comparaison des flottants a zero. Les coordonnees sont exprimees
# en metres dans un systeme projete : 1e-9 m (le nanometre) est tres en deca de
# toute precision de leve, mais reste largement au-dessus du bruit d'arrondi
# binaire. Comparer un flottant a 0.0 par egalite stricte serait illusoire.
TOLERANCE_ZERO: float = 1e-9


@dataclass(frozen=True, slots=True)
class SeuilsDiscretisation:
    """Seuils de classement d'un sommet. Regroupes pour ne pas propager quatre
    parametres a travers toute la chaine d'analyse, et pour qu'un appelant
    puisse en surcharger un seul sans repeter les autres."""

    angle: float = SEUIL_ANGLE
    fleche_forte: float = SEUIL_FLECHE_FORTE
    fleche_negligeable: float = SEUIL_FLECHE_NEGLIGEABLE
    corde_courte: float = SEUIL_CORDE_COURTE
    rayon_arc_serre: float = SEUIL_RAYON_ARC_SERRE


SEUILS_DEFAUT: SeuilsDiscretisation = SeuilsDiscretisation()


@dataclass(slots=True)
class MesureSommet:
    """Arc reconstruit localement autour d'un sommet intermediaire.

    - `indice` : position du sommet dans sa partie lineaire ;
    - `angle` : changement de direction au sommet, en degres ;
    - `rayon` : rayon du cercle passant par le sommet et ses deux voisins ;
    - `fleche_max` / `fleche_min` : les deux fleches des cordes adjacentes,
      ordonnees — `fleche_max` est l'ecart le plus defavorable du voisinage ;
    - `corde_fleche_max` / `corde_fleche_min` : longueurs des cordes portant
      respectivement `fleche_max` et `fleche_min`. La fleche croissant avec la
      corde a rayon fixe, `corde_fleche_max` est toujours la plus longue des
      deux : le couple decrit donc aussi la symetrie de l'echantillonnage
      autour du sommet ;
    - `type_anomalie` : classement du sommet, `None` s'il est conforme.
    """

    indice: int
    angle: float
    rayon: float
    fleche_max: float
    fleche_min: float
    corde_fleche_max: float
    corde_fleche_min: float
    type_anomalie: str | None


# ---------------------------------------------------------------------------
# Geometrie de l'arc : rayon, corde, fleche
# ---------------------------------------------------------------------------


def _distance_a_la_corde(
    precedent: list[float],
    sommet: list[float],
    suivant: list[float],
) -> float | None:
    """Distance planimetrique d'un sommet a la corde reliant ses deux voisins.

    Sert a juger la colinearite lors du nettoyage du trace. Retourne None
    lorsque la corde est de longueur nulle : les deux voisins sont confondus,
    aucune distance n'est definie.
    """
    ux, uy = sommet[0] - precedent[0], sommet[1] - precedent[1]
    vx, vy = suivant[0] - sommet[0], suivant[1] - sommet[1]
    longueur_corde = math.hypot(ux + vx, uy + vy)
    if longueur_corde < TOLERANCE_ZERO:
        return None
    # Deux fois l'aire du triangle, divisee par la base : la hauteur issue du
    # sommet, c'est-a-dire sa distance a la corde.
    return abs(ux * vy - uy * vx) / longueur_corde


def rayon_cercle_3_points(
    precedent: list[float],
    sommet: list[float],
    suivant: list[float],
) -> float:
    """Rayon du cercle passant par trois points (cercle circonscrit au triangle).

    Applique R = (a . b . c) / (4 . aire), l'aire du triangle valant la moitie
    de la norme du produit vectoriel. La formule est preferee a la resolution du
    centre du cercle : elle n'exige aucune division intermediaire et reste donc
    stable sur des triangles etires, cas courant sur un cable finement discretise.

    Retourne `math.inf` lorsque les trois points sont alignes : le « cercle » est
    alors une droite, de courbure nulle. Le test de degenerescence porte sur la
    distance du sommet a la corde, homogene a une longueur, et non sur le produit
    vectoriel brut dont l'ordre de grandeur varie comme une aire.
    """
    ux, uy = sommet[0] - precedent[0], sommet[1] - precedent[1]
    vx, vy = suivant[0] - sommet[0], suivant[1] - sommet[1]
    produit_vectoriel = ux * vy - uy * vx
    corde = math.hypot(suivant[0] - precedent[0], suivant[1] - precedent[1])
    if corde < TOLERANCE_ZERO or abs(produit_vectoriel) / corde < TOLERANCE_ZERO:
        return math.inf
    return (math.hypot(ux, uy) * math.hypot(vx, vy) * corde) / (2.0 * abs(produit_vectoriel))


def fleche_arc(rayon: float, corde: float) -> float:
    """Fleche de l'arc de rayon donne sous-tendu par une corde.

    Ecart maximal entre la corde tracee et l'arc reel, atteint au milieu de la
    corde. Relation classique rayon-fleche-corde :

        f = R - racine(R^2 - c^2 / 4)     soit     R = (c^2 + 4 f^2) / (8 f)

    L'implementation utilise la forme equivalente `(c/2)^2 / (R + racine(...))`.
    Ecrire la soustraction directement provoquerait une **annulation
    catastrophique** des que la corde est petite devant le rayon : les deux
    termes deviennent presque egaux et les chiffres significatifs disparaissent.
    Sur un rayon de 1000 km et une corde de 1 m, la forme directe perd trois
    decimales que la forme retenue conserve.

    Retourne 0 pour un rayon infini (points alignes, aucune courbure). Une corde
    superieure ou egale au diametre donne une fleche egale au rayon : c'est le
    demi-cercle, fleche maximale possible.
    """
    if math.isinf(rayon):
        return 0.0
    demi_corde = corde / 2.0
    if demi_corde >= rayon:
        return rayon
    # (R - d)(R + d) plutot que R*R - d*d : evite de former deux grands carres
    # dont la difference serait bruitee.
    reste = math.sqrt((rayon - demi_corde) * (rayon + demi_corde))
    return (demi_corde * demi_corde) / (rayon + reste)


# ---------------------------------------------------------------------------
# Nettoyage prealable du trace
# ---------------------------------------------------------------------------


def nettoyer_sommets(sommets: list[list[float]]) -> list[list[float]]:
    """Retire les sommets sans valeur geometrique d'une partie lineaire.

    Sont retires les doublons de coordonnees XY consecutifs et les sommets
    colineaires a 1 mm pres. Ces points n'apportent aucune information sur le
    trace mais faussent la reconstruction de l'arc : un sommet parasite pris
    comme voisin place deux des trois points du cercle presque au meme endroit,
    ce qui rend le rayon calcule arbitrairement grand.

    Le Z est preserve : seul le plan XY intervient dans la decision.
    """
    nettoyes: list[list[float]] = []
    for sommet in sommets:
        if nettoyes and math.dist(sommet[:2], nettoyes[-1][:2]) < TOLERANCE_ZERO:
            continue
        if len(nettoyes) >= 2:
            distance = _distance_a_la_corde(nettoyes[-2], nettoyes[-1], sommet)
            if distance is not None and distance < TOLERANCE_COLINEARITE:
                # Le sommet intermediaire est aligne : il est remplace, non ajoute.
                nettoyes[-1] = sommet
                continue
        nettoyes.append(sommet)
    return nettoyes


# ---------------------------------------------------------------------------
# Mesure des sommets
# ---------------------------------------------------------------------------


def classer_sommet(
    fleche_max: float,
    fleche_min: float,
    corde_fleche_min: float,
    rayon: float,
    seuils: SeuilsDiscretisation = SEUILS_DEFAUT,
) -> str | None:
    """Classe un sommet d'apres ses deux fleches, la plus courte de leurs cordes et le rayon.

    Deux defauts distincts sont recherches, par deux declencheurs independants :

      A. **Arc uniformement sous-decrit** — les **deux** cordes s'ecartent de
         l'arc d'au moins `fleche_negligeable` (10 cm). Le virage entier est
         rendu par trop peu de sommets : ce n'est pas un trou ponctuel, c'est
         toute la courbe qui manque de points.
      B. **Corde isolee trop longue** — **une** corde s'ecarte d'au moins
         `fleche_forte` (40 cm) alors que le virage est serre
         (rayon < `rayon_arc_serre`). Un sommet manque a cet endroit precis.

    Le garde-fou de rayon ne s'applique qu'au declencheur B, et c'est voulu :
    sur une courbe tres ample, une corde longue s'ecarte arithmetiquement de
    l'arc sans que le cable soit mal place — seule la forme est lissee. Le
    declencheur A, lui, ne peut pas se produire sur une courbe ample : il faudrait
    que les deux cordes soient longues, ce qui est deja un arc grossier.

    Deux exceptions ramenent le sommet a « conforme » :
      - les deux fleches restent sous `fleche_negligeable` : le trace suit l'arc ;
      - **echantillonnage dissymetrique** : le declencheur B exige que les
        **deux** cordes atteignent `corde_courte` (1 m). Le defaut recherche est
        un *manque* de sommets ; or deux sommets distants de quelques
        centimetres prouvent exactement le contraire — le trace y est
        localement sur-echantillonne. Le rayon reconstruit sur un tel triangle
        est dicte par l'orientation du micro-segment, la mesure la plus bruitee
        du jeu (a 8 cm, une erreur de leve d'1 cm vaut 7 degres de gisement), et
        la fleche attribuee a la longue corde n'est plus une mesure mais une
        **extrapolation** : entre ses deux extremites, aucun sommet ne temoigne
        d'une quelconque courbure. Le declencheur A n'a pas besoin de cette
        reserve — il exige deux fleches significatives, ce qu'une micro-corde ne
        peut pas produire ; la courbure y est corroboree des deux cotes.

    Ce garde-fou generalise l'ancienne tolerance de corde courte, qui ne testait
    que la corde portant `fleche_max`, donc la plus longue des deux : elle ne
    couvrait que le cas ou les deux cordes etaient courtes, et laissait passer
    l'echantillonnage dissymetrique. La fleche croissant avec la corde a rayon
    fixe, `corde_fleche_min` est toujours la plus courte : la tester seule
    couvre les deux situations. C'est pourquoi la corde portant `fleche_max`
    n'est plus un parametre : aucune decision ne s'y appuie.

    Retourne le type d'anomalie, ou None si le sommet est conforme.

    Le seuil de negligeabilite est **inclusif** : une fleche de 10 cm tout juste
    est tenue pour significative. La regle metier separe « superieure a 10 cm »
    et « inferieure a 10 cm » sans trancher l'egalite ; la retenir du cote
    significatif est le choix prudent, et l'egalite exacte entre deux flottants
    ne se rencontre pas sur des mesures reelles.
    """
    # Cas extreme : les deux cordes ratent l'arc de plus de 40 cm. La courbe
    # n'est pas decrite du tout, quel que soit son rayon.
    if fleche_min >= seuils.fleche_forte:
        return TYPE_COURBE_NON_DISCRETISEE
    if fleche_max < seuils.fleche_negligeable:
        return None
    if fleche_min < seuils.fleche_negligeable:
        # Un seul ecart significatif : declencheur B, sous reserve que les deux
        # cordes soient mesurables. `corde_fleche_min` etant toujours la plus
        # courte, ce seul test couvre aussi le cas des deux cordes courtes.
        if corde_fleche_min < seuils.corde_courte:
            return None
        if fleche_max >= seuils.fleche_forte and rayon < seuils.rayon_arc_serre:
            return TYPE_COURBE_MAL_DISCRETISEE
        return None
    # Declencheur A : les deux cordes s'ecartent significativement.
    return TYPE_COURBE_MAL_DISCRETISEE


def _mesurer_sommet(
    indice: int,
    precedent: list[float],
    sommet: list[float],
    suivant: list[float],
    seuils: SeuilsDiscretisation,
) -> MesureSommet | None:
    """Reconstruit l'arc local a un sommet, mesure ses deux fleches et le classe.

    Retourne None lorsque le sommet n'a pas d'arc a controler : angle de
    changement de direction inferieur au seuil, ou trois points alignes. Un
    sommet mesure mais conforme est bien retourne, avec `type_anomalie` a None :
    il compte dans les sommets evalues.
    """
    ux, uy = sommet[0] - precedent[0], sommet[1] - precedent[1]
    vx, vy = suivant[0] - sommet[0], suivant[1] - sommet[1]
    # atan2 donne l'angle de changement de direction dans [0, 180] degres, sans
    # perte de precision aux angles faibles (contrairement a acos du produit
    # scalaire normalise, instable pres de zero) — ce qui compte ici, le seuil
    # de filtrage etant precisement un petit angle.
    angle = math.degrees(math.atan2(abs(ux * vy - uy * vx), ux * vx + uy * vy))
    if angle < seuils.angle:
        return None

    rayon = rayon_cercle_3_points(precedent, sommet, suivant)
    if math.isinf(rayon):
        return None

    # Une fleche par corde adjacente : celle du segment qui arrive sur le sommet
    # et celle du segment qui en repart. Elles different des que le trace n'est
    # pas echantillonne regulierement — c'est la signature d'un trou de sommets.
    corde_entrante, corde_sortante = math.hypot(ux, uy), math.hypot(vx, vy)
    fleche_entrante = fleche_arc(rayon, corde_entrante)
    fleche_sortante = fleche_arc(rayon, corde_sortante)
    if fleche_entrante >= fleche_sortante:
        fleche_max, fleche_min = fleche_entrante, fleche_sortante
        corde_max, corde_min = corde_entrante, corde_sortante
    else:
        fleche_max, fleche_min = fleche_sortante, fleche_entrante
        corde_max, corde_min = corde_sortante, corde_entrante

    return MesureSommet(
        indice,
        angle,
        rayon,
        fleche_max,
        fleche_min,
        corde_max,
        corde_min,
        classer_sommet(fleche_max, fleche_min, corde_min, rayon, seuils),
    )


def mesurer_sommets(
    sommets: list[list[float]],
    seuils: SeuilsDiscretisation = SEUILS_DEFAUT,
) -> list[MesureSommet]:
    """Mesure l'arc local de tous les sommets intermediaires d'une partie.

    Les sommets sans arc mesurable (trace droit, points alignes) sont absents du
    resultat. Chaque mesure conserve l'indice de son sommet, indispensable au
    regroupement en portions puis a l'extraction de la geometrie fautive.
    """
    mesurer = _mesurer_sommet  # alias local (boucle critique)
    mesures: list[MesureSommet] = []
    for indice in range(1, len(sommets) - 1):
        mesure = mesurer(indice, sommets[indice - 1], sommets[indice], sommets[indice + 1], seuils)
        if mesure is not None:
            mesures.append(mesure)
    return mesures


# ---------------------------------------------------------------------------
# Analyse d'un cable
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PortionNonConforme:
    """Portion de courbe insuffisamment discretisee, isolee du reste du cable.

    - `sommets` : sommets non conformes consecutifs, encadres par le sommet qui
      les precede et celui qui les suit — c'est la portion a redensifier, et la
      geometrie ecrite dans le fichier d'ecarts ;
    - `type_anomalie` : type porte par tous les sommets de la portion ;
    - `fleche_max` : plus grande fleche mesuree sur la portion (metres) ;
    - `rayon_min` : plus petit rayon de courbure de la portion (metres), soit
      l'endroit ou la courbe est la plus serree ;
    - `angle_max` : plus grand changement de direction de la portion (degres) ;
    - `nombre_sommets_non_conformes` : sommets atteignant le seuil de fleche.
    """

    sommets: list[list[float]]
    type_anomalie: str
    fleche_max: float
    rayon_min: float
    angle_max: float
    nombre_sommets_non_conformes: int


@dataclass(slots=True)
class ResultatAnalyse:
    """Bilan de discretisation des courbes d'un cable."""

    portions: list[PortionNonConforme]
    nombre_sommets_evalues: int


def _cle_de_portion(paire: tuple[int, MesureSommet]) -> tuple[str | None, int]:
    """Cle de regroupement : (type d'anomalie, ecart entre indice et rang).

    L'ecart reste constant au sein d'une suite de sommets consecutifs et change
    des qu'un sommet conforme s'intercale, ce qui ferme la portion sans test
    explicite. Le type est ajoute a la cle pour qu'une portion ne melange jamais
    deux gravites : elle porte alors une priorite unique, sans arbitrage.
    """
    rang, mesure = paire
    return (mesure.type_anomalie, mesure.indice - rang)


def _grouper_sommets_consecutifs(mesures: list[MesureSommet]) -> Iterator[list[MesureSommet]]:
    """Regroupe les sommets non conformes d'indices consecutifs en portions.

    Un cable presentant deux arcs mal discretises separes par un trace correct
    produit ainsi deux portions distinctes, chacune localisee sur son troncon.
    """
    for _, groupe in groupby(enumerate(mesures), key=_cle_de_portion):
        yield [mesure for _, mesure in groupe]


def _construire_portion(sommets: list[list[float]], groupe: list[MesureSommet]) -> PortionNonConforme:
    """Isole la portion de trace couverte par une suite de sommets non conformes.

    La portion extraite va du sommet precedant le groupe a celui qui le suit :
    ces deux sommets ferment l'arc et rendent la portion exploitable dans QGIS.
    """
    # Le type est homogene sur le groupe : il fait partie de la cle de
    # regroupement, le premier sommet le porte donc pour tous.
    type_anomalie = groupe[0].type_anomalie
    return PortionNonConforme(
        sommets[groupe[0].indice - 1 : groupe[-1].indice + 2],
        type_anomalie if type_anomalie is not None else TYPE_COURBE_MAL_DISCRETISEE,
        max(mesure.fleche_max for mesure in groupe),
        min(mesure.rayon for mesure in groupe),
        max(mesure.angle for mesure in groupe),
        len(groupe),
    )


def analyser_geometrie(
    geometrie: dict[str, Any] | None,
    seuils: SeuilsDiscretisation = SEUILS_DEFAUT,
) -> ResultatAnalyse:
    """Analyse la discretisation des courbes de toute la geometrie d'un cable.

    Les troncons d'un MultiLineString sont d'abord **recolles** en polylignes
    continues : sans cela, les sommets de raccord ne seraient jamais evalues (ils
    sont bouts de partie, jamais sommets intermediaires) et un arc a cheval sur
    deux troncons echapperait au controle. Les polylignes restantes — troncons
    reellement disjoints — sont ensuite traitees independamment : aucun arc
    fictif n'est reconstruit entre elles.

    Le classement de chaque sommet est delegue a `classer_sommet` ; seules les
    portions non conformes sont retournees, chacune homogene en gravite.
    """
    portions: list[PortionNonConforme] = []
    nb_evalues = 0
    for partie in recoller_parties_lineaires(geometrie):
        sommets = nettoyer_sommets(partie)
        mesures = mesurer_sommets(sommets, seuils)
        nb_evalues += len(mesures)
        non_conformes = [mesure for mesure in mesures if mesure.type_anomalie is not None]
        portions.extend(_construire_portion(sommets, groupe) for groupe in _grouper_sommets_consecutifs(non_conformes))
    return ResultatAnalyse(portions, nb_evalues)


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def _est_a_controler(feature: dict[str, Any], ids_cables_aeriens: set[str]) -> bool:
    """Indique si un cable entre dans le perimetre du controle.

    Un cable doit etre au statut UnderCommissionning et ne pas etre porte par un
    cheminement aerien. Le set garantit un test d'appartenance en O(1).
    """
    if (feature.get("properties") or {}).get(CHAMP_STATUT) != STATUT_CONTROLE:
        return False
    return obtenir_id_feature(feature) not in ids_cables_aeriens


def detecter_anomalies(
    features: list[dict[str, Any]],
    ids_cables_aeriens: set[str] | None = None,
    seuils: SeuilsDiscretisation = SEUILS_DEFAUT,
) -> tuple[list[dict[str, Any]], int]:
    """Detecte les portions de courbe insuffisamment discretisees.

    Retourne (anomalies, nombre_sommets_evalues). Une anomalie est generee **par
    portion de courbe fautive** et non par cable : un cable presentant deux arcs
    mal discretises produit deux anomalies, chacune localisee sur son propre
    troncon.
    """
    exclus = ids_cables_aeriens if ids_cables_aeriens is not None else set()
    anomalies: list[dict[str, Any]] = []
    nb_sommets_evalues = 0
    analyser = analyser_geometrie  # alias local
    for feature in features:
        if not _est_a_controler(feature, exclus):
            continue
        resultat = analyser(feature.get("geometry"), seuils)
        nb_sommets_evalues += resultat.nombre_sommets_evalues
        if not resultat.portions:
            continue
        identifiant = obtenir_id_feature(feature)
        anomalies.extend(
            {
                "id_cable": identifiant,
                "type_anomalie": portion.type_anomalie,
                "fleche_max": round(portion.fleche_max, 3),
                "rayon_min": round(portion.rayon_min, 2),
                "angle_max": round(portion.angle_max, 1),
                "nombre_sommets_non_conformes": portion.nombre_sommets_non_conformes,
                "geometrie": {"type": "LineString", "coordinates": portion.sommets},
            }
            for portion in resultat.portions
        )
    return anomalies, nb_sommets_evalues


def compter_cables_controles(
    features: list[dict[str, Any]],
    ids_cables_aeriens: set[str] | None = None,
) -> int:
    """Compte les cables effectivement controles (UnderCommissionning, non aeriens)."""
    exclus = ids_cables_aeriens if ids_cables_aeriens is not None else set()
    return sum(1 for feature in features if _est_a_controler(feature, exclus))


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des portions de courbe mal discretisees.

    La geometrie de chaque feature est la **seule portion fautive** du cable, et
    non son trace complet : c'est le troncon a redensifier, directement
    exploitable dans QGIS sans avoir a retrouver l'arc dans une polyligne de
    plusieurs centaines de metres. Le crs est propage depuis le fichier source.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": FICHIER_CABLE_ELECTRIQUE,
                "id_cable": a["id_cable"],
                "fleche_max_m": a["fleche_max"],
                "rayon_min_m": a["rayon_min"],
                "angle_max_deg": a["angle_max"],
                "seuil_fleche_forte_m": SEUIL_FLECHE_FORTE,
                "seuil_fleche_negligeable_m": SEUIL_FLECHE_NEGLIGEABLE,
                "seuil_rayon_arc_serre_m": SEUIL_RAYON_ARC_SERRE,
                "seuil_angle_deg": SEUIL_ANGLE,
                "nombre_sommets_non_conformes": a["nombre_sommets_non_conformes"],
                "nombre_sommets_portion": len(a["geometrie"]["coordinates"]),
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
    """Execute le controle de discretisation des courbes en mode CLI.

    Charge les cables aeriens a exclure, analyse chaque cable electrique au
    statut UnderCommissionning non aerien et ecrit le fichier d'ecarts GeoJSON.
    L'absence du fichier cable est signalee dans le rapport sans bloquer
    l'execution.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    ids_cables_aeriens = charger_ids_cables_aeriens(repertoire_resolu)

    chemin_cable = os.path.join(repertoire_resolu, FICHIER_CABLE_ELECTRIQUE)
    collection = lire_geojson(chemin_cable) if os.path.isfile(chemin_cable) else None
    fichier_cable_absent = collection is None
    features = collection.get("features", []) if collection is not None else []
    crs = collection.get("crs") if collection is not None else None

    anomalies, nb_sommets_evalues = detecter_anomalies(features, ids_cables_aeriens)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)
    # Appartenance par set : un cable peut porter plusieurs portions fautives.
    cables_non_conformes = {anomalie["id_cable"] for anomalie in anomalies}

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        # Ventilation conservee a titre informatif : les deux types partagent la
        # meme priorite, le detail reste utile au diagnostic.
        "anomalies_par_type": compter_anomalies_par_type(anomalies),
        "nombre_cables_non_conformes": len(cables_non_conformes),
        "nombre_cables_controles": compter_cables_controles(features, ids_cables_aeriens),
        "nombre_cables_aeriens_exclus": len(ids_cables_aeriens),
        "nombre_sommets_evalues": nb_sommets_evalues,
        "seuil_fleche_forte_m": SEUIL_FLECHE_FORTE,
        "seuil_fleche_negligeable_m": SEUIL_FLECHE_NEGLIGEABLE,
        "seuil_rayon_arc_serre_m": SEUIL_RAYON_ARC_SERRE,
        "seuil_angle_deg": SEUIL_ANGLE,
        "fichier_cable_absent": fichier_cable_absent,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle de discretisation des courbes."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E509 : discretisation des courbes des cables electriques "
            "(RPD_CableElectrique_Reco au statut UnderCommissionning, hors cables "
            "aeriens) — sur les sommets dont le changement de direction atteint "
            "3 degres, l'arc local est reconstruit par un cercle passant par trois "
            "points, puis la fleche de chaque corde tracee est comparee a l'arc : "
            "anomalie si les deux fleches atteignent 10 cm, ou si l'une atteint "
            "40 cm sur un virage de rayon inferieur a 15 m."
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
