"""
Tests du controle E607 : localisation des points de comptage et ouvrages collectifs.

Couvre :
  - les couches controlees, le filtre de statut et les conteneurs autorises
  - le cas 1, geometrie propre, et sa distinction d'avec une geometrie heritee
  - le cas 2, voie du conteneur, et ses six motifs de rupture
  - la disjonction : une seule des deux voies suffit
  - la construction du GeoJSON d'ecarts
  - l'execution CLI
  - la coherence avec E605 et E606
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import json
import os
from typing import Any

from controle_e605 import (
    CHAMP_GEOMSUPP_HREF,
    TYPE_GEOMSUPP_ABSENTE,
    TYPE_GEOMSUPP_INTROUVABLE,
    TYPE_GEOMSUPP_INVALIDE,
)
from controle_e607 import (
    CHAMP_CONTENEUR_HREF,
    CHAMP_STATUT,
    COUCHES_CIBLES,
    COUCHES_CONTENEUR_AUTORISEES,
    EXTENSION,
    FICHIER_SORTIE,
    MOTIF_CONTENEUR_ABSENT,
    MOTIF_CONTENEUR_INTROUVABLE,
    MOTIF_CONTENEUR_NON_AUTORISE,
    PRIORITE_ANOMALIE,
    STATUTS_CONTROLES,
    TYPE_LOCALISATION_ABSENTE,
    Conteneur,
    classifier_ouvrage,
    compter_ouvrages_a_controler,
    construire_geojson_ecarts,
    detecter_anomalies_couche,
    est_a_controler,
    executer_controle_cli,
    motif_echec_conteneur,
    parcourir_ouvrages,
)
from utils_tests import ecrire_collection, ecrire_collection_avec_crs

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

COUCHE_CIBLE: str = "RPD_PointDeComptage_Reco"
AUTRE_COUCHE_CIBLE: str = "RPD_OuvrageCollectifBranchement_Reco"
COUCHE_AUTORISEE: str = "RPD_Coffret_Reco"
COUCHE_NON_AUTORISEE: str = "RPD_Support_Reco"

GEOM_CONTENEUR: dict[str, Any] = {"type": "Point", "coordinates": [10.0, 20.0, 30.0]}
GEOM_PROPRE: dict[str, Any] = {"type": "Point", "coordinates": [99.0, 99.0, 99.0]}
GEOM_SUPP: dict[str, Any] = {"type": "Polygon", "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]]}


def _ouvrage(
    identifiant: str = "o1",
    conteneur_href: Any = "k1",
    geometrie: Any = GEOM_CONTENEUR,
    statut: str = "UnderCommissionning",
    proprietes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ouvrage dont la geometrie est, par defaut, heritee du conteneur."""
    props: dict[str, Any] = {
        "id": identifiant,
        CHAMP_STATUT: statut,
        CHAMP_CONTENEUR_HREF: conteneur_href,
    }
    props.update(proprietes or {})
    return {"type": "Feature", "properties": props, "geometry": geometrie}


def _conteneurs(href_geomsupp: str | None = "g1", geometrie: Any = GEOM_CONTENEUR) -> dict[str, Conteneur]:
    return {"k1": Conteneur(geometrie, href_geomsupp)}


def _autorises() -> frozenset[str]:
    return frozenset({"k1"})


def _geomsupps(geometrie: Any = GEOM_SUPP) -> dict[str, Any]:
    return {"g1": geometrie}


def _ecrire_jeu(
    tmp_path: Any,
    ouvrages: list[dict[str, Any]] | None = None,
    couche: str = COUCHE_CIBLE,
    couche_conteneur: str = COUCHE_AUTORISEE,
    href_geomsupp: Any = "g1",
    geom_supp: Any = GEOM_SUPP,
) -> None:
    """Ecrit un jeu complet : ouvrage, conteneur et geometrie supplementaire."""
    ecrire_collection(
        str(tmp_path / f"{couche}{EXTENSION}"),
        ouvrages if ouvrages is not None else [_ouvrage()],
    )
    ecrire_collection(
        str(tmp_path / f"{couche_conteneur}{EXTENSION}"),
        [
            {
                "type": "Feature",
                "properties": {"id": "k1", CHAMP_GEOMSUPP_HREF: href_geomsupp},
                "geometry": GEOM_CONTENEUR,
            }
        ],
    )
    ecrire_collection(
        str(tmp_path / f"RPD_GeometrieSupplementaire_Reco{EXTENSION}"),
        [{"type": "Feature", "properties": {"id": "g1"}, "geometry": geom_supp}],
    )


# --------------------------------------------------------------------------- #
# Perimetre declare
# --------------------------------------------------------------------------- #


class TestPerimetre:
    """Couches controlees et conteneurs autorises."""

    def test_les_deux_couches_cibles(self) -> None:
        assert set(COUCHES_CIBLES) == {"RPD_PointDeComptage_Reco", "RPD_OuvrageCollectifBranchement_Reco"}

    def test_les_deux_conteneurs_autorises(self) -> None:
        assert COUCHES_CONTENEUR_AUTORISEES == frozenset({"RPD_Coffret_Reco", "RPD_BatimentTechnique_Reco"})

    def test_support_non_autorise(self) -> None:
        assert COUCHE_NON_AUTORISEE not in COUCHES_CONTENEUR_AUTORISEES

    def test_statuts_controles_declares(self) -> None:
        assert STATUTS_CONTROLES == frozenset({"UnderCommissionning", "Functional"})


class TestEstAControler:
    """Tests du filtre de statut."""

    def test_under_commissionning(self) -> None:
        assert est_a_controler({CHAMP_STATUT: "UnderCommissionning"}) is True

    def test_functional(self) -> None:
        assert est_a_controler({CHAMP_STATUT: "Functional"}) is True

    def test_projected_ignore(self) -> None:
        """Cas reel Echantillon : 4 points de comptage a l'etat de projet."""
        assert est_a_controler({CHAMP_STATUT: "Projected"}) is False

    def test_decommissioned_ignore(self) -> None:
        assert est_a_controler({CHAMP_STATUT: "Decommissioned"}) is False

    def test_statut_absent_ignore(self) -> None:
        assert est_a_controler({}) is False

    def test_meme_perimetre_de_statut_qu_e606(self) -> None:
        from controle_e606 import STATUTS_CONTROLES as STATUTS_E606

        assert STATUTS_CONTROLES == STATUTS_E606


# --------------------------------------------------------------------------- #
# Cas 2 — voie du conteneur
# --------------------------------------------------------------------------- #


class TestMotifEchecConteneur:
    """Tests de motif_echec_conteneur."""

    def test_voie_complete(self) -> None:
        assert motif_echec_conteneur("k1", _conteneurs(), _autorises(), _geomsupps()) is None

    def test_conteneur_absent(self) -> None:
        assert motif_echec_conteneur(None, _conteneurs(), _autorises(), _geomsupps()) == MOTIF_CONTENEUR_ABSENT

    def test_conteneur_introuvable(self) -> None:
        assert motif_echec_conteneur("k9", _conteneurs(), _autorises(), _geomsupps()) == MOTIF_CONTENEUR_INTROUVABLE

    def test_conteneur_non_autorise(self) -> None:
        """Un support existe comme conteneur mais ne satisfait pas le cas 2."""
        assert motif_echec_conteneur("k1", _conteneurs(), frozenset(), _geomsupps()) == MOTIF_CONTENEUR_NON_AUTORISE

    def test_geomsupp_absente(self) -> None:
        assert motif_echec_conteneur("k1", _conteneurs(None), _autorises(), _geomsupps()) == TYPE_GEOMSUPP_ABSENTE

    def test_geomsupp_introuvable(self) -> None:
        assert motif_echec_conteneur("k1", _conteneurs(), _autorises(), {}) == TYPE_GEOMSUPP_INTROUVABLE

    def test_geomsupp_invalide(self) -> None:
        assert motif_echec_conteneur("k1", _conteneurs(), _autorises(), _geomsupps(None)) == TYPE_GEOMSUPP_INVALIDE

    def test_geomsupp_coordonnees_vides(self) -> None:
        vide = {"type": "Polygon", "coordinates": []}
        assert motif_echec_conteneur("k1", _conteneurs(), _autorises(), _geomsupps(vide)) == TYPE_GEOMSUPP_INVALIDE


# --------------------------------------------------------------------------- #
# Disjonction
# --------------------------------------------------------------------------- #


class TestClassifierOuvrage:
    """Tests de classifier_ouvrage : une seule des deux voies suffit."""

    def test_cas_1_seul(self) -> None:
        """Geometrie propre, voie du conteneur rompue : conforme."""
        assert classifier_ouvrage(GEOM_PROPRE, "k1", _conteneurs(None), _autorises(), {}) is None

    def test_cas_2_seul(self) -> None:
        """Geometrie heritee, voie du conteneur complete : conforme."""
        assert classifier_ouvrage(GEOM_CONTENEUR, "k1", _conteneurs(), _autorises(), _geomsupps()) is None

    def test_les_deux_voies(self) -> None:
        assert classifier_ouvrage(GEOM_PROPRE, "k1", _conteneurs(), _autorises(), _geomsupps()) is None

    def test_aucune_voie(self) -> None:
        motif = classifier_ouvrage(GEOM_CONTENEUR, "k1", _conteneurs(None), _autorises(), _geomsupps())
        assert motif == TYPE_GEOMSUPP_ABSENTE

    def test_sans_geometrie_ni_conteneur(self) -> None:
        assert classifier_ouvrage(None, None, _conteneurs(), _autorises(), _geomsupps()) == MOTIF_CONTENEUR_ABSENT

    def test_geometrie_heritee_d_un_conteneur_non_autorise(self) -> None:
        """Cas reel Echantillon2 : geometrie heritee d'un support, non autorise."""
        motif = classifier_ouvrage(GEOM_CONTENEUR, "k1", _conteneurs(), frozenset(), _geomsupps())
        assert motif == MOTIF_CONTENEUR_NON_AUTORISE

    def test_geometrie_propre_dispense_de_la_voie_conteneur(self) -> None:
        assert classifier_ouvrage(GEOM_PROPRE, None, {}, frozenset(), {}) is None

    def test_geometrie_invalide_ne_vaut_pas_cas_1(self) -> None:
        vide = {"type": "Point", "coordinates": []}
        assert classifier_ouvrage(vide, None, {}, frozenset(), {}) == MOTIF_CONTENEUR_ABSENT


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


class TestDetecterAnomaliesCouche:
    """Tests de detecter_anomalies_couche."""

    def test_ouvrage_conforme(self) -> None:
        assert detecter_anomalies_couche(COUCHE_CIBLE, [_ouvrage()], _conteneurs(), _autorises(), _geomsupps()) == []

    def test_anomalie_documentee(self) -> None:
        ouvrage = _ouvrage(conteneur_href=None, geometrie=None)
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [ouvrage], _conteneurs(), _autorises(), _geomsupps())
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_LOCALISATION_ABSENTE
        assert anomalies[0]["couche_ouvrage"] == COUCHE_CIBLE
        assert anomalies[0]["id_ouvrage"] == "o1"
        assert anomalies[0]["id_conteneur"] is None
        assert anomalies[0]["motif"] == MOTIF_CONTENEUR_ABSENT

    def test_hors_statut_ignore(self) -> None:
        """Un ouvrage a l'etat de projet n'a pas a etre localisable."""
        ouvrage = _ouvrage(conteneur_href=None, geometrie=None, statut="Projected")
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [ouvrage], _conteneurs(), _autorises(), _geomsupps())
        assert anomalies == []

    def test_statut_functional_controle(self) -> None:
        ouvrage = _ouvrage(conteneur_href=None, geometrie=None, statut="Functional")
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [ouvrage], _conteneurs(), _autorises(), _geomsupps())
        assert len(anomalies) == 1

    def test_une_anomalie_par_ouvrage(self) -> None:
        ouvrage = _ouvrage(conteneur_href=None, geometrie=None)
        assert len(detecter_anomalies_couche(COUCHE_CIBLE, [ouvrage], {}, frozenset(), {})) == 1

    def test_geometrie_de_repli_sur_le_conteneur(self) -> None:
        ouvrage = _ouvrage(geometrie=None)
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [ouvrage], _conteneurs(None), _autorises(), _geomsupps())
        assert anomalies[0]["geometrie"] == GEOM_CONTENEUR

    def test_geometrie_nulle_sans_conteneur(self) -> None:
        ouvrage = _ouvrage(conteneur_href=None, geometrie=None)
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [ouvrage], _conteneurs(), _autorises(), _geomsupps())
        assert anomalies[0]["geometrie"] is None

    def test_plusieurs_ouvrages(self) -> None:
        ouvrages = [_ouvrage("o1"), _ouvrage("o2", conteneur_href=None, geometrie=None)]
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, ouvrages, _conteneurs(), _autorises(), _geomsupps())
        assert [a["id_ouvrage"] for a in anomalies] == ["o2"]

    def test_couche_vide(self) -> None:
        assert detecter_anomalies_couche(COUCHE_CIBLE, [], _conteneurs(), _autorises(), _geomsupps()) == []


class TestCompterOuvragesAControler:
    """Tests de compter_ouvrages_a_controler."""

    def test_comptage(self) -> None:
        ouvrages = [
            _ouvrage("o1"),
            _ouvrage("o2", statut="Functional"),
            _ouvrage("o3", statut="Projected"),
        ]
        assert compter_ouvrages_a_controler(ouvrages) == 2

    def test_liste_vide(self) -> None:
        assert compter_ouvrages_a_controler([]) == 0


class TestParcourirOuvrages:
    """Tests de parcourir_ouvrages."""

    def test_les_deux_couches_parcourues(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path)
        ecrire_collection(str(tmp_path / f"{AUTRE_COUCHE_CIBLE}{EXTENSION}"), [_ouvrage("o2")])
        couches = {couche: absente for couche, _, absente in parcourir_ouvrages(str(tmp_path))}
        assert couches == {COUCHE_CIBLE: False, AUTRE_COUCHE_CIBLE: False}

    def test_couche_absente_signalee(self, tmp_path: Any) -> None:
        couches = {couche: absente for couche, _, absente in parcourir_ouvrages(str(tmp_path))}
        assert all(couches.values())


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_LOCALISATION_ABSENTE,
            "couche_ouvrage": COUCHE_CIBLE,
            "id_ouvrage": "o1",
            "id_conteneur": "k1",
            "motif": MOTIF_CONTENEUR_NON_AUTORISE,
            "geometrie": GEOM_CONTENEUR,
        }

    def test_socle_commun(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["code_controle"] == "E607"
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["id_entite"] == "o1"
        assert props["type_anomalie"] == TYPE_LOCALISATION_ABSENTE
        assert props["description"]

    def test_proprietes_metier(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["couche_ouvrage"] == COUCHE_CIBLE
        assert props["fichier_source"] == f"{COUCHE_CIBLE}{EXTENSION}"
        assert props["id_conteneur"] == "k1"
        assert props["motif"] == MOTIF_CONTENEUR_NON_AUTORISE

    def test_fichier_source_suit_la_couche(self) -> None:
        """Les deux couches partagent le fichier d'ecarts : le type doit y figurer."""
        anomalie = {**self._anomalie(), "couche_ouvrage": AUTRE_COUCHE_CIBLE}
        props = construire_geojson_ecarts([anomalie])["features"][0]["properties"]
        assert props["fichier_source"] == f"{AUTRE_COUCHE_CIBLE}{EXTENSION}"

    def test_id_entite_replie_sur_le_conteneur(self) -> None:
        anomalie = {**self._anomalie(), "id_ouvrage": None}
        props = construire_geojson_ecarts([anomalie])["features"][0]["properties"]
        assert props["id_entite"] == "k1"

    def test_geometrie_conservee(self) -> None:
        assert construire_geojson_ecarts([self._anomalie()])["features"][0]["geometry"] == GEOM_CONTENEUR

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

    def test_repertoire_vide_non_bloquant(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert len(resultat["couches_absentes"]) == len(COUCHES_CIBLES)

    def test_nominal_conforme_par_le_conteneur(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_ouvrages_controles"] == 1
        assert resultat["nombre_conteneurs_autorises"] == 1
        assert resultat["priorite"] == "bloquant"

    def test_nominal_conforme_par_geometrie_propre(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_ouvrage(geometrie=GEOM_PROPRE)], href_geomsupp=None)
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_batiment_technique_autorise(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, couche_conteneur="RPD_BatimentTechnique_Reco")
        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0

    def test_support_non_autorise(self, tmp_path: Any) -> None:
        """Cas reel Echantillon2 : un point de comptage rattache a un support."""
        _ecrire_jeu(tmp_path, couche_conteneur=COUCHE_NON_AUTORISEE)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["anomalies_par_motif"] == {MOTIF_CONTENEUR_NON_AUTORISE: 1}

    def test_conteneur_absent(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_ouvrage(conteneur_href=None, geometrie=None)])
        assert executer_controle_cli(str(tmp_path))["anomalies_par_motif"] == {MOTIF_CONTENEUR_ABSENT: 1}

    def test_conteneur_introuvable(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_ouvrage(conteneur_href="k9", geometrie=None)])
        assert executer_controle_cli(str(tmp_path))["anomalies_par_motif"] == {MOTIF_CONTENEUR_INTROUVABLE: 1}

    def test_geomsupp_absente(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, href_geomsupp=None)
        assert executer_controle_cli(str(tmp_path))["anomalies_par_motif"] == {TYPE_GEOMSUPP_ABSENTE: 1}

    def test_geomsupp_introuvable(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, href_geomsupp="g9")
        assert executer_controle_cli(str(tmp_path))["anomalies_par_motif"] == {TYPE_GEOMSUPP_INTROUVABLE: 1}

    def test_geomsupp_invalide(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, geom_supp=None)
        assert executer_controle_cli(str(tmp_path))["anomalies_par_motif"] == {TYPE_GEOMSUPP_INVALIDE: 1}

    def test_les_deux_couches_controlees(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, href_geomsupp=None)
        ecrire_collection(
            str(tmp_path / f"{AUTRE_COUCHE_CIBLE}{EXTENSION}"),
            [_ouvrage("o2", conteneur_href=None, geometrie=None)],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_ouvrages_controles"] == 2
        assert resultat["nombre_anomalies"] == 2

    def test_ouvrages_hors_statut_non_comptes(self, tmp_path: Any) -> None:
        """Cas reel Echantillon : les points de comptage Projected sont exclus."""
        _ecrire_jeu(
            tmp_path,
            [_ouvrage("o1"), _ouvrage("o2", conteneur_href=None, geometrie=None, statut="Projected")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_ouvrages_controles"] == 1
        assert resultat["nombre_anomalies"] == 0

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
        ecrire_collection_avec_crs(str(tmp_path / f"{COUCHE_CIBLE}{EXTENSION}"), [_ouvrage()], "EPSG:2154")
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
            "nombre_ouvrages_controles",
            "nombre_conteneurs_autorises",
            "nombre_geometries_supplementaires",
            "couches_absentes",
            "couches_conteneur_absentes",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"


# --------------------------------------------------------------------------- #
# Coherence avec E605 et E606
# --------------------------------------------------------------------------- #


class TestCoherenceAvecLesControlesVoisins:
    """Les trois controles evaluent la meme chaine de localisation."""

    def test_discriminant_de_geometrie_propre_partage(self) -> None:
        from controle_e606 import possede_geometrie_propre as propre_e606
        from controle_e607 import possede_geometrie_propre as propre_e607

        assert propre_e606 is propre_e607

    def test_chaine_geomsupp_partagee_avec_e605(self) -> None:
        """Les trois motifs de rupture de chaine sont ceux d'E605."""
        from controle_e605 import _classifier_chaine_conteneur as chaine_e605
        from controle_e607 import _classifier_chaine_conteneur as chaine_e607

        assert chaine_e605 is chaine_e607

    def test_indexation_partagee_avec_e606(self) -> None:
        from controle_e606 import indexer_conteneurs_autorises as index_e606
        from controle_e607 import indexer_conteneurs_autorises as index_e607

        assert index_e606 is index_e607

    def test_repli_de_geometrie_partage(self) -> None:
        """Les trois controles appliquent la meme regle de repli sur le conteneur."""
        from controle_e605 import geometrie_ecart as repli_e605
        from controle_e607 import geometrie_ecart as repli_e607

        assert repli_e605 is repli_e607

    def test_couches_cibles_disjointes_d_e605(self) -> None:
        """E605 et E607 ne controlent jamais la meme entite."""
        from controle_e605 import COUCHES_CIBLES as CIBLES_E605

        assert not set(COUCHES_CIBLES) & set(CIBLES_E605)


# --------------------------------------------------------------------------- #
# Comportement multi-version (V1.0 / V1.1)
# --------------------------------------------------------------------------- #


class TestMultiVersion:
    """La localisation est controlee identiquement en V1.0 et V1.1."""

    def test_v11_champs_extra_sans_effet(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_ouvrage(proprietes={"Commentaire": "note"})])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
