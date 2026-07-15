"""
Utilitaires geometriques communs aux controles.

Module partage par les domaines altimetrie et cable. Centralise la
decomposition des geometries lineaires et l'identification de leurs extremites,
mecanismes utilises par plusieurs controles (E208, E504, E505, E506, E507).

Module pur (aucune E/S, aucune dependance externe) : entierement testable.
"""

from collections import Counter
from typing import Any


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
