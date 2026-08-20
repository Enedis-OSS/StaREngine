"""
Tests du controle E507 : coherence geometrique jonction / extremite de cable.

Couvre :
  - le chargement des cables controles (filtre Statut) et des jonctions
  - la conformite d'une jonction posee sur une extremite
  - la non-conformite d'une jonction sur un sommet intermediaire ou hors trace
  - la comparaison planimetrique stricte (XY exact, Z ignore)
  - les extremites topologiques d'un MultiLineString aux parties desordonnees
  - le perimetre (statut, references hors perimetre, geometries non exploitables)
  - la memorisation des extremites (aucune decomposition redondante)
  - la construction du GeoJSON d'ecarts et l'execution CLI complete
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import os
from typing import Any

from controle_e507 import (
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_JONCTION,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    STATUT_CONTROLE,
    TYPE_ANOMALIE,
    EntiteJonction,
    _obtenir_extremites,
    charger_geometries_cables_controles,
    charger_jonctions,
    compter_liens_controles,
    construire_geojson_ecarts,
    detecter_anomalies,
    executer_controle_cli,
)
from utils_tests import ecrire_collection

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

# Cable de reference : trace en trois sommets, extremites (0,0) et (100,0)
EXTREMITE_A: list[float] = [0.0, 0.0, 10.0]
SOMMET_INTERMEDIAIRE: list[float] = [50.0, 0.0, 10.0]
EXTREMITE_B: list[float] = [100.0, 0.0, 10.0]
TRACE_CABLE: list[list[float]] = [EXTREMITE_A, SOMMET_INTERMEDIAIRE, EXTREMITE_B]


def _feature_cable(
    identifiant: str,
    coordonnees: list[list[float]] | None = None,
    statut: str = STATUT_CONTROLE,
    geometrie: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Feature GeoJSON d'un cable electrique."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, "Statut": statut},
        "geometry": geometrie or {"type": "LineString", "coordinates": coordonnees or TRACE_CABLE},
    }


def _feature_jonction(
    identifiant: str,
    coordonnees: list[float],
    cables_href: Any = None,
    proprietes_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Feature GeoJSON Point d'une jonction referencant des cables."""
    proprietes: dict[str, Any] = {"id": identifiant, "cables_href": cables_href}
    if proprietes_extra:
        proprietes.update(proprietes_extra)
    return {
        "type": "Feature",
        "properties": proprietes,
        "geometry": {"type": "Point", "coordinates": coordonnees},
    }


def _ecrire_jeu_avec_anomalie(repertoire: str) -> None:
    """Ecrit un cable et une jonction en sommet intermediaire (anomalie garantie)."""
    ecrire_collection(os.path.join(repertoire, FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1")])
    ecrire_collection(
        os.path.join(repertoire, FICHIER_JONCTION),
        [_feature_jonction("j1", SOMMET_INTERMEDIAIRE, "c1")],
    )


def _jonction(
    identifiant: str,
    point: tuple[float, float] | None,
    ids_cables: list[str],
) -> EntiteJonction:
    """EntiteJonction minimale pour les tests de detection."""
    return EntiteJonction(id_entite=identifiant, point=point, ids_cables=ids_cables, geometrie=None)


def _geometries(coordonnees: list[list[float]] | None = None) -> dict[str, Any]:
    """Index {id_cable: geometrie} a un seul cable."""
    return {"c1": {"type": "LineString", "coordinates": coordonnees or TRACE_CABLE}}


# --------------------------------------------------------------------------- #
# Chargement des cables
# --------------------------------------------------------------------------- #


class TestChargerGeometriesCablesControles:
    """Tests de charger_geometries_cables_controles."""

    def test_filtre_le_statut(self, tmp_path: Any) -> None:
        ecrire_collection(
            os.path.join(tmp_path, FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1"), _feature_cable("c2", statut="Commissioned")],
        )
        index, absent = charger_geometries_cables_controles(str(tmp_path))
        assert set(index) == {"c1"}
        assert absent is False

    def test_cable_sans_identifiant_ignore(self, tmp_path: Any) -> None:
        cable = {"type": "Feature", "properties": {"Statut": STATUT_CONTROLE}, "geometry": None}
        ecrire_collection(os.path.join(tmp_path, FICHIER_CABLE_ELECTRIQUE), [cable])
        index, _ = charger_geometries_cables_controles(str(tmp_path))
        assert index == {}

    def test_fichier_absent(self, tmp_path: Any) -> None:
        index, absent = charger_geometries_cables_controles(str(tmp_path))
        assert index == {}
        assert absent is True


# --------------------------------------------------------------------------- #
# Chargement des jonctions
# --------------------------------------------------------------------------- #


class TestChargerJonctions:
    """Tests de charger_jonctions."""

    def test_jonction_sans_cables_href_ecartee(self, tmp_path: Any) -> None:
        """Une jonction sans reference ne peut produire aucun lien a controler."""
        ecrire_collection(
            os.path.join(tmp_path, FICHIER_JONCTION),
            [_feature_jonction("j1", EXTREMITE_A, None), _feature_jonction("j2", EXTREMITE_A, "c1")],
        )
        jonctions, _, _ = charger_jonctions(str(tmp_path))
        assert [j.id_entite for j in jonctions] == ["j2"]

    def test_point_extrait_en_2d(self, tmp_path: Any) -> None:
        ecrire_collection(
            os.path.join(tmp_path, FICHIER_JONCTION),
            [_feature_jonction("j1", [1.0, 2.0, 3.0], "c1")],
        )
        jonctions, _, _ = charger_jonctions(str(tmp_path))
        assert jonctions[0].point == (1.0, 2.0)

    def test_crs_retourne(self, tmp_path: Any) -> None:
        from utils_tests import ecrire_collection_avec_crs

        ecrire_collection_avec_crs(
            os.path.join(tmp_path, FICHIER_JONCTION),
            [_feature_jonction("j1", EXTREMITE_A, "c1")],
            "EPSG:2154",
        )
        _, _, crs = charger_jonctions(str(tmp_path))
        assert crs is not None
        assert "2154" in crs["properties"]["name"]

    def test_fichier_absent(self, tmp_path: Any) -> None:
        jonctions, absent, crs = charger_jonctions(str(tmp_path))
        assert jonctions == []
        assert absent is True
        assert crs is None


# --------------------------------------------------------------------------- #
# Detection des anomalies
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Tests de detecter_anomalies."""

    def test_jonction_sur_premiere_extremite(self) -> None:
        anomalies, _ = detecter_anomalies([_jonction("j1", (0.0, 0.0), ["c1"])], _geometries())
        assert anomalies == []

    def test_jonction_sur_derniere_extremite(self) -> None:
        anomalies, _ = detecter_anomalies([_jonction("j1", (100.0, 0.0), ["c1"])], _geometries())
        assert anomalies == []

    def test_jonction_sur_sommet_intermediaire(self) -> None:
        """Coeur de la regle : etre sur le trace ne suffit pas."""
        anomalies, _ = detecter_anomalies([_jonction("j1", (50.0, 0.0), ["c1"])], _geometries())
        assert len(anomalies) == 1
        assert anomalies[0]["id_jonction"] == "j1"
        assert anomalies[0]["id_cable"] == "c1"

    def test_jonction_sur_segment_hors_sommet(self) -> None:
        """Un point du segment, meme parfaitement aligne, n'est pas une extremite."""
        anomalies, _ = detecter_anomalies([_jonction("j1", (25.0, 0.0), ["c1"])], _geometries())
        assert len(anomalies) == 1

    def test_jonction_hors_trace(self) -> None:
        anomalies, _ = detecter_anomalies([_jonction("j1", (10.0, 40.0), ["c1"])], _geometries())
        assert len(anomalies) == 1

    def test_distance_diagnostic_reportee(self) -> None:
        """La distance a l'extremite la plus proche facilite le diagnostic."""
        anomalies, _ = detecter_anomalies([_jonction("j1", (3.0, 4.0), ["c1"])], _geometries())
        assert anomalies[0]["distance_extremite"] == 5.0

    def test_ecart_infime_non_tolere(self) -> None:
        """Aucune tolerance : la coincidence XY est une egalite stricte."""
        anomalies, _ = detecter_anomalies([_jonction("j1", (0.001, 0.0), ["c1"])], _geometries())
        assert len(anomalies) == 1

    def test_z_ignore(self) -> None:
        """Le Z n'entre pas dans la comparaison : XY exact suffit.

        Cas reel (Echantillon3) : jonction a 610.66 m, extremite du cable a
        610.67 m, XY identique au bit pres. Le defaut altimetrique releve
        d'E200-E209.
        """
        geometries = {"c1": {"type": "LineString", "coordinates": [[0.0, 0.0, 610.67], [100.0, 0.0, 5.0]]}}
        anomalies, _ = detecter_anomalies([_jonction("j1", (0.0, 0.0), ["c1"])], geometries)
        assert anomalies == []

    def test_multilinestring_parties_desordonnees(self) -> None:
        """Les vraies extremites, pas le premier/dernier sommet apres mise a plat."""
        geometries = {
            "c1": {
                "type": "MultiLineString",
                "coordinates": [
                    [[10.0, 0.0], [20.0, 0.0]],  # partie 0 : E1 -> E2
                    [[30.0, 0.0], [20.0, 0.0]],  # partie 1 : E3 -> E2
                ],
            }
        }
        # (10,0) et (30,0) sont les extremites topologiques
        anomalies, _ = detecter_anomalies([_jonction("j1", (10.0, 0.0), ["c1"])], geometries)
        assert anomalies == []
        anomalies, _ = detecter_anomalies([_jonction("j2", (30.0, 0.0), ["c1"])], geometries)
        assert anomalies == []
        # (20,0) est le point de raccord interne des deux parties : pas une extremite
        anomalies, _ = detecter_anomalies([_jonction("j3", (20.0, 0.0), ["c1"])], geometries)
        assert len(anomalies) == 1

    def test_reference_hors_perimetre_ignoree(self) -> None:
        """Cable d'un autre statut, d'un autre type ou inexistant : hors perimetre."""
        anomalies, _ = detecter_anomalies([_jonction("j1", (50.0, 0.0), ["inconnu"])], _geometries())
        assert anomalies == []

    def test_jonction_sans_geometrie_point(self) -> None:
        anomalies, _ = detecter_anomalies([_jonction("j1", None, ["c1"])], _geometries())
        assert anomalies == []

    def test_cable_boucle_non_exploitable(self) -> None:
        """Une geometrie fermee n'a aucune extremite : conformite non tranchable."""
        geometries = {"c1": {"type": "LineString", "coordinates": [[0.0, 0.0], [10.0, 10.0], [0.0, 0.0]]}}
        anomalies, non_exploitables = detecter_anomalies([_jonction("j1", (5.0, 5.0), ["c1"])], geometries)
        assert anomalies == []
        assert non_exploitables == {"c1"}

    def test_cable_sans_geometrie_non_exploitable(self) -> None:
        anomalies, non_exploitables = detecter_anomalies([_jonction("j1", (5.0, 5.0), ["c1"])], {"c1": None})
        assert anomalies == []
        assert non_exploitables == {"c1"}

    def test_une_anomalie_par_lien(self) -> None:
        """Une jonction liee a deux cables mal raccordes produit deux anomalies."""
        geometries = {
            "c1": {"type": "LineString", "coordinates": TRACE_CABLE},
            "c2": {"type": "LineString", "coordinates": TRACE_CABLE},
        }
        anomalies, _ = detecter_anomalies([_jonction("j1", (50.0, 0.0), ["c1", "c2"])], geometries)
        assert len(anomalies) == 2
        assert {a["id_cable"] for a in anomalies} == {"c1", "c2"}

    def test_plusieurs_jonctions_conformes(self) -> None:
        jonctions = [_jonction("j1", (0.0, 0.0), ["c1"]), _jonction("j2", (100.0, 0.0), ["c1"])]
        anomalies, _ = detecter_anomalies(jonctions, _geometries())
        assert anomalies == []


# --------------------------------------------------------------------------- #
# Memorisation des extremites
# --------------------------------------------------------------------------- #


class TestObtenirExtremites:
    """Tests de _obtenir_extremites (cache)."""

    def test_extremites_memorisees(self) -> None:
        cache: dict[str, Any] = {}
        geometries = _geometries()
        premier = _obtenir_extremites("c1", geometries, cache)
        second = _obtenir_extremites("c1", geometries, cache)
        assert premier == frozenset({(0.0, 0.0), (100.0, 0.0)})
        assert premier is second  # aucune redecomposition de la geometrie

    def test_cache_alimente(self) -> None:
        cache: dict[str, Any] = {}
        _obtenir_extremites("c1", _geometries(), cache)
        assert "c1" in cache

    def test_geometrie_vide_memorisee(self) -> None:
        """Un cable non exploitable n'est pas redecompose a chaque lien."""
        cache: dict[str, Any] = {}
        assert _obtenir_extremites("c1", {"c1": None}, cache) == frozenset()
        assert cache["c1"] == frozenset()


# --------------------------------------------------------------------------- #
# Comptage
# --------------------------------------------------------------------------- #


class TestCompterLiensControles:
    """Tests de compter_liens_controles."""

    def test_compte_les_liens_du_perimetre(self) -> None:
        jonctions = [
            _jonction("j1", (0.0, 0.0), ["c1", "hors_perimetre"]),
            _jonction("j2", (100.0, 0.0), ["c1"]),
        ]
        assert compter_liens_controles(jonctions, _geometries()) == 2

    def test_jonction_sans_point_exclue(self) -> None:
        assert compter_liens_controles([_jonction("j1", None, ["c1"])], _geometries()) == 0


# --------------------------------------------------------------------------- #
# GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def test_proprietes_anomalie(self) -> None:
        anomalies = [{"id_jonction": "j1", "id_cable": "c1", "distance_extremite": 12.5, "geometrie": None}]
        props = construire_geojson_ecarts(anomalies)["features"][0]["properties"]
        assert props["type_anomalie"] == TYPE_ANOMALIE
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["id_jonction"] == "j1"
        assert props["distance_extremite_m"] == 12.5

    def test_geometrie_de_la_jonction_conservee(self) -> None:
        """L'entite a repositionner est la jonction : c'est elle qu'on localise."""
        geometrie = {"type": "Point", "coordinates": [50.0, 0.0]}
        anomalies = [{"id_jonction": "j1", "id_cable": "c1", "distance_extremite": 50.0, "geometrie": geometrie}]
        assert construire_geojson_ecarts(anomalies)["features"][0]["geometry"] == geometrie

    def test_crs_propage(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([], crs)["crs"] == crs

    def test_sans_crs(self) -> None:
        assert "crs" not in construire_geojson_ecarts([])


# --------------------------------------------------------------------------- #
# Execution CLI
# --------------------------------------------------------------------------- #


class TestExecuterControleCli:
    """Tests de executer_controle_cli."""

    def test_repertoire_introuvable(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(os.path.join(tmp_path, "absent"))
        assert resultat["succes"] is False
        assert "erreur" in resultat

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["fichier_cable_absent"] is True
        assert resultat["fichier_jonction_absent"] is True

    def test_jeu_conforme(self, tmp_path: Any) -> None:
        ecrire_collection(os.path.join(tmp_path, FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1")])
        ecrire_collection(
            os.path.join(tmp_path, FICHIER_JONCTION),
            [_feature_jonction("j1", EXTREMITE_A, "c1"), _feature_jonction("j2", EXTREMITE_B, "c1")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_liens_controles"] == 2
        assert resultat["nombre_cables_controles"] == 1

    def test_jonction_intermediaire_detectee(self, tmp_path: Any) -> None:
        ecrire_collection(os.path.join(tmp_path, FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1")])
        ecrire_collection(
            os.path.join(tmp_path, FICHIER_JONCTION),
            [_feature_jonction("j1", SOMMET_INTERMEDIAIRE, "c1")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 1
        assert resultat["priorite"] == PRIORITE_ANOMALIE

    def test_cable_hors_statut_non_controle(self, tmp_path: Any) -> None:
        ecrire_collection(
            os.path.join(tmp_path, FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", statut="Commissioned")],
        )
        ecrire_collection(
            os.path.join(tmp_path, FICHIER_JONCTION),
            [_feature_jonction("j1", SOMMET_INTERMEDIAIRE, "c1")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_liens_controles"] == 0

    def test_cables_non_exploitables_reportes(self, tmp_path: Any) -> None:
        boucle = {"type": "LineString", "coordinates": [[0.0, 0.0], [10.0, 10.0], [0.0, 0.0]]}
        ecrire_collection(
            os.path.join(tmp_path, FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1", geometrie=boucle)],
        )
        ecrire_collection(
            os.path.join(tmp_path, FICHIER_JONCTION),
            [_feature_jonction("j1", [5.0, 5.0], "c1")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_cables_geometrie_non_exploitable"] == 1

    def test_fichier_sortie_ecrit(self, tmp_path: Any) -> None:
        _ecrire_jeu_avec_anomalie(str(tmp_path))
        resultat = executer_controle_cli(str(tmp_path))
        assert os.path.isfile(resultat["sortie"])
        assert resultat["sortie"].endswith(FICHIER_SORTIE)

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        ecrire_collection(os.path.join(tmp_path, FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(os.path.join(str(tmp_path), FICHIER_SORTIE))

    def test_repertoire_sortie_distinct(self, tmp_path: Any) -> None:
        entree = tmp_path / "entree"
        sortie = tmp_path / "sortie"
        entree.mkdir()
        _ecrire_jeu_avec_anomalie(str(entree))
        resultat = executer_controle_cli(str(entree), str(sortie))
        assert resultat["succes"] is True
        assert os.path.isfile(os.path.join(sortie, FICHIER_SORTIE))


# --------------------------------------------------------------------------- #
# Compatibilite V1.0 / V1.1
# --------------------------------------------------------------------------- #


class TestCompatibiliteVersions:
    """Le controle doit se comporter identiquement en V1.0 et V1.1."""

    def test_champs_additionnels_v1_1_sans_effet(self, tmp_path: Any) -> None:
        ecrire_collection(os.path.join(tmp_path, FICHIER_CABLE_ELECTRIQUE), [_feature_cable("c1")])
        ecrire_collection(
            os.path.join(tmp_path, FICHIER_JONCTION),
            [_feature_jonction("j1", EXTREMITE_A, "c1", proprietes_extra={"Commentaire": "essai", "Etiquette": "E"})],
        )
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_cables_href_separe_par_espaces(self, tmp_path: Any) -> None:
        """La convention d'espacement (E202) est acceptee comme la virgule."""
        ecrire_collection(
            os.path.join(tmp_path, FICHIER_CABLE_ELECTRIQUE),
            [_feature_cable("c1"), _feature_cable("c2")],
        )
        ecrire_collection(
            os.path.join(tmp_path, FICHIER_JONCTION),
            [_feature_jonction("j1", EXTREMITE_A, "c1 c2")],
        )
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0
