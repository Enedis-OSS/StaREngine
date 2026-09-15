"""
Tests du controle E500 : coherence du DomaineTension jonction / cables electriques.

Couvre :
  - extraction des references cables_href
  - chargement de l'index des DomaineTension des cables electriques
  - chargement des jonctions (avec/sans fichier, propagation du crs)
  - detection des incoherences (nominal, incoherent, references hors perimetre)
  - construction du GeoJSON d'ecarts
  - execution CLI complete
  - comportement identique en RecoStaR V1.0 et V1.1
"""

import os
from typing import Any

from controle_e500 import (
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_JONCTION,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    TYPE_ANOMALIE,
    EntiteJonction,
    _analyser_jonction,
    charger_domaines_tension_cables,
    charger_jonctions,
    compter_liens_controles,
    construire_geojson_ecarts,
    detecter_anomalies,
    executer_controle_cli,
)
from utils_cable import extraire_ids_cables_href
from utils_tests import (
    construire_feature_cable_electrique,
    construire_feature_jonction,
    ecrire_collection,
    ecrire_collection_avec_crs,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _jonction(
    identifiant: str = "j1",
    domaine_tension: Any = "BT",
    ids_cables: list[str] | None = None,
) -> EntiteJonction:
    """Construit une EntiteJonction de test."""
    return EntiteJonction(
        id_entite=identifiant,
        domaine_tension=domaine_tension,
        ids_cables=ids_cables if ids_cables is not None else [],
        geometrie={"type": "Point", "coordinates": [0.0, 0.0]},
    )


# --------------------------------------------------------------------------- #
# Extraction des references cables_href
# --------------------------------------------------------------------------- #


class TestExtraireIdsCablesHref:
    """Tests de utils_cable.extraire_ids_cables_href."""

    def test_chaine_unique(self) -> None:
        assert extraire_ids_cables_href("idA") == ["idA"]

    def test_chaine_multiple_virgules(self) -> None:
        assert extraire_ids_cables_href("idA,idB,idC") == ["idA", "idB", "idC"]

    def test_chaine_multiple_espaces(self) -> None:
        # Convention du controle aerien E202 (separateur espace)
        assert extraire_ids_cables_href("idA idB idC") == ["idA", "idB", "idC"]

    def test_espaces_ignores(self) -> None:
        assert extraire_ids_cables_href(" idA , idB ") == ["idA", "idB"]

    def test_liste(self) -> None:
        assert extraire_ids_cables_href(["idA", "idB"]) == ["idA", "idB"]

    def test_none_retourne_liste_vide(self) -> None:
        assert extraire_ids_cables_href(None) == []

    def test_chaine_vide_retourne_liste_vide(self) -> None:
        assert extraire_ids_cables_href("") == []


# --------------------------------------------------------------------------- #
# Chargement de l'index des cables electriques
# --------------------------------------------------------------------------- #


class TestChargerDomainesTensionCables:
    """Tests de charger_domaines_tension_cables."""

    def test_fichier_absent(self, tmp_path: Any) -> None:
        index, absent = charger_domaines_tension_cables(str(tmp_path))
        assert index == {}
        assert absent is True

    def test_index_id_vers_domaine(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [
                construire_feature_cable_electrique("c1", "BT"),
                construire_feature_cable_electrique("c2", "HTA"),
            ],
        )
        index, absent = charger_domaines_tension_cables(str(tmp_path))
        assert absent is False
        assert index == {"c1": "BT", "c2": "HTA"}

    def test_cable_sans_id_ignore(self, tmp_path: Any) -> None:
        feature = construire_feature_cable_electrique("c1", "BT")
        feature["properties"].pop("id")
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [feature])
        index, _ = charger_domaines_tension_cables(str(tmp_path))
        assert index == {}

    def test_domaine_absent_stocke_none(self, tmp_path: Any) -> None:
        feature = construire_feature_cable_electrique("c1", None)
        feature["properties"].pop("DomaineTension")
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), [feature])
        index, _ = charger_domaines_tension_cables(str(tmp_path))
        assert index == {"c1": None}


# --------------------------------------------------------------------------- #
# Chargement des jonctions
# --------------------------------------------------------------------------- #


class TestChargerJonctions:
    """Tests de charger_jonctions."""

    def test_fichier_absent(self, tmp_path: Any) -> None:
        jonctions, absent, crs = charger_jonctions(str(tmp_path))
        assert jonctions == []
        assert absent is True
        assert crs is None

    def test_chargement_nominal(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", "BT", "c1,c2")],
        )
        jonctions, absent, _ = charger_jonctions(str(tmp_path))
        assert absent is False
        assert len(jonctions) == 1
        assert jonctions[0].id_entite == "j1"
        assert jonctions[0].domaine_tension == "BT"
        assert jonctions[0].ids_cables == ["c1", "c2"]

    def test_crs_propage(self, tmp_path: Any) -> None:
        ecrire_collection_avec_crs(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", "BT", "c1")],
            "EPSG:2154",
        )
        _, _, crs = charger_jonctions(str(tmp_path))
        assert crs is not None
        assert crs["properties"]["name"].endswith("2154")


# --------------------------------------------------------------------------- #
# Detection des incoherences
# --------------------------------------------------------------------------- #


class TestAnalyserJonction:
    """Tests de _analyser_jonction."""

    def test_domaines_identiques_aucune_anomalie(self) -> None:
        jonction = _jonction("j1", "BT", ["c1"])
        assert _analyser_jonction(jonction, {"c1": "BT"}) == []

    def test_domaines_differents_anomalie(self) -> None:
        jonction = _jonction("j1", "BT", ["c1"])
        anomalies = _analyser_jonction(jonction, {"c1": "HTA"})
        assert len(anomalies) == 1
        assert anomalies[0]["id_jonction"] == "j1"
        assert anomalies[0]["id_cable"] == "c1"
        assert anomalies[0]["domaine_tension_jonction"] == "BT"
        assert anomalies[0]["domaine_tension_cable"] == "HTA"

    def test_une_anomalie_par_cable_incoherent(self) -> None:
        jonction = _jonction("j1", "BT", ["c1", "c2", "c3"])
        index = {"c1": "BT", "c2": "HTA", "c3": "HTB"}
        anomalies = _analyser_jonction(jonction, index)
        assert len(anomalies) == 2  # c2 et c3 different, c1 conforme

    def test_reference_cable_non_electrique_ignoree(self) -> None:
        # c_terre n'est pas dans l'index electrique -> hors perimetre E500
        jonction = _jonction("j1", "BT", ["c_terre"])
        assert _analyser_jonction(jonction, {"c1": "BT"}) == []

    def test_reference_orpheline_ignoree(self) -> None:
        jonction = _jonction("j1", "BT", ["inexistant"])
        assert _analyser_jonction(jonction, {}) == []

    def test_jonction_sans_cable_aucune_anomalie(self) -> None:
        assert _analyser_jonction(_jonction("j1", "BT", []), {"c1": "BT"}) == []

    def test_jonction_domaine_none_vs_cable_bt(self) -> None:
        # Comparaison stricte : None != "BT" -> anomalie
        jonction = _jonction("j1", None, ["c1"])
        assert len(_analyser_jonction(jonction, {"c1": "BT"})) == 1

    def test_jonction_none_et_cable_none_conforme(self) -> None:
        jonction = _jonction("j1", None, ["c1"])
        assert _analyser_jonction(jonction, {"c1": None}) == []


class TestDetecterAnomalies:
    """Tests de detecter_anomalies et compter_liens_controles."""

    def test_plusieurs_jonctions(self) -> None:
        jonctions = [
            _jonction("j1", "BT", ["c1"]),  # conforme
            _jonction("j2", "HTA", ["c2"]),  # incoherent (c2 = BT)
        ]
        index = {"c1": "BT", "c2": "BT"}
        anomalies = detecter_anomalies(jonctions, index)
        assert len(anomalies) == 1
        assert anomalies[0]["id_jonction"] == "j2"

    def test_aucune_jonction(self) -> None:
        assert detecter_anomalies([], {"c1": "BT"}) == []

    def test_compter_liens_controles(self) -> None:
        jonctions = [
            _jonction("j1", "BT", ["c1", "c_terre"]),  # 1 lien electrique
            _jonction("j2", "BT", ["c2"]),  # 1 lien electrique
        ]
        index = {"c1": "BT", "c2": "BT"}
        assert compter_liens_controles(jonctions, index) == 2


# --------------------------------------------------------------------------- #
# Construction du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "id_jonction": "j1",
            "id_cable": "c1",
            "domaine_tension_jonction": "BT",
            "domaine_tension_cable": "HTA",
            "geometrie": {"type": "Point", "coordinates": [1.0, 2.0]},
        }

    def test_type_feature_collection(self) -> None:
        resultat = construire_geojson_ecarts([self._anomalie()])
        assert resultat["type"] == "FeatureCollection"

    def test_proprietes(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["type_anomalie"] == TYPE_ANOMALIE
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["id_jonction"] == "j1"
        assert props["id_cable"] == "c1"
        assert props["domaine_tension_jonction"] == "BT"
        assert props["domaine_tension_cable"] == "HTA"

    def test_geometrie_jonction_conservee(self) -> None:
        geom = construire_geojson_ecarts([self._anomalie()])["features"][0]["geometry"]
        assert geom == {"type": "Point", "coordinates": [1.0, 2.0]}

    def test_sans_crs(self) -> None:
        assert "crs" not in construire_geojson_ecarts([self._anomalie()])

    def test_avec_crs(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([self._anomalie()], crs)["crs"] == crs

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([])["features"] == []


# --------------------------------------------------------------------------- #
# Execution CLI
# --------------------------------------------------------------------------- #


class TestCli:
    """Tests de executer_controle_cli."""

    def _ecrire_jeu(
        self,
        tmp_path: Any,
        jonctions: list[dict[str, Any]],
        cables: list[dict[str, Any]],
    ) -> None:
        """Ecrit un jeu de donnees minimal (jonctions + cables electriques)."""
        ecrire_collection(str(tmp_path / FICHIER_JONCTION), jonctions)
        ecrire_collection(str(tmp_path / FICHIER_CABLE_ELECTRIQUE), cables)

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_nominal_sans_anomalie(self, tmp_path: Any) -> None:
        self._ecrire_jeu(
            tmp_path,
            [construire_feature_jonction("j1", "BT", "c1")],
            [construire_feature_cable_electrique("c1", "BT")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_jonctions_analysees"] == 1
        assert resultat["nombre_cables_electriques"] == 1
        assert resultat["nombre_liens_controles"] == 1

    def test_nominal_avec_anomalie(self, tmp_path: Any) -> None:
        self._ecrire_jeu(
            tmp_path,
            [construire_feature_jonction("j1", "BT", "c1")],
            [construire_feature_cable_electrique("c1", "HTA")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 1

    def test_fichiers_absents_signales(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichier_jonction_absent"] is True
        assert resultat["fichier_cable_absent"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        self._ecrire_jeu(
            tmp_path,
            [construire_feature_jonction("j1", "BT", "c1")],
            [construire_feature_cable_electrique("c1", "HTA")],
        )
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_sortie_personnalisee(self, tmp_path: Any) -> None:
        # Domaines de tension incoherents : anomalie garantie
        self._ecrire_jeu(
            tmp_path,
            [construire_feature_jonction("j1", "BT", "c1")],
            [construire_feature_cable_electrique("c1", "HTA")],
        )
        dossier_sortie = str(tmp_path / "resultats")
        executer_controle_cli(str(tmp_path), dossier_sortie)
        assert os.path.isfile(os.path.join(dossier_sortie, FICHIER_SORTIE))

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        self._ecrire_jeu(
            tmp_path,
            [construire_feature_jonction("j1", "BT", "c1")],
            [construire_feature_cable_electrique("c1", "BT")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_rapport_champs_obligatoires(self, tmp_path: Any) -> None:
        self._ecrire_jeu(
            tmp_path,
            [construire_feature_jonction("j1", "BT", "c1")],
            [construire_feature_cable_electrique("c1", "BT")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "nombre_jonctions_analysees",
            "nombre_cables_electriques",
            "nombre_liens_controles",
            "fichier_jonction_absent",
            "fichier_cable_absent",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"


# --------------------------------------------------------------------------- #
# Comportement multi-version (V1.0 / V1.1)
# --------------------------------------------------------------------------- #


class TestMultiVersion:
    """Le controle doit se comporter identiquement en V1.0 et V1.1.

    Les jeux V1.1 comportent des champs additionnels (Commentaire, Etiquette)
    qui ne doivent pas influencer le resultat : seuls id, DomaineTension et
    cables_href sont pertinents.
    """

    # Champs additionnels presents uniquement en V1.1
    _EXTRA_JONCTION_V11 = {"Commentaire": "note"}
    _EXTRA_CABLE_V11 = {"Etiquette": "E1", "Commentaire": "note"}

    def _jeu_v10(self, tmp_path: Any, dt_jonction: str, dt_cable: str) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", dt_jonction, "c1")],
        )
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [construire_feature_cable_electrique("c1", dt_cable)],
        )

    def _jeu_v11(self, tmp_path: Any, dt_jonction: str, dt_cable: str) -> None:
        ecrire_collection(
            str(tmp_path / FICHIER_JONCTION),
            [construire_feature_jonction("j1", dt_jonction, "c1", proprietes_extra=self._EXTRA_JONCTION_V11)],
        )
        ecrire_collection(
            str(tmp_path / FICHIER_CABLE_ELECTRIQUE),
            [construire_feature_cable_electrique("c1", dt_cable, proprietes_extra=self._EXTRA_CABLE_V11)],
        )

    def test_v10_coherent(self, tmp_path: Any) -> None:
        self._jeu_v10(tmp_path, "BT", "BT")
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_v10_incoherent(self, tmp_path: Any) -> None:
        self._jeu_v10(tmp_path, "BT", "HTA")
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 1

    def test_v11_coherent(self, tmp_path: Any) -> None:
        self._jeu_v11(tmp_path, "BT", "BT")
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_v11_incoherent(self, tmp_path: Any) -> None:
        self._jeu_v11(tmp_path, "BT", "HTA")
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 1

    def test_champs_v11_sans_effet(self, tmp_path: Any) -> None:
        # Meme incoherence detectee que la version soit enrichie ou non
        self._jeu_v10(tmp_path, "BT", "HTA")
        r_v10 = executer_controle_cli(str(tmp_path))["nombre_anomalies"]
        self._jeu_v11(tmp_path, "BT", "HTA")
        r_v11 = executer_controle_cli(str(tmp_path))["nombre_anomalies"]
        assert r_v10 == r_v11 == 1
