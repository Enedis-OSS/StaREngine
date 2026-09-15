"""
Tests de la detection de version RecoStaR (fonctions_communes/version_recostar.py).

Ces tests accompagnent le mecanisme commun plutot qu'un controle : la version
d'un jeu est une propriete de la donnee, pas du controle qui la lit.
"""

import json
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.modele_recostar import CHAMP_TYPE_LEVE, FICHIER_POINT_LEVE
from recostar.controle.fonctions_communes.version_recostar import (
    JETON_AUTO,
    VERSION_DEFAUT,
    VERSIONS_SUPPORTEES,
    detecter_version_depuis_features,
    determiner_version_depuis_repertoire,
    resoudre_version,
)


def _point_v1_0(identifiant: str) -> dict[str, Any]:
    """Point leve V1.0 : le champ TypeLeve y est present."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, CHAMP_TYPE_LEVE: "Altitude"},
        "geometry": {"type": "Point", "coordinates": [0.0, 0.0, 0.0]},
    }


def _point_v1_1(identifiant: str) -> dict[str, Any]:
    """Point leve V1.1 : le champ TypeLeve a ete retire du format."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {"type": "Point", "coordinates": [0.0, 0.0, 0.0]},
    }


class TestReferentielDesVersions:
    """Coherence des constantes exposees."""

    def test_version_par_defaut_supportee(self) -> None:
        assert VERSION_DEFAUT in VERSIONS_SUPPORTEES

    def test_jeton_auto_n_est_pas_une_version(self) -> None:
        """`auto` est une demande de detection, pas une valeur de version."""
        assert JETON_AUTO not in VERSIONS_SUPPORTEES


class TestDetecterVersionDepuisFeatures:
    """Deduction de la version depuis les proprietes des entites."""

    def test_type_leve_present_donne_v1_0(self) -> None:
        assert detecter_version_depuis_features([_point_v1_0("p1")]) == "1.0"

    def test_type_leve_absent_non_concluant(self) -> None:
        """L'absence du champ ne prouve rien : l'appelant decide du repli."""
        assert detecter_version_depuis_features([_point_v1_1("p1")]) is None

    def test_collection_vide_non_concluante(self) -> None:
        assert detecter_version_depuis_features([]) is None

    def test_une_seule_entite_suffit(self) -> None:
        """Le champ n'existant pas en V1.1, une occurrence tranche."""
        features = [_point_v1_1("p1"), _point_v1_0("p2")]
        assert detecter_version_depuis_features(features) == "1.0"

    def test_proprietes_absentes(self) -> None:
        feature: dict[str, Any] = {"type": "Feature", "properties": None, "geometry": None}
        assert detecter_version_depuis_features([feature]) is None


class TestResoudreVersion:
    """Resolution depuis des entites deja chargees."""

    def test_auto_detecte_v1_0(self) -> None:
        assert resoudre_version(JETON_AUTO, [_point_v1_0("p1")]) == "1.0"

    def test_auto_replie_sur_le_defaut(self) -> None:
        assert resoudre_version(JETON_AUTO, [_point_v1_1("p1")]) == VERSION_DEFAUT

    def test_version_explicite_prime_sur_la_detection(self) -> None:
        """Une version imposee n'est jamais contredite par le contenu."""
        assert resoudre_version("1.0", [_point_v1_1("p1")]) == "1.0"
        assert resoudre_version("1.1", [_point_v1_0("p1")]) == "1.1"

    def test_auto_sur_collection_vide(self) -> None:
        assert resoudre_version(JETON_AUTO, []) == VERSION_DEFAUT


class TestDeterminerVersionDepuisRepertoire:
    """Resolution pour les controles dont les points leves ne sont pas une source."""

    def _ecrire_points(self, repertoire: Path, features: list[dict[str, Any]]) -> None:
        collection = {"type": "FeatureCollection", "features": features}
        (repertoire / FICHIER_POINT_LEVE).write_text(json.dumps(collection), encoding="utf-8")

    def test_version_explicite_ne_lit_pas_le_disque(self, tmp_path: Path) -> None:
        """Sans couche de detection, une version imposee doit suffire."""
        assert determiner_version_depuis_repertoire(str(tmp_path), "1.0") == "1.0"

    def test_couche_absente_replie_sur_le_defaut(self, tmp_path: Path) -> None:
        """La couche n'etant pas une source de ces controles, son absence
        ne doit pas les empecher de s'executer."""
        assert determiner_version_depuis_repertoire(str(tmp_path), JETON_AUTO) == VERSION_DEFAUT

    def test_detection_depuis_la_couche(self, tmp_path: Path) -> None:
        self._ecrire_points(tmp_path, [_point_v1_0("p1")])
        assert determiner_version_depuis_repertoire(str(tmp_path), JETON_AUTO) == "1.0"

    def test_couche_vide_replie_sur_le_defaut(self, tmp_path: Path) -> None:
        self._ecrire_points(tmp_path, [])
        assert determiner_version_depuis_repertoire(str(tmp_path), JETON_AUTO) == VERSION_DEFAUT
