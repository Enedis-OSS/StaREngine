#!/usr/bin/env python3
"""
Tests du contrôle de validité des géométries (E0115 / E0015).

Couvre le comptage des positions dans les trois écritures GML, les seuils par
type de géométrie, l'aiguillage entre les codes E-1108 et E-1109, et l'analyse
d'un GML de bout en bout.

Le cas fondateur est reproduit en dernier : un `gml:posList` vide, que la
validation XSD déclare conforme et qu'aucun contrôle ne relevait avant E0115.
"""

import defusedxml.ElementTree as DefusedET  # type: ignore

from recostar.controle.xsd_structuration.codes_controle import RANG_GEOMETRIE
from recostar.controle.xsd_structuration.codes_verificateur_xsd import resoudre_code_erreur_xsd
from recostar.controle.xsd_structuration.e0115 import AnalyseurGeometries
from recostar.controle.xsd_structuration.priorites_structuration import PRIORITE_FORTE
from recostar.controle.xsd_structuration.regles_geometrie import (
    CODE_GEOMETRIE_INVALIDE,
    CODE_GEOMSUPP_SANS_GEOMETRIE,
    POSITIONS_MINIMALES_DEFAUT,
    compter_positions,
    positions_attendues,
    type_geometrie,
    valider_geometrie,
    valider_objet,
)
from recostar.controle.xsd_structuration.versions import resoudre_profil

NS = 'xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:RecoStaR="http://StaR-Elec.com"'

# Géométries de référence, dans les écritures que GML admet.
_LS_VIDE = '<gml:LineString srsDimension="3"><gml:posList></gml:posList></gml:LineString>'
_LS_UN_POINT = '<gml:LineString srsDimension="3"><gml:posList>1 2 3</gml:posList></gml:LineString>'
_LS_VALIDE = '<gml:LineString srsDimension="3"><gml:posList>1 2 3 4 5 6</gml:posList></gml:LineString>'
_POINT_VALIDE = '<gml:Point srsDimension="3"><gml:pos>1 2 3</gml:pos></gml:Point>'
_POINT_VIDE = '<gml:Point srsDimension="3"><gml:pos></gml:pos></gml:Point>'

_TYPE_GEOMSUPP = "RPD_GeometrieSupplementaire_Reco"


def _geometrie(contenu: str):
    """Construit un élément RecoStaR:Geometrie portant la géométrie donnée."""
    return DefusedET.fromstring(f"<RecoStaR:Geometrie {NS}>{contenu}</RecoStaR:Geometrie>")


class TestComptagePositions:
    """Comptage des positions dans les trois écritures GML."""

    def test_poslist_vide(self) -> None:
        assert compter_positions(_geometrie(_LS_VIDE)) == 0

    def test_poslist_trois_dimensions(self) -> None:
        """Six valeurs en dimension 3 valent deux positions."""
        assert compter_positions(_geometrie(_LS_VALIDE)) == 2

    def test_poslist_deux_dimensions(self) -> None:
        geom = '<gml:LineString srsDimension="2"><gml:posList>1 2 3 4 5 6</gml:posList></gml:LineString>'
        assert compter_positions(_geometrie(geom)) == 3

    def test_dimension_absente_vaut_deux(self) -> None:
        """Sans srsDimension déclaré, la position est supposée planimétrique."""
        geom = "<gml:LineString><gml:posList>1 2 3 4</gml:posList></gml:LineString>"
        assert compter_positions(_geometrie(geom)) == 2

    def test_dimension_illisible_ne_fait_pas_echouer(self) -> None:
        geom = '<gml:LineString srsDimension="trois"><gml:posList>1 2 3 4</gml:posList></gml:LineString>'
        assert compter_positions(_geometrie(geom)) == 2

    def test_noeuds_pos_comptes_un_par_un(self) -> None:
        geom = '<gml:LineString srsDimension="3"><gml:pos>1 2 3</gml:pos><gml:pos>4 5 6</gml:pos></gml:LineString>'
        assert compter_positions(_geometrie(geom)) == 2

    def test_ecritures_mixtes_cumulees(self) -> None:
        """Un tracé mêlant posList et pos reste correctement dénombré."""
        geom = (
            '<gml:LineString srsDimension="3"><gml:posList>1 2 3</gml:posList><gml:pos>4 5 6</gml:pos></gml:LineString>'
        )
        assert compter_positions(_geometrie(geom)) == 2

    def test_coordinates_forme_heritee(self) -> None:
        geom = '<gml:LineString srsDimension="2"><gml:coordinates>1,2 3,4</gml:coordinates></gml:LineString>'
        assert compter_positions(_geometrie(geom)) == 2


class TestSeuils:
    """Nombre minimal de positions selon le type de géométrie."""

    def test_point(self) -> None:
        assert positions_attendues("Point") == 1

    def test_ligne(self) -> None:
        assert positions_attendues("LineString") == 2

    def test_anneau(self) -> None:
        assert positions_attendues("LinearRing") == 3

    def test_type_inconnu_retombe_sur_le_defaut(self) -> None:
        """Mieux vaut contrôler une géométrie inconnue que la laisser passer."""
        assert positions_attendues("Tesseract") == POSITIONS_MINIMALES_DEFAUT

    def test_type_absent(self) -> None:
        assert positions_attendues(None) == POSITIONS_MINIMALES_DEFAUT


class TestTypeGeometrie:
    """Résolution du type porté par le conteneur RecoStaR:Geometrie."""

    def test_linestring(self) -> None:
        assert type_geometrie(_geometrie(_LS_VALIDE)) == "LineString"

    def test_conteneur_vide(self) -> None:
        assert type_geometrie(_geometrie("")) is None


class TestValiderGeometrie:
    """Verdict porté sur une géométrie isolée."""

    def test_ligne_valide(self) -> None:
        assert valider_geometrie("RPD_PleineTerre_Reco", "id1", _geometrie(_LS_VALIDE)) is None

    def test_poslist_vide_signalee(self) -> None:
        erreur = valider_geometrie("RPD_PleineTerre_Reco", "id1", _geometrie(_LS_VIDE))
        assert erreur is not None
        assert erreur.type_erreur == CODE_GEOMETRIE_INVALIDE
        assert erreur.positions_trouvees == 0
        assert erreur.positions_attendues == 2

    def test_ligne_a_un_point_signalee(self) -> None:
        """Une courbe joint deux points : un seul ne la définit pas."""
        erreur = valider_geometrie("RPD_PleineTerre_Reco", "id1", _geometrie(_LS_UN_POINT))
        assert erreur is not None
        assert erreur.positions_trouvees == 1

    def test_point_valide(self) -> None:
        assert valider_geometrie("RPD_Coffret_Reco", "id1", _geometrie(_POINT_VALIDE)) is None

    def test_point_vide_signale(self) -> None:
        assert valider_geometrie("RPD_Coffret_Reco", "id1", _geometrie(_POINT_VIDE)) is not None

    def test_priorite_forte(self) -> None:
        """Les deux codes du vérificateur sont classés « forte »."""
        erreur = valider_geometrie("RPD_PleineTerre_Reco", "id1", _geometrie(_LS_VIDE))
        assert erreur is not None
        assert erreur.priorite == PRIORITE_FORTE

    def test_message_nomme_ce_qui_manque(self) -> None:
        erreur = valider_geometrie("RPD_PleineTerre_Reco", "id1", _geometrie(_LS_VIDE))
        assert erreur is not None
        assert "aucune position" in erreur.message
        assert "RPD_PleineTerre_Reco" in erreur.message

    def test_serialisation(self) -> None:
        erreur = valider_geometrie("RPD_PleineTerre_Reco", "id42", _geometrie(_LS_VIDE))
        assert erreur is not None
        donnees = erreur.vers_dict()
        assert donnees["gml_id"] == "id42"
        assert donnees["severite"] == "ERREUR"
        assert donnees["type_geometrie"] == "LineString"


class TestAiguillageDesCodes:
    """E-1109 vise la géométrie supplémentaire, E-1108 tout autre objet."""

    def _code(self, type_rpd: str, contenu: str) -> str | None:
        erreur = valider_geometrie(type_rpd, "id1", _geometrie(contenu))
        if erreur is None:
            return None
        return resoudre_code_erreur_xsd(RANG_GEOMETRIE, erreur.type_erreur)

    def test_cheminement_vide_donne_e1108(self) -> None:
        assert self._code("RPD_PleineTerre_Reco", _LS_VIDE) == "E-1108"

    def test_cable_vide_donne_e1108(self) -> None:
        assert self._code("RPD_CableElectrique_Reco", _LS_VIDE) == "E-1108"

    def test_geometrie_supplementaire_donne_e1109(self) -> None:
        assert self._code(_TYPE_GEOMSUPP, _LS_VIDE) == "E-1109"

    def test_geometrie_supplementaire_sans_contenu(self) -> None:
        """Conteneur Geometrie vide : l'objet n'a pas d'autre raison d'être."""
        erreur = valider_geometrie(_TYPE_GEOMSUPP, "id1", _geometrie(""))
        assert erreur is not None
        assert erreur.type_erreur == CODE_GEOMSUPP_SANS_GEOMETRIE

    def test_geometrie_supplementaire_valide(self) -> None:
        assert self._code(_TYPE_GEOMSUPP, _LS_VALIDE) is None


class TestValiderObjet:
    """Validation de toutes les géométries d'un objet RPD."""

    def _objet(self, contenu_geometries: str):
        return DefusedET.fromstring(
            f"<RecoStaR:RPD_PleineTerre_Reco {NS}>{contenu_geometries}</RecoStaR:RPD_PleineTerre_Reco>"
        )

    def test_objet_sans_element_geometrie(self) -> None:
        """L'absence de l'élément relève de la séquence (E0110), pas de ce moteur."""
        objet = self._objet("<RecoStaR:PrecisionXY>A</RecoStaR:PrecisionXY>")
        assert valider_objet("RPD_PleineTerre_Reco", "id1", objet) == []

    def test_objet_a_geometrie_valide(self) -> None:
        objet = self._objet(f"<RecoStaR:Geometrie>{_LS_VALIDE}</RecoStaR:Geometrie>")
        assert valider_objet("RPD_PleineTerre_Reco", "id1", objet) == []

    def test_objet_a_geometrie_vide(self) -> None:
        objet = self._objet(f"<RecoStaR:Geometrie>{_LS_VIDE}</RecoStaR:Geometrie>")
        assert len(valider_objet("RPD_PleineTerre_Reco", "id1", objet)) == 1


class TestAnalyseGml:
    """Analyse d'un fichier GML de bout en bout."""

    _GABARIT = """<?xml version="1.0" encoding="utf-8"?>
<gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:RecoStaR="http://StaR-Elec.com">
{membres}
</gml:FeatureCollection>"""

    def _membre(self, type_rpd: str, gml_id: str, geometrie: str) -> str:
        return (
            f'<gml:featureMember><RecoStaR:{type_rpd} gml:id="{gml_id}">'
            f"<RecoStaR:Geometrie>{geometrie}</RecoStaR:Geometrie>"
            f"</RecoStaR:{type_rpd}></gml:featureMember>"
        )

    def _analyser(self, tmp_path, membres: str):
        chemin = tmp_path / "jeu.gml"
        chemin.write_text(self._GABARIT.format(membres=membres), encoding="utf-8")
        return AnalyseurGeometries(chemin, resoudre_profil("1.1")).analyser()

    def test_jeu_conforme(self, tmp_path) -> None:
        membres = self._membre("RPD_PleineTerre_Reco", "id1", _LS_VALIDE)
        assert self._analyser(tmp_path, membres) == []

    def test_poslist_vide_detectee(self, tmp_path) -> None:
        """Le cas fondateur : la validation XSD déclare ce GML conforme."""
        membres = self._membre("RPD_PleineTerre_Reco", "id1", _LS_VIDE)
        erreurs = self._analyser(tmp_path, membres)
        assert len(erreurs) == 1
        assert erreurs[0].gml_id == "id1"

    def test_plusieurs_objets_signales(self, tmp_path) -> None:
        membres = "".join(self._membre("RPD_PleineTerre_Reco", f"id{i}", _LS_VIDE) for i in range(3)) + self._membre(
            "RPD_PleineTerre_Reco", "id_ok", _LS_VALIDE
        )
        erreurs = self._analyser(tmp_path, membres)
        assert [e.gml_id for e in erreurs] == ["id0", "id1", "id2"]

    def test_types_ep_ignores(self, tmp_path) -> None:
        """Les objets EP sont hors périmètre, comme pour le contrôle d'ordre."""
        membres = self._membre("EP_RemonteeAeroSouterraine_Reco", "id1", _LS_VIDE)
        assert self._analyser(tmp_path, membres) == []

    def test_type_hors_profil_ignore(self, tmp_path) -> None:
        membres = self._membre("RPD_Zebre_Reco", "id1", _LS_VIDE)
        assert self._analyser(tmp_path, membres) == []

    def test_tous_types_porteurs_controles(self, tmp_path) -> None:
        """Le contrôle ne se restreint pas aux cheminements."""
        membres = (
            self._membre("RPD_PleineTerre_Reco", "chem", _LS_VIDE)
            + self._membre("RPD_CableElectrique_Reco", "cable", _LS_VIDE)
            + self._membre(_TYPE_GEOMSUPP, "geomsupp", _LS_VIDE)
        )
        erreurs = self._analyser(tmp_path, membres)
        assert {e.gml_id for e in erreurs} == {"chem", "cable", "geomsupp"}
