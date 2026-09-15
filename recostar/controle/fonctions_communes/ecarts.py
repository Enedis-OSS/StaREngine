"""
Selection des anomalies revenant a un controle donne.

Depuis que chaque controle porte un code du verificateur, plusieurs controles
partagent un meme moteur de detection : celui-ci releve toutes les anomalies
qu'il sait voir, chaque controle ne retenant que celles de son code.

Ce module porte le seul geste identique a tous : le tri des anomalies du moteur
par code appelant. La construction des ecarts, leur ecriture et le rapport
restent dans chaque moteur, qui seul connait ses compteurs metier.
"""

from typing import Any


def filtrer_par_type(anomalies: list[dict[str, Any]], types_retenus: frozenset[str]) -> list[dict[str, Any]]:
    """Ne garde que les anomalies relevant du controle appelant.

    Le filtrage est fait sur `type_anomalie` : c'est la seule maille a laquelle
    un moteur partage distingue ce qui revient a chacun de ses controles.
    """
    return [anomalie for anomalie in anomalies if anomalie.get("type_anomalie") in types_retenus]
