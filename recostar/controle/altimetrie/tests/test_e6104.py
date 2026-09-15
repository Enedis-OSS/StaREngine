"""
Tests du controle E-6104 : levé de charge sans levé d'altitude superposé.

Couvre :
  - le filtre de perimetre par TypeLeve
  - la lecture planimetrique de la position, Z ecarte
  - la superposition a TOLERANCE_SUPERPOSITION
  - la lecture directe du GML source et le repli GeoJSON
  - la restriction a la RecoStaR V1.0, la V1.1 etant sans objet
  - l'execution CLI complete
"""

import json
from typing import Any

from recostar.controle.altimetrie.e6104 import (
    FICHIER_SORTIE,
    FICHIER_SOURCE,
    TYPE_CHARGE_SANS_ALTITUDE,
    compter_points_controles,
    construire_geojson_ecarts,
    detecter_anomalies,
    executer_controle_cli,
    filtrer_par_type,
    point_planimetrique,
    type_leve,
)
from recostar.controle.altimetrie.tests.utils_tests import ecrire_collection
from recostar.controle.fonctions_communes.geojson import PRIORITE_FORTE
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


def _plor(
    identifiant: str = "p1",
    type_leve_valeur: Any = TYPE_LEVE_CHARGE,
    position: list[float] | None = None,
) -> dict[str, Any]:
    """Point leve sous forme de feature, tel que les deux sources le rendent."""
    proprietes: dict[str, Any] = {"id": identifiant}
    if type_leve_valeur is not None:
        proprietes[CHAMP_TYPE_LEVE] = type_leve_valeur
    geometrie = None if position is None else {"type": "Point", "coordinates": position}
    return {"type": "Feature", "properties": proprietes, "geometry": geometrie}


# Sentinelle : distingue « position par defaut » de « aucune geometrie », que
# None ne saurait separer dans un argument optionnel.
_DEFAUT: Any = object()

POSITION_CHARGE: list[float] = [10.0, 20.0, 5.0]
POSITION_ALTITUDE: list[float] = [10.0, 20.0, 123.456]


def _charge(identifiant: str = "c1", position: Any = _DEFAUT) -> dict[str, Any]:
    return _plor(identifiant, TYPE_LEVE_CHARGE, POSITION_CHARGE if position is _DEFAUT else position)


def _altitude(identifiant: str = "a1", position: Any = _DEFAUT) -> dict[str, Any]:
    return _plor(identifiant, TYPE_LEVE_ALTITUDE, POSITION_ALTITUDE if position is _DEFAUT else position)


def _membre_gml(fid: str, type_leve_valeur: str, position: str) -> str:
    return _MEMBRE_PLOR.format(fid=fid, type_leve=type_leve_valeur, position=position)


def _ecrire_gml(tmp_path: Any, membres: list[str], nom: str = "recolement.gml") -> Any:
    chemin = tmp_path / nom
    chemin.write_text(f"{_ENTETE_GML}\n" + "\n".join(membres) + "\n</gml:FeatureCollection>", encoding="utf-8")
    return chemin


def _ecrire_geojson(tmp_path: Any, features: list[dict[str, Any]]) -> None:
    ecrire_collection(str(tmp_path / FICHIER_SOURCE), features)


# --------------------------------------------------------------------------- #
# Perimetre et lecture
# --------------------------------------------------------------------------- #


class TestPerimetre:
    """Seuls les leves de charge sont qualifies par la regle."""

    def test_type_leve_lu(self) -> None:
        assert type_leve(_charge()) == TYPE_LEVE_CHARGE

    def test_type_absent(self) -> None:
        assert type_leve(_plor(type_leve_valeur=None)) is None

    def test_filtrer_charges(self) -> None:
        points = [_charge("c1"), _altitude("a1"), _charge("c2")]
        assert [f["properties"]["id"] for f in filtrer_par_type(points, TYPE_LEVE_CHARGE)] == ["c1", "c2"]

    def test_comptage_du_perimetre(self) -> None:
        """Les leves d'altitude ne sont pas comptes : la regle ne les qualifie pas."""
        assert compter_points_controles([_charge("c1"), _altitude("a1"), _altitude("a2")]) == 1


class TestPointPlanimetrique:
    """Le Z est ecarte : la superposition est planimetrique."""

    def test_position_3d(self) -> None:
        point = point_planimetrique(_charge(position=[10.0, 20.0, 5.0]))
        assert point is not None
        assert (point.x, point.y) == (10.0, 20.0)

    def test_position_2d_admise(self) -> None:
        point = point_planimetrique(_charge(position=[10.0, 20.0]))
        assert point is not None

    def test_sans_geometrie(self) -> None:
        assert point_planimetrique(_charge(position=None)) is None

    def test_geometrie_non_ponctuelle(self) -> None:
        feature = {"properties": {}, "geometry": {"type": "LineString", "coordinates": [[1.0, 2.0]]}}
        assert point_planimetrique(feature) is None


# --------------------------------------------------------------------------- #
# Regle metier
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Tests de detecter_anomalies."""

    def test_charge_avec_altitude_superposee(self) -> None:
        assert detecter_anomalies([_charge(position=[10.0, 20.0, 5.0]), _altitude(position=[10.0, 20.0, 123.0])]) == []

    def test_altitudes_differentes_sans_effet(self) -> None:
        """La superposition est planimetrique : les Z n'ont pas a coincider."""
        points = [_charge(position=[10.0, 20.0, 0.0]), _altitude(position=[10.0, 20.0, 999.0])]
        assert detecter_anomalies(points) == []

    def test_charge_orpheline_signalee(self) -> None:
        anomalies = detecter_anomalies([_charge("c1")])
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_CHARGE_SANS_ALTITUDE
        assert anomalies[0]["id_point_leve"] == "c1"

    def test_altitude_ailleurs_ne_repond_pas(self) -> None:
        points = [_charge(position=[10.0, 20.0, 5.0]), _altitude(position=[50.0, 60.0, 123.0])]
        assert len(detecter_anomalies(points)) == 1

    def test_tolerance_admise(self) -> None:
        """L'arrondi millimetrique de la source ne doit pas separer deux leves."""
        points = [_charge(position=[10.0, 20.0, 5.0]), _altitude(position=[10.0005, 20.0, 123.0])]
        assert detecter_anomalies(points) == []

    def test_ecart_centimetrique_refuse(self) -> None:
        points = [_charge(position=[10.0, 20.0, 5.0]), _altitude(position=[10.05, 20.0, 123.0])]
        assert len(detecter_anomalies(points)) == 1

    def test_altitude_isolee_conforme(self) -> None:
        """Un leve d'altitude seul est le cas courant : il n'appelle aucune charge."""
        assert detecter_anomalies([_altitude("a1")]) == []

    def test_charge_sans_position_ignoree(self) -> None:
        assert detecter_anomalies([_charge("c1", position=None)]) == []

    def test_une_anomalie_par_charge(self) -> None:
        charges = [_charge("c1"), _charge("c2"), _charge("c3")]
        assert len(detecter_anomalies(charges)) == 3

    def test_collection_vide(self) -> None:
        assert detecter_anomalies([]) == []


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    @staticmethod
    def _anomalie() -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_CHARGE_SANS_ALTITUDE,
            "id_point_leve": "c1",
            "geometrie": {"type": "Point", "coordinates": [10.0, 20.0, 5.0]},
        }

    def test_proprietes_du_socle(self) -> None:
        proprietes = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-6104"
        assert proprietes["priorite"] == PRIORITE_FORTE
        assert proprietes["couche"] == "RPD_PointLeveOuvrageReseau_Reco"

    def test_geometrie_du_leve_de_charge(self) -> None:
        """C'est a cet endroit qu'un leve d'altitude manque."""
        geometrie = construire_geojson_ecarts([self._anomalie()])["features"][0]["geometry"]
        assert geometrie["coordinates"] == [10.0, 20.0, 5.0]

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([])["features"] == []


# --------------------------------------------------------------------------- #
# Execution CLI
# --------------------------------------------------------------------------- #


class TestCli:
    """Tests de executer_controle_cli."""

    def test_aucune_source_sans_objet(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat[CLE_SANS_OBJET] is True
        assert resultat["nombre_anomalies"] == 0

    def test_gml_charge_orpheline(self, tmp_path: Any) -> None:
        _ecrire_gml(tmp_path, [_membre_gml("c1", TYPE_LEVE_CHARGE, "10.0 20.0 5.0")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["source"] == SOURCE_GML
        assert resultat["version_detectee"] == VERSION_LEVE
        assert resultat["anomalies_par_type"] == {TYPE_CHARGE_SANS_ALTITUDE: 1}
        assert resultat["nombre_points_controles"] == 1

    def test_gml_couple_conforme(self, tmp_path: Any) -> None:
        _ecrire_gml(
            tmp_path,
            [
                _membre_gml("c1", TYPE_LEVE_CHARGE, "10.0 20.0 5.0"),
                _membre_gml("a1", TYPE_LEVE_ALTITUDE, "10.0 20.0 123.456"),
            ],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["sortie"] is None

    def test_gml_prioritaire_sur_le_geojson(self, tmp_path: Any) -> None:
        _ecrire_gml(tmp_path, [_membre_gml("c1", TYPE_LEVE_CHARGE, "10.0 20.0 5.0")])
        _ecrire_geojson(tmp_path, [_charge("c1"), _altitude("a1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["source"] == SOURCE_GML
        assert resultat["nombre_anomalies"] == 1

    def test_repli_geojson(self, tmp_path: Any) -> None:
        _ecrire_geojson(tmp_path, [_charge("c1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["source"] == SOURCE_GEOJSON
        assert resultat["nombre_anomalies"] == 1

    def test_v1_1_sans_objet(self, tmp_path: Any) -> None:
        """Sans TypeLeve, les deux types ne sont plus distinguables."""
        _ecrire_geojson(tmp_path, [_plor("p1", type_leve_valeur=None, position=[10.0, 20.0, 5.0])])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat[CLE_SANS_OBJET] is True
        assert resultat["version_detectee"] == "1.1"

    def test_version_forcee_v1_1_sans_objet(self, tmp_path: Any) -> None:
        _ecrire_geojson(tmp_path, [_charge("c1")])
        assert executer_controle_cli(str(tmp_path), version="1.1")[CLE_SANS_OBJET] is True

    def test_chemin_gml_explicite(self, tmp_path: Any) -> None:
        chemin = _ecrire_gml(tmp_path, [_membre_gml("c1", TYPE_LEVE_CHARGE, "10.0 20.0 5.0")], nom="a.gml")
        _ecrire_gml(tmp_path, [_membre_gml("a1", TYPE_LEVE_ALTITUDE, "10.0 20.0 1.0")], nom="b.gml")
        resultat = executer_controle_cli(str(tmp_path), chemin_gml=chemin)
        assert resultat["nombre_anomalies"] == 1

    def test_fichier_ecarts_ecrit(self, tmp_path: Any) -> None:
        _ecrire_gml(tmp_path, [_membre_gml("c1", TYPE_LEVE_CHARGE, "10.0 20.0 5.0")])
        chemin = executer_controle_cli(str(tmp_path))["sortie"]
        assert chemin is not None
        assert chemin.endswith(FICHIER_SORTIE)
        with open(chemin, encoding="utf-8") as flux:
            proprietes = json.load(flux)["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-6104"
        assert proprietes["id_point_leve"] == "c1"
