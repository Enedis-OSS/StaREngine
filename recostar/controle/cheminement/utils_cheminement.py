"""Utilitaires specifiques au domaine cheminement."""

from typing import Any


def extraire_ids_cables_href(valeur: Any) -> list[str]:
    """Extrait les identifiants cables depuis le champ cables_href.

    Gere les formes presentes dans les donnees Recostar :
    - chaine unique  : "id<uuid>"
    - chaine multiple separee par virgules : "id<uuid1>,id<uuid2>"
    - liste          : ["id<uuid1>", "id<uuid2>"]
    - null ou absent : liste vide

    La separation par virgule est conforme au format de serialisation GML->GeoJSON.
    """
    if isinstance(valeur, str) and valeur:
        return [cid.strip() for cid in valeur.split(",") if cid.strip()]
    if isinstance(valeur, list):
        return [str(cid) for cid in valeur if cid is not None]
    return []
