"""Tests du traitement de reprojection des GML RecoStaR."""

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree import ElementTree as ET  # nosec B405

import defusedxml.ElementTree as DefusedET  # type: ignore
import pytest
from pyproj import CRS, Transformer

from recostar.traitement.reprojection.reprojection_gml import (
    DIMENSION_DEFAUT,
    ResultatReprojection,
    _chemin_sortie_par_defaut,
    _decimales_pour,
    _formater,
    executer_reprojection,
    lire_crs_source,
    reprojeter_arbre,
    reprojeter_positions,
)

NS_GML = "{http://www.opengis.net/gml/3.2}"
NS_RECOSTAR = "{http://StaR-Elec.com}"


@pytest.fixture
def transformateur_2154_3947():
    """Transformateur Lambert-93 vers CC47."""
    return Transformer.from_crs(CRS("EPSG:2154"), CRS("EPSG:3947"), always_xy=True)


def _positions(chemin) -> list[float]:
    """Toutes les coordonnees portees par un GML, a plat."""
    racine = DefusedET.parse(chemin).getroot()
    valeurs: list[float] = []
    for element in racine.iter():
        if element.tag in (f"{NS_GML}posList", f"{NS_GML}pos") and element.text:
            valeurs.extend(float(valeur) for valeur in element.text.split())
    return valeurs


class TestLectureProjectionSource:
    """La projection d'entree est deduite du fichier, jamais demandee."""

    def _racine(self, srs_metadata: str | None, srs_geometrie: str | None) -> ET.Element:
        """Arbre minimal portant les projections demandees."""
        racine = ET.Element(f"{NS_GML}FeatureCollection")
        if srs_metadata is not None:
            metadata = ET.SubElement(racine, f"{NS_RECOSTAR}Metadata")
            ET.SubElement(metadata, f"{NS_RECOSTAR}SRS").text = srs_metadata
        if srs_geometrie is not None:
            ET.SubElement(racine, f"{NS_GML}Point").set("srsName", srs_geometrie)
        return racine

    def test_metadata_fait_foi(self):
        """Le champ Metadata/SRS est la source primaire."""
        epsg, avertissements = lire_crs_source(self._racine("EPSG:2154", "EPSG:2154"))
        assert epsg == "EPSG:2154"
        assert avertissements == []

    def test_urn_ogc_normalisee(self):
        """Une URN OGC est ramenee au format canonique."""
        epsg, _ = lire_crs_source(self._racine("urn:ogc:def:crs:EPSG::3947", None))
        assert epsg == "EPSG:3947"

    def test_repli_sur_les_geometries(self):
        """Sans Metadata/SRS, la projection vient des srsName."""
        epsg, avertissements = lire_crs_source(self._racine(None, "EPSG:3947"))
        assert epsg == "EPSG:3947"
        assert any("Metadata/SRS absent" in message for message in avertissements)

    def test_divergence_signalee(self):
        """Un srsName contredisant le declare est remonte sans bloquer."""
        epsg, avertissements = lire_crs_source(self._racine("EPSG:2154", "EPSG:3947"))
        assert epsg == "EPSG:2154"
        assert any("differe des srsName" in message for message in avertissements)

    def test_geometries_heterogenes_signalees(self):
        """Plusieurs projections dans les géométries constituent un avertissement."""
        racine = self._racine(None, "EPSG:2154")
        ET.SubElement(racine, f"{NS_GML}Point").set("srsName", "EPSG:3947")
        _, avertissements = lire_crs_source(racine)
        assert any("heterogenes" in message for message in avertissements)

    def test_valeur_non_reconnue(self):
        """Une valeur hors format EPSG ne fournit aucune projection."""
        epsg, avertissements = lire_crs_source(self._racine("WGS84", None))
        assert epsg is None
        assert any("non reconnue" in message for message in avertissements)

    def test_aucune_projection(self):
        """Un fichier muet sur sa projection ne produit rien."""
        assert lire_crs_source(self._racine(None, None)) == (None, [])


class TestReprojectionPositions:
    """Transformation des listes de positions GML."""

    def test_altitude_conservee(self, transformateur_2154_3947):
        """Seules les coordonnees planimetriques sont transformees."""
        texte, nb = reprojeter_positions("650000 6860000 123.45 651000 6861000 -7.5", transformateur_2154_3947, 3, 3)
        valeurs = texte.split()
        assert nb == 2
        assert valeurs[2] == "123.45"
        assert valeurs[5] == "-7.5"

    def test_coordonnees_transformees(self, transformateur_2154_3947):
        """Les X/Y changent effectivement de valeur."""
        texte, _ = reprojeter_positions("650000 6860000 0", transformateur_2154_3947, 3, 3)
        assert texte.split()[:2] != ["650000", "6860000"]

    def test_dimension_deux(self, transformateur_2154_3947):
        """Une geometrie planimetrique est traitee sans altitude."""
        texte, nb = reprojeter_positions("650000 6860000", transformateur_2154_3947, 2, 3)
        assert nb == 1
        assert len(texte.split()) == 2

    def test_texte_incoherent_inchange(self, transformateur_2154_3947):
        """Un nombre de valeurs non multiple de la dimension est laisse tel quel."""
        texte, nb = reprojeter_positions("650000 6860000 0 651000", transformateur_2154_3947, 3, 3)
        assert nb == 0
        assert texte == "650000 6860000 0 651000"

    def test_texte_vide_inchange(self, transformateur_2154_3947):
        """Une liste vide ne produit aucune position."""
        assert reprojeter_positions("", transformateur_2154_3947, 3, 3) == ("", 0)

    @pytest.mark.parametrize(
        ("valeur", "decimales", "attendu"),
        [(1609012.1100, 3, "1609012.11"), (43.8918736, 9, "43.8918736"), (0.0, 3, "0")],
    )
    def test_formatage_sans_zeros_superflus(self, valeur, decimales, attendu):
        """Le formatage evite la notation scientifique et les zeros inutiles."""
        assert _formater(valeur, decimales) == attendu

    def test_decimales_selon_nature_du_crs(self):
        """Un CRS geographique exige davantage de decimales qu'un CRS projete."""
        assert _decimales_pour("EPSG:4326") > _decimales_pour("EPSG:2154")


class TestReprojectionArbre:
    """Realignement des projections declarees dans l'arbre."""

    def _arbre(self) -> ET.Element:
        """Arbre portant un Metadata/SRS et une geometrie."""
        racine = ET.Element(f"{NS_GML}FeatureCollection")
        metadata = ET.SubElement(racine, f"{NS_RECOSTAR}Metadata")
        ET.SubElement(metadata, f"{NS_RECOSTAR}SRS").text = "EPSG:2154"
        ligne = ET.SubElement(racine, f"{NS_GML}LineString")
        ligne.set("srsName", "EPSG:2154")
        positions = ET.SubElement(ligne, f"{NS_GML}posList")
        positions.set("srsDimension", "3")
        positions.text = "650000 6860000 12 651000 6861000 13"
        return racine

    def test_srs_name_realigne(self, transformateur_2154_3947):
        """Les srsName suivent la projection de sortie."""
        racine = self._arbre()
        nb_geometries, nb_positions = reprojeter_arbre(racine, transformateur_2154_3947, "EPSG:3947")
        assert nb_geometries == 1
        assert nb_positions == 2
        ligne = racine.find(f"{NS_GML}LineString")
        assert ligne is not None
        assert ligne.get("srsName") == "EPSG:3947"

    def test_metadata_srs_realigne(self, transformateur_2154_3947):
        """Le champ Metadata/SRS suit lui aussi."""
        racine = self._arbre()
        reprojeter_arbre(racine, transformateur_2154_3947, "EPSG:3947")
        srs = racine.find(f"{NS_RECOSTAR}Metadata/{NS_RECOSTAR}SRS")
        assert srs is not None
        assert srs.text == "EPSG:3947"

    def test_dimension_par_defaut(self, transformateur_2154_3947):
        """Sans srsDimension, la 3D du format est presumee."""
        racine = self._arbre()
        positions = racine.find(f"{NS_GML}LineString/{NS_GML}posList")
        assert positions is not None
        del positions.attrib["srsDimension"]
        _, nb_positions = reprojeter_arbre(racine, transformateur_2154_3947, "EPSG:3947")
        assert nb_positions == 6 // DIMENSION_DEFAUT


class TestExecutionComplete:
    """Traitement de bout en bout, depuis le fichier."""

    def test_reprojection_reussie(self, gml_lambert93, tmp_path):
        """Le fichier produit declare la projection demandee."""
        sortie = tmp_path / "sortie.gml"
        resultat = executer_reprojection(str(gml_lambert93), "EPSG:3947", str(sortie))
        assert resultat.succes
        assert resultat.epsg_source == "EPSG:2154"
        assert resultat.epsg_cible == "EPSG:3947"
        assert resultat.nb_positions == 2
        assert 'srsName="EPSG:3947"' in sortie.read_text(encoding="utf-8")

    def test_aller_retour_fidele(self, gml_lambert93, tmp_path):
        """Reprojeter puis revenir restitue les coordonnees d'origine."""
        intermediaire = tmp_path / "cc47.gml"
        retour = tmp_path / "retour.gml"
        executer_reprojection(str(gml_lambert93), "EPSG:3947", str(intermediaire))
        executer_reprojection(str(intermediaire), "EPSG:2154", str(retour))
        origine = _positions(gml_lambert93)
        final = _positions(retour)
        assert len(origine) == len(final)
        assert max(abs(a - b) for a, b in zip(origine, final, strict=True)) < 0.01

    def test_commentaire_preserve(self, gml_lambert93, tmp_path):
        """Le commentaire d'en-tete du GML source survit au traitement."""
        sortie = tmp_path / "sortie.gml"
        executer_reprojection(str(gml_lambert93), "EPSG:3947", str(sortie))
        assert "GML au format RecoStar-v1.1." in sortie.read_text(encoding="utf-8")

    def test_prefixes_namespace_preserves(self, gml_lambert93, tmp_path):
        """Les prefixes d'origine sont conserves, sans ns0 genere."""
        sortie = tmp_path / "sortie.gml"
        executer_reprojection(str(gml_lambert93), "EPSG:3947", str(sortie))
        contenu = sortie.read_text(encoding="utf-8")
        assert "xmlns:RecoStaR=" in contenu
        assert "ns0:" not in contenu

    def test_chemin_sortie_par_defaut(self, gml_lambert93):
        """Sans chemin de sortie, le fichier est suffixe par la projection."""
        resultat = executer_reprojection(str(gml_lambert93), "EPSG:3947")
        assert resultat.succes
        assert resultat.chemin_sortie.endswith("recolement_epsg3947.gml")

    def test_projection_source_deduite_des_geometries(self, gml_sans_metadata, tmp_path):
        """Sans Metadata/SRS, le traitement se rabat sur les geometries."""
        resultat = executer_reprojection(str(gml_sans_metadata), "EPSG:3947", str(tmp_path / "s.gml"))
        assert resultat.succes
        assert resultat.epsg_source == "EPSG:2154"
        assert any("Metadata/SRS absent" in message for message in resultat.avertissements)

    def test_divergence_remontee(self, gml_projections_divergentes, tmp_path):
        """Une divergence declaree/geometries n'interrompt pas le traitement."""
        resultat = executer_reprojection(str(gml_projections_divergentes), "EPSG:4326", str(tmp_path / "s.gml"))
        assert resultat.succes
        assert any("differe des srsName" in message for message in resultat.avertissements)

    def test_fichier_introuvable(self, tmp_path):
        """Un chemin invalide est rapporte sans exception."""
        resultat = executer_reprojection(str(tmp_path / "absent.gml"), "EPSG:3947")
        assert not resultat.succes
        assert "introuvable" in resultat.erreur

    def test_epsg_sortie_non_reconnu(self, gml_lambert93):
        """Une projection de sortie hors format EPSG est refusee."""
        resultat = executer_reprojection(str(gml_lambert93), "WGS84")
        assert not resultat.succes
        assert "non reconnue" in resultat.erreur

    def test_gml_illisible(self, tmp_path):
        """Un fichier XML malforme est rapporte comme tel."""
        chemin = tmp_path / "casse.gml"
        chemin.write_text("<gml:FeatureCollection>", encoding="utf-8")
        resultat = executer_reprojection(str(chemin), "EPSG:3947")
        assert not resultat.succes
        assert "illisible" in resultat.erreur

    def test_projection_source_absente(self, tmp_path):
        """Un GML muet sur sa projection ne peut pas etre reprojete."""
        chemin = tmp_path / "muet.gml"
        chemin.write_text(
            '<gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2"/>',
            encoding="utf-8",
        )
        resultat = executer_reprojection(str(chemin), "EPSG:3947")
        assert not resultat.succes
        assert "Projection d'entree introuvable" in resultat.erreur


class TestResultatReprojection:
    """Serialisation du compte rendu."""

    def test_succes_sans_cles_superflues(self):
        """Un resultat nominal n'expose ni erreur ni avertissement."""
        resultat = ResultatReprojection()
        resultat.succes = True
        resultat.epsg_source = "EPSG:2154"
        resultat.epsg_cible = "EPSG:3947"
        donnees = resultat.vers_dict()
        assert donnees["succes"] is True
        assert "erreur" not in donnees
        assert "avertissements" not in donnees

    def test_erreur_exposee(self):
        """Un echec porte son motif."""
        resultat = ResultatReprojection()
        resultat.erreur = "motif"
        assert resultat.vers_dict()["erreur"] == "motif"

    def test_avertissements_exposes(self):
        """Les avertissements accompagnent le compte rendu quand il y en a."""
        resultat = ResultatReprojection()
        resultat.avertissements = ["divergence"]
        assert resultat.vers_dict()["avertissements"] == ["divergence"]

    def test_nom_de_sortie_derive(self, tmp_path):
        """Le nom par defaut combine l'entree et la projection visee."""
        entree = tmp_path / "reco.gml"
        attendu = tmp_path / "reco_epsg3947.gml"
        assert _chemin_sortie_par_defaut(str(entree), "EPSG:3947") == str(attendu)
