"""
Lecture des points leves dans le GML source.

Deux controles portent sur des attributs du point leve que la conversion ne
conserve pas : E-6207 (la valeur de `Leve` face a l'altitude) et E-6104 (un leve
de charge sans leve d'altitude superpose). `conversion_V1_1/recostar_to_geojson`
normalise un GML V1.0 vers le modele V1.1 et supprime `Leve` et `TypeLeve` ; le
GeoJSON ne peut donc pas en temoigner, et le GML reste la seule source fiable.

Les deux controles lisent la meme couche, de la meme facon : la lecture est
tenue ici plutot que dans l'un d'eux, qu'il faudrait sinon importer depuis
l'autre.

Forme de sortie
---------------
Les objets GML sont rendus sous la **forme d'une feature GeoJSON**. Les regles
metier sont ecrites pour cette forme — elles sont aussi appliquees au repli
GeoJSON — et les presenter ainsi evite d'en tenir deux versions, une par source.
Seuls les champs que les regles lisent sont traduits.

La version n'est pas resolue ici : `detecter_version` appartient a la famille
`xsd_structuration`, et `fonctions_communes` n'importe aucune famille. Le chemin
du GML effectivement lu est retourne, a charge pour l'appelant d'y lire la
version — trois lignes, contre une inversion de dependances.
"""

from pathlib import Path
from typing import Any

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import Element  # nosec B405

from recostar.controle.fonctions_communes.geojson import lire_geojson
from recostar.controle.fonctions_communes.lecture_gml import (
    ATTR_GML_ID,
    charger_racine,
    parcourir_objets,
    positions_geometrie,
    texte_enfant,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_LEVE,
    CHAMP_TYPE_LEVE,
    FICHIER_POINT_LEVE,
)
from recostar.controle.fonctions_communes.source_gml import resoudre_chemin_gml

# Type d'objet RPD lu par ce module.
TYPE_RPD_POINT_LEVE: str = "RPD_PointLeveOuvrageReseau_Reco"

# Nombre minimal de coordonnees decrivant une position exploitable.
COORDONNEES_MINIMALES: int = 2

# Source effectivement lue, reportee au rapport des controles : un resultat vide
# n'a pas le meme sens selon qu'il vient du GML ou d'un GeoJSON prive du champ.
SOURCE_GML: str = "gml"
SOURCE_GEOJSON: str = "geojson"

# Version du format portant le couple Leve / TypeLeve. La V1.1 les a retires.
VERSION_LEVE: str = "1.0"


def element_vers_feature(element: Element) -> dict[str, Any]:
    """Traduit un point leve GML en feature exploitable par les regles metier.

    La geometrie est conservee des deux coordonnees planimetriques : E-6104 n'a
    besoin que d'elles pour juger une superposition, et la retirer faute de Z
    priverait ce controle d'un point parfaitement localise. L'absence d'altitude
    est jugee par les regles qui en ont besoin, non ici.
    """
    proprietes: dict[str, Any] = {
        "id": element.get(ATTR_GML_ID),
        CHAMP_TYPE_LEVE: texte_enfant(element, CHAMP_TYPE_LEVE),
        CHAMP_LEVE: texte_enfant(element, CHAMP_LEVE),
    }
    coordonnees = positions_geometrie(element)
    geometrie = {"type": "Point", "coordinates": coordonnees} if len(coordonnees) >= COORDONNEES_MINIMALES else None
    return {"type": "Feature", "properties": proprietes, "geometry": geometrie}


def lire_points_leve_gml(chemin_gml: Path) -> list[dict[str, Any]]:
    """Lit les points leves d'un GML et les rend sous forme de features.

    Les objets d'un autre type sont ecartes : les controles appelants ne portent
    que sur les RPD_PointLeveOuvrageReseau_Reco.
    """
    racine = charger_racine(chemin_gml)
    return [element_vers_feature(element) for element in parcourir_objets(racine, frozenset({TYPE_RPD_POINT_LEVE}))]


def charger_points_leve(
    repertoire: Path,
    chemin_gml: Path | None = None,
) -> tuple[list[dict[str, Any]] | None, str, Path | None, dict[str, Any] | None]:
    """Choisit la source et en lit les points leves.

    Retourne (features, source, chemin_gml_lu, crs). `features` a None signale
    l'absence des deux sources, seul cas ou l'appelant n'a rien a lire.

    Le GML est prefere : lui seul porte `Leve` et `TypeLeve` en toutes
    circonstances. Le repli GeoJSON ne vaut que pour un jeu issu du convertisseur
    V1.0, qui conserve ces attributs ; `chemin_gml_lu` vaut alors None, et
    l'appelant sait qu'il doit deduire la version du contenu.
    """
    gml_resolu, _ = resoudre_chemin_gml(repertoire, chemin_gml)
    if gml_resolu is not None:
        return lire_points_leve_gml(gml_resolu), SOURCE_GML, gml_resolu, None

    collection = lire_geojson(str(repertoire / FICHIER_POINT_LEVE))
    if collection is None:
        return None, SOURCE_GEOJSON, None, None
    return collection.get("features", []), SOURCE_GEOJSON, None, collection.get("crs")
