"""
Tests du moteur de chaine de localisation des noeuds sans geometrie propre.

Couvre :
  - la validite d'une geometrie GeoJSON
  - l'indexation des conteneurs et des geometries supplementaires
  - les deux filtres de perimetre par couche : moteur et chaine de conteneur
  - le classement en cascade des six types d'anomalie
  - la distinction geometrie heritee / geometrie directe
  - la regle de geometrie directe sur le point de comptage et l'ouvrage
    collectif, hors perimetre des regles de chaine
  - la construction du GeoJSON d'ecarts
  - l'execution CLI
  - le comportement identique en RecoStaR V1.0 et V1.1
"""

import json
import os
from typing import Any

from recostar.controle.conteneur.detection_localisation_noeud import (
    COUCHES_CHAINE_CONTROLEE,
    COUCHES_CIBLES,
    COUCHES_CONTROLEES,
    COUCHES_OUVRAGES_LOCALISABLES,
    COUCHES_PARCOURUES,
    PRIORITE_ANOMALIE,
    TYPE_GEOMETRIE_DIRECTE,
    chaine_conteneur_a_controler,
    classifier_noeud,
    compter_noeuds_a_controler,
    compter_noeuds_non_conformes,
    construire_geojson_ecarts,
    couches_du_controle,
    detecter_anomalies_couche,
    est_a_controler,
    executer_analyse,
)
from recostar.controle.conteneur.e6105 import PROFIL_ECARTS as _PROFIL_6105
from recostar.controle.conteneur.e6105 import TYPES_RETENUS as _TYPES_6105
from recostar.controle.conteneur.e6106 import PROFIL_ECARTS as _PROFIL_6106
from recostar.controle.conteneur.e6106 import TYPES_RETENUS as _TYPES_6106
from recostar.controle.conteneur.e6112 import PROFIL_ECARTS as _PROFIL_6112
from recostar.controle.conteneur.e6112 import TYPES_RETENUS as _TYPES_6112
from recostar.controle.conteneur.e6209 import PROFIL_ECARTS as _PROFIL_6209
from recostar.controle.conteneur.e6209 import TYPES_RETENUS as _TYPES_6209
from recostar.controle.conteneur.tests.utils_tests import ecrire_collection, ecrire_collection_avec_crs
from recostar.controle.fonctions_communes.geojson import PRIORITE_FORTE
from recostar.controle.fonctions_communes.localisation_conteneur import (
    TYPE_CONTENEUR_ABSENT,
    TYPE_CONTENEUR_INTROUVABLE,
    TYPE_GEOMSUPP_ABSENTE,
    TYPE_GEOMSUPP_INTROUVABLE,
    TYPE_GEOMSUPP_INVALIDE,
    Conteneur,
    geometrie_valide,
    indexer_conteneurs,
    indexer_geometries_supplementaires,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_CONTENEUR_HREF,
    CHAMP_GEOMSUPP_HREF,
    COUCHE_GEOM_SUPP,
    COUCHES_CONTENEUR,
    EXTENSION_COUCHE,
)

# Le moteur est partage : chaque type d'anomalie revient au controle qui porte
# son code. Les tests lui passent ce profil, faute de quoi le code d'erreur et
# la priorite des ecarts ne seraient pas resolus.
_PROFIL_PAR_TYPE = {
    **dict.fromkeys(_TYPES_6105, _PROFIL_6105),
    **dict.fromkeys(_TYPES_6106, _PROFIL_6106),
    **dict.fromkeys(_TYPES_6112, _PROFIL_6112),
    **dict.fromkeys(_TYPES_6209, _PROFIL_6209),
}

_PROFIL_DEFAUT = _PROFIL_6105
_TOUS_LES_TYPES = frozenset(_PROFIL_PAR_TYPE)
_FICHIER_TEST = "ecarts_moteur_test.geojson"


def _profil(anomalies):
    """Profil du controle a qui revient le type de la premiere anomalie."""
    if not anomalies:
        return _PROFIL_DEFAUT
    return _PROFIL_PAR_TYPE.get(anomalies[0].get("type_anomalie"), _PROFIL_DEFAUT)


def _executer(repertoire, sortie=None, **options):
    """Execute le moteur sur tous ses types, comme avant la scission."""
    return executer_analyse(repertoire, _TOUS_LES_TYPES, _PROFIL_DEFAUT, _FICHIER_TEST, sortie, **options)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

COUCHE_CIBLE: str = "RPD_SupportModules_Reco"
AUTRE_COUCHE_CIBLE: str = "RPD_Terre_Reco"
# Ouvrage soumis a la seule regle de geometrie directe : sa chaine releve d'E-6109.
COUCHE_OUVRAGE_LOCALISABLE: str = "RPD_PointDeComptage_Reco"
GEOM_CONTENEUR: dict[str, Any] = {"type": "Point", "coordinates": [10.0, 20.0, 30.0]}
GEOM_PROPRE: dict[str, Any] = {"type": "Point", "coordinates": [99.0, 99.0, 99.0]}
GEOM_SUPP: dict[str, Any] = {"type": "Polygon", "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]]}


def _feature(identifiant: str, proprietes: dict[str, Any], geometrie: Any) -> dict[str, Any]:
    props: dict[str, Any] = {"id": identifiant}
    props.update(proprietes)
    return {"type": "Feature", "properties": props, "geometry": geometrie}


def _noeud(
    identifiant: str = "n1",
    conteneur_href: Any = "k1",
    geometrie: Any = GEOM_CONTENEUR,
    proprietes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Noeud dont la geometrie est, par defaut, heritee du conteneur."""
    props: dict[str, Any] = {CHAMP_CONTENEUR_HREF: conteneur_href}
    props.update(proprietes or {})
    return _feature(identifiant, props, geometrie)


def _conteneurs(href_geomsupp: str | None = "g1", geometrie: Any = GEOM_CONTENEUR) -> dict[str, Conteneur]:
    return {"k1": Conteneur(geometrie, href_geomsupp)}


def _geomsupps(geometrie: Any = GEOM_SUPP) -> dict[str, Any]:
    return {"g1": geometrie}


def _ecrire_jeu(
    tmp_path: Any,
    noeuds: list[dict[str, Any]] | None = None,
    couche: str = COUCHE_CIBLE,
    href_geomsupp: Any = "g1",
    geom_supp: Any = GEOM_SUPP,
) -> None:
    """Ecrit un jeu complet : noeuds, conteneur et geometrie supplementaire."""
    ecrire_collection(str(tmp_path / f"{couche}{EXTENSION_COUCHE}"), noeuds if noeuds is not None else [_noeud()])
    ecrire_collection(
        str(tmp_path / "RPD_Coffret_Reco.geojson"),
        [_feature("k1", {CHAMP_GEOMSUPP_HREF: href_geomsupp}, GEOM_CONTENEUR)],
    )
    ecrire_collection(
        str(tmp_path / f"{COUCHE_GEOM_SUPP}{EXTENSION_COUCHE}"),
        [_feature("g1", {}, geom_supp)],
    )


# --------------------------------------------------------------------------- #
# Validite d'une geometrie
# --------------------------------------------------------------------------- #


class TestGeometrieValide:
    """Tests de geometrie_valide."""

    def test_polygone(self) -> None:
        assert geometrie_valide(GEOM_SUPP) is True

    def test_point(self) -> None:
        assert geometrie_valide(GEOM_CONTENEUR) is True

    def test_nulle(self) -> None:
        assert geometrie_valide(None) is False

    def test_sans_type(self) -> None:
        assert geometrie_valide({"coordinates": [[0.0, 0.0]]}) is False

    def test_coordonnees_vides(self) -> None:
        assert geometrie_valide({"type": "Polygon", "coordinates": []}) is False

    def test_coordonnees_absentes(self) -> None:
        assert geometrie_valide({"type": "Polygon"}) is False

    def test_collection_non_vide(self) -> None:
        collection = {"type": "GeometryCollection", "geometries": [GEOM_CONTENEUR]}
        assert geometrie_valide(collection) is True

    def test_collection_vide(self) -> None:
        assert geometrie_valide({"type": "GeometryCollection", "geometries": []}) is False

    def test_non_dictionnaire(self) -> None:
        assert geometrie_valide("Point") is False


# --------------------------------------------------------------------------- #
# Perimetre
# --------------------------------------------------------------------------- #


class TestEstAControler:
    """Tests du filtre de perimetre."""

    def test_couche_cible(self) -> None:
        assert est_a_controler(COUCHE_CIBLE) is True

    def test_les_six_couches_cibles(self) -> None:
        assert set(COUCHES_CIBLES) == {
            "RPD_CoupeCircuitAFusibles_Reco",
            "RPD_JeuBarres_Reco",
            "RPD_ModuleRaccordement_Reco",
            "RPD_SupportModules_Reco",
            "RPD_Terre_Reco",
            "RPD_PosteElectrique_Reco",
        }

    def test_jonction_hors_perimetre(self) -> None:
        """RPD_Jonction_Reco ne fait pas partie des couches controlees."""
        assert est_a_controler("RPD_Jonction_Reco") is False

    def test_couche_conteneur_hors_perimetre(self) -> None:
        assert est_a_controler("RPD_Coffret_Reco") is False

    def test_couche_inconnue_hors_perimetre(self) -> None:
        assert est_a_controler("RPD_NouvelleEntite_Reco") is False

    def test_couches_conteneur_declarees(self) -> None:
        assert set(COUCHES_CONTENEUR) == {
            "RPD_Coffret_Reco",
            "RPD_Support_Reco",
            "RPD_BatimentTechnique_Reco",
            "RPD_EnceinteCloturee_Reco",
        }


class TestPerimetreGeometrieDirecte:
    """Le perimetre de la geometrie directe est plus large que celui des chaines."""

    def test_les_deux_ouvrages_localisables(self) -> None:
        assert set(COUCHES_OUVRAGES_LOCALISABLES) == {
            "RPD_PointDeComptage_Reco",
            "RPD_OuvrageCollectifBranchement_Reco",
        }

    def test_ouvrages_localisables_dans_le_perimetre_du_moteur(self) -> None:
        for couche in COUCHES_OUVRAGES_LOCALISABLES:
            assert est_a_controler(couche) is True

    def test_ouvrages_localisables_hors_perimetre_de_chaine(self) -> None:
        """Leur chaine de conteneur releve d'E-6109, pas de ce moteur."""
        for couche in COUCHES_OUVRAGES_LOCALISABLES:
            assert chaine_conteneur_a_controler(couche) is False

    def test_couches_cibles_dans_le_perimetre_de_chaine(self) -> None:
        for couche in COUCHES_CIBLES:
            assert chaine_conteneur_a_controler(couche) is True

    def test_couche_hors_perimetre_sans_chaine(self) -> None:
        assert chaine_conteneur_a_controler("RPD_Jonction_Reco") is False

    def test_perimetre_parcouru_est_l_union(self) -> None:
        assert set(COUCHES_PARCOURUES) == set(COUCHES_CIBLES) | set(COUCHES_OUVRAGES_LOCALISABLES)
        assert len(COUCHES_PARCOURUES) == len(set(COUCHES_PARCOURUES))


class TestCouchesDuControle:
    """Chaque controle ne compte que les entites de ses propres regles."""

    def test_e6209_couvre_tout_le_perimetre(self) -> None:
        assert couches_du_controle(_TYPES_6209) == COUCHES_CONTROLEES

    def test_e6105_limite_a_la_chaine(self) -> None:
        assert couches_du_controle(_TYPES_6105) == COUCHES_CHAINE_CONTROLEE

    def test_e6106_limite_a_la_chaine(self) -> None:
        assert couches_du_controle(_TYPES_6106) == COUCHES_CHAINE_CONTROLEE

    def test_union_des_types_couvre_tout(self) -> None:
        assert couches_du_controle(_TOUS_LES_TYPES) == COUCHES_CONTROLEES

    def test_aucun_type_retenu(self) -> None:
        assert couches_du_controle(frozenset()) == frozenset()

    def test_type_inconnu_ignore(self) -> None:
        """Un type sans perimetre declare ne fait pas echouer le moteur."""
        assert couches_du_controle(frozenset({"type_inexistant"})) == frozenset()


# --------------------------------------------------------------------------- #
# Indexation
# --------------------------------------------------------------------------- #


class TestIndexerConteneurs:
    """Tests de indexer_conteneurs."""

    def test_index_multi_couches(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / "RPD_Coffret_Reco.geojson"),
            [_feature("k1", {CHAMP_GEOMSUPP_HREF: "g1"}, GEOM_CONTENEUR)],
        )
        ecrire_collection(
            str(tmp_path / "RPD_Support_Reco.geojson"),
            [_feature("k2", {CHAMP_GEOMSUPP_HREF: "g2"}, GEOM_CONTENEUR)],
        )
        index, absentes = indexer_conteneurs(str(tmp_path))
        assert set(index) == {"k1", "k2"}
        assert index["k1"].href_geomsupp == "g1"
        assert set(absentes) == {"RPD_BatimentTechnique_Reco", "RPD_EnceinteCloturee_Reco"}

    def test_href_espaces_normalise(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / "RPD_Coffret_Reco.geojson"),
            [_feature("k1", {CHAMP_GEOMSUPP_HREF: " g1 "}, GEOM_CONTENEUR)],
        )
        index, _ = indexer_conteneurs(str(tmp_path))
        assert index["k1"].href_geomsupp == "g1"

    def test_href_absent(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / "RPD_Coffret_Reco.geojson"), [_feature("k1", {}, GEOM_CONTENEUR)])
        index, _ = indexer_conteneurs(str(tmp_path))
        assert index["k1"].href_geomsupp is None

    def test_conteneur_sans_identifiant_ecarte(self, tmp_path: Any) -> None:
        feature = _feature("k1", {}, GEOM_CONTENEUR)
        feature["properties"].pop("id")
        ecrire_collection(str(tmp_path / "RPD_Coffret_Reco.geojson"), [feature])
        index, _ = indexer_conteneurs(str(tmp_path))
        assert index == {}

    def test_toutes_couches_absentes(self, tmp_path: Any) -> None:
        index, absentes = indexer_conteneurs(str(tmp_path))
        assert index == {}
        assert set(absentes) == set(COUCHES_CONTENEUR)


class TestIndexerGeometriesSupplementaires:
    """Tests de indexer_geometries_supplementaires."""

    def test_index(self, tmp_path: Any) -> None:
        ecrire_collection(
            str(tmp_path / f"{COUCHE_GEOM_SUPP}{EXTENSION_COUCHE}"),
            [_feature("g1", {}, GEOM_SUPP)],
        )
        assert indexer_geometries_supplementaires(str(tmp_path)) == {"g1": GEOM_SUPP}

    def test_geometrie_nulle_conservee(self, tmp_path: Any) -> None:
        """L'entite existe : c'est sa geometrie qui est invalide, nuance utile."""
        ecrire_collection(
            str(tmp_path / f"{COUCHE_GEOM_SUPP}{EXTENSION_COUCHE}"),
            [_feature("g1", {}, None)],
        )
        assert indexer_geometries_supplementaires(str(tmp_path)) == {"g1": None}

    def test_fichier_absent(self, tmp_path: Any) -> None:
        assert indexer_geometries_supplementaires(str(tmp_path)) == {}


# --------------------------------------------------------------------------- #
# Classement en cascade
# --------------------------------------------------------------------------- #


class TestClassifierNoeud:
    """Tests de classifier_noeud (fonction pure)."""

    def test_chaine_complete_conforme(self) -> None:
        assert classifier_noeud(GEOM_CONTENEUR, "k1", _conteneurs(), _geomsupps()) == []

    def test_noeud_sans_geometrie_conforme(self) -> None:
        """Le cas nominal du GML : aucune geometrie a la source."""
        assert classifier_noeud(None, "k1", _conteneurs(), _geomsupps()) == []

    def test_conteneur_absent(self) -> None:
        assert classifier_noeud(GEOM_CONTENEUR, None, _conteneurs(), _geomsupps()) == [TYPE_CONTENEUR_ABSENT]

    def test_conteneur_introuvable(self) -> None:
        assert classifier_noeud(GEOM_CONTENEUR, "k9", _conteneurs(), _geomsupps()) == [TYPE_CONTENEUR_INTROUVABLE]

    def test_absence_de_conteneur_court_circuite(self) -> None:
        """Sans conteneur, ni la geometrie ni la suite ne sont evaluables."""
        assert classifier_noeud(GEOM_PROPRE, None, _conteneurs(None), {}) == [TYPE_CONTENEUR_ABSENT]

    def test_geometrie_heritee_non_signalee(self) -> None:
        """Une geometrie egale a celle du conteneur est heritee par l'export."""
        assert classifier_noeud(GEOM_CONTENEUR, "k1", _conteneurs(), _geomsupps()) == []

    def test_geometrie_directe_signalee(self) -> None:
        assert classifier_noeud(GEOM_PROPRE, "k1", _conteneurs(), _geomsupps()) == [TYPE_GEOMETRIE_DIRECTE]

    def test_geomsupp_absente(self) -> None:
        assert classifier_noeud(None, "k1", _conteneurs(None), _geomsupps()) == [TYPE_GEOMSUPP_ABSENTE]

    def test_geomsupp_introuvable(self) -> None:
        assert classifier_noeud(None, "k1", _conteneurs(), {}) == [TYPE_GEOMSUPP_INTROUVABLE]

    def test_geomsupp_invalide(self) -> None:
        assert classifier_noeud(None, "k1", _conteneurs(), _geomsupps(None)) == [TYPE_GEOMSUPP_INVALIDE]

    def test_geomsupp_coordonnees_vides_invalide(self) -> None:
        vide = {"type": "Polygon", "coordinates": []}
        assert classifier_noeud(None, "k1", _conteneurs(), _geomsupps(vide)) == [TYPE_GEOMSUPP_INVALIDE]

    def test_geometrie_directe_et_chaine_rompue_cumulent(self) -> None:
        """Deux defauts independants : le noeud et la chaine de son conteneur."""
        codes = classifier_noeud(GEOM_PROPRE, "k1", _conteneurs(None), _geomsupps())
        assert codes == [TYPE_GEOMETRIE_DIRECTE, TYPE_GEOMSUPP_ABSENTE]

    def test_une_seule_rupture_de_chaine_signalee(self) -> None:
        """La cascade s'arrete a la premiere rupture : pas d'anomalies redondantes."""
        assert len(classifier_noeud(None, "k1", _conteneurs(None), {})) == 1

    def test_geometrie_invalide_non_signalee(self) -> None:
        """Une geometrie sans coordonnees ne localise rien : elle n'est pas propre."""
        vide = {"type": "Point", "coordinates": []}
        assert classifier_noeud(vide, "k1", _conteneurs(), _geomsupps()) == []


class TestClassifierNoeudHorsChaine:
    """Perimetre du point de comptage et de l'ouvrage collectif.

    Seule la regle de geometrie directe y est evaluee : leur chaine de conteneur
    releve d'E-6109, la reevaluer produirait deux fois la meme anomalie.
    """

    def test_geometrie_propre_et_conteneur_signales(self) -> None:
        """Le cas vise : la position est decrite deux fois."""
        codes = classifier_noeud(GEOM_PROPRE, "k1", _conteneurs(), _geomsupps(), False)
        assert codes == [TYPE_GEOMETRIE_DIRECTE]

    def test_geometrie_heritee_conforme(self) -> None:
        assert classifier_noeud(GEOM_CONTENEUR, "k1", _conteneurs(), _geomsupps(), False) == []

    def test_geometrie_propre_sans_conteneur_conforme(self) -> None:
        """Sans rattachement, la geometrie propre est la voie normale d'E-6109."""
        assert classifier_noeud(GEOM_PROPRE, None, _conteneurs(), _geomsupps(), False) == []

    def test_sans_geometrie_ni_conteneur_conforme(self) -> None:
        """L'absence de localisation releve d'E-6109, pas de ce moteur."""
        assert classifier_noeud(None, None, _conteneurs(), _geomsupps(), False) == []

    def test_reference_morte_avec_geometrie_signalee(self) -> None:
        """Le rattachement se lit sur l'attribut, pas sur sa resolution."""
        codes = classifier_noeud(GEOM_PROPRE, "k9", _conteneurs(), _geomsupps(), False)
        assert codes == [TYPE_GEOMETRIE_DIRECTE]

    def test_reference_morte_sans_geometrie_conforme(self) -> None:
        assert classifier_noeud(None, "k9", _conteneurs(), _geomsupps(), False) == []

    def test_reference_morte_geometrie_invalide_conforme(self) -> None:
        vide = {"type": "Point", "coordinates": []}
        assert classifier_noeud(vide, "k9", _conteneurs(), _geomsupps(), False) == []

    def test_chaine_rompue_non_signalee(self) -> None:
        """Le conteneur sans geometrie supplementaire reste l'affaire d'E-6109."""
        assert classifier_noeud(GEOM_CONTENEUR, "k1", _conteneurs(None), _geomsupps(), False) == []

    def test_chaine_rompue_n_empeche_pas_la_geometrie_directe(self) -> None:
        codes = classifier_noeud(GEOM_PROPRE, "k1", _conteneurs(None), _geomsupps(), False)
        assert codes == [TYPE_GEOMETRIE_DIRECTE]


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


class TestDetecterAnomaliesCouche:
    """Tests de detecter_anomalies_couche."""

    def test_couche_conforme(self) -> None:
        assert detecter_anomalies_couche(COUCHE_CIBLE, [_noeud()], _conteneurs(), _geomsupps()) == []

    def test_anomalie_documentee(self) -> None:
        noeud = _noeud(geometrie=GEOM_PROPRE)
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [noeud], _conteneurs(), _geomsupps())
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_GEOMETRIE_DIRECTE
        assert anomalies[0]["couche_noeud"] == COUCHE_CIBLE
        assert anomalies[0]["id_noeud"] == "n1"
        assert anomalies[0]["id_conteneur"] == "k1"
        assert anomalies[0]["id_geometrie_supplementaire"] == "g1"

    def test_couche_hors_perimetre_ignoree(self) -> None:
        """Une couche non ciblee ne produit aucune anomalie, meme fautive."""
        noeud = _noeud(conteneur_href=None)
        assert detecter_anomalies_couche("RPD_Jonction_Reco", [noeud], _conteneurs(), _geomsupps()) == []

    def test_autre_couche_cible_controlee(self) -> None:
        noeud = _noeud(conteneur_href=None)
        anomalies = detecter_anomalies_couche(AUTRE_COUCHE_CIBLE, [noeud], _conteneurs(), _geomsupps())
        assert [a["type_anomalie"] for a in anomalies] == [TYPE_CONTENEUR_ABSENT]

    def test_geometrie_de_repli_sur_le_conteneur(self) -> None:
        """Un noeud sans geometrie reste localisable par celle de son conteneur."""
        noeud = _noeud(geometrie=None)
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [noeud], _conteneurs(None), _geomsupps())
        assert anomalies[0]["geometrie"] == GEOM_CONTENEUR

    def test_geometrie_nulle_sans_conteneur(self) -> None:
        noeud = _noeud(conteneur_href=None, geometrie=None)
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, [noeud], _conteneurs(), _geomsupps())
        assert anomalies[0]["geometrie"] is None

    def test_conteneur_fautif_multiplie_les_anomalies(self) -> None:
        """La regle qualifie l'entite : chaque noeud heberge est prive de position."""
        noeuds = [_noeud("n1"), _noeud("n2"), _noeud("n3")]
        anomalies = detecter_anomalies_couche(COUCHE_CIBLE, noeuds, _conteneurs(None), _geomsupps())
        assert len(anomalies) == 3

    def test_couche_vide(self) -> None:
        assert detecter_anomalies_couche(COUCHE_CIBLE, [], _conteneurs(), _geomsupps()) == []


class TestDetecterAnomaliesOuvrageLocalisable:
    """Detection sur le point de comptage et l'ouvrage collectif."""

    def test_geometrie_propre_et_conteneur_signales(self) -> None:
        ouvrage = _noeud(geometrie=GEOM_PROPRE)
        anomalies = detecter_anomalies_couche(COUCHE_OUVRAGE_LOCALISABLE, [ouvrage], _conteneurs(), _geomsupps())
        assert len(anomalies) == 1
        assert anomalies[0]["type_anomalie"] == TYPE_GEOMETRIE_DIRECTE
        assert anomalies[0]["couche_noeud"] == COUCHE_OUVRAGE_LOCALISABLE
        assert anomalies[0]["geometrie"] == GEOM_PROPRE

    def test_geometrie_heritee_conforme(self) -> None:
        anomalies = detecter_anomalies_couche(COUCHE_OUVRAGE_LOCALISABLE, [_noeud()], _conteneurs(), _geomsupps())
        assert anomalies == []

    def test_sans_conteneur_aucune_anomalie(self) -> None:
        """Ni conteneur_absent ni conteneur_introuvable : ces regles sont a E-6109."""
        ouvrage = _noeud(conteneur_href=None, geometrie=GEOM_PROPRE)
        assert detecter_anomalies_couche(COUCHE_OUVRAGE_LOCALISABLE, [ouvrage], _conteneurs(), _geomsupps()) == []

    def test_chaine_rompue_non_signalee(self) -> None:
        anomalies = detecter_anomalies_couche(COUCHE_OUVRAGE_LOCALISABLE, [_noeud()], _conteneurs(None), _geomsupps())
        assert anomalies == []

    def test_ouvrage_collectif_traite_comme_le_point_de_comptage(self) -> None:
        ouvrage = _noeud(geometrie=GEOM_PROPRE)
        anomalies = detecter_anomalies_couche(
            "RPD_OuvrageCollectifBranchement_Reco", [ouvrage], _conteneurs(), _geomsupps()
        )
        assert [a["type_anomalie"] for a in anomalies] == [TYPE_GEOMETRIE_DIRECTE]


class TestComptages:
    """Tests des comptages du rapport."""

    def test_noeuds_a_controler(self) -> None:
        assert compter_noeuds_a_controler(COUCHE_CIBLE, [_noeud("n1"), _noeud("n2")]) == 2

    def test_noeuds_couche_hors_perimetre_non_comptes(self) -> None:
        assert compter_noeuds_a_controler("RPD_Jonction_Reco", [_noeud("j1"), _noeud("j2")]) == 0

    def test_ouvrage_localisable_compte_pour_e6209(self) -> None:
        entites = [_noeud("o1"), _noeud("o2")]
        assert compter_noeuds_a_controler(COUCHE_OUVRAGE_LOCALISABLE, entites, COUCHES_CONTROLEES) == 2

    def test_ouvrage_localisable_non_compte_pour_la_chaine(self) -> None:
        """E-6105 et E-6106 ne controlent pas ces entites : elles sortent du denominateur."""
        entites = [_noeud("o1"), _noeud("o2")]
        assert compter_noeuds_a_controler(COUCHE_OUVRAGE_LOCALISABLE, entites, COUCHES_CHAINE_CONTROLEE) == 0

    def test_noeuds_non_conformes_dedoublonnes(self) -> None:
        anomalies = [
            {"couche_noeud": COUCHE_CIBLE, "id_noeud": "n1"},
            {"couche_noeud": COUCHE_CIBLE, "id_noeud": "n1"},
            {"couche_noeud": COUCHE_CIBLE, "id_noeud": "n2"},
        ]
        assert compter_noeuds_non_conformes(anomalies) == 2

    def test_noeuds_homonymes_de_couches_differentes_distingues(self) -> None:
        anomalies = [
            {"couche_noeud": COUCHE_CIBLE, "id_noeud": "n1"},
            {"couche_noeud": AUTRE_COUCHE_CIBLE, "id_noeud": "n1"},
        ]
        assert compter_noeuds_non_conformes(anomalies) == 2

    def test_liste_vide(self) -> None:
        assert compter_noeuds_non_conformes([]) == 0


# --------------------------------------------------------------------------- #
# GeoJSON d'ecarts
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "type_anomalie": TYPE_GEOMSUPP_ABSENTE,
            "couche_noeud": COUCHE_CIBLE,
            "id_noeud": "n1",
            "id_conteneur": "k1",
            "id_geometrie_supplementaire": None,
            "geometrie": GEOM_CONTENEUR,
        }

    def test_socle_commun(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()], _profil([self._anomalie()]))["features"][0]["properties"]
        # Le socle porte l'identite du controle qui emet l'ecart : depuis la
        # scission, c'est le code du verificateur lui-meme.
        assert props["code_controle"].startswith("E-")
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert props["id_entite"] == "n1"
        assert props["type_anomalie"] == TYPE_GEOMSUPP_ABSENTE
        assert props["description"]

    def test_proprietes_metier(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()], _profil([self._anomalie()]))["features"][0]["properties"]
        assert props["couche_noeud"] == COUCHE_CIBLE
        assert props["fichier_source"] == f"{COUCHE_CIBLE}{EXTENSION_COUCHE}"
        assert props["id_conteneur"] == "k1"
        assert props["id_geometrie_supplementaire"] is None

    def test_fichier_source_suit_la_couche(self) -> None:
        """Les six couches partagent le fichier d'ecarts : le type doit y figurer."""
        anomalie = {**self._anomalie(), "couche_noeud": AUTRE_COUCHE_CIBLE}
        props = construire_geojson_ecarts([anomalie], _profil([anomalie]))["features"][0]["properties"]
        assert props["fichier_source"] == f"{AUTRE_COUCHE_CIBLE}{EXTENSION_COUCHE}"

    def test_description_par_type(self) -> None:
        for type_anomalie in (
            TYPE_CONTENEUR_ABSENT,
            TYPE_CONTENEUR_INTROUVABLE,
            TYPE_GEOMETRIE_DIRECTE,
            TYPE_GEOMSUPP_ABSENTE,
            TYPE_GEOMSUPP_INTROUVABLE,
            TYPE_GEOMSUPP_INVALIDE,
        ):
            anomalie = {**self._anomalie(), "type_anomalie": type_anomalie}
            props = construire_geojson_ecarts([anomalie], _profil([anomalie]))["features"][0]["properties"]
            assert props["description"] != type_anomalie, type_anomalie

    def test_geometrie_conservee(self) -> None:
        assert (
            construire_geojson_ecarts([self._anomalie()], _profil([self._anomalie()]))["features"][0]["geometry"]
            == GEOM_CONTENEUR
        )

    def test_avec_crs(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([self._anomalie()], _profil([self._anomalie()]), crs)["crs"] == crs

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([], _PROFIL_DEFAUT)["features"] == []


# --------------------------------------------------------------------------- #
# Execution CLI
# --------------------------------------------------------------------------- #


class TestCli:
    """Tests de executer_controle_cli."""

    def test_repertoire_inexistant(self) -> None:
        resultat = _executer("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_repertoire_vide_non_bloquant(self, tmp_path: Any) -> None:
        """Toutes les couches parcourues sont remontees absentes, chaine ou non."""
        resultat = _executer(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert len(resultat["couches_absentes"]) == len(COUCHES_PARCOURUES)

    def test_nominal_conforme(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path)
        resultat = _executer(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_noeuds_controles"] == 1
        assert resultat["nombre_conteneurs"] == 1
        assert resultat["nombre_geometries_supplementaires"] == 1
        assert resultat["priorite"] == PRIORITE_FORTE

    def test_geometrie_directe(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud(geometrie=GEOM_PROPRE)])
        resultat = _executer(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_GEOMETRIE_DIRECTE: 1}

    def test_conteneur_absent(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud(conteneur_href=None)])
        assert _executer(str(tmp_path))["anomalies_par_type"] == {TYPE_CONTENEUR_ABSENT: 1}

    def test_conteneur_introuvable(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud(conteneur_href="k9")])
        assert _executer(str(tmp_path))["anomalies_par_type"] == {TYPE_CONTENEUR_INTROUVABLE: 1}

    def test_geomsupp_absente(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, href_geomsupp=None)
        assert _executer(str(tmp_path))["anomalies_par_type"] == {TYPE_GEOMSUPP_ABSENTE: 1}

    def test_geomsupp_introuvable(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, href_geomsupp="g9")
        assert _executer(str(tmp_path))["anomalies_par_type"] == {TYPE_GEOMSUPP_INTROUVABLE: 1}

    def test_geomsupp_invalide(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, geom_supp=None)
        assert _executer(str(tmp_path))["anomalies_par_type"] == {TYPE_GEOMSUPP_INVALIDE: 1}

    def test_les_six_couches_parcourues(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path)
        ecrire_collection(
            str(tmp_path / f"{AUTRE_COUCHE_CIBLE}{EXTENSION_COUCHE}"),
            [_noeud("t1", conteneur_href=None)],
        )
        resultat = _executer(str(tmp_path))
        assert resultat["nombre_noeuds_controles"] == 2
        assert resultat["anomalies_par_type"] == {TYPE_CONTENEUR_ABSENT: 1}

    def test_jonction_non_parcourue(self, tmp_path: Any) -> None:
        """Une RPD_Jonction_Reco fautive n'est pas controlee par ce moteur."""
        _ecrire_jeu(tmp_path)
        ecrire_collection(
            str(tmp_path / "RPD_Jonction_Reco.geojson"),
            [_noeud("j1", conteneur_href=None, proprietes={"TypeJonction": "RemonteeAeroSouterraine"})],
        )
        resultat = _executer(str(tmp_path))
        assert resultat["nombre_noeuds_controles"] == 1
        assert resultat["nombre_anomalies"] == 0

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud(conteneur_href=None)])
        _executer(str(tmp_path))
        assert os.path.isfile(str(tmp_path / _FICHIER_TEST))

    def test_aucun_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path)
        resultat = _executer(str(tmp_path))
        assert resultat["sortie"] is None
        assert not os.path.isfile(str(tmp_path / _FICHIER_TEST))

    def test_crs_propage(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud(conteneur_href=None)])
        ecrire_collection_avec_crs(
            str(tmp_path / f"{COUCHE_CIBLE}{EXTENSION_COUCHE}"),
            [_noeud(conteneur_href=None)],
            "EPSG:2154",
        )
        _executer(str(tmp_path))
        with open(str(tmp_path / _FICHIER_TEST), encoding="utf-8") as fichier:
            ecarts = json.load(fichier)
        assert "2154" in ecarts["crs"]["properties"]["name"]

    def test_rapport_champs_obligatoires(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path)
        resultat = _executer(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "anomalies_par_type",
            "nombre_noeuds_controles",
            "nombre_noeuds_non_conformes",
            "nombre_conteneurs",
            "nombre_geometries_supplementaires",
            "couches_absentes",
            "couches_conteneur_absentes",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"


class TestCliOuvrageLocalisable:
    """Execution complete sur le point de comptage, bout en bout."""

    def _executer_e6209(self, repertoire: str) -> dict[str, Any]:
        """Execute le seul E-6209, avec son perimetre elargi."""
        return executer_analyse(repertoire, _TYPES_6209, _PROFIL_6209, _FICHIER_TEST)

    def test_geometrie_propre_et_conteneur_signales(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud(geometrie=GEOM_PROPRE)], couche=COUCHE_OUVRAGE_LOCALISABLE)
        resultat = self._executer_e6209(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["anomalies_par_type"] == {TYPE_GEOMETRIE_DIRECTE: 1}
        assert resultat["nombre_noeuds_controles"] == 1

    def test_geometrie_heritee_conforme(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud()], couche=COUCHE_OUVRAGE_LOCALISABLE)
        resultat = self._executer_e6209(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0

    def test_reference_morte_signalee(self, tmp_path: Any) -> None:
        """Le rattachement se lit sur l'attribut, meme s'il ne resout rien."""
        _ecrire_jeu(
            tmp_path,
            [_noeud(conteneur_href="k9", geometrie=GEOM_PROPRE)],
            couche=COUCHE_OUVRAGE_LOCALISABLE,
        )
        resultat = self._executer_e6209(str(tmp_path))
        assert resultat["anomalies_par_type"] == {TYPE_GEOMETRIE_DIRECTE: 1}

    def test_sans_conteneur_conforme(self, tmp_path: Any) -> None:
        _ecrire_jeu(
            tmp_path,
            [_noeud(conteneur_href=None, geometrie=GEOM_PROPRE)],
            couche=COUCHE_OUVRAGE_LOCALISABLE,
        )
        assert self._executer_e6209(str(tmp_path))["nombre_anomalies"] == 0

    def test_e6105_ignore_l_ouvrage_localisable(self, tmp_path: Any) -> None:
        """Un ouvrage sans conteneur ne doit pas ressortir en conteneur_absent."""
        _ecrire_jeu(
            tmp_path,
            [_noeud(conteneur_href=None, geometrie=GEOM_PROPRE)],
            couche=COUCHE_OUVRAGE_LOCALISABLE,
        )
        resultat = executer_analyse(str(tmp_path), _TYPES_6105, _PROFIL_6105, _FICHIER_TEST)
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_noeuds_controles"] == 0

    def test_ecart_porte_le_code_e6209(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud(geometrie=GEOM_PROPRE)], couche=COUCHE_OUVRAGE_LOCALISABLE)
        chemin = self._executer_e6209(str(tmp_path))["sortie"]
        assert chemin is not None
        with open(chemin, encoding="utf-8") as flux:
            proprietes = json.load(flux)["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-6209"
        assert proprietes["couche"] == COUCHE_OUVRAGE_LOCALISABLE
        assert proprietes["fichier_source"] == f"{COUCHE_OUVRAGE_LOCALISABLE}{EXTENSION_COUCHE}"


# --------------------------------------------------------------------------- #
# Comportement multi-version (V1.0 / V1.1)
# --------------------------------------------------------------------------- #


class TestMultiVersion:
    """La chaine de localisation est controlee identiquement en V1.0 et V1.1."""

    def test_v11_champs_extra_sans_effet(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud(proprietes={"Commentaire": "note"})])
        resultat = _executer(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0


# --------------------------------------------------------------------------- #
# Scission E-6105 / E-6112
# --------------------------------------------------------------------------- #


class TestScissionConteneurAbsent:
    """L'absence de conteneur releve d'E-6112, la reference morte d'E-6105."""

    def _executer_6112(self, repertoire: str) -> dict[str, Any]:
        from recostar.controle.conteneur.e6112 import executer_controle_cli

        return executer_controle_cli(repertoire)

    def _executer_6105(self, repertoire: str) -> dict[str, Any]:
        from recostar.controle.conteneur.e6105 import executer_controle_cli

        return executer_controle_cli(repertoire)

    def test_types_retenus_disjoints(self) -> None:
        assert not _TYPES_6105 & _TYPES_6112

    def test_absence_ne_sort_que_d_e6112(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud(conteneur_href=None)])
        assert self._executer_6112(str(tmp_path))["anomalies_par_type"] == {TYPE_CONTENEUR_ABSENT: 1}
        assert self._executer_6105(str(tmp_path))["nombre_anomalies"] == 0

    def test_reference_morte_ne_sort_que_d_e6105(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud(conteneur_href="k9")])
        assert self._executer_6105(str(tmp_path))["anomalies_par_type"] == {TYPE_CONTENEUR_INTROUVABLE: 1}
        assert self._executer_6112(str(tmp_path))["nombre_anomalies"] == 0

    def test_noeud_conforme(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path)
        assert self._executer_6112(str(tmp_path))["nombre_anomalies"] == 0
        assert self._executer_6105(str(tmp_path))["nombre_anomalies"] == 0

    def test_exclusivite_par_construction(self) -> None:
        """Un noeud a une reference, ou n'en a pas : jamais les deux."""
        for reference in (None, "k1", "k9"):
            codes = classifier_noeud(GEOM_CONTENEUR, reference, _conteneurs(), _geomsupps())
            assert not (TYPE_CONTENEUR_ABSENT in codes and TYPE_CONTENEUR_INTROUVABLE in codes)

    def test_code_erreur_de_chaque_controle(self, tmp_path: Any) -> None:
        _ecrire_jeu(tmp_path, [_noeud(conteneur_href=None)])
        chemin = self._executer_6112(str(tmp_path))["sortie"]
        assert chemin is not None
        with open(chemin, encoding="utf-8") as flux:
            proprietes = json.load(flux)["features"][0]["properties"]
        assert proprietes["code_erreur"] == "E-6112"
        assert proprietes["priorite"] == PRIORITE_FORTE

    def test_les_six_couches_du_perimetre(self, tmp_path: Any) -> None:
        """E-6112 porte sur les memes couches qu'E-6105 : celles de la chaine."""
        from recostar.controle.conteneur.e6112 import TYPES_RETENUS

        assert couches_du_controle(TYPES_RETENUS) == COUCHES_CHAINE_CONTROLEE
        assert len(COUCHES_CHAINE_CONTROLEE) == 6
