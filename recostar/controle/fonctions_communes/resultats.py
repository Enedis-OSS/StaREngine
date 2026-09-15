"""
Construction des rapports retournes par les controles.

Un controle dont la couche source est absente du jeu de donnees n'a rien a
verifier. Ce n'est pas un echec : c'est un controle sans objet, dont le resultat
est connu — aucune anomalie, puisqu'il n'existe aucune entite susceptible d'en
porter une. Le traiter comme un echec declasserait la famille en « Incomplet »
et ferait apparaitre « echec » dans la colonne Anomalies du rapport, la ou le
jeu de donnees est simplement partiel.

La distinction porte sur la cause, pas sur la gravite :

- **sans objet** : la couche que le controle lit n'est pas livree. Rien n'est
  verifiable parce qu'il n'y a rien a verifier. Statut conforme, zero anomalie.
- **echec** : le controle aurait du s'executer mais n'a pas pu — repertoire
  d'entree inexistant, referentiel externe indisponible, parametre requis
  manquant, fichier present mais illisible. La conformite reste inconnue, le
  statut « Incomplet » est alors le bon.

Le rapport garde la trace du motif : un controle conforme sans avoir rien lu ne
doit pas etre confondu, a la lecture, avec un controle conforme apres analyse.
"""

from typing import Any

# Marqueur porte par le rapport d'un controle sans element a controler. La
# synthese le remonte jusqu'au rapport PDF, qui en restitue le motif.
CLE_SANS_OBJET: str = "sans_objet"

# Motif du cas le plus frequent : le repertoire ne contient aucune couche.
MOTIF_AUCUN_GEOJSON: str = "Aucun fichier GeoJSON dans le repertoire"


def motif_couche_absente(nom_fichier: str, repertoire: str) -> str:
    """Redige le motif d'un controle prive de sa couche source.

    Centralise la formulation : les 13 controles concernes affichaient chacun
    la leur, ce qui rendait le rapport irregulier d'une famille a l'autre.
    """
    return f"Couche {nom_fichier} absente de {repertoire} : aucun element a controler"


def rapport_sans_objet(motif: str, **compteurs: Any) -> dict[str, Any]:
    """Construit le rapport d'un controle qui n'avait aucun element a controler.

    Le rapport est celui d'un controle conforme — `succes` vrai, aucune anomalie
    — augmente du marqueur `sans_objet` et de son motif, qui disent *pourquoi*
    il n'y avait rien a compter.

    `compteurs` recoit les champs propres au controle appelant (nombre d'entites
    analysees, couches absentes...) : la forme de son rapport est ainsi preservee
    pour ses appelants, qui n'ont pas a distinguer ce cas.
    """
    return {
        "succes": True,
        CLE_SANS_OBJET: True,
        "motif": motif,
        "nombre_anomalies": 0,
        "anomalies_par_type": {},
        # Aucun fichier d'ecarts n'est ecrit : il n'y a pas d'ecart a porter.
        # Meme valeur que celle rendue par `ecrire_geojson_si_anomalies` sur une
        # collection vide, pour que les appelants n'aient qu'un cas a traiter.
        "sortie": None,
        **compteurs,
    }


def est_sans_objet(rapport: dict[str, Any]) -> bool:
    """Indique si un rapport est celui d'un controle sans element a controler."""
    return bool(rapport.get(CLE_SANS_OBJET))
