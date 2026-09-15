"""
Tests du controle E-9401 : cheminements d'un meme cable disjoints.

Couvre :
  - les cinq couches de cheminement, galerie comprise
  - l'assemblage et le comptage des troncons
  - la tolerance de jonction, qui rattrape l'arrondi millimetrique
  - le regroupement transitif de troncons
  - le perimetre : tous types de cable, tous statuts
  - l'ecart produit et l'execution CLI
"""

import json
import os
from typing import Any

from shapely.geometry import shape

from recostar.controle.cheminement.e9401 import (
    EPSILON_LONGUEUR,
    FICHIER_SORTIE,
    Cheminement,
    assembler,
    construire_geojson_ecarts,
    detecter_anomalies,
    ecart_minimal,
    indexer_cheminements_par_cable,
    regrouper_a_la_tolerance,
)
from recostar.controle.fonctions_communes.geometrie import TOLERANCE_SUPERPOSITION
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_CABLES_HREF,
    CHAMP_STATUT,
    COUCHE_AERIEN,
    COUCHE_FOURREAU,
    COUCHE_GALERIE,
    COUCHE_PLEINE_TERRE,
    COUCHE_PROTECTION_MECANIQUE,
    COUCHES_CHEMINEMENT,
    EXTENSION_COUCHE,
)

TYPE_ANOMALIE = "cheminements_disjoints"


def _ligne(depart: float, arrivee: float) -> dict[str, Any]:
    """Segment horizontal, de `depart` a `arrivee` sur l'axe des X."""
    return {"type": "LineString", "coordinates": [[depart, 0.0], [arrivee, 0.0]]}


def _cheminement(identifiant: str, id_cable: Any, depart: float, arrivee: float, **props: Any) -> dict[str, Any]:
    proprietes: dict[str, Any] = {"id": identifiant, CHAMP_CABLES_HREF: id_cable, **props}
    return {"type": "Feature", "id": identifiant, "properties": proprietes, "geometry": _ligne(depart, arrivee)}


def _forme(depart: float, arrivee: float) -> Any:
    return shape(_ligne(depart, arrivee))


def _ecrire(tmp_path: Any, couche: str, features: list[dict[str, Any]]) -> None:
    chemin = tmp_path / f"{couche}{EXTENSION_COUCHE}"
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump({"type": "FeatureCollection", "features": features}, fichier)


def _c(identifiant: str, depart: float, arrivee: float, couche: str = COUCHE_FOURREAU) -> Cheminement:
    return Cheminement(couche, identifiant, _forme(depart, arrivee))


class TestPerimetre:
    """Les cinq voies de cheminement, galerie comprise."""

    def test_cinq_couches(self) -> None:
        assert set(COUCHES_CHEMINEMENT) == {
            COUCHE_FOURREAU,
            COUCHE_GALERIE,
            COUCHE_PLEINE_TERRE,
            COUCHE_PROTECTION_MECANIQUE,
            COUCHE_AERIEN,
        }

    def test_galerie_indexee(self, tmp_path: Any) -> None:
        """La galerie n'était déclarée nulle part avant ce contrôle."""
        _ecrire(tmp_path, COUCHE_GALERIE, [_cheminement("g1", "c1", 0.0, 10.0)])
        index, _, _ = indexer_cheminements_par_cable(str(tmp_path))
        assert [c.couche for c in index["c1"]] == [COUCHE_GALERIE]

    def test_toutes_les_couches_indexees(self, tmp_path: Any) -> None:
        for indice, couche in enumerate(COUCHES_CHEMINEMENT):
            _ecrire(tmp_path, couche, [_cheminement(f"x{indice}", "c1", indice * 10.0, indice * 10.0 + 10.0)])
        index, _, absentes = indexer_cheminements_par_cable(str(tmp_path))
        assert len(index["c1"]) == len(COUCHES_CHEMINEMENT)
        assert absentes == []

    def test_couches_absentes_reportees(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_FOURREAU, [])
        _, _, absentes = indexer_cheminements_par_cable(str(tmp_path))
        assert COUCHE_GALERIE in absentes

    def test_tous_statuts_controles(self, tmp_path: Any) -> None:
        """La règle porte sur la continuité, non sur l'avancement des travaux."""
        _ecrire(
            tmp_path,
            COUCHE_FOURREAU,
            [
                _cheminement("f1", "c1", 0.0, 10.0, **{CHAMP_STATUT: "Projected"}),
                _cheminement("f2", "c1", 50.0, 60.0, **{CHAMP_STATUT: "Decommissioned"}),
            ],
        )
        index, _, _ = indexer_cheminements_par_cable(str(tmp_path))
        assert len(index["c1"]) == 2
        assert len(detecter_anomalies(index)) == 1

    def test_cheminement_mutualise_alimente_chaque_cable(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_FOURREAU, [_cheminement("f1", "c1,c2", 0.0, 10.0)])
        index, _, _ = indexer_cheminements_par_cable(str(tmp_path))
        assert set(index) == {"c1", "c2"}

    def test_cheminement_sans_cable_ignore(self, tmp_path: Any) -> None:
        """Un cheminement orphelin relève d'E-9400, non d'ici."""
        _ecrire(tmp_path, COUCHE_FOURREAU, [_cheminement("f1", None, 0.0, 10.0)])
        index, _, _ = indexer_cheminements_par_cable(str(tmp_path))
        assert index == {}

    def test_geometrie_negligeable_ecartee(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_FOURREAU, [_cheminement("f1", "c1", 0.0, EPSILON_LONGUEUR / 2)])
        index, _, _ = indexer_cheminements_par_cable(str(tmp_path))
        assert index == {}

    def test_geometrie_non_lineaire_ecartee(self, tmp_path: Any) -> None:
        feature = _cheminement("f1", "c1", 0.0, 10.0)
        feature["geometry"] = {"type": "Point", "coordinates": [0.0, 0.0]}
        _ecrire(tmp_path, COUCHE_FOURREAU, [feature])
        index, _, _ = indexer_cheminements_par_cable(str(tmp_path))
        assert index == {}


class TestAssembler:
    """Le recollement met la discontinuité en évidence."""

    def test_cheminements_contigus(self) -> None:
        assert len(assembler([_c("a", 0.0, 10.0), _c("b", 10.0, 20.0)])) == 1

    def test_cheminements_disjoints(self) -> None:
        assert len(assembler([_c("a", 0.0, 10.0), _c("b", 30.0, 40.0)])) == 2

    def test_cheminement_unique(self) -> None:
        assert len(assembler([_c("a", 0.0, 10.0)])) == 1

    def test_trois_troncons(self) -> None:
        troncons = assembler([_c("a", 0.0, 10.0), _c("b", 30.0, 40.0), _c("c", 60.0, 70.0)])
        assert len(troncons) == 3

    def test_ordre_de_declaration_indifferent(self) -> None:
        """Le recollement ne dépend pas de l'ordre de lecture du répertoire."""
        avant = assembler([_c("b", 10.0, 20.0), _c("a", 0.0, 10.0)])
        assert len(avant) == 1


class TestTolerance:
    """L'arrondi millimétrique ne doit pas faire sortir une voie continue."""

    def test_ecart_submillimetrique_recolle(self) -> None:
        troncons = assembler([_c("a", 0.0, 10.0), _c("b", 10.0005, 20.0)])
        assert len(troncons) == 2
        assert regrouper_a_la_tolerance(troncons) == 1

    def test_seuil_inclusif(self) -> None:
        troncons = assembler([_c("a", 0.0, 10.0), _c("b", 10.0 + TOLERANCE_SUPERPOSITION, 20.0)])
        assert regrouper_a_la_tolerance(troncons) == 1

    def test_ecart_centimetrique_signale(self) -> None:
        troncons = assembler([_c("a", 0.0, 10.0), _c("b", 10.02, 20.0)])
        assert regrouper_a_la_tolerance(troncons) == 2

    def test_regroupement_transitif(self) -> None:
        """Un tronçon peut souder deux groupes jusque-là séparés."""
        troncons = assembler([_c("a", 0.0, 10.0), _c("c", 20.0, 30.0), _c("b", 10.0005, 19.9995)])
        assert len(troncons) == 3
        assert regrouper_a_la_tolerance(troncons) == 1

    def test_deux_groupes_distincts(self) -> None:
        troncons = assembler([_c("a", 0.0, 10.0), _c("b", 10.0005, 20.0), _c("c", 90.0, 100.0)])
        assert regrouper_a_la_tolerance(troncons) == 2


class TestEcartMinimal:
    """La distance rendue est celle des deux tronçons les plus proches."""

    def test_deux_troncons(self) -> None:
        assert ecart_minimal(assembler([_c("a", 0.0, 10.0), _c("b", 15.0, 20.0)])) == 5.0

    def test_le_plus_faible_retenu(self) -> None:
        troncons = assembler([_c("a", 0.0, 10.0), _c("b", 12.0, 20.0), _c("c", 100.0, 110.0)])
        assert ecart_minimal(troncons) == 2.0


class TestDetecterAnomalies:
    """Une anomalie par câble, documentée."""

    def test_voie_continue(self) -> None:
        assert detecter_anomalies({"c1": [_c("a", 0.0, 10.0), _c("b", 10.0, 20.0)]}) == []

    def test_cable_a_un_seul_cheminement(self) -> None:
        assert detecter_anomalies({"c1": [_c("a", 0.0, 10.0)]}) == []

    def test_voie_interrompue(self) -> None:
        anomalies = detecter_anomalies({"c1": [_c("a", 0.0, 10.0), _c("b", 30.0, 40.0)]})
        assert [a["type_anomalie"] for a in anomalies] == [TYPE_ANOMALIE]

    def test_anomalie_documentee(self) -> None:
        cheminements = [_c("f1", 0.0, 10.0), _c("g1", 30.0, 40.0, COUCHE_GALERIE)]
        anomalie = detecter_anomalies({"c1": cheminements})[0]
        assert anomalie["id_cable"] == "c1"
        assert anomalie["nombre_cheminements"] == 2
        assert anomalie["nombre_troncons"] == 2
        assert anomalie["ecart_minimal_m"] == 20.0
        assert anomalie["couches"] == sorted([COUCHE_FOURREAU, COUCHE_GALERIE])
        assert anomalie["ids_cheminements"] == ["f1", "g1"]

    def test_une_anomalie_par_cable(self) -> None:
        index = {
            "c1": [_c("a", 0.0, 10.0), _c("b", 30.0, 40.0)],
            "c2": [_c("d", 0.0, 10.0), _c("e", 60.0, 70.0)],
        }
        assert [a["id_cable"] for a in detecter_anomalies(index)] == ["c1", "c2"]

    def test_ordre_deterministe(self) -> None:
        index = {nom: [_c("a", 0.0, 10.0), _c("b", 30.0, 40.0)] for nom in ("c3", "c1", "c2")}
        assert [a["id_cable"] for a in detecter_anomalies(index)] == ["c1", "c2", "c3"]

    def test_geometrie_est_la_voie_entiere(self) -> None:
        anomalie = detecter_anomalies({"c1": [_c("a", 0.0, 10.0), _c("b", 30.0, 40.0)]})[0]
        assert anomalie["geometrie"]["type"] == "MultiLineString"


class TestGeojsonEcarts:
    """Le socle commun et les champs de diagnostic."""

    def _props(self) -> dict[str, Any]:
        anomalies = detecter_anomalies({"c1": [_c("a", 0.0, 10.0), _c("b", 30.0, 40.0)]})
        return construire_geojson_ecarts(anomalies)["features"][0]["properties"]

    def test_socle_commun(self) -> None:
        props = self._props()
        assert props["code_controle"] == "E-9401"
        assert props["code_erreur"] == "E-9401"
        assert props["id_entite"] == "c1"
        assert props["priorite"] == "forte"
        assert props["description"] != TYPE_ANOMALIE

    def test_diagnostic_expose(self) -> None:
        props = self._props()
        assert props["nombre_troncons"] == 2
        assert props["ecart_minimal_m"] == 20.0
        assert props["ids_cheminements"] == "a, b"

    def test_crs_propage(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        anomalies = detecter_anomalies({"c1": [_c("a", 0.0, 10.0), _c("b", 30.0, 40.0)]})
        assert construire_geojson_ecarts(anomalies, crs)["crs"] == crs

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([])["features"] == []


class TestCli:
    """Exécution du contrôle."""

    def _executer(self, repertoire: str, sortie: str | None = None) -> dict[str, Any]:
        from recostar.controle.cheminement.e9401 import executer_controle_cli

        return executer_controle_cli(repertoire, sortie)

    def test_repertoire_introuvable(self) -> None:
        assert self._executer("/chemin/inexistant")["succes"] is False

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        resultat = self._executer(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_voie_continue(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_FOURREAU, [_cheminement("f1", "c1", 0.0, 10.0)])
        _ecrire(tmp_path, COUCHE_GALERIE, [_cheminement("g1", "c1", 10.0, 20.0)])
        assert self._executer(str(tmp_path))["nombre_anomalies"] == 0

    def test_voie_interrompue(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_FOURREAU, [_cheminement("f1", "c1", 0.0, 10.0)])
        _ecrire(tmp_path, COUCHE_AERIEN, [_cheminement("a1", "c1", 30.0, 40.0)])
        resultat = self._executer(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_ANOMALIE: 1}
        assert resultat["nombre_cables_controles"] == 1
        assert resultat["nombre_cheminements_indexes"] == 2

    def test_tolerance_reportee(self, tmp_path: Any) -> None:
        assert self._executer(str(tmp_path))["tolerance_jonction_m"] == TOLERANCE_SUPERPOSITION

    def test_fichier_sortie_ecrit(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_FOURREAU, [_cheminement("f1", "c1", 0.0, 10.0), _cheminement("f2", "c1", 30.0, 40.0)])
        chemin = self._executer(str(tmp_path))["sortie"]
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))
        with open(chemin, encoding="utf-8") as fichier:
            props = json.load(fichier)["features"][0]["properties"]
        assert props["code_erreur"] == "E-9401"

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        _ecrire(tmp_path, COUCHE_FOURREAU, [_cheminement("f1", "c1", 0.0, 10.0), _cheminement("f2", "c1", 10.0, 20.0)])
        self._executer(str(tmp_path))
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_repertoire_sortie_distinct(self, tmp_path: Any) -> None:
        source = tmp_path / "src"
        source.mkdir()
        destination = tmp_path / "dst"
        _ecrire(source, COUCHE_FOURREAU, [_cheminement("f1", "c1", 0.0, 10.0), _cheminement("f2", "c1", 30.0, 40.0)])
        self._executer(str(source), str(destination))
        assert os.path.isfile(str(destination / FICHIER_SORTIE))
