"""
Controle E-6207 : PLOR avec valeur de « levé » différente de l'altitude du PLOR

Un RPD_PointLeveOuvrageReseau_Reco de TypeLeve AltitudeGeneratrice porte deux
fois la meme grandeur : la valeur relevee sur le terrain, dans son champ `Leve`,
et l'altitude de sa geometrie. Les deux doivent coincider ; sinon, l'une des deux
est fausse et rien ne dit laquelle.

Le GML source fait foi
----------------------
Ce controle lit le **GML d'entree**, non les GeoJSON. La raison tient a la
conversion : `conversion_V1_1/recostar_to_geojson` normalise un GML V1.0 vers le
modele V1.1 et, ce faisant, **supprime `Leve` et `TypeLeve`** — seule la valeur
d'un leve de ChargeGeneratrice survit, sous un autre nom. Le cas que vise
E-6207, `TypeLeve = AltitudeGeneratrice`, est precisement celui que cette
normalisation ecarte : le GeoJSON n'en porte plus aucune trace.

Le GML est transmis par le pipeline de famille (cf. `FAMILLES_AVEC_GML`), ou
localise dans le repertoire a defaut. Sans GML, le controle se replie sur les
GeoJSON : ils portent l'attribut lorsqu'ils viennent du convertisseur
`conversion_V1`, qui le conserve. Le repli est signale par `source` dans le
rapport, afin qu'un resultat vide ne soit jamais pris pour une verification.

Restreint a la RecoStaR V1.0
----------------------------
Le triplet `Leve` / `TypeLeve` / altitude n'existe qu'en V1.0. La V1.1 l'a
remplace par le seul `ChargeGeneratrice` — une charge, non une altitude — et le
leve d'altitude y a disparu du schema : la regle est alors **sans objet**, et le
controle le declare tel quel plutot que de retourner un faux conforme.

La version est lue dans l'en-tete du GML, ou elle est declaree
(`xsd_structuration.detection_version`). Sur le repli GeoJSON, elle est deduite
du champ `TypeLeve`, discriminant des deux versions
(`fonctions_communes.version_recostar`).

Perimetre : les seules entites de TypeLeve AltitudeGeneratrice. Un leve de
ChargeGeneratrice mesure une charge mecanique, qu'aucune altitude n'a vocation a
egaler ; il est ignore, comme l'est un type absent ou inconnu — la validite de la
valeur releve d'E0014, regle E_LEVE_TYPE.

Deux absences ne sont pas des anomalies de ce controle :
  - `Leve` non renseigne : il n'y a rien a confronter, et l'exigence de presence
    releve du controle de structuration ;
  - altitude absente de la geometrie : c'est l'anomalie d'E-5107, qui signale
    toute entite privee de composante Z. La signaler ici aussi produirait deux
    anomalies pour une meme cause.

Egalite stricte, sans tolerance
-------------------------------
Les deux valeurs proviennent du **meme document**, lues par le meme analyseur :
le texte de l'element `Leve` et le troisieme terme de la `posList`. Deux
ecritures decimales identiques donnent le meme flottant ; une tolerance ne
couvrirait donc aucun artefact numerique, et masquerait un ecart reel au
millimetre. Meme parti que le moteur des sommets de cables, dont la docstring
de TOLERANCE_SUPERPOSITION
rappelle que son egalite exacte X/Y/Z ne doit pas etre relachee.

L'ecart mesure est reporte au fichier d'ecarts : c'est lui qui dit a l'operateur
s'il corrige une saisie ou un arrondi.

Usage CLI :
    python -m recostar.controle.altimetrie.e6207 --repertoire <chemin> [--sortie <chemin>]
                                                 [--gml <fichier.gml>] [--version {auto,1.0,1.1}]

Sortie : ecarts_e6207_leve_different_altitude.geojson
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_LEVE,
    CHAMP_TYPE_LEVE,
    FICHIER_POINT_LEVE,
    TYPE_LEVE_ALTITUDE,
)
from recostar.controle.fonctions_communes.points_leve_gml import (
    VERSION_LEVE,
    charger_points_leve,
)
from recostar.controle.fonctions_communes.proprietes import valeur_numerique
from recostar.controle.fonctions_communes.resultats import (
    motif_couche_absente,
    rapport_sans_objet,
)
from recostar.controle.fonctions_communes.version_recostar import (
    JETON_AUTO,
    VERSIONS_SUPPORTEES,
    resoudre_version,
)
from recostar.controle.xsd_structuration.detection_version import detecter_version

# Fichier source analyse par ce controle
FICHIER_SOURCE: str = FICHIER_POINT_LEVE

# Fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6207_leve_different_altitude.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-6207"

# Type d'anomalie unique produit par ce controle
TYPE_LEVE_DIFFERENT: str = "leve_different_altitude"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    TYPE_LEVE_DIFFERENT: ("La valeur de levé du point levé diffère de l'altitude de sa géométrie."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_point_leve",),
    couche_source=FICHIER_SOURCE,
)


# ---------------------------------------------------------------------------
# Regle metier (fonctions pures, testables sans I/O)
# ---------------------------------------------------------------------------


def est_leve_altitude(proprietes: dict[str, Any]) -> bool:
    """Indique si le point leve mesure une altitude generatrice.

    Seul ce type porte une valeur comparable a l'altitude de la geometrie. Un
    leve de charge mesure une grandeur d'une autre nature.
    """
    return proprietes.get(CHAMP_TYPE_LEVE) == TYPE_LEVE_ALTITUDE


def altitude_geometrie(geometrie: dict[str, Any] | None) -> float | None:
    """Retourne l'altitude d'une geometrie Point, ou None si elle n'en porte pas.

    Une geometrie a deux dimensions n'a pas d'altitude a confronter : son defaut
    est celui d'E-5107, qui signale toute entite privee de composante Z.
    """
    if not geometrie or geometrie.get("type") != "Point":
        return None
    coordonnees = geometrie.get("coordinates")
    if not coordonnees or len(coordonnees) < 3:
        return None
    return valeur_numerique(coordonnees[2])


def ecart_leve_altitude(feature: dict[str, Any]) -> float | None:
    """Retourne l'ecart entre la valeur de leve et l'altitude, ou None.

    None signifie « rien a confronter » : entite hors perimetre, valeur de leve
    absente ou non numerique, altitude absente. Un ecart nul est une conformite,
    et se distingue de None — d'ou le retour du flottant plutot qu'un booleen.
    """
    proprietes = feature.get("properties") or {}
    if not est_leve_altitude(proprietes):
        return None
    leve = valeur_numerique(proprietes.get(CHAMP_LEVE))
    if leve is None:
        return None
    altitude = altitude_geometrie(feature.get("geometry"))
    if altitude is None:
        return None
    return leve - altitude


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detecte les points leves dont le leve differe de leur altitude.

    L'egalite est stricte : les deux valeurs sortent du meme document et du meme
    analyseur, aucune tolerance ne couvrirait d'artefact numerique.
    """
    anomalies: list[dict[str, Any]] = []
    calculer_ecart = ecart_leve_altitude  # alias local (boucle)
    for feature in features:
        ecart = calculer_ecart(feature)
        if ecart is None or ecart == 0.0:
            continue
        proprietes = feature.get("properties") or {}
        anomalies.append(
            {
                "type_anomalie": TYPE_LEVE_DIFFERENT,
                "id_point_leve": obtenir_id_feature(feature),
                "leve": valeur_numerique(proprietes.get(CHAMP_LEVE)),
                "altitude": altitude_geometrie(feature.get("geometry")),
                "ecart": ecart,
                "geometrie": feature.get("geometry"),
            }
        )
    return anomalies


def compter_points_controles(features: list[dict[str, Any]]) -> int:
    """Compte les points leves entrant dans le perimetre du controle."""
    return sum(1 for feature in features if est_leve_altitude(feature.get("properties") or {}))


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des levés discordants.

    Les deux valeurs et leur ecart sont reportes : c'est l'ecart qui dit a
    l'operateur s'il corrige une saisie ou un arrondi, et le reproduire evite de
    rouvrir la donnee source pour le mesurer.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": FICHIER_SOURCE,
                "id_point_leve": a["id_point_leve"],
                "leve": a["leve"],
                "altitude": a["altitude"],
                "ecart": a["ecart"],
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


def charger_source(
    repertoire: Path,
    chemin_gml: Path | None,
    version_demandee: str,
) -> tuple[list[dict[str, Any]] | None, str, str | None, dict[str, Any] | None]:
    """Choisit la source, en lit les points leves et resout la version.

    La lecture est partagee avec E-6104 (`fonctions_communes.points_leve_gml`) ;
    seule la resolution de version reste ici : elle se lit dans l'en-tete du GML
    quand il y en a un, et se deduit du contenu sinon.
    """
    features, source, gml_lu, crs = charger_points_leve(repertoire, chemin_gml)
    if features is None:
        return None, source, None, None
    if gml_lu is not None:
        version_gml = detecter_version(gml_lu)
        version = version_demandee if version_demandee != JETON_AUTO else (version_gml or VERSION_LEVE)
        return features, source, version, crs
    return features, source, resoudre_version(version_demandee, features), crs


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
    chemin_gml: Path | None = None,
) -> dict[str, Any]:
    """Execute le controle E-6207 et ecrit ses ecarts.

    Lit les points leves depuis le GML source — seule source portant `Leve` et
    `TypeLeve` apres conversion — et n'applique la regle qu'en V1.0. En V1.1, le
    rapport est celui d'un controle sans objet : le couple a disparu du schema,
    il n'y a rien a confronter.
    """
    repertoire_resolu = Path(repertoire).resolve()
    features, source, version_effective, crs = charger_source(repertoire_resolu, chemin_gml, version)
    if features is None:
        return rapport_sans_objet(
            motif_couche_absente(FICHIER_SOURCE, str(repertoire_resolu)),
            source=source,
            nombre_points_controles=0,
        )

    if version_effective != VERSION_LEVE:
        return rapport_sans_objet(
            f"Jeu en RecoStaR V{version_effective} : le couple Leve / TypeLeve n'existe qu'en V{VERSION_LEVE}",
            source=source,
            version_detectee=version_effective,
            nombre_points_controles=0,
        )

    anomalies = detecter_anomalies(features)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else str(repertoire_resolu)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "source": source,
        "version_detectee": version_effective,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": {TYPE_LEVE_DIFFERENT: len(anomalies)} if anomalies else {},
        "nombre_points_controles": compter_points_controles(features),
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle E-6207."""
    choix_version = (JETON_AUTO,) + VERSIONS_SUPPORTEES
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E-6207 : en RecoStaR V1.0, la valeur de levé d'un PLOR de "
            "type AltitudeGeneratrice doit égaler l'altitude de sa géométrie."
        )
    )
    parseur.add_argument("--repertoire", required=True, help=f"Repertoire contenant {FICHIER_SOURCE}")
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    parseur.add_argument(
        "--gml",
        default=None,
        help="Fichier GML source (defaut : le GML present dans le repertoire, s'il est unique)",
    )
    parseur.add_argument(
        "--version",
        default=JETON_AUTO,
        choices=choix_version,
        help="Version RecoStaR du jeu (defaut : detection automatique)",
    )
    arguments = parseur.parse_args()
    chemin_gml = Path(arguments.gml) if arguments.gml is not None else None
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, arguments.version, chemin_gml)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
