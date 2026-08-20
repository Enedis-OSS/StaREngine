"""
Tests unitaires du controle E206 (point de leve sur les sommets des geomsupp
de batiments techniques rattaches a un poste electrique).

Couvre :
- extraction des batiments lies a un poste eligible (Statut UnderCommissionning)
- extraction des geomsupp liees aux batiments eligibles
- construction de l'ensemble des coordonnees de points de leve (snapping, Z ignore)
- extraction des sommets 2D (MultiPolygon / Polygon, fermeture d'anneau dedupliquee)
- detection sur les SOMMETS uniquement (point sur sommet / arete / interieur)
- construction du GeoJSON de sortie (champ version inclus)
- execution CLI bout en bout via tmp_path (modes auto et explicite)
"""

from __future__ import annotations

import json
import os
from typing import Any

from controle_e204 import CHAMP_TYPE_LEVE, JETON_AUTO, VERSION_DEFAUT
from controle_e206 import (
    CHAMP_CONTENEUR_HREF,
    CHAMP_HREF_GEOM_SUPP,
    CHAMP_STATUT,
    FICHIER_BATIMENT,
    FICHIER_GEOM_SUPP,
    FICHIER_POINT_LEVE,
    FICHIER_POSTE,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    VALEUR_STATUT_ELIGIBLE,
    charger_coordonnees_points_leve,
    construire_geojson_ecarts,
    detecter_geomsupp_sans_point_leve_sur_sommets,
    executer_controle_cli,
    extraire_hrefs_geomsupp_de_batiments,
    extraire_ids_batiments_de_postes_eligibles,
    extraire_sommets_2d,
)
from utils_tests import (
    construire_feature,
    construire_feature_avec_proprietes,
    ecrire_collection,
)

# ---------------------------------------------------------------------------
# Donnees de test partagees
# ---------------------------------------------------------------------------

# Carre 2D 1m x 1m. Sommets : (0,0) (1,0) (1,1) (0,1).
_POLY_1M = [[[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]]]

# Carre 3D 1m x 1m : verifie que la composante Z est ignoree.
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

# Carre loin du precedent (sommets a 100,100 ...).
_POLY_LOIN = [[[[100.0, 100.0], [101.0, 100.0], [101.0, 101.0], [100.0, 101.0], [100.0, 100.0]]]]

_POINT_SUR_SOMMET = [0.0, 0.0]  # coincide avec un sommet de _POLY_1M
_POINT_SUR_ARETE = [0.5, 0.0]  # milieu d'une arete : sur la geometrie, pas un sommet
_POINT_INTERIEUR = [0.5, 0.5]  # interieur : sur la geometrie, pas un sommet
_POINT_EXTERIEUR = [50.0, 50.0]


def _feature_poste(
    identifiant: str,
    conteneur_href: str | None,
    statut: str | None = None,
) -> dict[str, Any]:
    """Feature poste electrique Point avec conteneur_href et statut optionnels."""
    props: dict[str, Any] = {}
    if conteneur_href is not None:
        props[CHAMP_CONTENEUR_HREF] = conteneur_href
    if statut is not None:
        props[CHAMP_STATUT] = statut
    return construire_feature_avec_proprietes(identifiant, "Point", [0.0, 0.0], props)


def _feature_batiment(identifiant: str, geomsupp_href: str | None) -> dict[str, Any]:
    """Feature batiment technique Point avec geometriesupplementaire_href optionnel."""
    props: dict[str, Any] = {}
    if geomsupp_href is not None:
        props[CHAMP_HREF_GEOM_SUPP] = geomsupp_href
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
# Tests de extraire_ids_batiments_de_postes_eligibles
# ---------------------------------------------------------------------------


class TestExtraireIdsBatimentsDePostesEligibles:
    def test_poste_eligible_inclus(self) -> None:
        features = [_feature_poste("p1", "bat1", statut=VALEUR_STATUT_ELIGIBLE)]
        assert extraire_ids_batiments_de_postes_eligibles(features) == frozenset({"bat1"})

    def test_poste_statut_different_exclu(self) -> None:
        features = [_feature_poste("p1", "bat1", statut="AutreStatut")]
        assert extraire_ids_batiments_de_postes_eligibles(features) == frozenset()

    def test_poste_sans_statut_exclu(self) -> None:
        features = [_feature_poste("p1", "bat1", statut=None)]
        assert extraire_ids_batiments_de_postes_eligibles(features) == frozenset()

    def test_poste_sans_conteneur_ignore(self) -> None:
        features = [_feature_poste("p1", None, statut=VALEUR_STATUT_ELIGIBLE)]
        assert extraire_ids_batiments_de_postes_eligibles(features) == frozenset()

    def test_conteneur_multi_valeurs_separees_virgule(self) -> None:
        features = [_feature_poste("p1", "bat1,bat2", statut=VALEUR_STATUT_ELIGIBLE)]
        assert extraire_ids_batiments_de_postes_eligibles(features) == frozenset({"bat1", "bat2"})

    def test_meme_batiment_plusieurs_postes_deduplique(self) -> None:
        features = [
            _feature_poste("p1", "bat1", statut=VALEUR_STATUT_ELIGIBLE),
            _feature_poste("p2", "bat1", statut=VALEUR_STATUT_ELIGIBLE),
        ]
        assert extraire_ids_batiments_de_postes_eligibles(features) == frozenset({"bat1"})

    def test_filtre_mixte(self) -> None:
        features = [
            _feature_poste("p1", "bat1", statut=VALEUR_STATUT_ELIGIBLE),  # inclus
            _feature_poste("p2", "bat2", statut="AutreStatut"),  # exclu
            _feature_poste("p3", "bat3", statut=None),  # exclu
        ]
        assert extraire_ids_batiments_de_postes_eligibles(features) == frozenset({"bat1"})

    def test_collection_vide(self) -> None:
        assert extraire_ids_batiments_de_postes_eligibles([]) == frozenset()


# ---------------------------------------------------------------------------
# Tests de extraire_hrefs_geomsupp_de_batiments
# ---------------------------------------------------------------------------


class TestExtraireHrefsGeomSuppDeBatiments:
    def test_batiment_eligible_inclus(self) -> None:
        features = [_feature_batiment("bat1", "gs1")]
        assert extraire_hrefs_geomsupp_de_batiments(features, frozenset({"bat1"})) == frozenset({"gs1"})

    def test_batiment_non_eligible_ignore(self) -> None:
        features = [_feature_batiment("bat1", "gs1")]
        assert extraire_hrefs_geomsupp_de_batiments(features, frozenset({"bat_autre"})) == frozenset()

    def test_batiment_sans_href_ignore(self) -> None:
        features = [_feature_batiment("bat1", None)]
        assert extraire_hrefs_geomsupp_de_batiments(features, frozenset({"bat1"})) == frozenset()

    def test_meme_geomsupp_plusieurs_batiments_deduplique(self) -> None:
        features = [
            _feature_batiment("bat1", "gs1"),
            _feature_batiment("bat2", "gs1"),
        ]
        ids = frozenset({"bat1", "bat2"})
        assert extraire_hrefs_geomsupp_de_batiments(features, ids) == frozenset({"gs1"})

    def test_ids_eligibles_vides(self) -> None:
        features = [_feature_batiment("bat1", "gs1")]
        assert extraire_hrefs_geomsupp_de_batiments(features, frozenset()) == frozenset()

    def test_collection_vide(self) -> None:
        assert extraire_hrefs_geomsupp_de_batiments([], frozenset({"bat1"})) == frozenset()


# ---------------------------------------------------------------------------
# Tests de charger_coordonnees_points_leve
# ---------------------------------------------------------------------------


class TestChargerCoordonneesPointsLeve:
    def test_point_2d_charge(self) -> None:
        features = [_feature_point_leve("p1", [1.0, 2.0])]
        assert charger_coordonnees_points_leve(features) == frozenset({(1.0, 2.0)})

    def test_point_3d_z_ignore(self) -> None:
        features = [_feature_point_leve("p1", [1.0, 2.0, 5.0])]
        assert charger_coordonnees_points_leve(features) == frozenset({(1.0, 2.0)})

    def test_snapping_precision(self) -> None:
        # 1.234 et 1.236 snappes au cm donnent la meme cle
        features = [
            _feature_point_leve("p1", [1.234, 2.0]),
            _feature_point_leve("p2", [1.236, 2.0]),
        ]
        assert charger_coordonnees_points_leve(features) == frozenset({(1.23, 2.0), (1.24, 2.0)})

    def test_geometrie_non_point_ignoree(self) -> None:
        ligne = construire_feature("l1", "LineString", [[0.0, 0.0], [1.0, 1.0]])
        assert charger_coordonnees_points_leve([ligne]) == frozenset()

    def test_geometrie_absente_ignoree(self) -> None:
        feature: dict[str, Any] = {"type": "Feature", "properties": {"id": "p1"}, "geometry": None}
        assert charger_coordonnees_points_leve([feature]) == frozenset()

    def test_collection_vide(self) -> None:
        assert charger_coordonnees_points_leve([]) == frozenset()


# ---------------------------------------------------------------------------
# Tests de extraire_sommets_2d
# ---------------------------------------------------------------------------


class TestExtraireSommets2d:
    def test_multipolygon_sommets(self) -> None:
        geom = {"type": "MultiPolygon", "coordinates": _POLY_1M}
        assert extraire_sommets_2d(geom) == {(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)}

    def test_fermeture_anneau_dedupliquee(self) -> None:
        # 5 positions dans l'anneau (premier == dernier) -> 4 sommets uniques
        geom = {"type": "MultiPolygon", "coordinates": _POLY_1M}
        assert len(extraire_sommets_2d(geom)) == 4

    def test_z_ignore(self) -> None:
        geom = {"type": "MultiPolygon", "coordinates": _POLY_1M_3D}
        assert extraire_sommets_2d(geom) == {(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)}

    def test_polygon_simple(self) -> None:
        geom = {"type": "Polygon", "coordinates": _POLY_1M[0]}
        assert extraire_sommets_2d(geom) == {(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)}

    def test_coordinates_absentes(self) -> None:
        assert extraire_sommets_2d({"type": "MultiPolygon"}) == set()


# ---------------------------------------------------------------------------
# Tests de detecter_geomsupp_sans_point_leve_sur_sommets
# ---------------------------------------------------------------------------


class TestDetecterGeomSuppSansPointLeveSurSommets:
    def _coords(self, coordonnees_liste: list[list[float]]) -> frozenset[tuple[float, float]]:
        features = [_feature_point_leve(f"p{i}", c) for i, c in enumerate(coordonnees_liste)]
        return charger_coordonnees_points_leve(features)

    def test_point_sur_sommet_pas_anomalie(self) -> None:
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        coords = self._coords([_POINT_SUR_SOMMET])
        assert detecter_geomsupp_sans_point_leve_sur_sommets(geomsupp, frozenset({"gs1"}), coords) == []

    def test_point_sur_arete_produit_anomalie(self) -> None:
        # E206 : un point sur une arete (pas un sommet) est une anomalie.
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        coords = self._coords([_POINT_SUR_ARETE])
        anomalies = detecter_geomsupp_sans_point_leve_sur_sommets(geomsupp, frozenset({"gs1"}), coords)
        assert len(anomalies) == 1
        assert anomalies[0]["id_geomsupp"] == "gs1"

    def test_point_interieur_produit_anomalie(self) -> None:
        # E206 : un point interieur (pas un sommet) est une anomalie.
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        coords = self._coords([_POINT_INTERIEUR])
        assert len(detecter_geomsupp_sans_point_leve_sur_sommets(geomsupp, frozenset({"gs1"}), coords)) == 1

    def test_point_exterieur_produit_anomalie(self) -> None:
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        coords = self._coords([_POINT_EXTERIEUR])
        assert len(detecter_geomsupp_sans_point_leve_sur_sommets(geomsupp, frozenset({"gs1"}), coords)) == 1

    def test_point_3d_sur_sommet_pas_anomalie(self) -> None:
        # Le point de leve porte un Z ; la comparaison reste planimetrique.
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M_3D)]
        coords = self._coords([[0.0, 0.0, 99.0]])
        assert detecter_geomsupp_sans_point_leve_sur_sommets(geomsupp, frozenset({"gs1"}), coords) == []

    def test_aucun_point_leve_toutes_anomalies(self) -> None:
        geomsupp = [
            _feature_geomsupp("gs1", _POLY_1M),
            _feature_geomsupp("gs2", _POLY_LOIN),
        ]
        ids = frozenset({"gs1", "gs2"})
        assert len(detecter_geomsupp_sans_point_leve_sur_sommets(geomsupp, ids, frozenset())) == 2

    def test_geomsupp_non_liee_ignoree(self) -> None:
        geomsupp = [_feature_geomsupp("gs_orpheline", _POLY_1M)]
        assert detecter_geomsupp_sans_point_leve_sur_sommets(geomsupp, frozenset({"gs_autre"}), frozenset()) == []

    def test_ids_lies_vides(self) -> None:
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        assert detecter_geomsupp_sans_point_leve_sur_sommets(geomsupp, frozenset(), frozenset()) == []

    def test_deux_geomsupp_une_anomalie(self) -> None:
        geomsupp = [
            _feature_geomsupp("gs1", _POLY_1M),
            _feature_geomsupp("gs2", _POLY_LOIN),
        ]
        ids = frozenset({"gs1", "gs2"})
        coords = self._coords([_POINT_SUR_SOMMET])  # sommet de gs1 uniquement
        anomalies = detecter_geomsupp_sans_point_leve_sur_sommets(geomsupp, ids, coords)
        assert len(anomalies) == 1
        assert anomalies[0]["id_geomsupp"] == "gs2"

    def test_geomsupp_sans_geometrie_ignoree(self) -> None:
        feature: dict[str, Any] = {"type": "Feature", "properties": {"id": "gs1"}, "geometry": None}
        assert detecter_geomsupp_sans_point_leve_sur_sommets([feature], frozenset({"gs1"}), frozenset()) == []

    def test_geomsupp_sans_sommet_ignoree(self) -> None:
        feature = {
            "type": "Feature",
            "properties": {"id": "gs1"},
            "geometry": {"type": "MultiPolygon", "coordinates": []},
        }
        assert detecter_geomsupp_sans_point_leve_sur_sommets([feature], frozenset({"gs1"}), frozenset()) == []

    def test_anomalie_contient_geometrie_source(self) -> None:
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        anomalies = detecter_geomsupp_sans_point_leve_sur_sommets(geomsupp, frozenset({"gs1"}), frozenset())
        assert anomalies[0]["geometrie"]["type"] == "MultiPolygon"


# ---------------------------------------------------------------------------
# Tests de construire_geojson_ecarts
# ---------------------------------------------------------------------------


class TestConstruireGeojsonEcarts:
    def test_collection_vide(self) -> None:
        assert construire_geojson_ecarts([], "1.1") == {"type": "FeatureCollection", "features": []}

    def test_structure_feature(self) -> None:
        anomalies = [{"id_geomsupp": "gs1", "geometrie": {"type": "MultiPolygon", "coordinates": _POLY_1M}}]
        geojson = construire_geojson_ecarts(anomalies, "1.1")
        feat = geojson["features"][0]
        assert feat["geometry"]["type"] == "MultiPolygon"
        props = feat["properties"]
        assert props["id_entite"] == "gs1"
        assert props["type_anomalie"] == "point_leve_sommet_absent"
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["version"] == "1.1"

    def test_version_incluse_dans_proprietes(self) -> None:
        anomalies = [{"id_geomsupp": "gs1", "geometrie": {"type": "MultiPolygon", "coordinates": _POLY_1M}}]
        geojson = construire_geojson_ecarts(anomalies, "1.0")
        assert geojson["features"][0]["properties"]["version"] == "1.0"

    def test_crs_propage_si_present(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([], "1.1", crs=crs)["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        assert "crs" not in construire_geojson_ecarts([], "1.1")


# ---------------------------------------------------------------------------
# Helpers CLI
# ---------------------------------------------------------------------------


def _ecrire_quatre_fichiers(
    repertoire: str,
    features_postes: list[dict[str, Any]],
    features_batiments: list[dict[str, Any]],
    features_geomsupp: list[dict[str, Any]],
    features_points: list[dict[str, Any]],
) -> None:
    """Ecrit les quatre fichiers sources dans le repertoire de test."""
    ecrire_collection(os.path.join(repertoire, FICHIER_POSTE), features_postes)
    ecrire_collection(os.path.join(repertoire, FICHIER_BATIMENT), features_batiments)
    ecrire_collection(os.path.join(repertoire, FICHIER_GEOM_SUPP), features_geomsupp)
    ecrire_collection(os.path.join(repertoire, FICHIER_POINT_LEVE), features_points)


def _chaine_nominale(
    point_coords: list[float],
    avec_type_leve: bool = False,
    statut_poste: str = VALEUR_STATUT_ELIGIBLE,
) -> tuple[list[dict[str, Any]], ...]:
    """Construit une chaine Poste -> Batiment -> GeomSupp -> PointLeve coherente."""
    postes = [_feature_poste("p1", "bat1", statut=statut_poste)]
    batiments = [_feature_batiment("bat1", "gs1")]
    geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
    points = [_feature_point_leve("pl1", point_coords, avec_type_leve=avec_type_leve)]
    return postes, batiments, geomsupp, points


# ---------------------------------------------------------------------------
# Tests CLI bout en bout
# ---------------------------------------------------------------------------


class TestCli:
    def test_fichier_poste_absent_retourne_erreur(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_BATIMENT), [])
        ecrire_collection(str(tmp_path / FICHIER_GEOM_SUPP), [])
        ecrire_collection(str(tmp_path / FICHIER_POINT_LEVE), [])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert "erreur" in resultat

    def test_fichier_batiment_absent_retourne_erreur(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_POSTE), [])
        ecrire_collection(str(tmp_path / FICHIER_GEOM_SUPP), [])
        ecrire_collection(str(tmp_path / FICHIER_POINT_LEVE), [])
        assert executer_controle_cli(str(tmp_path))["succes"] is False

    def test_fichier_geomsupp_absent_retourne_erreur(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_POSTE), [])
        ecrire_collection(str(tmp_path / FICHIER_BATIMENT), [])
        ecrire_collection(str(tmp_path / FICHIER_POINT_LEVE), [])
        assert executer_controle_cli(str(tmp_path))["succes"] is False

    def test_fichier_point_leve_absent_retourne_erreur(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_POSTE), [])
        ecrire_collection(str(tmp_path / FICHIER_BATIMENT), [])
        ecrire_collection(str(tmp_path / FICHIER_GEOM_SUPP), [])
        assert executer_controle_cli(str(tmp_path))["succes"] is False

    # --- Version 1.0 (TypeLeve present) ---

    def test_v1_0_sans_anomalie(self, tmp_path: Any) -> None:
        postes, batiments, geomsupp, points = _chaine_nominale(_POINT_SUR_SOMMET, avec_type_leve=True)
        _ecrire_quatre_fichiers(str(tmp_path), postes, batiments, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["version_detectee"] == "1.0"
        assert resultat["nombre_geomsupp_controlees"] == 1
        assert resultat["nombre_anomalies"] == 0

    def test_v1_0_avec_anomalie_point_hors_sommet(self, tmp_path: Any) -> None:
        postes, batiments, geomsupp, points = _chaine_nominale(_POINT_INTERIEUR, avec_type_leve=True)
        _ecrire_quatre_fichiers(str(tmp_path), postes, batiments, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["version_detectee"] == "1.0"
        assert resultat["nombre_anomalies"] == 1

    # --- Version 1.1 (TypeLeve absent -> repli) ---

    def test_v1_1_sans_anomalie(self, tmp_path: Any) -> None:
        postes, batiments, geomsupp, points = _chaine_nominale(_POINT_SUR_SOMMET)
        _ecrire_quatre_fichiers(str(tmp_path), postes, batiments, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["version_detectee"] == VERSION_DEFAUT
        assert resultat["nombre_anomalies"] == 0

    def test_v1_1_avec_anomalie(self, tmp_path: Any) -> None:
        postes, batiments, geomsupp, points = _chaine_nominale(_POINT_EXTERIEUR)
        _ecrire_quatre_fichiers(str(tmp_path), postes, batiments, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1

    # --- Filtrage metier ---

    def test_poste_non_eligible_geomsupp_non_controlee(self, tmp_path: Any) -> None:
        # Statut different d'UnderCommissionning : la chaine n'est pas controlee.
        postes, batiments, geomsupp, points = _chaine_nominale(_POINT_EXTERIEUR, statut_poste="AutreStatut")
        _ecrire_quatre_fichiers(str(tmp_path), postes, batiments, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_geomsupp_controlees"] == 0
        assert resultat["nombre_anomalies"] == 0

    def test_batiment_non_rattache_a_poste_ignore(self, tmp_path: Any) -> None:
        # Le batiment existe mais aucun poste eligible ne le reference.
        postes = [_feature_poste("p1", "bat_autre", statut=VALEUR_STATUT_ELIGIBLE)]
        batiments = [_feature_batiment("bat1", "gs1")]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points: list[dict[str, Any]] = []
        _ecrire_quatre_fichiers(str(tmp_path), postes, batiments, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_geomsupp_controlees"] == 0
        assert resultat["nombre_anomalies"] == 0

    def test_geomsupp_non_liee_non_comptee(self, tmp_path: Any) -> None:
        postes = [_feature_poste("p1", "bat1", statut=VALEUR_STATUT_ELIGIBLE)]
        batiments = [_feature_batiment("bat1", "gs1")]
        geomsupp = [
            _feature_geomsupp("gs1", _POLY_1M),
            _feature_geomsupp("gs_orpheline", _POLY_LOIN),
        ]
        points = [_feature_point_leve("pl1", _POINT_SUR_SOMMET, avec_type_leve=True)]
        _ecrire_quatre_fichiers(str(tmp_path), postes, batiments, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_geomsupp_controlees"] == 1
        assert resultat["nombre_anomalies"] == 0

    # --- Gestion de version ---

    def test_version_auto_detecte_v1_0(self, tmp_path: Any) -> None:
        postes, batiments, geomsupp, points = _chaine_nominale(_POINT_SUR_SOMMET, avec_type_leve=True)
        _ecrire_quatre_fichiers(str(tmp_path), postes, batiments, geomsupp, points)
        assert executer_controle_cli(str(tmp_path), version=JETON_AUTO)["version_detectee"] == "1.0"

    def test_version_auto_repli_v1_1(self, tmp_path: Any) -> None:
        postes, batiments, geomsupp, points = _chaine_nominale(_POINT_SUR_SOMMET)
        _ecrire_quatre_fichiers(str(tmp_path), postes, batiments, geomsupp, points)
        assert executer_controle_cli(str(tmp_path), version=JETON_AUTO)["version_detectee"] == VERSION_DEFAUT

    def test_version_explicite_surcharge_detection(self, tmp_path: Any) -> None:
        # TypeLeve present (signal v1.0) mais version forcee a 1.1.
        postes, batiments, geomsupp, points = _chaine_nominale(_POINT_SUR_SOMMET, avec_type_leve=True)
        _ecrire_quatre_fichiers(str(tmp_path), postes, batiments, geomsupp, points)
        assert executer_controle_cli(str(tmp_path), version="1.1")["version_detectee"] == "1.1"

    # --- Comportements communs / sortie ---

    def test_rapport_inclut_priorite_et_version(self, tmp_path: Any) -> None:
        _ecrire_quatre_fichiers(str(tmp_path), [], [], [], [])
        resultat = executer_controle_cli(str(tmp_path))
        assert "version_detectee" in resultat
        assert resultat["priorite"] == PRIORITE_ANOMALIE

    def test_ecrit_fichier_geojson_sortie(self, tmp_path: Any) -> None:
        postes, batiments, geomsupp, points = _chaine_nominale(_POINT_EXTERIEUR, avec_type_leve=True)
        _ecrire_quatre_fichiers(str(tmp_path), postes, batiments, geomsupp, points)
        executer_controle_cli(str(tmp_path))
        chemin_sortie = str(tmp_path / FICHIER_SORTIE)
        assert os.path.isfile(chemin_sortie)
        with open(chemin_sortie, encoding="utf-8") as f:
            contenu = json.load(f)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 1

    def test_repertoire_sortie_distinct(self, tmp_path: Any) -> None:
        postes, batiments, geomsupp, points = _chaine_nominale(_POINT_EXTERIEUR)
        _ecrire_quatre_fichiers(str(tmp_path), postes, batiments, geomsupp, points)
        dossier_sortie = str(tmp_path / "sortie")
        resultat = executer_controle_cli(str(tmp_path), dossier_sortie)
        assert resultat["succes"] is True
        assert os.path.isfile(os.path.join(dossier_sortie, FICHIER_SORTIE))

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        postes, batiments, geomsupp, points = _chaine_nominale(_POINT_SUR_SOMMET, avec_type_leve=True)
        _ecrire_quatre_fichiers(str(tmp_path), postes, batiments, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(os.path.join(str(tmp_path), FICHIER_SORTIE))
