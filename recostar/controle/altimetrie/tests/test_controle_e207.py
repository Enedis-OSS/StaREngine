"""
Tests unitaires du controle E207 (coherence points de leve / geomsupp de supports).

E207 reutilise le moteur de detection spatiale d'E205 (deja teste dans
test_controle_e205). Ces tests ciblent donc les specificites d'E207 :
- filtrage des supports eligibles (Statut UnderCommissionning) ;
- garde de version : desactivation en v1.0 (applicable=False), actif en v1.1 ;
- orchestration CLI bout en bout (superposition sur toute la geometrie).
"""

from __future__ import annotations

import json
import os
from typing import Any

from controle_e204 import CHAMP_TYPE_LEVE, JETON_AUTO
from controle_e205 import CHAMP_HREF_GEOM_SUPP, CHAMP_STATUT, VALEUR_STATUT_V1_1
from controle_e207 import (
    FICHIER_GEOM_SUPP,
    FICHIER_POINT_LEVE,
    FICHIER_SORTIE,
    FICHIER_SUPPORT,
    PRIORITE_ANOMALIE,
    VERSION_APPLICABLE,
    executer_controle_cli,
    extraire_hrefs_geomsupp_liees_supports,
)
from utils_tests import (
    construire_feature,
    construire_feature_avec_proprietes,
    ecrire_collection,
)

# ---------------------------------------------------------------------------
# Donnees de test partagees
# ---------------------------------------------------------------------------

# Carre 2D 1m x 1m : le point (0.5, 0.5) est a l'interieur, (0,0) est un sommet.
_POLY_1M = [[[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]]]
_POLY_LOIN = [[[[100.0, 100.0], [101.0, 100.0], [101.0, 101.0], [100.0, 101.0], [100.0, 100.0]]]]

_POINT_INTERIEUR = [0.5, 0.5]  # sur la surface (accepte par E205/E207)
_POINT_EXTERIEUR = [50.0, 50.0]


def _feature_support(
    identifiant: str,
    href: str | None,
    statut: str | None = None,
) -> dict[str, Any]:
    """Feature support Point avec geometriesupplementaire_href et statut optionnels."""
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
# Tests de extraire_hrefs_geomsupp_liees_supports
# ---------------------------------------------------------------------------


class TestExtraireHrefsGeomSuppLieesSupports:
    def test_support_under_commissioning_inclus(self) -> None:
        features = [_feature_support("s1", "gs1", statut=VALEUR_STATUT_V1_1)]
        assert extraire_hrefs_geomsupp_liees_supports(features) == frozenset({"gs1"})

    def test_support_statut_different_exclu(self) -> None:
        features = [_feature_support("s1", "gs1", statut="AutreStatut")]
        assert extraire_hrefs_geomsupp_liees_supports(features) == frozenset()

    def test_support_sans_statut_exclu(self) -> None:
        features = [_feature_support("s1", "gs1", statut=None)]
        assert extraire_hrefs_geomsupp_liees_supports(features) == frozenset()

    def test_support_sans_href_ignore(self) -> None:
        features = [_feature_support("s1", None, statut=VALEUR_STATUT_V1_1)]
        assert extraire_hrefs_geomsupp_liees_supports(features) == frozenset()

    def test_href_vide_ignore(self) -> None:
        props = {CHAMP_HREF_GEOM_SUPP: "", CHAMP_STATUT: VALEUR_STATUT_V1_1}
        feature = construire_feature_avec_proprietes("s1", "Point", [0.0, 0.0], props)
        assert extraire_hrefs_geomsupp_liees_supports([feature]) == frozenset()

    def test_meme_href_plusieurs_supports_deduplique(self) -> None:
        features = [
            _feature_support("s1", "gs1", statut=VALEUR_STATUT_V1_1),
            _feature_support("s2", "gs1", statut=VALEUR_STATUT_V1_1),
        ]
        assert extraire_hrefs_geomsupp_liees_supports(features) == frozenset({"gs1"})

    def test_filtre_mixte(self) -> None:
        features = [
            _feature_support("s1", "gs1", statut=VALEUR_STATUT_V1_1),  # inclus
            _feature_support("s2", "gs2", statut="AutreStatut"),  # exclu
            _feature_support("s3", "gs3", statut=None),  # exclu
        ]
        assert extraire_hrefs_geomsupp_liees_supports(features) == frozenset({"gs1"})

    def test_collection_vide(self) -> None:
        assert extraire_hrefs_geomsupp_liees_supports([]) == frozenset()


# ---------------------------------------------------------------------------
# Helpers CLI
# ---------------------------------------------------------------------------


def _ecrire_trois_fichiers(
    repertoire: str,
    features_supports: list[dict[str, Any]],
    features_geomsupp: list[dict[str, Any]],
    features_points: list[dict[str, Any]],
) -> None:
    """Ecrit les trois fichiers sources dans le repertoire de test."""
    ecrire_collection(os.path.join(repertoire, FICHIER_SUPPORT), features_supports)
    ecrire_collection(os.path.join(repertoire, FICHIER_GEOM_SUPP), features_geomsupp)
    ecrire_collection(os.path.join(repertoire, FICHIER_POINT_LEVE), features_points)


# ---------------------------------------------------------------------------
# Tests CLI bout en bout
# ---------------------------------------------------------------------------


class TestCli:
    def test_fichier_point_leve_absent_retourne_erreur(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_SUPPORT), [])
        ecrire_collection(str(tmp_path / FICHIER_GEOM_SUPP), [])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert "erreur" in resultat

    # --- Version 1.1 : controle actif ---

    def test_v1_1_sans_anomalie(self, tmp_path: Any) -> None:
        supports = [_feature_support("s1", "gs1", statut=VALEUR_STATUT_V1_1)]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR)]  # sur la surface
        _ecrire_trois_fichiers(str(tmp_path), supports, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["applicable"] is True
        assert resultat["version_detectee"] == VERSION_APPLICABLE
        assert resultat["nombre_geomsupp_controlees"] == 1
        assert resultat["nombre_anomalies"] == 0

    def test_v1_1_avec_anomalie(self, tmp_path: Any) -> None:
        supports = [_feature_support("s1", "gs1", statut=VALEUR_STATUT_V1_1)]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_EXTERIEUR)]
        _ecrire_trois_fichiers(str(tmp_path), supports, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["applicable"] is True
        assert resultat["nombre_anomalies"] == 1

    def test_v1_1_point_sur_surface_pas_anomalie(self, tmp_path: Any) -> None:
        # Comportement identique a E205 : un point interieur (pas un sommet) valide.
        supports = [_feature_support("s1", "gs1", statut=VALEUR_STATUT_V1_1)]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR)]
        _ecrire_trois_fichiers(str(tmp_path), supports, geomsupp, points)
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_v1_1_support_autre_statut_non_controle(self, tmp_path: Any) -> None:
        supports = [
            _feature_support("s1", "gs1", statut=VALEUR_STATUT_V1_1),
            _feature_support("s2", "gs2", statut="AutreStatut"),
        ]
        geomsupp = [
            _feature_geomsupp("gs1", _POLY_1M),
            _feature_geomsupp("gs2", _POLY_LOIN),
        ]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR)]
        _ecrire_trois_fichiers(str(tmp_path), supports, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_geomsupp_controlees"] == 1
        assert resultat["nombre_anomalies"] == 0

    def test_v1_1_geomsupp_non_liee_non_comptee(self, tmp_path: Any) -> None:
        supports = [_feature_support("s1", "gs1", statut=VALEUR_STATUT_V1_1)]
        geomsupp = [
            _feature_geomsupp("gs1", _POLY_1M),
            _feature_geomsupp("gs_orpheline", _POLY_LOIN),
        ]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR)]
        _ecrire_trois_fichiers(str(tmp_path), supports, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_geomsupp_controlees"] == 1
        assert resultat["nombre_anomalies"] == 0

    def test_v1_1_support_absent_retourne_erreur(self, tmp_path: Any) -> None:
        # En v1.1, le fichier des supports est requis.
        ecrire_collection(str(tmp_path / FICHIER_GEOM_SUPP), [])
        ecrire_collection(str(tmp_path / FICHIER_POINT_LEVE), [])
        assert executer_controle_cli(str(tmp_path), version="1.1")["succes"] is False

    def test_v1_1_geomsupp_absent_retourne_erreur(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_SUPPORT), [])
        ecrire_collection(str(tmp_path / FICHIER_POINT_LEVE), [])
        assert executer_controle_cli(str(tmp_path), version="1.1")["succes"] is False

    # --- Version 1.0 : controle desactive ---

    def test_v1_0_desactive_via_type_leve(self, tmp_path: Any) -> None:
        # TypeLeve present -> v1.0 detectee -> E207 desactive.
        supports = [_feature_support("s1", "gs1", statut=VALEUR_STATUT_V1_1)]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_EXTERIEUR, avec_type_leve=True)]
        _ecrire_trois_fichiers(str(tmp_path), supports, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["applicable"] is False
        assert resultat["version_detectee"] == "1.0"
        assert resultat["nombre_geomsupp_controlees"] == 0
        assert resultat["nombre_anomalies"] == 0

    def test_v1_0_desactive_sans_fichier_support(self, tmp_path: Any) -> None:
        # En v1.0, l'absence du fichier des supports n'est pas bloquante.
        points = [_feature_point_leve("p1", _POINT_EXTERIEUR, avec_type_leve=True)]
        ecrire_collection(str(tmp_path / FICHIER_POINT_LEVE), points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["applicable"] is False

    def test_v1_0_force_desactive(self, tmp_path: Any) -> None:
        supports = [_feature_support("s1", "gs1", statut=VALEUR_STATUT_V1_1)]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_EXTERIEUR)]  # pas de TypeLeve
        _ecrire_trois_fichiers(str(tmp_path), supports, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path), version="1.0")
        assert resultat["applicable"] is False
        assert resultat["nombre_anomalies"] == 0

    # --- Gestion de version ---

    def test_v1_1_auto_repli_sans_type_leve(self, tmp_path: Any) -> None:
        supports = [_feature_support("s1", "gs1", statut=VALEUR_STATUT_V1_1)]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR)]  # pas de TypeLeve -> v1.1
        _ecrire_trois_fichiers(str(tmp_path), supports, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path), version=JETON_AUTO)
        assert resultat["version_detectee"] == VERSION_APPLICABLE
        assert resultat["applicable"] is True

    def test_version_explicite_1_1_surcharge_type_leve(self, tmp_path: Any) -> None:
        # TypeLeve present (signal v1.0) mais version forcee a 1.1 : controle actif.
        supports = [_feature_support("s1", "gs1", statut=VALEUR_STATUT_V1_1)]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_INTERIEUR, avec_type_leve=True)]
        _ecrire_trois_fichiers(str(tmp_path), supports, geomsupp, points)
        resultat = executer_controle_cli(str(tmp_path), version="1.1")
        assert resultat["applicable"] is True
        assert resultat["version_detectee"] == "1.1"

    # --- Sortie ---

    def test_rapport_inclut_priorite_et_version(self, tmp_path: Any) -> None:
        _ecrire_trois_fichiers(str(tmp_path), [], [], [])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["priorite"] == PRIORITE_ANOMALIE
        assert "version_detectee" in resultat
        assert "applicable" in resultat

    def test_ecrit_fichier_geojson_sortie(self, tmp_path: Any) -> None:
        supports = [_feature_support("s1", "gs1", statut=VALEUR_STATUT_V1_1)]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_EXTERIEUR)]
        _ecrire_trois_fichiers(str(tmp_path), supports, geomsupp, points)
        executer_controle_cli(str(tmp_path))
        chemin_sortie = str(tmp_path / FICHIER_SORTIE)
        assert os.path.isfile(chemin_sortie)
        with open(chemin_sortie, encoding="utf-8") as f:
            contenu = json.load(f)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 1

    def test_aucune_sortie_en_v1_0(self, tmp_path: Any) -> None:
        points = [_feature_point_leve("p1", _POINT_EXTERIEUR, avec_type_leve=True)]
        ecrire_collection(str(tmp_path / FICHIER_POINT_LEVE), points)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["applicable"] is False
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_repertoire_sortie_distinct(self, tmp_path: Any) -> None:
        supports = [_feature_support("s1", "gs1", statut=VALEUR_STATUT_V1_1)]
        geomsupp = [_feature_geomsupp("gs1", _POLY_1M)]
        points = [_feature_point_leve("p1", _POINT_EXTERIEUR)]
        _ecrire_trois_fichiers(str(tmp_path), supports, geomsupp, points)
        dossier_sortie = str(tmp_path / "sortie")
        resultat = executer_controle_cli(str(tmp_path), dossier_sortie)
        assert resultat["succes"] is True
        assert os.path.isfile(os.path.join(dossier_sortie, FICHIER_SORTIE))
