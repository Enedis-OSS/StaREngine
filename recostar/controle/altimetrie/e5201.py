"""
Controle altimetrique des sommets des cables.

Detecte les incoherences altimetriques locales le long des cables en analysant
des fenetres glissantes de 4 sommets consecutifs. Pour chaque fenetre, l'ecart
entre les 2 sommets centraux est compare a la tendance altimetrique definie par
les sommets extremes. Si l'ecart residuel est superieur a 40 cm, les sommets
centraux sont signales en anomalie.

Chaque cable est traite comme une entite unique, sur l'integralite de ses
sommets :
- LineString : analyse directe de ses sommets.
- MultiLineString : les troncons sont recolles en une polyligne continue via
  shapely.ops.linemerge (reordonnancement, orientation et deduplication des
  noeuds partages, Z preserve), puis analyses comme un seul cable. Un cable dont
  les troncons sont reellement disjoints (linemerge ne produit pas un LineString
  unique) est ecarte : il ne forme pas un ensemble continu.

Gestion des versions RecoStaR :
- v1.0 : controle des couches RPD_CableElectrique_Reco et RPD_CableTerre_Reco.
- v1.1 : v1.0 + RPD_CableTelecommunication_Reco.
Dans toutes les versions, seules les entites dont le champ Statut vaut
« UnderCommissionning » sont controlees. La version est detectee via le
mecanisme commun `version_recostar` (champ TypeLeve dans RPD_PointLeveOuvrageReseau_Reco)
et peut etre imposee en CLI.

Les entites dont l'identifiant apparait dans un cheminement aerien
(RPD_Aerien_Reco.cables_href) sont exclues du controle, quelle que soit la
couche.

Usage CLI :
    python -m recostar.controle.altimetrie.e5201 --repertoire <chemin> [--sortie <chemin>]
                                                 [--version {auto,1.0,1.1}]

Sortie : ecarts_e5201_controle_alti_sommets.geojson
"""

import argparse
import json
import math
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_ecarts_par_type,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.geometrie import recoller_parties_lineaires
from recostar.controle.fonctions_communes.modele_recostar import (
    FICHIER_AERIEN,
    STATUT_MISE_EN_SERVICE,
)
from recostar.controle.fonctions_communes.references_cables import (
    charger_ids_cables_aeriens,
    filtrer_cables_a_controler,
    resoudre_fichiers_cables,
)
from recostar.controle.fonctions_communes.resultats import rapport_sans_objet

# Detection de version, commune a tous les controles GeoJSON
from recostar.controle.fonctions_communes.version_recostar import (
    JETON_AUTO,
    VERSIONS_SUPPORTEES,
    determiner_version_depuis_repertoire,
)

# Ensemble des couches a controler selon la version RecoStaR. La v1.1 ajoute la
# couche telecommunication aux deux couches deja controlees en v1.0.

# Filtrage metier : seules les entites en cours de mise en service sont controlees
VALEUR_STATUT_CONTROLE: str = STATUT_MISE_EN_SERVICE


# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e5201_controle_alti_sommets.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E-5201"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "ecart_altimetrique_sommet": ("L'écart altimétrique résiduel du sommet de câble dépasse le seuil autorisé."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable",),
)


# Seuil d'ecart altimetrique residuel au-dela duquel une anomalie est declaree (metres)
SEUIL_ECART_ALTI: float = 0.40


# Nombre de sommets ignores en debut et en fin de chaque cable
NB_SOMMETS_IGNORES: int = 3

# Taille de la fenetre glissante analysee
TAILLE_FENETRE: int = 4


def _distance_2d(point_a: Sequence[float], point_b: Sequence[float]) -> float:
    """Calcule la distance planaire entre deux sommets 3D."""
    return math.hypot(point_a[0] - point_b[0], point_a[1] - point_b[1])


def _ecart_residuel_centraux(fenetre: Sequence[Sequence[float]]) -> float:
    """Calcule l'ecart altimetrique residuel entre les 2 sommets centraux.

    La tendance altimetrique definie par le premier et le dernier sommet de la
    fenetre est retranchee de l'ecart brut observe entre les sommets centraux.
    Cela neutralise les pentes naturelles du trace et limite les faux positifs.
    """
    p0, p1, p2, p3 = fenetre
    longueur_totale = _distance_2d(p0, p3)
    ecart_brut = p2[2] - p1[2]

    # Si la fenetre est degeneree en 2D, la tendance est indefinie
    if longueur_totale <= 0.0:
        return math.fabs(ecart_brut)

    pente = (p3[2] - p0[2]) / longueur_totale
    ecart_attendu = pente * _distance_2d(p1, p2)
    return math.fabs(ecart_brut - ecart_attendu)


def _indices_centraux_valides(nb_sommets: int) -> range:
    """Retourne la plage des indices de sommets centraux analyses.

    Les NB_SOMMETS_IGNORES premiers et derniers sommets sont exclus de l'analyse.
    """
    debut_fenetre_min = NB_SOMMETS_IGNORES - 1
    debut_fenetre_max = nb_sommets - NB_SOMMETS_IGNORES - TAILLE_FENETRE + 2
    return range(max(0, debut_fenetre_min), max(0, debut_fenetre_max))


def _analyser_sommets_cable(
    coordonnees: list[list[float]],
) -> dict[int, float]:
    """Analyse un cable et retourne les indices de sommets anomaux avec leur ecart max.

    Chaque sommet central peut apparaitre dans plusieurs fenetres ; l'ecart
    residuel maximal observe est conserve afin de refleter la situation la plus severe.
    """
    anomalies_par_indice: dict[int, float] = {}

    # Fonctions locales pour limiter le cout des acces globaux dans la boucle critique
    maj_max = anomalies_par_indice.__setitem__
    lecture_max = anomalies_par_indice.get

    for debut in _indices_centraux_valides(len(coordonnees)):
        fenetre = coordonnees[debut : debut + TAILLE_FENETRE]
        ecart = _ecart_residuel_centraux(fenetre)
        if ecart <= SEUIL_ECART_ALTI:
            continue
        for indice_central in (debut + 1, debut + 2):
            if ecart > lecture_max(indice_central, -1.0):
                maj_max(indice_central, ecart)

    return anomalies_par_indice


def _reconstituer_sommets_cable(
    geometrie: dict[str, Any],
) -> list[list[float]] | None:
    """Retourne la sequence de sommets du cable traite comme entite unique.

    Le recollement est delegue au module commun (recoller_parties_lineaires),
    qui reordonne les troncons, gere leur orientation et deduplique les noeuds
    partages en preservant le Z. Ce controle exige un cable **d'un seul tenant** :
    des troncons reellement disjoints donnent plusieurs polylignes, et le cable
    est alors ecarte — il ne forme pas un ensemble continu. Une geometrie non
    lineaire ne donne aucune partie et retourne donc None de la meme facon.
    """
    parties = recoller_parties_lineaires(geometrie)
    return parties[0] if len(parties) == 1 else None


def _cable_est_analysable(sommets: list[list[float]]) -> bool:
    """Indique si le cable possede assez de sommets 3D pour etre analyse.

    Un cable trop court (moins de TAILLE_FENETRE sommets) ou comportant un
    sommet sans composante Z est ignore.
    """
    if len(sommets) < TAILLE_FENETRE:
        return False
    return all(len(point) >= 3 for point in sommets)


def _cable_est_eligible(
    cable: dict[str, Any],
    ids_exclus: set[str],
) -> list[list[float]] | None:
    """Retourne les sommets du cable s'il est eligible au controle.

    Un cable est eligible si son identifiant n'est pas reference par un
    cheminement aerien et si sa geometrie peut etre reconstituee en une polyligne
    unique (LineString, ou MultiLineString connexe). La validite altimetrique
    (nombre de sommets, presence de Z) est verifiee ensuite par
    _cable_est_analysable.
    """
    identifiant = obtenir_id_feature(cable)
    if identifiant is None or identifiant in ids_exclus:
        return None

    geometrie = cable.get("geometry") or {}
    return _reconstituer_sommets_cable(geometrie)


def controler_altimetrie_sommets(
    cables: list[dict[str, Any]],
    ids_cables_exclus: set[str],
) -> list[dict[str, Any]]:
    """Execute le controle altimetrique sur l'ensemble des cables eligibles.

    Chaque cable LineString est analyse comme une entite unique : la fenetre
    glissante parcourt l'integralite de ses sommets. Retourne une liste
    d'anomalies avec, pour chaque sommet signale, son identifiant de cable, son
    indice sequentiel dans la geometrie, ses coordonnees et l'ecart residuel.
    """
    anomalies: list[dict[str, Any]] = []

    for cable in cables:
        sommets = _cable_est_eligible(cable, ids_cables_exclus)
        if sommets is None or not _cable_est_analysable(sommets):
            continue

        identifiant = obtenir_id_feature(cable)
        anomalies_cable = _analyser_sommets_cable(sommets)
        for indice, ecart in anomalies_cable.items():
            anomalies.append(
                {
                    "id_cable": identifiant,
                    "indice_sommet": indice,
                    "coordonnees": sommets[indice],
                    "ecart_residuel": round(ecart, 4),
                }
            )

    return anomalies


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection Point des sommets en ecart altimetrique.

    Le champ crs est propage depuis le fichier source pour assurer
    l'affichage correct dans QGIS.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "id_cable": a["id_cable"],
                "couche": a.get("couche"),
                "indice_sommet": a["indice_sommet"],
                "ecart_residuel_m": a["ecart_residuel"],
                "seuil_m": SEUIL_ECART_ALTI,
                "type_anomalie": "ecart_altimetrique_sommet",
            },
            "geometry": {
                "type": "Point",
                "coordinates": a["coordonnees"],
            },
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, PROFIL_ECARTS)


def controler_couches_cables(
    repertoire: str,
    fichiers_cables: Sequence[str],
    ids_cables_exclus: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[str]]:
    """Execute le controle sur chaque couche de cables presente dans le repertoire.

    Pour chaque couche, seules les entites au statut « UnderCommissionning » sont
    controlees. Les couches absentes sont ignorees silencieusement (cas nominal
    pour la telecommunication en v1.0 ou sur les jeux ne la contenant pas). La
    couche d'origine est annotee sur chaque anomalie. Le CRS est propage depuis
    la premiere couche presente qui en porte un.

    Retourne (anomalies, crs, couches_traitees).
    """
    anomalies: list[dict[str, Any]] = []
    crs: dict[str, Any] | None = None
    couches_traitees: list[str] = []

    for fichier in fichiers_cables:
        collection = lire_geojson(os.path.join(repertoire, fichier))
        if collection is None:
            continue

        nom_couche = Path(fichier).stem
        couches_traitees.append(nom_couche)
        if crs is None:
            crs = collection.get("crs")

        features_a_controler = filtrer_cables_a_controler(collection.get("features", []))
        anomalies_couche = controler_altimetrie_sommets(features_a_controler, ids_cables_exclus)
        for anomalie in anomalies_couche:
            anomalie["couche"] = nom_couche
        anomalies.extend(anomalies_couche)

    return anomalies, crs, couches_traitees


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
) -> dict[str, Any]:
    """Execute le controle altimetrique des sommets en mode CLI.

    Resout la version RecoStaR, determine les couches a controler, filtre les
    entites par statut, execute le controle sur chaque couche presente et ecrit
    le fichier de sortie.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    version_effective = determiner_version_depuis_repertoire(repertoire_resolu, version)
    fichiers_cables = resoudre_fichiers_cables(version_effective)
    ids_exclus = charger_ids_cables_aeriens(repertoire_resolu)

    anomalies, crs, couches_traitees = controler_couches_cables(repertoire_resolu, fichiers_cables, ids_exclus)
    if not couches_traitees:
        return rapport_sans_objet(f"Aucune couche de cables dans {repertoire_resolu} : aucun element a controler")

    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "version_detectee": version_effective,
        "couches_controlees": couches_traitees,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_ecarts_par_type(geojson_ecarts),
        "cables_exclus": len(ids_exclus),
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle altimetrique des sommets."""
    choix_version = (JETON_AUTO,) + VERSIONS_SUPPORTEES
    parseur = argparse.ArgumentParser(description="Controle altimetrique des sommets des cables")
    parseur.add_argument(
        "--repertoire",
        required=True,
        help=f"Repertoire contenant les couches de cables et {FICHIER_AERIEN}",
    )
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    parseur.add_argument(
        "--version",
        choices=choix_version,
        default=JETON_AUTO,
        help=(
            "Version RecoStaR a controler. 'auto' (defaut) la deduit des "
            "proprietes GeoJSON (TypeLeve dans PointLeve) ; sinon imposer "
            "'1.0' ou '1.1'."
        ),
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, arguments.version)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
