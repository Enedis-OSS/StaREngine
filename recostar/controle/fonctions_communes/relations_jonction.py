"""
Index inverse de la relation jonction -> materiel.

Le GML ne porte cette relation que dans un sens : la jonction reference son
materiel par `materiel_href`. Interroger un materiel pour savoir quelles
jonctions le designent suppose donc de retourner l'index.

E-7102 (rattachement du materiel a une jonction) et E-9601 (unicite des
identifiants de materiel entre jonctions) posent tous deux cette question, sur
le meme index.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from recostar.controle.fonctions_communes.geojson import obtenir_id_feature
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_MATERIEL_HREF,
    CHAMP_STATUT,
    CHAMP_TYPE_JONCTION,
)
from recostar.controle.fonctions_communes.proprietes import normaliser_valeur


@dataclass(frozen=True, slots=True)
class LienJonction:
    """Reference d'une jonction vers un materiel, telle qu'indexee.

    Conserve ce dont l'anomalie a besoin — l'identite de la jonction, son type
    et son statut bruts, sa geometrie — sans retenir la feature entiere.
    `slots` : l'index en porte un par lien, soit potentiellement des milliers
    par jeu.

    Le statut est retenu pour E-7103, qui exige que la boite portant un materiel
    soit en cours de mise en service. Sa valeur par defaut vaut absence : un
    statut non renseigne n'est aucun des etats du schema.
    """

    id_jonction: str | None
    type_jonction: Any
    geometrie: dict[str, Any] | None
    statut: Any = None


def indexer_jonctions_par_materiel(features_jonction: list[dict[str, Any]]) -> dict[str, list[LienJonction]]:
    """Construit l'index {id_materiel: [jonctions le referencant]}.

    Une liste est conservee par materiel — et non un lien unique — afin qu'un
    materiel reference plusieurs fois soit evalue sur chacun de ses liens :
    c'est precisement l'anomalie que cherche E-9601.

    Les jonctions sans `materiel_href` sont ignorees, ne participant pas a la
    relation. Le href est normalise (espaces de bord supprimes) comme du cote
    du catalogue de materiel, sans quoi les controles resoudraient des liens
    differents.
    """
    index: defaultdict[str, list[LienJonction]] = defaultdict(list)
    for feature in features_jonction:
        proprietes = feature.get("properties") or {}
        reference = proprietes.get(CHAMP_MATERIEL_HREF)
        if normaliser_valeur(reference) is None:
            continue
        index[str(reference).strip()].append(
            LienJonction(
                obtenir_id_feature(feature),
                proprietes.get(CHAMP_TYPE_JONCTION),
                feature.get("geometry"),
                proprietes.get(CHAMP_STATUT),
            )
        )
    return dict(index)
