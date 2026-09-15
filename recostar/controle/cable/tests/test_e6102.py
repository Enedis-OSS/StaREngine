"""
Tests du controle E-6102 : le cable n'est pas coupe a chaque noeud.

Couvre :
  - la resolution de l'emprise le long de la chaine noeud -> conteneur -> geomsupp
  - les deux voies de conformite : coincidence avec le point, contact avec l'emprise
  - la distinction coupure manquante / noeud a l'ecart du trace (E-6111)
  - la tolerance planimetrique
  - la detection par cable, extremites indeterminees comprises
  - l'execution CLI complete
"""

import json
from typing import Any

from recostar.controle.cable.e6102 import (
    FICHIER_SORTIE,
    TYPE_CABLE_NON_COUPE,
    NoeudTraverse,
    classifier_noeud,
    compter_cables_non_conformes,
    construire_geojson_ecarts,
    detecter_anomalies_cable,
    est_a_une_extremite,
    est_sur_le_trace,
    executer_controle_cli,
    indexer_noeuds_par_cable,
    resoudre_emprise,
)
from recostar.controle.cable.tests.utils_tests import ecrire_collection
from recostar.controle.fonctions_communes.geojson import PRIORITE_FORTE
from recostar.controle.fonctions_communes.geometrie import forme_shapely
from recostar.controle.fonctions_communes.localisation_conteneur import Conteneur

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

COUCHE_NOEUD: str = "RPD_JeuBarres_Reco"
TRACE: dict[str, Any] = {"type": "LineString", "coordinates": [[0.0, 0.0], [100.0, 0.0]]}
EXTREMITES: list[tuple[float, float]] = [(0.0, 0.0), (100.0, 0.0)]

# Emprise carree d'un poste, de x=90 a x=110 et y=-10 a y=10
EMPRISE: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [[[90.0, -10.0], [110.0, -10.0], [110.0, 10.0], [90.0, 10.0], [90.0, -10.0]]],
}


def _noeud(point: tuple[float, float], emprise: Any | None = None) -> NoeudTraverse:
    return NoeudTraverse(couche=COUCHE_NOEUD, identifiant="n1", point=point, emprise=emprise)


def _feature(identifiant: str, proprietes: dict[str, Any], geometrie: Any) -> dict[str, Any]:
    props: dict[str, Any] = {"id": identifiant}
    props.update(proprietes)
    return {"type": "Feature", "properties": props, "geometry": geometrie}


def _cable(identifiant: str = "c1", trace: Any = None) -> dict[str, Any]:
    return _feature(identifiant, {"Statut": "UnderCommissionning"}, trace if trace is not None else TRACE)


def _feature_noeud(
    identifiant: str,
    point: tuple[float, float],
    cables: str = "c1",
    conteneur: str | None = None,
) -> dict[str, Any]:
    proprietes: dict[str, Any] = {"cables_href": cables, "Statut": "UnderCommissionning"}
    if conteneur is not None:
        proprietes["conteneur_href"] = conteneur
    return _feature(identifiant, proprietes, {"type": "Point", "coordinates": [point[0], point[1]]})


def _ecrire_jeu(
    tmp_path: Any,
    noeuds: list[dict[str, Any]],
    cables: list[dict[str, Any]] | None = None,
    avec_emprise: bool = False,
) -> None:
    """Ecrit un jeu complet : cables, noeuds et, au besoin, la chaine d'emprise."""
    ecrire_collection(
        str(tmp_path / "RPD_CableElectrique_Reco.geojson"),
        cables if cables is not None else [_cable()],
    )
    ecrire_collection(str(tmp_path / f"{COUCHE_NOEUD}.geojson"), noeuds)
    if avec_emprise:
        ecrire_collection(
            str(tmp_path / "RPD_Coffret_Reco.geojson"),
            [_feature("k1", {"geometriesupplementaire_href": "g1"}, {"type": "Point", "coordinates": [100.0, 0.0]})],
        )
        ecrire_collection(
            str(tmp_path / "RPD_GeometrieSupplementaire_Reco.geojson"),
            [_feature("g1", {}, EMPRISE)],
        )


# --------------------------------------------------------------------------- #
# Resolution de l'emprise
# --------------------------------------------------------------------------- #


class TestResoudreEmprise:
    """Chaine noeud -> conteneur -> geometrie supplementaire."""

    @staticmethod
    def _contexte() -> tuple[dict[str, Conteneur], dict[str, Any], dict[str, Any]]:
        return {"k1": Conteneur(None, "g1")}, {"g1": EMPRISE}, {}

    def test_chaine_complete(self) -> None:
        conteneurs, geomsupps, formes = self._contexte()
        emprise = resoudre_emprise({"conteneur_href": "k1"}, conteneurs, geomsupps, formes)
        assert emprise is not None

    def test_sans_conteneur(self) -> None:
        conteneurs, geomsupps, formes = self._contexte()
        assert resoudre_emprise({}, conteneurs, geomsupps, formes) is None

    def test_conteneur_introuvable(self) -> None:
        conteneurs, geomsupps, formes = self._contexte()
        assert resoudre_emprise({"conteneur_href": "k9"}, conteneurs, geomsupps, formes) is None

    def test_conteneur_sans_geomsupp(self) -> None:
        geomsupps: dict[str, Any] = {"g1": EMPRISE}
        assert resoudre_emprise({"conteneur_href": "k1"}, {"k1": Conteneur(None, None)}, geomsupps, {}) is None

    def test_geomsupp_introuvable(self) -> None:
        conteneurs, _, formes = self._contexte()
        assert resoudre_emprise({"conteneur_href": "k1"}, conteneurs, {}, formes) is None

    def test_forme_mise_en_cache(self) -> None:
        """Un poste heberge plusieurs noeuds : l'emprise n'est convertie qu'une fois."""
        conteneurs, geomsupps, formes = self._contexte()
        premiere = resoudre_emprise({"conteneur_href": "k1"}, conteneurs, geomsupps, formes)
        seconde = resoudre_emprise({"conteneur_href": "k1"}, conteneurs, geomsupps, formes)
        assert premiere is seconde
        assert list(formes) == ["g1"]


# --------------------------------------------------------------------------- #
# Regle metier
# --------------------------------------------------------------------------- #


class TestEstAUneExtremite:
    """Les deux voies de conformite."""

    def test_cas_1_coincidence_avec_le_point(self) -> None:
        assert est_a_une_extremite(_noeud((100.0, 0.0)), EXTREMITES) is True

    def test_cas_1_autre_extremite(self) -> None:
        assert est_a_une_extremite(_noeud((0.0, 0.0)), EXTREMITES) is True

    def test_noeud_au_milieu(self) -> None:
        assert est_a_une_extremite(_noeud((50.0, 0.0)), EXTREMITES) is False

    def test_tolerance_admise(self) -> None:
        """L'arrondi millimetrique de la source ne doit pas separer deux points."""
        assert est_a_une_extremite(_noeud((100.0005, 0.0)), EXTREMITES) is True

    def test_ecart_centimetrique_refuse(self) -> None:
        assert est_a_une_extremite(_noeud((100.05, 0.0)), EXTREMITES) is False

    def test_cas_2_extremite_dans_l_emprise(self) -> None:
        """Le cable s'arrete au bord du poste : le noeud est au centre."""
        emprise = forme_shapely(EMPRISE)
        assert est_a_une_extremite(_noeud((150.0, 0.0), emprise), EXTREMITES) is True

    def test_cas_2_emprise_a_l_ecart(self) -> None:
        loin = {"type": "Polygon", "coordinates": [[[500.0, 0.0], [510.0, 0.0], [510.0, 10.0], [500.0, 0.0]]]}
        assert est_a_une_extremite(_noeud((505.0, 5.0), forme_shapely(loin)), EXTREMITES) is False

    def test_sans_emprise_le_cas_2_ne_s_applique_pas(self) -> None:
        assert est_a_une_extremite(_noeud((150.0, 0.0)), EXTREMITES) is False


class TestEstSurLeTrace:
    """Distinction entre coupure manquante et noeud a l'ecart."""

    def test_noeud_sur_le_trace(self) -> None:
        assert est_sur_le_trace(forme_shapely(TRACE), _noeud((50.0, 0.0))) is True

    def test_noeud_a_l_ecart(self) -> None:
        assert est_sur_le_trace(forme_shapely(TRACE), _noeud((50.0, 25.0))) is False

    def test_trace_absent(self) -> None:
        assert est_sur_le_trace(None, _noeud((50.0, 0.0))) is False


class TestClassifierNoeud:
    """Composition des deux regles."""

    def test_noeud_traverse_signale(self) -> None:
        assert classifier_noeud(_noeud((50.0, 0.0)), EXTREMITES, forme_shapely(TRACE)) is True

    def test_noeud_a_une_extremite_conforme(self) -> None:
        assert classifier_noeud(_noeud((100.0, 0.0)), EXTREMITES, forme_shapely(TRACE)) is False

    def test_noeud_hors_trace_hors_perimetre(self) -> None:
        """Un noeud a l'ecart du cable releve d'E-6111, pas de ce controle."""
        assert classifier_noeud(_noeud((50.0, 25.0)), EXTREMITES, forme_shapely(TRACE)) is False

    def test_emprise_prime_sur_le_trace(self) -> None:
        """Le cable traverse l'emprise mais s'y termine : conforme."""
        noeud = NoeudTraverse(COUCHE_NOEUD, "n1", (100.0, 0.0), forme_shapely(EMPRISE))
        assert classifier_noeud(noeud, EXTREMITES, forme_shapely(TRACE)) is False


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


class TestDetecterAnomaliesCable:
    """Tests de detecter_anomalies_cable."""

    def test_anomalie_documentee(self) -> None:
        anomalies = detecter_anomalies_cable(_cable(), [_noeud((50.0, 0.0))])
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_CABLE_NON_COUPE
        assert anomalies[0]["id_cable"] == "c1"
        assert anomalies[0]["id_noeud"] == "n1"
        assert anomalies[0]["couche_noeud"] == COUCHE_NOEUD
        assert anomalies[0]["geometrie"] == {"type": "Point", "coordinates": [50.0, 0.0]}

    def test_une_anomalie_par_noeud_traverse(self) -> None:
        noeuds = [_noeud((25.0, 0.0)), _noeud((50.0, 0.0)), _noeud((75.0, 0.0))]
        assert len(detecter_anomalies_cable(_cable(), noeuds)) == 3

    def test_cable_conforme(self) -> None:
        assert detecter_anomalies_cable(_cable(), [_noeud((0.0, 0.0)), _noeud((100.0, 0.0))]) == []

    def test_cable_sans_geometrie_ignore(self) -> None:
        assert detecter_anomalies_cable(_feature("c1", {}, None), [_noeud((50.0, 0.0))]) == []

    def test_cable_ferme_ignore(self) -> None:
        """Une boucle n'a pas d'extremite : aucune position n'y vaut coupure."""
        boucle = {"type": "LineString", "coordinates": [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 0.0]]}
        assert detecter_anomalies_cable(_cable(trace=boucle), [_noeud((10.0, 0.0))]) == []

    def test_aucun_noeud(self) -> None:
        assert detecter_anomalies_cable(_cable(), []) == []


class TestComptages:
    """Tests des comptages du rapport."""

    def test_cables_non_conformes_dedoublonnes(self) -> None:
        anomalies = [{"id_cable": "c1"}, {"id_cable": "c1"}, {"id_cable": "c2"}]
        assert compter_cables_non_conformes(anomalies) == 2

    def test_liste_vide(self) -> None:
        assert compter_cables_non_conformes([]) == 0


# --------------------------------------------------------------------------- #
# Indexation
# --------------------------------------------------------------------------- #


class TestIndexerNoeudsParCable:
    """Tests de indexer_noeuds_par_cable."""

    def test_noeud_indexe(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_feature_noeud("n1", (50.0, 0.0))])
        index, _ = indexer_noeuds_par_cable(str(tmp_path))
        assert [noeud.identifiant for noeud in index["c1"]] == ["n1"]

    def test_noeud_multi_cables(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_feature_noeud("n1", (50.0, 0.0), cables="c1,c2")])
        index, _ = indexer_noeuds_par_cable(str(tmp_path))
        assert set(index) >= {"c1", "c2"}

    def test_noeud_sans_cable_ecarte(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_feature_noeud("n1", (50.0, 0.0), cables="")])
        assert indexer_noeuds_par_cable(str(tmp_path))[0] == {}

    def test_noeud_sans_geometrie_ecarte(self, tmp_path: Any) -> None:
        """Sans position, la coupure n'est pas jugeable : E-6105 a E-6109 s'en chargent."""
        noeud = _feature("n1", {"cables_href": "c1", "Statut": "UnderCommissionning"}, None)
        _ecrire_jeu(tmp_path, [noeud])
        assert indexer_noeuds_par_cable(str(tmp_path))[0] == {}

    def test_emprise_resolue(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_feature_noeud("n1", (100.0, 0.0), conteneur="k1")], avec_emprise=True)
        index, _ = indexer_noeuds_par_cable(str(tmp_path))
        assert index["c1"][0].emprise is not None

    def test_couches_absentes_remontees(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_feature_noeud("n1", (50.0, 0.0))])
        _, absentes = indexer_noeuds_par_cable(str(tmp_path))
        assert COUCHE_NOEUD not in absentes
        assert absentes


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts et execution CLI
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    @staticmethod
    def _anomalie() -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_CABLE_NON_COUPE,
            "id_cable": "c1",
            "id_noeud": "n1",
            "couche_noeud": COUCHE_NOEUD,
            "geometrie": {"type": "Point", "coordinates": [50.0, 0.0]},
        }

    def test_proprietes_du_socle(self) -> None:
        proprietes = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-6102"
        assert proprietes["priorite"] == PRIORITE_FORTE
        assert proprietes["couche_noeud"] == COUCHE_NOEUD

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([])["features"] == []


class TestCli:
    """Tests de executer_controle_cli."""

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_repertoire_vide_non_bloquant(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["fichier_cable_absent"] is True

    def test_noeud_traverse_signale(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_feature_noeud("n1", (50.0, 0.0))])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_CABLE_NON_COUPE: 1}
        assert resultat["nombre_cables_controles"] == 1
        assert resultat["nombre_cables_non_conformes"] == 1

    def test_noeuds_aux_extremites_conformes(self, tmp_path: Any) -> None:
        noeuds = [_feature_noeud("n1", (0.0, 0.0)), _feature_noeud("n2", (100.0, 0.0))]
        _ecrire_jeu(tmp_path, noeuds)
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_cable_finissant_dans_l_emprise_conforme(self, tmp_path: Any) -> None:
        """Le cas vise : le cable s'arrete au bord du poste, le noeud est au centre."""
        cable = _cable(trace={"type": "LineString", "coordinates": [[0.0, 0.0], [90.0, 0.0]]})
        _ecrire_jeu(tmp_path, [_feature_noeud("n1", (100.0, 0.0), conteneur="k1")], [cable], avec_emprise=True)
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_cable_traversant_l_emprise_signale(self, tmp_path: Any) -> None:
        """Le cable ne s'arrete pas dans le poste : la coupure manque bien."""
        cable = _cable(trace={"type": "LineString", "coordinates": [[0.0, 0.0], [200.0, 0.0]]})
        _ecrire_jeu(tmp_path, [_feature_noeud("n1", (100.0, 0.0), conteneur="k1")], [cable], avec_emprise=True)
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 1

    def test_cable_hors_statut_ignore(self, tmp_path: Any) -> None:
        cable = _feature("c1", {"Statut": "Functional"}, TRACE)
        _ecrire_jeu(tmp_path, [_feature_noeud("n1", (50.0, 0.0))], [cable])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_cables_controles"] == 0
        assert resultat["nombre_anomalies"] == 0

    def test_fichier_ecarts_ecrit(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_feature_noeud("n1", (50.0, 0.0))])
        chemin = executer_controle_cli(str(tmp_path))["sortie"]
        assert chemin is not None
        assert chemin.endswith(FICHIER_SORTIE)
        with open(chemin, encoding="utf-8") as flux:
            proprietes = json.load(flux)["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-6102"
        assert proprietes["id_cable"] == "c1"

    def test_aucun_fichier_si_conforme(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_feature_noeud("n1", (0.0, 0.0))])
        assert executer_controle_cli(str(tmp_path))["sortie"] is None
