"""
Tests unitaires du controle E205 (coherence points de leve / geomsupp de coffrets).

Couvre :
- extraction des hrefs selon la version (v1.0 : tous coffrets, v1.1 : Statut filtre)
- detection de version (mecanisme E204 reutilise : TypeLeve dans PointLeve)
- chargement des points de leve en geometries Shapely 2D
- detection spatiale (point present / absent, geomsupp non liee ignoree)
- tolerance planimetrique de superposition (point pose sur le contour)
- construction du GeoJSON de sortie (champ version inclus)
- execution CLI bout en bout via tmp_path (modes auto et explicite)
"""

from __future__ import annotations

import json
import os
from typing import Any

from controle_e204 import CHAMP_TYPE_LEVE, JETON_AUTO, VERSION_DEFAUT
from controle_e205 import (
    CHAMP_HREF_GEOM_SUPP,
    CHAMP_STATUT,
    FICHIER_COFFRET,
    FICHIER_GEOM_SUPP,
    FICHIER_POINT_LEVE,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    TOLERANCE_SUPERPOSITION,
    VALEUR_STATUT_V1_1,
    _charger_points_leve,
    construire_geojson_ecarts,
    detecter_geomsupp_sans_point_leve,
    executer_controle_cli,
    extraire_hrefs_geomsupp_liees_coffrets,
)
from utils_tests import (
    construire_feature,
    construire_feature_avec_proprietes,
    ecrire_collection,
)

# ---------------------------------------------------------------------------
# Donnees de test partagees
# ---------------------------------------------------------------------------

# Carre 2D de 1m x 1m : le point (0.5, 0.5) est a l'interieur
_POLY_1M = [[[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]]]

# Carre 3D de 1m x 1m : verifie que force_2d fonctionne
_POLY_1M_3D = [
    [
        [
            [0.0, 0.0, 5.0],
            [1.0, 0.0, 5.0],
            [1.0, 1.0, 5.0],
            [0.0, 1.0, 5.0],
            [0.0, 0.0, 5.0],
        ]
    ]
]

# Carre loin du precedent
_POLY_LOIN = [[[[100.0, 100.0], [101.0, 100.0], [101.0, 101.0], [100.0, 101.0], [100.0, 100.0]]]]

_POINT_INTERIEUR = [0.5, 0.5]
_POINT_SUR_BORD = [0.0, 0.0]  # sommet de _POLY_1M
_POINT_EXTERIEUR = [50.0, 50.0]

# Geometrie supplementaire a l'echelle Lambert-93, dont le premier cote reprend
# un segment reel de Echantillon3. Le point de leve _POINT_SUR_ARETE est le
# milieu de ce cote arrondi au millimetre a la source : il tombe 2,3e-4 m a
# l'EXTERIEUR du polygone, la ou le predicat « intersects » le rejetait.
_ARETE_A = [668683.578, 6735670.133]
_ARETE_B = [668683.031, 6735670.398]
_SOMMET_OPPOSE = [668684.0, 6735671.0]
_POLY_ARETE = [[[_ARETE_A, _ARETE_B, _SOMMET_OPPOSE, _ARETE_A]]]
_POINT_SUR_ARETE = [668683.305, 6735670.265]

# Memes reperes, points ecartes vers l'EXTERIEUR du polygone (2,0 mm et 9,6 mm
# du contour) : de vraies erreurs de saisie, que la tolerance ne doit pas
# absorber. La direction est opposee a _SOMMET_OPPOSE, sinon l'ecart ferait
# rentrer le point dans le polygone et le test ne prouverait rien.
_POINT_ECARTE_2MM = [668683.303, 6735670.264]
_POINT_ECARTE_1CM = [668683.298, 6735670.258]


def _feature_coffret(
    identifiant: str,
    href: str | None,
    statut: str | None = None,
) -> dict[str, Any]:
    """Feature coffret Point avec href optionnel et statut optionnel."""
    props: dict[str, Any] = {}
    if href is not None:
        props[CHAMP_HREF_GEOM_SUPP] = href
    if statut is not None:
        props[CHAMP_STATUT] = statut
    return construire_feature_avec_proprietes(identifiant, "Point", [0.0, 0.0], props)


def _feature_geomsupp(identifiant: str, coords_multi: list[Any]) -> dict[str, Any]:
    """Feature geometrie supplementaire MultiPolygon."""
    return construire_feature(identifiant, "MultiPolygon", coords_multi)


def _feature_point_leve(
    identifiant: str,
    coords: list[float],
    avec_type_leve: bool = False,
) -> dict[str, Any]:
    """Feature point de leve Point, avec ou sans champ TypeLeve (discriminant v1.0)."""
    if avec_type_leve:
        return construire_feature_avec_proprietes(
            identifiant, "Point", coords, {CHAMP_TYPE_LEVE: "AltitudeGeneratrice"}
        )
    return construire_feature(identifiant, "Point", coords)


# ---------------------------------------------------------------------------
# Tests de extraire_hrefs_geomsupp_liees_coffrets
# ---------------------------------------------------------------------------


class TestExtraireHrefsGeomSuppLieesCoffrets:
    # --- Comportement commun aux deux versions ---

    def test_coffret_sans_href_ignore(self) -> None:
        features = [_feature_coffret("c1", None)]
        assert extraire_hrefs_geomsupp_liees_coffrets(features, "1.0") == frozenset()

    def test_href_vide_ignore(self) -> None:
        props = {CHAMP_HREF_GEOM_SUPP: ""}
        feature = construire_feature_avec_proprietes("c1", "Point", [0.0, 0.0], props)
        assert extraire_hrefs_geomsupp_liees_coffrets([feature], "1.0") == frozenset()

    def test_collection_vide_retourne_frozenset_vide(self) -> None:
        assert extraire_hrefs_geomsupp_liees_coffrets([], "1.0") == frozenset()
        assert extraire_hrefs_geomsupp_liees_coffrets([], "1.1") == frozenset()

    def test_meme_href_plusieurs_coffrets_deduplique(self) -> None:
        features = [
            _feature_coffret("c1", "gs1"),
            _feature_coffret("c2", "gs1"),
        ]
        assert extraire_hrefs_geomsupp_liees_coffrets(features, "1.0") == frozenset({"gs1"})

    # --- Version 1.0 : tous les coffrets eligibles ---

    def test_v1_0_coffret_avec_href_inclus(self) -> None:
        features = [_feature_coffret("c1", "gs1")]
        assert extraire_hrefs_geomsupp_liees_coffrets(features, "1.0") == frozenset({"gs1"})

    def test_v1_0_plusieurs_coffrets_hrefs_distincts(self) -> None:
        features = [
            _feature_coffret("c1", "gs1"),
            _feature_coffret("c2", "gs2"),
        ]
        assert extraire_hrefs_geomsupp_liees_coffrets(features, "1.0") == frozenset({"gs1", "gs2"})

    def test_v1_0_coffret_avec_statut_non_filtre(self) -> None:
        # En v1.0, le champ Statut est ignore
        features = [_feature_coffret("c1", "gs1", statut="AutreStatut")]
        assert extraire_hrefs_geomsupp_liees_coffrets(features, "1.0") == frozenset({"gs1"})

    # --- Version 1.1 : uniquement coffrets UnderCommissionning ---

    def test_v1_1_coffret_under_commissioning_inclus(self) -> None:
        features = [_feature_coffret("c1", "gs1", statut=VALEUR_STATUT_V1_1)]
        assert extraire_hrefs_geomsupp_liees_coffrets(features, "1.1") == frozenset({"gs1"})

    def test_v1_1_coffret_sans_statut_exclu(self) -> None:
        features = [_feature_coffret("c1", "gs1", statut=None)]
        assert extraire_hrefs_geomsupp_liees_coffrets(features, "1.1") == frozenset()

    def test_v1_1_coffret_statut_different_exclu(self) -> None:
        features = [_feature_coffret("c1", "gs1", statut="AutreStatut")]
        assert extraire_hrefs_geomsupp_liees_coffrets(features, "1.1") == frozenset()

    def test_v1_1_filtre_mixte(self) -> None:
        features = [
            _feature_coffret("c1", "gs1", statut=VALEUR_STATUT_V1_1),  # inclus
            _feature_coffret("c2", "gs2", statut="AutreStatut"),  # exclu
            _feature_coffret("c3", "gs3", statut=None),  # exclu
        ]
        assert extraire_hrefs_geomsupp_liees_coffrets(features, "1.1") == frozenset({"gs1"})


# ---------------------------------------------------------------------------
# Tests de _charger_points_leve
# ---------------------------------------------------------------------------


class TestChargerPointsLeve:
    def test_point_2d_charge(self) -> None:
        features = [_feature_point_leve("p1", [1.0, 2.0])]
        assert len(_charger_points_leve(features)) == 1

    def test_point_3d_force_2d(self) -> None:
        features = [_feature_point_leve("p1", [1.0, 2.0, 5.0])]
        points = _charger_points_leve(features)
        assert len(points) == 1
        assert points[0].has_z is False

    def test_geometrie_non_point_ignoree(self) -> None:
        ligne = construire_feature("l1", "LineString", [[0.0, 0.0], [1.0, 1.0]])
        assert _charger_points_leve([ligne]) == []

    def test_geometrie_absente_ignoree(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "p1"},
            "geometry": None,
        }
        assert _charger_points_leve([feature]) == []

    def test_collection_vide_retourne_liste_vide(self) -> None:
        assert _charger_points_leve([]) == []

    def test_plusieurs_points_charges(self) -> None:
        features = [
            _feature_point_leve("p1", [0.0, 0.0]),
            _feature_point_leve("p2", [1.0, 1.0]),
        ]
        assert len(_charger_points_leve(features)) == 2


# ---------------------------------------------------------------------------
# Tests de detecter_geomsupp_sans_point_leve
# ---------------------------------------------------------------------------


class TestDetecterGeomSuppSansPointLeve:
    def _points_leve(self, coordonnees_liste: list[list[float]]) -> list[Any]:
        features = [_feature_point_leve(f"p{i}", c) for i, c in enumerate(coordonnees_liste)]
        return _charger_points_leve(features)

    def test_point_interieur_pas_anomalie(self) -> None:
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        ids_lies = frozenset({"gs1"})
        points = self._points_leve([_POINT_INTERIEUR])
        assert detecter_geomsupp_sans_point_leve(geomsupp, ids_lies, points) == []

    def test_point_sur_bord_pas_anomalie(self) -> None:
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        ids_lies = frozenset({"gs1"})
        points = self._points_leve([_POINT_SUR_BORD])
        assert detecter_geomsupp_sans_point_leve(geomsupp, ids_lies, points) == []

    def test_point_exterieur_produit_anomalie(self) -> None:
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        ids_lies = frozenset({"gs1"})
        points = self._points_leve([_POINT_EXTERIEUR])
        anomalies = detecter_geomsupp_sans_point_leve(geomsupp, ids_lies, points)
        assert len(anomalies) == 1
        assert anomalies[0]["id_geomsupp"] == "gs1"

    def test_aucun_point_leve_toutes_anomalies(self) -> None:
        geomsupp = [
            _feature_geomsupp("gs1", _POLY_1M),
            _feature_geomsupp("gs2", _POLY_LOIN),
        ]
        ids_lies = frozenset({"gs1", "gs2"})
        anomalies = detecter_geomsupp_sans_point_leve(geomsupp, ids_lies, [])
        assert len(anomalies) == 2

    def test_geomsupp_non_liee_ignoree(self) -> None:
        geomsupp = [_feature_geomsupp("gs_orpheline", _POLY_1M)]
        ids_lies = frozenset({"gs_autre"})
        assert detecter_geomsupp_sans_point_leve(geomsupp, ids_lies, []) == []

    def test_ids_lies_vides_aucune_anomalie(self) -> None:
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        assert detecter_geomsupp_sans_point_leve(geomsupp, frozenset(), []) == []

    def test_deux_geomsupp_une_anomalie(self) -> None:
        geomsupp = [
            _feature_geomsupp("gs1", _POLY_1M),
            _feature_geomsupp("gs2", _POLY_LOIN),
        ]
        ids_lies = frozenset({"gs1", "gs2"})
        points = self._points_leve([_POINT_INTERIEUR])
        anomalies = detecter_geomsupp_sans_point_leve(geomsupp, ids_lies, points)
        assert len(anomalies) == 1
        assert anomalies[0]["id_geomsupp"] == "gs2"

    def test_geomsupp_sans_geometrie_ignoree(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "gs1"},
            "geometry": None,
        }
        assert detecter_geomsupp_sans_point_leve([feature], frozenset({"gs1"}), []) == []

    def test_anomalie_contient_geometrie_source(self) -> None:
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        anomalies = detecter_geomsupp_sans_point_leve(geomsupp, frozenset({"gs1"}), [])
        assert anomalies[0]["geometrie"]["type"] == "MultiPolygon"

    def test_point_3d_intercepte_polygon_2d(self) -> None:
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M_3D)]
        ids_lies = frozenset({"gs1"})
        # Z tres different du polygone (Z=5) : force_2d doit neutraliser l'ecart
        points = self._points_leve([[0.5, 0.5, 99.0]])
        assert detecter_geomsupp_sans_point_leve(geomsupp, ids_lies, points) == []


# ---------------------------------------------------------------------------
# Tests de la tolerance planimetrique de superposition
# ---------------------------------------------------------------------------


class TestToleranceSuperposition:
    """Verifie que la tolerance admet un point de leve pose sur le CONTOUR du
    polygone malgre l'arrondi millimetrique, sans absorber un ecart reel.

    Le contact avec un contour est de mesure nulle, comme le contact avec une
    ligne : c'est le meme mode de defaillance que celui corrige sur E209. Un
    point INTERIEUR au polygone n'a jamais ete concerne, ce test etant
    numeriquement robuste (cf. test_point_interieur_pas_anomalie).
    """

    def _anomalies(self, coordonnees_point: list[float]) -> int:
        """Nombre d'anomalies pour un point de leve face a _POLY_ARETE."""
        points = _charger_points_leve([_feature_point_leve("p1", coordonnees_point)])
        return len(
            detecter_geomsupp_sans_point_leve([_feature_geomsupp("gs1", _POLY_ARETE)], frozenset({"gs1"}), points)
        )

    def test_tolerance_vaut_un_millimetre(self) -> None:
        assert TOLERANCE_SUPERPOSITION == 0.001

    def test_point_sur_arete_arrondi_au_millimetre_conforme(self) -> None:
        # Milieu d'un cote arrondi au mm : 2,3e-4 m a l'exterieur du polygone
        assert self._anomalies(_POINT_SUR_ARETE) == 0

    def test_point_ecarte_de_deux_millimetres_produit_anomalie(self) -> None:
        assert self._anomalies(_POINT_ECARTE_2MM) == 1

    def test_point_ecarte_d_un_centimetre_produit_anomalie(self) -> None:
        # La tolerance ne doit pas absorber une vraie erreur de saisie terrain
        assert self._anomalies(_POINT_ECARTE_1CM) == 1

    def test_point_sur_sommet_reste_conforme(self) -> None:
        # Cas historiquement couvert : la tolerance ne le degrade pas
        assert self._anomalies(_ARETE_A) == 0


# ---------------------------------------------------------------------------
# Tests de construire_geojson_ecarts
# ---------------------------------------------------------------------------


class TestConstruireGeojsonEcarts:
    def test_collection_vide(self) -> None:
        geojson = construire_geojson_ecarts([], "1.1")
        assert geojson == {"type": "FeatureCollection", "features": []}

    def test_structure_feature(self) -> None:
        anomalies = [
            {
                "id_geomsupp": "gs1",
                "geometrie": {"type": "MultiPolygon", "coordinates": _POLY_1M},
            }
        ]
        geojson = construire_geojson_ecarts(anomalies, "1.1")
        assert len(geojson["features"]) == 1
        feat = geojson["features"][0]
        assert feat["geometry"]["type"] == "MultiPolygon"
        props = feat["properties"]
        assert props["id_entite"] == "gs1"
        assert props["type_anomalie"] == "point_leve_absent"
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["version"] == "1.1"

    def test_version_incluse_dans_proprietes(self) -> None:
        anomalies = [
            {
                "id_geomsupp": "gs1",
                "geometrie": {"type": "MultiPolygon", "coordinates": _POLY_1M},
            }
        ]
        geojson_v1_0 = construire_geojson_ecarts(anomalies, "1.0")
        assert geojson_v1_0["features"][0]["properties"]["version"] == "1.0"

    def test_crs_propage_si_present(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        geojson = construire_geojson_ecarts([], "1.1", crs=crs)
        assert geojson["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        assert "crs" not in construire_geojson_ecarts([], "1.1")


# ---------------------------------------------------------------------------
# Helpers CLI
# ---------------------------------------------------------------------------


def _ecrire_trois_fichiers(
    repertoire: str,
    features_coffrets: list[dict[str, Any]],
    features_geomsupp: list[dict[str, Any]],
    features_points: list[dict[str, Any]],
) -> None:
    """Ecrit les trois fichiers sources dans le repertoire de test."""
    ecrire_collection(os.path.join(repertoire, FICHIER_COFFRET), features_coffrets)
    ecrire_collection(os.path.join(repertoire, FICHIER_GEOM_SUPP), features_geomsupp)
    ecrire_collection(os.path.join(repertoire, FICHIER_POINT_LEVE), features_points)


# ---------------------------------------------------------------------------
# Tests CLI bout en bout
# ---------------------------------------------------------------------------


class TestCli:
    def test_fichier_coffret_absent_retourne_erreur(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_GEOM_SUPP), [])
        ecrire_collection(str(tmp_path / FICHIER_POINT_LEVE), [])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert "erreur" in resultat

    def test_fichier_geomsupp_absent_retourne_erreur(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_COFFRET), [])
        ecrire_collection(str(tmp_path / FICHIER_POINT_LEVE), [])
        assert executer_controle_cli(str(tmp_path))["succes"] is False

    def test_fichier_point_leve_absent_retourne_erreur(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_COFFRET), [])
        ecrire_collection(str(tmp_path / FICHIER_GEOM_SUPP), [])
        assert executer_controle_cli(str(tmp_path))["succes"] is False

    # --- Version 1.0 ---

    def test_v1_0_sans_anomalie(self, tmp_path: Any) -> None:
        coffrets = [_feature_coffret("c1", "gs1")]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR, avec_type_leve=True)]
        _ecrire_trois_fichiers(str(tmp_path), coffrets, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["version_detectee"] == "1.0"

    def test_v1_0_avec_anomalie(self, tmp_path: Any) -> None:
        coffrets = [_feature_coffret("c1", "gs1")]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_EXTERIEUR, avec_type_leve=True)]
        _ecrire_trois_fichiers(str(tmp_path), coffrets, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 1
        assert resultat["version_detectee"] == "1.0"

    def test_v1_0_tous_coffrets_controles(self, tmp_path: Any) -> None:
        # En v1.0, les coffrets sans Statut sont tous inclus
        coffrets = [
            _feature_coffret("c1", "gs1"),
            _feature_coffret("c2", "gs2"),
        ]
        geomsupp = [
            _feature_geomsupp("gs1", _POLY_1M),
            _feature_geomsupp("gs2", _POLY_LOIN),
        ]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR, avec_type_leve=True)]
        _ecrire_trois_fichiers(str(tmp_path), coffrets, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_geomsupp_controlees"] == 2
        assert resultat["nombre_anomalies"] == 1  # gs2 sans point de leve

    # --- Version 1.1 ---

    def test_v1_1_sans_anomalie(self, tmp_path: Any) -> None:
        coffrets = [_feature_coffret("c1", "gs1", statut=VALEUR_STATUT_V1_1)]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR)]
        _ecrire_trois_fichiers(str(tmp_path), coffrets, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["version_detectee"] == VERSION_DEFAUT

    def test_v1_1_coffret_autre_statut_ignore(self, tmp_path: Any) -> None:
        # gs2 est lie a un coffret sans UnderCommissionning : pas controle
        coffrets = [
            _feature_coffret("c1", "gs1", statut=VALEUR_STATUT_V1_1),
            _feature_coffret("c2", "gs2", statut="AutreStatut"),
        ]
        geomsupp = [
            _feature_geomsupp("gs1", _POLY_1M),
            _feature_geomsupp("gs2", _POLY_LOIN),
        ]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR)]
        _ecrire_trois_fichiers(str(tmp_path), coffrets, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_geomsupp_controlees"] == 1
        assert resultat["nombre_anomalies"] == 0

    def test_v1_1_coffret_sans_statut_ignore(self, tmp_path: Any) -> None:
        coffrets = [_feature_coffret("c1", "gs1", statut=None)]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = []
        _ecrire_trois_fichiers(str(tmp_path), coffrets, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path), version="1.1")
        assert resultat["nombre_geomsupp_controlees"] == 0
        assert resultat["nombre_anomalies"] == 0

    # --- Gestion de version ---

    def test_version_auto_detecte_v1_0_via_type_leve(self, tmp_path: Any) -> None:
        coffrets = [_feature_coffret("c1", "gs1")]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR, avec_type_leve=True)]
        _ecrire_trois_fichiers(str(tmp_path), coffrets, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path), version=JETON_AUTO)
        assert resultat["version_detectee"] == "1.0"

    def test_version_auto_repli_v1_1_sans_type_leve(self, tmp_path: Any) -> None:
        coffrets = [_feature_coffret("c1", "gs1", statut=VALEUR_STATUT_V1_1)]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR)]
        _ecrire_trois_fichiers(str(tmp_path), coffrets, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path), version=JETON_AUTO)
        assert resultat["version_detectee"] == VERSION_DEFAUT

    def test_version_explicite_1_1_surcharge_detection(self, tmp_path: Any) -> None:
        # TypeLeve present (signal v1.0) mais version forcee a 1.1
        coffrets = [
            _feature_coffret("c1", "gs1", statut=VALEUR_STATUT_V1_1),
            _feature_coffret("c2", "gs2"),  # sans statut : exclu en v1.1
        ]
        geomsupp = [
            _feature_geomsupp("gs1", _POLY_1M),
            _feature_geomsupp("gs2", _POLY_LOIN),
        ]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR, avec_type_leve=True)]
        _ecrire_trois_fichiers(str(tmp_path), coffrets, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path), version="1.1")
        assert resultat["version_detectee"] == "1.1"
        # gs2 exclu (pas de statut), gs1 a un point de leve : 0 anomalie
        assert resultat["nombre_geomsupp_controlees"] == 1
        assert resultat["nombre_anomalies"] == 0

    def test_version_explicite_1_0_surcharge_detection(self, tmp_path: Any) -> None:
        # Pas de TypeLeve (signal v1.1) mais version forcee a 1.0 : tous les coffrets inclus
        coffrets = [
            _feature_coffret("c1", "gs1"),
            _feature_coffret("c2", "gs2"),
        ]
        geomsupp = [
            _feature_geomsupp("gs1", _POLY_1M),
            _feature_geomsupp("gs2", _POLY_LOIN),
        ]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR)]
        _ecrire_trois_fichiers(str(tmp_path), coffrets, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path), version="1.0")
        assert resultat["version_detectee"] == "1.0"
        assert resultat["nombre_geomsupp_controlees"] == 2
        assert resultat["nombre_anomalies"] == 1  # gs2 sans point de leve

    # --- Comportements communs ---

    def test_rapport_inclut_version_detectee(self, tmp_path: Any) -> None:
        _ecrire_trois_fichiers(str(tmp_path), [], [], [])
        resultat = executer_controle_cli(str(tmp_path))
        assert "version_detectee" in resultat
        assert resultat["priorite"] == PRIORITE_ANOMALIE

    def test_ecrit_fichier_geojson_sortie(self, tmp_path: Any) -> None:
        coffrets = [_feature_coffret("c1", "gs1")]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_EXTERIEUR, avec_type_leve=True)]
        _ecrire_trois_fichiers(str(tmp_path), coffrets, geomsupp, points)
        executer_controle_cli(str(tmp_path))
        chemin_sortie = str(tmp_path / FICHIER_SORTIE)
        assert os.path.isfile(chemin_sortie)
        with open(chemin_sortie, encoding="utf-8") as f:
            contenu = json.load(f)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 1

    def test_repertoire_sortie_distinct(self, tmp_path: Any) -> None:
        coffrets = [_feature_coffret("c1", "gs1")]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_EXTERIEUR, avec_type_leve=True)]
        _ecrire_trois_fichiers(str(tmp_path), coffrets, geomsupp, points)
        dossier_sortie = str(tmp_path / "sortie")
        resultat = executer_controle_cli(str(tmp_path), dossier_sortie)
        assert resultat["succes"] is True
        assert os.path.isfile(os.path.join(dossier_sortie, FICHIER_SORTIE))

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        coffrets = [_feature_coffret("c1", "gs1")]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR, avec_type_leve=True)]
        _ecrire_trois_fichiers(str(tmp_path), coffrets, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(os.path.join(str(tmp_path), FICHIER_SORTIE))

    def test_geomsupp_non_liee_non_comptee(self, tmp_path: Any) -> None:
        coffrets = [_feature_coffret("c1", "gs1")]
        geomsupp = [
            _feature_geomsupp("gs1", _POLY_1M),
            _feature_geomsupp("gs_orpheline", _POLY_LOIN),
        ]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR, avec_type_leve=True)]
        _ecrire_trois_fichiers(str(tmp_path), coffrets, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_geomsupp_controlees"] == 1
