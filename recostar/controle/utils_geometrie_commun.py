"""
Utilitaires geometriques communs aux controles.

Module partage par les domaines altimetrie et cable, ainsi que par le calcul des
longueurs (traitement/calcul_longueurs). Centralise la decomposition des
geometries lineaires, l'identification de leurs extremites, la correction des
altitudes manquantes et les tolerances numeriques communes, mecanismes utilises
par plusieurs controles (E205, E208, E209, E504, E505, E506, E507) et par le
calcul de longueur.

Module pur (aucune E/S) : entierement testable. Seule dependance externe,
shapely, requise par le recollement des geometries multi-parties — elle est deja
une dependance declaree du projet (E202, E205, E209, E400, E404).
"""

from collections import Counter
from typing import Any

from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge

# Tolerance de comparaison d'une altitude a zero. Les Z sont des flottants issus
# du parsing GML : un test d'egalite stricte a 0.0 serait fragile.
TOLERANCE_Z: float = 1e-9

# Tolerance planimetrique de superposition, en metres (1 mm).
#
# Les coordonnees RecoStaR sont arrondies au millimetre a la source (posList du
# GML). Deux objets censes se toucher ailleurs que sur un sommet commun ne sont
# donc jamais exactement en contact une fois arrondis : un predicat de tolerance
# nulle (« intersects ») les separe a tort. Le cas se produit meme lorsque le
# contact est mathematiquement exact, l'arithmetique flottante double precision
# laissant un residu de l'ordre de 1e-10 m.
#
# La valeur retenue couvre exactement l'arrondi de la donnee source et rien de
# plus : un objet reellement ecarte, meme au centimetre, reste detecte. Elle est
# volontairement plus stricte que l'EPSILON_SPATIAL de E404 (1 cm), qui arbitre
# une adjacence metier entre cheminements et non un artefact numerique.
#
# A n'appliquer qu'aux contacts de mesure nulle (point sur une ligne, point sur
# le contour d'un polygone). Un test d'appartenance surfacique est deja robuste,
# et une regle metier volontairement stricte — l'egalite exacte X/Y/Z d'E208 —
# ne doit pas etre relachee.
TOLERANCE_SUPERPOSITION: float = 0.001


def extraire_parties_lineaires(geometrie: dict[str, Any] | None) -> list[list[list[float]]]:
    """Retourne les polylignes (listes de sommets) d'une geometrie lineaire.

    LineString -> une partie ; MultiLineString -> ses parties ; autre -> aucune.
    """
    if not geometrie:
        return []
    coordonnees = geometrie.get("coordinates")
    if not coordonnees:
        return []
    type_geom = geometrie.get("type")
    if type_geom == "LineString":
        return [coordonnees]
    if type_geom == "MultiLineString":
        return coordonnees
    return []


def recoller_parties_lineaires(geometrie: dict[str, Any] | None) -> list[list[list[float]]]:
    """Retourne les polylignes **continues maximales** d'une geometrie lineaire.

    Complement de `extraire_parties_lineaires`, a employer par tout controle qui
    parcourt des sommets **consecutifs** (fenetre glissante, triplets, mesure
    d'angle). Les parties d'un MultiLineString RecoStaR n'etant ni ordonnees ni
    orientees, les traiter separement laisse echapper les sommets de raccord :
    ils sont bouts de partie, jamais sommets intermediaires, et ne sont donc
    jamais evalues. Le recollement les restitue.

    Delegue a `shapely.ops.linemerge`, qui reordonne les troncons, gere leur
    orientation et deduplique les noeuds partages **en preservant le Z**.

    - LineString -> une partie, inchangee ;
    - MultiLineString connexe -> une seule polyligne recollee ;
    - MultiLineString aux troncons reellement disjoints -> les polylignes
      maximales obtenues, a traiter independamment ;
    - autre type, ou geometrie vide -> aucune partie.

    Un appelant qui exige une entite d'un seul tenant (cas d'E202) teste donc
    simplement la longueur du resultat.
    """
    parties = extraire_parties_lineaires(geometrie)
    # Une partie isolee n'a rien a recoller ; un troncon de moins de deux
    # sommets ne decrit aucune ligne et ferait echouer la construction shapely.
    lineaires = [partie for partie in parties if len(partie) >= 2]
    if len(lineaires) < 2:
        return parties

    fusion = linemerge(MultiLineString(lineaires))
    if isinstance(fusion, LineString):
        return [[list(sommet) for sommet in fusion.coords]]
    return [[list(sommet) for sommet in ligne.coords] for ligne in fusion.geoms]


def extraire_extremites(geometrie: dict[str, Any] | None) -> list[tuple[float, float]]:
    """Retourne les extremites topologiques planimetriques d'une geometrie lineaire.

    Un MultiLineString RecoStaR n'a pas ses parties ordonnees ni orientees : le
    premier sommet de la premiere partie peut coincider avec le dernier sommet
    de la derniere. Prendre le premier et le dernier sommet apres mise a plat
    donnerait donc des extremites fausses — jusqu'a designer un raccord interne
    et manquer les vrais bouts. Les vraies extremites sont les bouts de partie
    qui n'en rejoignent aucun autre, c'est-a-dire les sommets apparaissant un
    nombre impair de fois parmi les bouts de partie.

    Un LineString simple retombe naturellement sur ses deux bouts. Une geometrie
    fermee (boucle) ne renvoie aucune extremite.

    Le Z est ecarte : l'identite d'une extremite est planimetrique.
    """
    occurrences: Counter[tuple[float, float]] = Counter()
    for sommets in extraire_parties_lineaires(geometrie):
        if len(sommets) < 2:
            continue
        occurrences[(sommets[0][0], sommets[0][1])] += 1
        occurrences[(sommets[-1][0], sommets[-1][1])] += 1
    return [sommet for sommet, nb in occurrences.items() if nb % 2 == 1]


def est_z_nul(valeur: float) -> bool:
    """Indique si une altitude doit etre consideree comme non renseignee.

    Le format RecoStaR n'a pas de valeur d'absence : une altitude manquante est
    ecrite 0.0 dans la posList. Un Z nul est donc traite comme absent, et non
    comme une altitude au niveau de la mer.
    """
    return abs(valeur) < TOLERANCE_Z


def corriger_z_nuls(coordonnees: list[list[float]]) -> list[float]:
    """Retourne les Z d'une polyligne, les Z nuls remplaces par le plus proche valide.

    Parcours avant puis arriere pour propager les altitudes valides vers les
    sommets dont Z vaut 0.0. Si la polyligne n'a aucun Z valide, les valeurs
    restent a 0.0.

    Sans cette correction, un unique sommet a Z=0 au milieu d'altitudes NGF
    produit un denivele fictif egal a l'altitude du terrain — soit des centaines
    de metres attribuees a un segment de quelques centimetres. C'est le mode de
    defaillance que ce module neutralise, pour le calcul de longueur comme pour
    les controles E504 (densite de sommets) et E505 (longueur maximale).
    """
    nb = len(coordonnees)
    # Pre-allocation : la taille est connue, une comprehension evite les
    # reallocations successives d'un append en boucle.
    z_corrige = [coord[2] if len(coord) > 2 else 0.0 for coord in coordonnees]

    _est_z_nul = est_z_nul  # alias local (boucle critique)

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
