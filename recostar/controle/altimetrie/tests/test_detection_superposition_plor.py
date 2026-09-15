"""
Tests du moteur de superposition des points leves et de ses deux controles.

Couvre :
  - les deux cles de groupement : complete (E-3300) et planimetrique (E-6206)
  - la distinction entre superposition de meme type et de types differents
  - l'englobement d'E-3300 par E-6206
  - le groupement, une anomalie par groupe et non par point
  - la repartition des anomalies entre les deux codes voisins
  - la lecture directe du GML source et le repli GeoJSON
  - la restriction a la RecoStaR V1.0, la V1.1 etant sans objet
  - l'execution CLI complete
"""

import json
from typing import Any

from recostar.controle.altimetrie.detection_superposition_plor import (
    FICHIER_SOURCE,
    TYPE_SUPERPOSITION_COMPLETE,
    TYPE_SUPERPOSITION_XY,
    cle_complete,
    cle_planimetrique,
    compter_points_controles,
    construire_geojson_ecarts,
    detecter_anomalies,
    grouper_par_cle,
)
from recostar.controle.altimetrie.e3300 import FICHIER_SORTIE, PROFIL_ECARTS, executer_controle_cli
from recostar.controle.altimetrie.e6206 import FICHIER_SORTIE as FICHIER_SORTIE_6206
from recostar.controle.altimetrie.e6206 import PROFIL_ECARTS as PROFIL_6206
from recostar.controle.altimetrie.e6206 import executer_controle_cli as executer_6206
from recostar.controle.altimetrie.tests.utils_tests import ecrire_collection
from recostar.controle.fonctions_communes.geojson import PRIORITE_BASSE, PRIORITE_MOYENNE
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_TYPE_LEVE,
    TYPE_LEVE_ALTITUDE,
    TYPE_LEVE_CHARGE,
)
from recostar.controle.fonctions_communes.points_leve_gml import SOURCE_GEOJSON, SOURCE_GML, VERSION_LEVE
from recostar.controle.fonctions_communes.resultats import CLE_SANS_OBJET

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_ENTETE_GML: str = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2"'
    ' xmlns:RecoStaR="http://StaR-Elec.com"'
    ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
    ' xsi:schemaLocation="http://StaR-Elec.com'
    ' https://github.com/enedis/StaR-Elec/main/SchemaStarElecRecoStar.xsd">'
)

_MEMBRE_PLOR: str = """  <gml:featureMember>
    <RecoStaR:RPD_PointLeveOuvrageReseau_Reco gml:id="{fid}">
      <RecoStaR:TypeLeve>{type_leve}</RecoStaR:TypeLeve>
      <RecoStaR:Geometrie>
        <gml:Point srsDimension="3"><gml:pos>{position}</gml:pos></gml:Point>
      </RecoStaR:Geometrie>
    </RecoStaR:RPD_PointLeveOuvrageReseau_Reco>
  </gml:featureMember>"""

POSITION: list[float] = [10.0, 20.0, 123.456]
# Sentinelle : distingue « position par defaut » de « aucune geometrie ».
_DEFAUT: Any = object()


def _plor(
    identifiant: str = "p1",
    type_leve: Any = TYPE_LEVE_ALTITUDE,
    position: Any = _DEFAUT,
) -> dict[str, Any]:
    """Point leve sous forme de feature, tel que les deux sources le rendent."""
    proprietes: dict[str, Any] = {"id": identifiant}
    if type_leve is not None:
        proprietes[CHAMP_TYPE_LEVE] = type_leve
    coordonnees = POSITION if position is _DEFAUT else position
    geometrie = None if coordonnees is None else {"type": "Point", "coordinates": coordonnees}
    return {"type": "Feature", "properties": proprietes, "geometry": geometrie}


def _membre_gml(fid: str, type_leve: str, position: str) -> str:
    return _MEMBRE_PLOR.format(fid=fid, type_leve=type_leve, position=position)


def _ecrire_gml(tmp_path: Any, membres: list[str], nom: str = "recolement.gml") -> Any:
    chemin = tmp_path / nom
    chemin.write_text(f"{_ENTETE_GML}\n" + "\n".join(membres) + "\n</gml:FeatureCollection>", encoding="utf-8")
    return chemin


def _ecrire_geojson(tmp_path: Any, features: list[dict[str, Any]]) -> None:
    ecrire_collection(str(tmp_path / FICHIER_SOURCE), features)


# --------------------------------------------------------------------------- #
# Cle de groupement
# --------------------------------------------------------------------------- #


class TestCleSuperposition:
    """La cle est le couple (coordonnees completes, TypeLeve)."""

    def test_coordonnees_et_type(self) -> None:
        assert cle_complete(_plor()) == ((10.0, 20.0, 123.456), TYPE_LEVE_ALTITUDE)

    def test_type_absent_admis(self) -> None:
        """Un type absent reste une cle : deux leves sans type se comparent."""
        assert cle_complete(_plor(type_leve=None)) == ((10.0, 20.0, 123.456), None)

    def test_sans_geometrie(self) -> None:
        assert cle_complete(_plor(position=None)) is None

    def test_geometrie_non_ponctuelle(self) -> None:
        feature = {"properties": {}, "geometry": {"type": "LineString", "coordinates": [[1.0, 2.0]]}}
        assert cle_complete(feature) is None

    def test_coordonnees_vides(self) -> None:
        assert cle_complete(_plor(position=[])) is None


class TestGrouperParCle:
    """Seuls les groupes en doublon sont retournes."""

    def test_point_isole_ecarte(self) -> None:
        assert grouper_par_cle([_plor("p1")], cle_complete) == {}

    def test_doublon_retenu(self) -> None:
        groupes = grouper_par_cle([_plor("p1"), _plor("p2")], cle_complete)
        assert list(groupes.values()) == [["p1", "p2"]]

    def test_triplet(self) -> None:
        groupes = grouper_par_cle([_plor("p1"), _plor("p2"), _plor("p3")], cle_complete)
        assert list(groupes.values()) == [["p1", "p2", "p3"]]


# --------------------------------------------------------------------------- #
# Regle metier
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Le moteur releve les deux mailles en un seul parcours."""

    @staticmethod
    def _types(anomalies: list[dict[str, Any]]) -> list[str]:
        return sorted(a["type_anomalie"] for a in anomalies)

    def test_superposition_complete_porte_les_deux_mailles(self) -> None:
        """E-6206 englobe E-3300 : un groupe superpose en X,Y,Z l'est en X,Y."""
        anomalies = detecter_anomalies([_plor("p1"), _plor("p2")])
        assert self._types(anomalies) == [TYPE_SUPERPOSITION_COMPLETE, TYPE_SUPERPOSITION_XY]
        for anomalie in anomalies:
            assert anomalie["ids_entites"] == ["p1", "p2"]
            assert anomalie["nb_points"] == 2
            assert anomalie["type_leve"] == TYPE_LEVE_ALTITUDE

    def test_z_different_porte_la_seule_maille_xy(self) -> None:
        """Le cas propre a E-6206 : meme X,Y, Z differents."""
        points = [_plor("p1", position=[10.0, 20.0, 1.0]), _plor("p2", position=[10.0, 20.0, 2.0])]
        anomalies = detecter_anomalies(points)
        assert self._types(anomalies) == [TYPE_SUPERPOSITION_XY]
        assert anomalies[0]["coordonnees"] == [10.0, 20.0]

    def test_types_differents_conformes(self) -> None:
        """Une charge et une altitude au meme point : c'est ce qu'E-6104 exige."""
        points = [_plor("a1", TYPE_LEVE_ALTITUDE), _plor("c1", TYPE_LEVE_CHARGE)]
        assert detecter_anomalies(points) == []

    def test_positions_differentes_conformes(self) -> None:
        points = [_plor("p1"), _plor("p2", position=[50.0, 60.0, 1.0])]
        assert detecter_anomalies(points) == []

    def test_une_anomalie_par_groupe(self) -> None:
        """Le groupe est l'unite a corriger, non le point."""
        points = [
            _plor("p1"),
            _plor("p2"),
            _plor("p3", position=[5.0, 5.0, 5.0]),
            _plor("p4", position=[5.0, 5.0, 5.0]),
        ]
        anomalies = detecter_anomalies(points)
        completes = [a for a in anomalies if a["type_anomalie"] == TYPE_SUPERPOSITION_COMPLETE]
        assert len(completes) == 2
        assert sorted(a["nb_points"] for a in completes) == [2, 2]

    def test_point_isole_conforme(self) -> None:
        assert detecter_anomalies([_plor("p1")]) == []

    def test_collection_vide(self) -> None:
        assert detecter_anomalies([]) == []

    def test_comptage_des_points_comparables(self) -> None:
        points = [_plor("p1"), _plor("p2", position=None)]
        assert compter_points_controles(points) == 1


class TestClePlanimetrique:
    """Cle de la maille E-6206 : X, Y et TypeLeve."""

    def test_z_ignore(self) -> None:
        assert cle_planimetrique(_plor(position=[10.0, 20.0, 99.0])) == ((10.0, 20.0), TYPE_LEVE_ALTITUDE)

    def test_point_2d_admis(self) -> None:
        assert cle_planimetrique(_plor(position=[10.0, 20.0])) == ((10.0, 20.0), TYPE_LEVE_ALTITUDE)

    def test_sans_geometrie(self) -> None:
        assert cle_planimetrique(_plor(position=None)) is None

    def test_coordonnee_unique_refusee(self) -> None:
        assert cle_planimetrique(_plor(position=[10.0])) is None


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    @staticmethod
    def _anomalie() -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_SUPERPOSITION_COMPLETE,
            "coordonnees": [10.0, 20.0, 123.456],
            "type_leve": TYPE_LEVE_ALTITUDE,
            "ids_entites": ["p1", "p2"],
            "nb_points": 2,
        }

    def test_proprietes_du_socle(self) -> None:
        proprietes = construire_geojson_ecarts([self._anomalie()], PROFIL_ECARTS)["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-3300"
        assert proprietes["priorite"] == PRIORITE_BASSE
        assert proprietes["couche"] == "RPD_PointLeveOuvrageReseau_Reco"

    def test_identifiants_du_groupe_joints(self) -> None:
        """L'ecart nomme tous les points a arbitrer."""
        proprietes = construire_geojson_ecarts([self._anomalie()], PROFIL_ECARTS)["features"][0]["properties"]
        assert proprietes["ids_entites"] == "p1,p2"
        assert proprietes["nb_points"] == 2
        assert proprietes[CHAMP_TYPE_LEVE] == TYPE_LEVE_ALTITUDE

    def test_position_du_groupe(self) -> None:
        geometrie = construire_geojson_ecarts([self._anomalie()], PROFIL_ECARTS)["features"][0]["geometry"]
        assert geometrie["coordinates"] == [10.0, 20.0, 123.456]

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([], PROFIL_ECARTS)["features"] == []


# --------------------------------------------------------------------------- #
# Execution CLI
# --------------------------------------------------------------------------- #


class TestCli:
    """Tests de executer_controle_cli."""

    def test_aucune_source_sans_objet(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat[CLE_SANS_OBJET] is True
        assert resultat["nombre_anomalies"] == 0

    def test_gml_superposition_signalee(self, tmp_path: Any) -> None:
        _ecrire_gml(
            tmp_path,
            [
                _membre_gml("p1", TYPE_LEVE_ALTITUDE, "10.0 20.0 123.456"),
                _membre_gml("p2", TYPE_LEVE_ALTITUDE, "10.0 20.0 123.456"),
            ],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["source"] == SOURCE_GML
        assert resultat["version_detectee"] == VERSION_LEVE
        assert resultat["anomalies_par_type"] == {TYPE_SUPERPOSITION_COMPLETE: 1}
        assert resultat["nombre_points_en_doublon"] == 2

    def test_gml_types_differents_conformes(self, tmp_path: Any) -> None:
        _ecrire_gml(
            tmp_path,
            [
                _membre_gml("a1", TYPE_LEVE_ALTITUDE, "10.0 20.0 123.456"),
                _membre_gml("c1", TYPE_LEVE_CHARGE, "10.0 20.0 123.456"),
            ],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["sortie"] is None

    def test_gml_prioritaire_sur_le_geojson(self, tmp_path: Any) -> None:
        _ecrire_gml(tmp_path, [_membre_gml("p1", TYPE_LEVE_ALTITUDE, "10.0 20.0 1.0")])
        _ecrire_geojson(tmp_path, [_plor("p1"), _plor("p2")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["source"] == SOURCE_GML
        assert resultat["nombre_anomalies"] == 0

    def test_repli_geojson(self, tmp_path: Any) -> None:
        _ecrire_geojson(tmp_path, [_plor("p1"), _plor("p2")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["source"] == SOURCE_GEOJSON
        assert resultat["nombre_anomalies"] == 1

    def test_v1_1_sans_objet(self, tmp_path: Any) -> None:
        """Sans TypeLeve, comparer des coordonnees nues serait une autre regle."""
        _ecrire_geojson(tmp_path, [_plor("p1", type_leve=None), _plor("p2", type_leve=None)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat[CLE_SANS_OBJET] is True
        assert resultat["version_detectee"] == "1.1"

    def test_version_forcee_v1_1_sans_objet(self, tmp_path: Any) -> None:
        _ecrire_geojson(tmp_path, [_plor("p1"), _plor("p2")])
        assert executer_controle_cli(str(tmp_path), version="1.1")[CLE_SANS_OBJET] is True

    def test_fichier_ecarts_ecrit(self, tmp_path: Any) -> None:
        _ecrire_geojson(tmp_path, [_plor("p1"), _plor("p2")])
        chemin = executer_controle_cli(str(tmp_path))["sortie"]
        assert chemin is not None
        assert chemin.endswith(FICHIER_SORTIE)
        with open(chemin, encoding="utf-8") as flux:
            proprietes = json.load(flux)["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-3300"
        assert proprietes["ids_entites"] == "p1,p2"


# --------------------------------------------------------------------------- #
# Repartition entre les deux controles
# --------------------------------------------------------------------------- #


class TestRepartitionEntreControles:
    """Chaque controle ne retient que la maille de son code."""

    def test_types_retenus_disjoints(self) -> None:
        from recostar.controle.altimetrie.e3300 import TYPES_RETENUS as TYPES_3300
        from recostar.controle.altimetrie.e6206 import TYPES_RETENUS as TYPES_6206

        assert not TYPES_3300 & TYPES_6206

    def test_superposition_complete_sort_des_deux_controles(self, tmp_path: Any) -> None:
        """Le meme groupe est signale sous les deux codes : E-6206 englobe E-3300."""
        _ecrire_geojson(tmp_path, [_plor("p1"), _plor("p2")])
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 1
        assert executer_6206(str(tmp_path))["nombre_anomalies"] == 1

    def test_z_different_ne_sort_que_d_e6206(self, tmp_path: Any) -> None:
        points = [_plor("p1", position=[10.0, 20.0, 1.0]), _plor("p2", position=[10.0, 20.0, 2.0])]
        _ecrire_geojson(tmp_path, points)
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0
        assert executer_6206(str(tmp_path))["nombre_anomalies"] == 1

    def test_fichiers_de_sortie_distincts(self, tmp_path: Any) -> None:
        _ecrire_geojson(tmp_path, [_plor("p1"), _plor("p2")])
        assert executer_controle_cli(str(tmp_path))["sortie"].endswith(FICHIER_SORTIE)
        assert executer_6206(str(tmp_path))["sortie"].endswith(FICHIER_SORTIE_6206)

    def test_code_erreur_de_chaque_controle(self, tmp_path: Any) -> None:
        _ecrire_geojson(tmp_path, [_plor("p1"), _plor("p2")])
        chemin = executer_6206(str(tmp_path))["sortie"]
        assert chemin is not None
        with open(chemin, encoding="utf-8") as flux:
            proprietes = json.load(flux)["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-6206"
        assert proprietes["priorite"] == PRIORITE_MOYENNE

    def test_geojson_du_profil_6206(self) -> None:
        anomalie = {
            "type_anomalie": TYPE_SUPERPOSITION_XY,
            "coordonnees": [10.0, 20.0],
            "type_leve": TYPE_LEVE_ALTITUDE,
            "ids_entites": ["p1", "p2"],
            "nb_points": 2,
        }
        proprietes = construire_geojson_ecarts([anomalie], PROFIL_6206)["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-6206"
