"""
Tests du controle E-6207 : valeur de leve differente de l'altitude du PLOR.

Couvre :
  - le filtre de perimetre par TypeLeve
  - la lecture des deux valeurs et leurs absences
  - l'egalite stricte, sans tolerance
  - la lecture directe du GML source, seule source portant Leve / TypeLeve
  - le repli sur les GeoJSON en l'absence de GML
  - la restriction a la RecoStaR V1.0, la V1.1 etant sans objet
  - la construction du GeoJSON d'ecarts
  - l'execution CLI complete
"""

import json
from typing import Any

from recostar.controle.altimetrie.e6207 import (
    FICHIER_SORTIE,
    FICHIER_SOURCE,
    TYPE_LEVE_DIFFERENT,
    altitude_geometrie,
    compter_points_controles,
    construire_geojson_ecarts,
    detecter_anomalies,
    ecart_leve_altitude,
    est_leve_altitude,
    executer_controle_cli,
)
from recostar.controle.altimetrie.tests.utils_tests import ecrire_collection
from recostar.controle.fonctions_communes.geojson import PRIORITE_MOYENNE
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_LEVE,
    CHAMP_TYPE_LEVE,
    TYPE_LEVE_ALTITUDE,
    TYPE_LEVE_CHARGE,
)
from recostar.controle.fonctions_communes.points_leve_gml import (
    SOURCE_GEOJSON,
    SOURCE_GML,
    VERSION_LEVE,
    lire_points_leve_gml,
)
from recostar.controle.fonctions_communes.proprietes import valeur_numerique
from recostar.controle.fonctions_communes.resultats import CLE_SANS_OBJET

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _plor(
    identifiant: str = "p1",
    leve: Any = 123.456,
    altitude: Any = 123.456,
    type_leve: Any = TYPE_LEVE_ALTITUDE,
) -> dict[str, Any]:
    """Point leve V1.0, conforme par defaut : leve et altitude coincident."""
    proprietes: dict[str, Any] = {"id": identifiant}
    if type_leve is not None:
        proprietes[CHAMP_TYPE_LEVE] = type_leve
    if leve is not None:
        proprietes[CHAMP_LEVE] = leve
    coordonnees = [10.0, 20.0] if altitude is None else [10.0, 20.0, altitude]
    return {
        "type": "Feature",
        "properties": proprietes,
        "geometry": {"type": "Point", "coordinates": coordonnees},
    }


def _plor_v1_1(identifiant: str = "p1") -> dict[str, Any]:
    """Point leve V1.1 : aucun TypeLeve, c'est le discriminant de version."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, "ChargeGeneratrice": 12.5},
        "geometry": {"type": "Point", "coordinates": [10.0, 20.0, 123.456]},
    }


def _ecrire(tmp_path: Any, features: list[dict[str, Any]]) -> None:
    ecrire_collection(str(tmp_path / FICHIER_SOURCE), features)


# --------------------------------------------------------------------------- #
# Perimetre
# --------------------------------------------------------------------------- #


class TestEstLeveAltitude:
    """Seul le leve d'altitude porte une valeur comparable a une altitude."""

    def test_altitude_generatrice(self) -> None:
        assert est_leve_altitude({CHAMP_TYPE_LEVE: TYPE_LEVE_ALTITUDE}) is True

    def test_charge_generatrice_hors_perimetre(self) -> None:
        """Une charge mecanique n'a pas vocation a egaler une altitude."""
        assert est_leve_altitude({CHAMP_TYPE_LEVE: TYPE_LEVE_CHARGE}) is False

    def test_type_absent(self) -> None:
        assert est_leve_altitude({}) is False

    def test_type_inconnu(self) -> None:
        assert est_leve_altitude({CHAMP_TYPE_LEVE: "Bidon"}) is False


# --------------------------------------------------------------------------- #
# Lecture des valeurs
# --------------------------------------------------------------------------- #


class TestValeurNumerique:
    """Tests de valeur_numerique."""

    def test_flottant(self) -> None:
        assert valeur_numerique(12.5) == 12.5

    def test_entier(self) -> None:
        assert valeur_numerique(12) == 12.0

    def test_chaine_numerique(self) -> None:
        assert valeur_numerique(" 12.5 ") == 12.5

    def test_chaine_non_numerique(self) -> None:
        assert valeur_numerique("douze") is None

    def test_none(self) -> None:
        assert valeur_numerique(None) is None

    def test_booleen_ecarte(self) -> None:
        """bool est un sous-type de int : il ne decrit aucune mesure."""
        assert valeur_numerique(True) is None


class TestAltitudeGeometrie:
    """Tests de altitude_geometrie."""

    def test_point_3d(self) -> None:
        assert altitude_geometrie({"type": "Point", "coordinates": [1.0, 2.0, 3.0]}) == 3.0

    def test_point_2d_sans_altitude(self) -> None:
        """L'absence de Z est l'anomalie d'E-5107, pas celle-ci."""
        assert altitude_geometrie({"type": "Point", "coordinates": [1.0, 2.0]}) is None

    def test_geometrie_lineaire(self) -> None:
        assert altitude_geometrie({"type": "LineString", "coordinates": [[1.0, 2.0, 3.0]]}) is None

    def test_geometrie_absente(self) -> None:
        assert altitude_geometrie(None) is None


# --------------------------------------------------------------------------- #
# Regle metier
# --------------------------------------------------------------------------- #


class TestEcartLeveAltitude:
    """Tests de ecart_leve_altitude."""

    def test_valeurs_egales(self) -> None:
        assert ecart_leve_altitude(_plor(leve=123.456, altitude=123.456)) == 0.0

    def test_ecart_positif(self) -> None:
        assert ecart_leve_altitude(_plor(leve=124.0, altitude=123.0)) == 1.0

    def test_ecart_negatif(self) -> None:
        assert ecart_leve_altitude(_plor(leve=123.0, altitude=124.0)) == -1.0

    def test_ecart_millimetrique_detecte(self) -> None:
        """Egalite stricte : aucun arrondi n'est tolere."""
        ecart = ecart_leve_altitude(_plor(leve=123.457, altitude=123.456))
        assert ecart is not None and ecart != 0.0

    def test_ecritures_decimales_equivalentes(self) -> None:
        """« 123.456 » et « 123.4560 » donnent le meme flottant."""
        assert ecart_leve_altitude(_plor(leve="123.4560", altitude=123.456)) == 0.0

    def test_hors_perimetre(self) -> None:
        assert ecart_leve_altitude(_plor(type_leve=TYPE_LEVE_CHARGE)) is None

    def test_leve_absent(self) -> None:
        assert ecart_leve_altitude(_plor(leve=None)) is None

    def test_altitude_absente(self) -> None:
        assert ecart_leve_altitude(_plor(altitude=None)) is None


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Tests de detecter_anomalies."""

    def test_anomalie_documentee(self) -> None:
        anomalies = detecter_anomalies([_plor(leve=124.0, altitude=123.0)])
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_LEVE_DIFFERENT
        assert anomalies[0]["id_point_leve"] == "p1"
        assert anomalies[0]["leve"] == 124.0
        assert anomalies[0]["altitude"] == 123.0
        assert anomalies[0]["ecart"] == 1.0

    def test_point_conforme(self) -> None:
        assert detecter_anomalies([_plor()]) == []

    def test_une_anomalie_par_point(self) -> None:
        points = [_plor("p1", leve=1.0, altitude=2.0), _plor("p2", leve=3.0, altitude=4.0)]
        assert len(detecter_anomalies(points)) == 2

    def test_charge_generatrice_ignoree(self) -> None:
        assert detecter_anomalies([_plor(leve=1.0, altitude=999.0, type_leve=TYPE_LEVE_CHARGE)]) == []

    def test_collection_vide(self) -> None:
        assert detecter_anomalies([]) == []

    def test_comptage_du_perimetre(self) -> None:
        points = [_plor("p1"), _plor("p2", type_leve=TYPE_LEVE_CHARGE), _plor("p3", type_leve=None)]
        assert compter_points_controles(points) == 1


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    @staticmethod
    def _anomalie() -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_LEVE_DIFFERENT,
            "id_point_leve": "p1",
            "leve": 124.0,
            "altitude": 123.0,
            "ecart": 1.0,
            "geometrie": {"type": "Point", "coordinates": [10.0, 20.0, 123.0]},
        }

    def test_proprietes_du_socle(self) -> None:
        proprietes = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-6207"
        assert proprietes["priorite"] == PRIORITE_MOYENNE
        assert proprietes["ecart"] == 1.0

    def test_couche_source_reportee(self) -> None:
        proprietes = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert proprietes["couche"] == "RPD_PointLeveOuvrageReseau_Reco"

    def test_avec_crs(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([self._anomalie()], crs)["crs"] == crs

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([])["features"] == []


# --------------------------------------------------------------------------- #
# Execution CLI et restriction de version
# --------------------------------------------------------------------------- #


class TestCli:
    """Tests de executer_controle_cli."""

    def test_couche_absente_sans_objet(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat[CLE_SANS_OBJET] is True
        assert resultat["nombre_anomalies"] == 0

    def test_v1_0_anomalie_signalee(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, [_plor(leve=124.0, altitude=123.0)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["version_detectee"] == VERSION_LEVE
        assert resultat["anomalies_par_type"] == {TYPE_LEVE_DIFFERENT: 1}
        assert resultat["nombre_points_controles"] == 1

    def test_v1_0_conforme(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, [_plor()])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["sortie"] is None

    def test_v1_1_sans_objet(self, tmp_path: Any) -> None:
        """Le couple Leve / TypeLeve n'existe pas en V1.1 : rien a confronter."""
        _ecrire(tmp_path, [_plor_v1_1()])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat[CLE_SANS_OBJET] is True
        assert resultat["version_detectee"] == "1.1"
        assert resultat["nombre_anomalies"] == 0

    def test_version_forcee_v1_1_sans_objet(self, tmp_path: Any) -> None:
        """Meme sur un jeu V1.0, la version demandee fait foi."""
        _ecrire(tmp_path, [_plor(leve=124.0, altitude=123.0)])
        assert executer_controle_cli(str(tmp_path), version="1.1")[CLE_SANS_OBJET] is True

    def test_version_forcee_v1_0(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, [_plor(leve=124.0, altitude=123.0)])
        resultat = executer_controle_cli(str(tmp_path), version="1.0")
        assert resultat["nombre_anomalies"] == 1

    def test_fichier_ecarts_ecrit(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, [_plor(leve=124.0, altitude=123.0)])
        chemin = executer_controle_cli(str(tmp_path))["sortie"]
        assert chemin is not None
        assert chemin.endswith(FICHIER_SORTIE)
        with open(chemin, encoding="utf-8") as flux:
            proprietes = json.load(flux)["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-6207"
        assert proprietes["ecart"] == 1.0


# --------------------------------------------------------------------------- #
# Lecture du GML source
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
      <RecoStaR:NumeroPoint>{fid}</RecoStaR:NumeroPoint>
      {leve}
      <RecoStaR:Geometrie>
        <gml:Point srsDimension="3"><gml:pos>{position}</gml:pos></gml:Point>
      </RecoStaR:Geometrie>
    </RecoStaR:RPD_PointLeveOuvrageReseau_Reco>
  </gml:featureMember>"""


def _membre_gml(
    fid: str = "p1",
    type_leve: str | None = TYPE_LEVE_ALTITUDE,
    leve: str | None = "123.456",
    position: str = "10.0 20.0 123.456",
) -> str:
    """Un RPD_PointLeveOuvrageReseau_Reco au format GML V1.0."""
    lignes = []
    if type_leve is not None:
        lignes.append(f"<RecoStaR:TypeLeve>{type_leve}</RecoStaR:TypeLeve>")
    if leve is not None:
        lignes.append(f'<RecoStaR:Leve uom="m">{leve}</RecoStaR:Leve>')
    return _MEMBRE_PLOR.format(fid=fid, leve="\n      ".join(lignes), position=position)


def _ecrire_gml(tmp_path: Any, membres: list[str], nom: str = "recolement.gml") -> Any:
    chemin = tmp_path / nom
    chemin.write_text(f"{_ENTETE_GML}\n" + "\n".join(membres) + "\n</gml:FeatureCollection>", encoding="utf-8")
    return chemin


class TestLirePointsLeveGml:
    """Traduction des objets GML en features exploitables par la regle."""

    def test_champs_traduits(self, tmp_path: Any) -> None:
        chemin = _ecrire_gml(tmp_path, [_membre_gml()])
        features = lire_points_leve_gml(chemin)
        assert len(features) == 1
        proprietes = features[0]["properties"]
        assert proprietes["id"] == "p1"
        assert proprietes[CHAMP_TYPE_LEVE] == TYPE_LEVE_ALTITUDE
        assert proprietes[CHAMP_LEVE] == "123.456"
        assert features[0]["geometry"]["coordinates"] == [10.0, 20.0, 123.456]

    def test_leve_absent(self, tmp_path: Any) -> None:
        chemin = _ecrire_gml(tmp_path, [_membre_gml(leve=None)])
        assert lire_points_leve_gml(chemin)[0]["properties"][CHAMP_LEVE] is None

    def test_position_2d_conservee(self, tmp_path: Any) -> None:
        """La planimetrie est gardee : E-6104 en a besoin pour la superposition."""
        chemin = _ecrire_gml(tmp_path, [_membre_gml(position="10.0 20.0")])
        assert lire_points_leve_gml(chemin)[0]["geometry"]["coordinates"] == [10.0, 20.0]

    def test_position_2d_sans_altitude_a_confronter(self, tmp_path: Any) -> None:
        """Sans Z, la regle d'E-6207 ne s'applique pas : E-5107 s'en charge."""
        chemin = _ecrire_gml(tmp_path, [_membre_gml(position="10.0 20.0")])
        assert detecter_anomalies(lire_points_leve_gml(chemin)) == []

    def test_plusieurs_points(self, tmp_path: Any) -> None:
        chemin = _ecrire_gml(tmp_path, [_membre_gml("p1"), _membre_gml("p2")])
        assert [f["properties"]["id"] for f in lire_points_leve_gml(chemin)] == ["p1", "p2"]

    def test_autres_objets_ecartes(self, tmp_path: Any) -> None:
        autre = '  <gml:featureMember>\n    <RecoStaR:RPD_Coffret_Reco gml:id="k1"/>\n  </gml:featureMember>'
        chemin = _ecrire_gml(tmp_path, [autre, _membre_gml()])
        assert len(lire_points_leve_gml(chemin)) == 1


class TestCliDepuisGml:
    """Execution complete depuis le GML, sans aucun GeoJSON."""

    def test_source_gml_prioritaire(self, tmp_path: Any) -> None:
        """Le GML prime meme si un GeoJSON est present : lui seul est fiable."""
        _ecrire_gml(tmp_path, [_membre_gml(leve="124.0")])
        _ecrire(tmp_path, [_plor()])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["source"] == SOURCE_GML
        assert resultat["nombre_anomalies"] == 1

    def test_anomalie_detectee_sans_geojson(self, tmp_path: Any) -> None:
        _ecrire_gml(tmp_path, [_membre_gml(leve="124.0")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["source"] == SOURCE_GML
        assert resultat["version_detectee"] == VERSION_LEVE
        assert resultat["anomalies_par_type"] == {TYPE_LEVE_DIFFERENT: 1}

    def test_conforme(self, tmp_path: Any) -> None:
        _ecrire_gml(tmp_path, [_membre_gml()])
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_charge_generatrice_hors_perimetre(self, tmp_path: Any) -> None:
        _ecrire_gml(tmp_path, [_membre_gml(type_leve=TYPE_LEVE_CHARGE, leve="999.0")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_points_controles"] == 0
        assert resultat["nombre_anomalies"] == 0

    def test_chemin_gml_explicite(self, tmp_path: Any) -> None:
        """Deux GML dans le repertoire : la detection automatique n'y suffit pas."""
        chemin = _ecrire_gml(tmp_path, [_membre_gml(leve="124.0")], nom="a.gml")
        _ecrire_gml(tmp_path, [_membre_gml()], nom="b.gml")
        resultat = executer_controle_cli(str(tmp_path), chemin_gml=chemin)
        assert resultat["source"] == SOURCE_GML
        assert resultat["nombre_anomalies"] == 1

    def test_repli_geojson_sans_gml(self, tmp_path: Any) -> None:
        """Sans GML, le GeoJSON d'un convertisseur V1.0 reste exploitable."""
        _ecrire(tmp_path, [_plor(leve=124.0, altitude=123.0)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["source"] == SOURCE_GEOJSON
        assert resultat["nombre_anomalies"] == 1

    def test_ecart_reporte(self, tmp_path: Any) -> None:
        _ecrire_gml(tmp_path, [_membre_gml(leve="123.457")])
        chemin = executer_controle_cli(str(tmp_path))["sortie"]
        assert chemin is not None
        with open(chemin, encoding="utf-8") as flux:
            proprietes = json.load(flux)["features"][0]["properties"]
        assert proprietes["leve"] == 123.457
        assert proprietes["altitude"] == 123.456
