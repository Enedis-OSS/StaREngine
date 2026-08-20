"""
Tests du controle E606 : localisation des remontees aero-souterraines.

Couvre :
  - le filtre de perimetre (TypeJonction et Statut)
  - l'indexation conjointe des conteneurs et des supports
  - le cas 1, geometrie propre, et sa distinction d'avec une geometrie heritee
  - le cas 2, voie du support, et ses cinq motifs de rupture
  - la disjonction : une seule des deux voies suffit
  - la construction du GeoJSON d'ecarts
  - l'execution CLI
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import json
import os
from typing import Any

from controle_e606 import (
    CHAMP_CONTENEUR_HREF,
    CHAMP_GEOMSUPP_HREF,
    CHAMP_STATUT,
    CHAMP_TYPE_JONCTION,
    COUCHE_SUPPORT,
    EXTENSION,
    FICHIER_JONCTION,
    FICHIER_SORTIE,
    MOTIF_CONTENEUR_NON_SUPPORT,
    MOTIF_GEOMSUPP_ABSENTE,
    MOTIF_GEOMSUPP_INTROUVABLE,
    MOTIF_GEOMSUPP_INVALIDE,
    MOTIF_SUPPORT_ABSENT,
    MOTIF_SUPPORT_INTROUVABLE,
    PRIORITE_ANOMALIE,
    STATUTS_CONTROLES,
    TYPE_JONCTION_CONTROLE,
    TYPE_LOCALISATION_ABSENTE,
    Conteneur,
    classifier_jonction,
    compter_jonctions_a_controler,
    construire_geojson_ecarts,
    detecter_anomalies,
    est_a_controler,
    executer_controle_cli,
    indexer_conteneurs_et_supports,
    motif_echec_support,
    possede_geometrie_propre,
)
from utils_geojson import EXTENSION_GEOJSON
from utils_tests import ecrire_collection, ecrire_collection_avec_crs

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

GEOM_SUPPORT: dict[str, Any] = {"type": "Point", "coordinates": [10.0, 20.0, 30.0]}
GEOM_PROPRE: dict[str, Any] = {"type": "Point", "coordinates": [99.0, 99.0, 99.0]}
GEOM_SUPP: dict[str, Any] = {"type": "Polygon", "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]]}


def _jonction(
    identifiant: str = "j1",
    conteneur_href: Any = "s1",
    geometrie: Any = GEOM_SUPPORT,
    type_jonction: str = TYPE_JONCTION_CONTROLE,
    statut: str = "UnderCommissionning",
) -> dict[str, Any]:
    """Jonction RAS dont la geometrie est, par defaut, heritee du support."""
    return {
        "type": "Feature",
        "properties": {
            "id": identifiant,
            CHAMP_TYPE_JONCTION: type_jonction,
            CHAMP_STATUT: statut,
            CHAMP_CONTENEUR_HREF: conteneur_href,
        },
        "geometry": geometrie,
    }


def _conteneurs(href_geomsupp: str | None = "g1", geometrie: Any = GEOM_SUPPORT) -> dict[str, Conteneur]:
    return {"s1": Conteneur(geometrie, href_geomsupp)}


def _supports() -> frozenset[str]:
    return frozenset({"s1"})


def _geomsupps(geometrie: Any = GEOM_SUPP) -> dict[str, Any]:
    return {"g1": geometrie}


def _ecrire_jeu(
    tmp_path: Any,
    jonctions: list[dict[str, Any]] | None = None,
    couche_conteneur: str = COUCHE_SUPPORT,
    href_geomsupp: Any = "g1",
    geom_supp: Any = GEOM_SUPP,
) -> None:
    """Ecrit un jeu complet : jonction, conteneur et geometrie supplementaire."""
    ecrire_collection(
        str(tmp_path / FICHIER_JONCTION),
        jonctions if jonctions is not None else [_jonction()],
    )
    ecrire_collection(
        str(tmp_path / f"{couche_conteneur}{EXTENSION}"),
        [
            {
                "type": "Feature",
                "properties": {"id": "s1", CHAMP_GEOMSUPP_HREF: href_geomsupp},
                "geometry": GEOM_SUPPORT,
            }
        ],
    )
    ecrire_collection(
        str(tmp_path / f"RPD_GeometrieSupplementaire_Reco{EXTENSION}"),
        [{"type": "Feature", "properties": {"id": "g1"}, "geometry": geom_supp}],
    )


# --------------------------------------------------------------------------- #
# Perimetre
# --------------------------------------------------------------------------- #


class TestEstAControler:
    """Tests du filtre de perimetre."""

    def test_remontee_under_commissionning(self) -> None:
        assert est_a_controler(_jonction()["properties"]) is True

    def test_remontee_functional(self) -> None:
        assert est_a_controler(_jonction(statut="Functional")["properties"]) is True

    def test_autre_statut_ignore(self) -> None:
        assert est_a_controler(_jonction(statut="Decommissioned")["properties"]) is False

    def test_autre_type_jonction_ignore(self) -> None:
        assert est_a_controler(_jonction(type_jonction="Derivation")["properties"]) is False

    def test_type_absent_ignore(self) -> None:
        assert est_a_controler({CHAMP_STATUT: "Functional"}) is False

    def test_statut_absent_ignore(self) -> None:
        assert est_a_controler({CHAMP_TYPE_JONCTION: TYPE_JONCTION_CONTROLE}) is False

    def test_perimetre_declare(self) -> None:
        assert TYPE_JONCTION_CONTROLE == "RemonteeAeroSouterraine"
        assert STATUTS_CONTROLES == frozenset({"UnderCommissionning", "Functional"})


# --------------------------------------------------------------------------- #
# Indexation
# --------------------------------------------------------------------------- #


class TestIndexerConteneursEtSupports:
    """Tests de indexer_conteneurs_et_supports."""

    def test_supports_distingues_des_autres_conteneurs(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / f"{COUCHE_SUPPORT}{EXTENSION}"),
            [{"type": "Feature", "properties": {"id": "s1", CHAMP_GEOMSUPP_HREF: "g1"}, "geometry": GEOM_SUPPORT}],
        )
        ecrire_collection(
            str(tmp_path / f"RPD_Coffret_Reco{EXTENSION}"),
            [{"type": "Feature", "properties": {"id": "k1", CHAMP_GEOMSUPP_HREF: "g2"}, "geometry": GEOM_SUPPORT}],
        )
        conteneurs, supports, absentes = indexer_conteneurs_et_supports(str(tmp_path))
        assert set(conteneurs) == {"s1", "k1"}
        assert supports == frozenset({"s1"})
        assert "RPD_BatimentTechnique_Reco" in absentes

    def test_href_normalise(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / f"{COUCHE_SUPPORT}{EXTENSION}"),
            [{"type": "Feature", "properties": {"id": "s1", CHAMP_GEOMSUPP_HREF: " g1 "}, "geometry": None}],
        )
        conteneurs, _, _ = indexer_conteneurs_et_supports(str(tmp_path))
        assert conteneurs["s1"].href_geomsupp == "g1"

    def test_conteneur_sans_identifiant_ecarte(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / f"{COUCHE_SUPPORT}{EXTENSION}"),
            [{"type": "Feature", "properties": {}, "geometry": GEOM_SUPPORT}],
        )
        conteneurs, supports, _ = indexer_conteneurs_et_supports(str(tmp_path))
        assert conteneurs == {} and supports == frozenset()

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        conteneurs, supports, absentes = indexer_conteneurs_et_supports(str(tmp_path))
        assert conteneurs == {} and supports == frozenset()
        assert len(absentes) == 4

    def test_extension_alignee_sur_le_socle(self) -> None:
        """L'extension provient du module commun, pas d'une constante locale."""
        assert EXTENSION == EXTENSION_GEOJSON


# --------------------------------------------------------------------------- #
# Cas 1 — geometrie propre
# --------------------------------------------------------------------------- #


class TestPossedeGeometriePropre:
    """Tests de possede_geometrie_propre."""

    def test_geometrie_differente_du_conteneur(self) -> None:
        assert possede_geometrie_propre(GEOM_PROPRE, "s1", _conteneurs()) is True

    def test_geometrie_heritee_non_propre(self) -> None:
        """Une geometrie identique a celle du conteneur a ete injectee par l'export."""
        assert possede_geometrie_propre(GEOM_SUPPORT, "s1", _conteneurs()) is False

    def test_sans_conteneur_la_geometrie_est_propre(self) -> None:
        assert possede_geometrie_propre(GEOM_PROPRE, None, _conteneurs()) is True

    def test_conteneur_non_resolu_la_geometrie_est_propre(self) -> None:
        assert possede_geometrie_propre(GEOM_PROPRE, "s9", _conteneurs()) is True

    def test_geometrie_absente(self) -> None:
        assert possede_geometrie_propre(None, "s1", _conteneurs()) is False

    def test_geometrie_invalide(self) -> None:
        assert possede_geometrie_propre({"type": "Point", "coordinates": []}, None, _conteneurs()) is False

    def test_conteneur_sans_geometrie(self) -> None:
        """Rien n'a pu etre herite : la geometrie de la jonction lui est propre."""
        assert possede_geometrie_propre(GEOM_PROPRE, "s1", _conteneurs(geometrie=None)) is True


# --------------------------------------------------------------------------- #
# Cas 2 — voie du support
# --------------------------------------------------------------------------- #


class TestMotifEchecSupport:
    """Tests de motif_echec_support."""

    def test_voie_complete(self) -> None:
        assert motif_echec_support("s1", _conteneurs(), _supports(), _geomsupps()) is None

    def test_support_absent(self) -> None:
        assert motif_echec_support(None, _conteneurs(), _supports(), _geomsupps()) == MOTIF_SUPPORT_ABSENT

    def test_support_introuvable(self) -> None:
        assert motif_echec_support("s9", _conteneurs(), _supports(), _geomsupps()) == MOTIF_SUPPORT_INTROUVABLE

    def test_conteneur_non_support(self) -> None:
        """Un coffret existe comme conteneur mais ne satisfait pas le cas 2."""
        assert motif_echec_support("s1", _conteneurs(), frozenset(), _geomsupps()) == MOTIF_CONTENEUR_NON_SUPPORT

    def test_geomsupp_absente(self) -> None:
        assert motif_echec_support("s1", _conteneurs(None), _supports(), _geomsupps()) == MOTIF_GEOMSUPP_ABSENTE

    def test_geomsupp_introuvable(self) -> None:
        assert motif_echec_support("s1", _conteneurs(), _supports(), {}) == MOTIF_GEOMSUPP_INTROUVABLE

    def test_geomsupp_invalide(self) -> None:
        assert motif_echec_support("s1", _conteneurs(), _supports(), _geomsupps(None)) == MOTIF_GEOMSUPP_INVALIDE

    def test_geomsupp_coordonnees_vides(self) -> None:
        vide = {"type": "Polygon", "coordinates": []}
        assert motif_echec_support("s1", _conteneurs(), _supports(), _geomsupps(vide)) == MOTIF_GEOMSUPP_INVALIDE


# --------------------------------------------------------------------------- #
# Disjonction
# --------------------------------------------------------------------------- #


class TestClassifierJonction:
    """Tests de classifier_jonction : une seule des deux voies suffit."""

    def test_cas_1_seul(self) -> None:
        """Geometrie propre, voie du support rompue : conforme."""
        assert classifier_jonction(GEOM_PROPRE, "s1", _conteneurs(None), _supports(), {}) is None

    def test_cas_2_seul(self) -> None:
        """Geometrie heritee, voie du support complete : conforme."""
        assert classifier_jonction(GEOM_SUPPORT, "s1", _conteneurs(), _supports(), _geomsupps()) is None

    def test_les_deux_voies(self) -> None:
        assert classifier_jonction(GEOM_PROPRE, "s1", _conteneurs(), _supports(), _geomsupps()) is None

    def test_aucune_voie(self) -> None:
        motif = classifier_jonction(GEOM_SUPPORT, "s1", _conteneurs(None), _supports(), _geomsupps())
        assert motif == MOTIF_GEOMSUPP_ABSENTE

    def test_sans_geometrie_ni_support(self) -> None:
        assert classifier_jonction(None, None, _conteneurs(), _supports(), _geomsupps()) == MOTIF_SUPPORT_ABSENT

    def test_geometrie_propre_dispense_de_la_voie_support(self) -> None:
        """Une geometrie propre sans aucun conteneur reste conforme."""
        assert classifier_jonction(GEOM_PROPRE, None, {}, frozenset(), {}) is None


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Tests de detecter_anomalies."""

    def test_jonction_conforme(self) -> None:
        assert detecter_anomalies([_jonction()], _conteneurs(), _supports(), _geomsupps()) == []

    def test_hors_perimetre_ignore(self) -> None:
        jonctions = [
            _jonction("j1", conteneur_href=None, geometrie=None, type_jonction="Derivation"),
            _jonction("j2", conteneur_href=None, geometrie=None, statut="Projected"),
        ]
        assert detecter_anomalies(jonctions, _conteneurs(), _supports(), _geomsupps()) == []

    def test_anomalie_documentee(self) -> None:
        jonction = _jonction(conteneur_href=None, geometrie=None)
        anomalies = detecter_anomalies([jonction], _conteneurs(), _supports(), _geomsupps())
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_LOCALISATION_ABSENTE
        assert anomalies[0]["id_jonction"] == "j1"
        assert anomalies[0]["id_support"] is None
        assert anomalies[0]["motif"] == MOTIF_SUPPORT_ABSENT

    def test_une_anomalie_par_jonction(self) -> None:
        """La regle est une disjonction : son echec ne produit qu'une anomalie."""
        jonction = _jonction(conteneur_href=None, geometrie=None)
        assert len(detecter_anomalies([jonction], {}, frozenset(), {})) == 1

    def test_geometrie_de_repli_sur_le_conteneur(self) -> None:
        jonction = _jonction(geometrie=None)
        anomalies = detecter_anomalies([jonction], _conteneurs(None), _supports(), _geomsupps())
        assert anomalies[0]["geometrie"] == GEOM_SUPPORT

    def test_geometrie_nulle_sans_conteneur(self) -> None:
        jonction = _jonction(conteneur_href=None, geometrie=None)
        anomalies = detecter_anomalies([jonction], _conteneurs(), _supports(), _geomsupps())
        assert anomalies[0]["geometrie"] is None

    def test_plusieurs_jonctions(self) -> None:
        jonctions = [_jonction("j1"), _jonction("j2", conteneur_href=None, geometrie=None)]
        anomalies = detecter_anomalies(jonctions, _conteneurs(), _supports(), _geomsupps())
        assert [a["id_jonction"] for a in anomalies] == ["j2"]


class TestCompterJonctionsAControler:
    """Tests de compter_jonctions_a_controler."""

    def test_comptage(self) -> None:
        jonctions = [
            _jonction("j1"),
            _jonction("j2", statut="Functional"),
            _jonction("j3", type_jonction="Jonction"),
            _jonction("j4", statut="Projected"),
        ]
        assert compter_jonctions_a_controler(jonctions) == 2

    def test_liste_vide(self) -> None:
        assert compter_jonctions_a_controler([]) == 0


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_LOCALISATION_ABSENTE,
            "id_jonction": "j1",
            "id_support": "s1",
            "motif": MOTIF_GEOMSUPP_ABSENTE,
            "geometrie": GEOM_SUPPORT,
        }

    def test_socle_commun(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["code_controle"] == "E606"
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["id_entite"] == "j1"
        assert props["type_anomalie"] == TYPE_LOCALISATION_ABSENTE
        assert props["description"]

    def test_proprietes_metier(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["fichier_source"] == FICHIER_JONCTION
        assert props["id_support"] == "s1"
        assert props["motif"] == MOTIF_GEOMSUPP_ABSENTE

    def test_id_entite_replie_sur_le_support(self) -> None:
        anomalie = {**self._anomalie(), "id_jonction": None}
        props = construire_geojson_ecarts([anomalie])["features"][0]["properties"]
        assert props["id_entite"] == "s1"

    def test_geometrie_conservee(self) -> None:
        assert construire_geojson_ecarts([self._anomalie()])["features"][0]["geometry"] == GEOM_SUPPORT

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

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_fichiers_absents_non_bloquants(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichier_jonction_absent"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_nominal_conforme_par_le_support(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_jonctions_controlees"] == 1
        assert resultat["nombre_supports"] == 1
        assert resultat["priorite"] == "bloquant"

    def test_nominal_conforme_par_geometrie_propre(self, tmp_path: Any) -> None:
        """Cas 1 : la voie du support est rompue, la geometrie propre suffit."""
        _ecrire_jeu(tmp_path, [_jonction(geometrie=GEOM_PROPRE)], href_geomsupp=None)
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_support_absent(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_jonction(conteneur_href=None, geometrie=None)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_motif"] == {MOTIF_SUPPORT_ABSENT: 1}

    def test_support_introuvable(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_jonction(conteneur_href="s9", geometrie=None)])
        assert executer_controle_cli(str(tmp_path))["anomalies_par_motif"] == {MOTIF_SUPPORT_INTROUVABLE: 1}

    def test_conteneur_non_support(self, tmp_path: Any) -> None:
        """Une remontee rattachee a un coffret ne satisfait pas le cas 2."""
        _ecrire_jeu(tmp_path, couche_conteneur="RPD_Coffret_Reco")
        assert executer_controle_cli(str(tmp_path))["anomalies_par_motif"] == {MOTIF_CONTENEUR_NON_SUPPORT: 1}

    def test_geomsupp_absente(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, href_geomsupp=None)
        assert executer_controle_cli(str(tmp_path))["anomalies_par_motif"] == {MOTIF_GEOMSUPP_ABSENTE: 1}

    def test_geomsupp_introuvable(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, href_geomsupp="g9")
        assert executer_controle_cli(str(tmp_path))["anomalies_par_motif"] == {MOTIF_GEOMSUPP_INTROUVABLE: 1}

    def test_geomsupp_invalide(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, geom_supp=None)
        assert executer_controle_cli(str(tmp_path))["anomalies_par_motif"] == {MOTIF_GEOMSUPP_INVALIDE: 1}

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, href_geomsupp=None)
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / FICHIER_SORTIE))

    def test_crs_propage(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, href_geomsupp=None)
        ecrire_collection_avec_crs(str(tmp_path / FICHIER_JONCTION), [_jonction()], "EPSG:2154")
        executer_controle_cli(str(tmp_path))
        with open(str(tmp_path / FICHIER_SORTIE), encoding="utf-8") as fichier:
            ecarts = json.load(fichier)
        assert "2154" in ecarts["crs"]["properties"]["name"]

    def test_rapport_champs_obligatoires(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path)
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "anomalies_par_motif",
            "nombre_jonctions_analysees",
            "nombre_jonctions_controlees",
            "nombre_supports",
            "nombre_geometries_supplementaires",
            "fichier_jonction_absent",
            "couches_conteneur_absentes",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"


# --------------------------------------------------------------------------- #
# Coherence avec E605
# --------------------------------------------------------------------------- #


class TestCoherenceAvecE605:
    """E605 et E606 evaluent la meme chaine, sur des entites disjointes."""

    def test_definition_de_geometrie_valide_partagee(self) -> None:
        from controle_e605 import geometrie_valide as valide_e605
        from controle_e606 import geometrie_valide as valide_e606

        assert valide_e605 is valide_e606

    def test_jonction_hors_perimetre_e605(self) -> None:
        """E605 ne controle plus les jonctions : E606 les prend en charge."""
        from controle_e605 import COUCHES_CIBLES

        assert "RPD_Jonction_Reco" not in COUCHES_CIBLES


# --------------------------------------------------------------------------- #
# Comportement multi-version (V1.0 / V1.1)
# --------------------------------------------------------------------------- #


class TestMultiVersion:
    """La localisation est controlee identiquement en V1.0 et V1.1."""

    def test_v11_champs_extra_sans_effet(self, tmp_path: Any) -> None:
        jonction = _jonction()
        jonction["properties"]["Commentaire"] = "note"
        _ecrire_jeu(tmp_path, [jonction])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
