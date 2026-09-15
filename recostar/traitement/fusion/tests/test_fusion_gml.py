"""Tests du traitement de fusion des GML RecoStaR."""

from collections import Counter

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree import ElementTree as ET  # nosec B405

import defusedxml.ElementTree as DefusedET  # type: ignore
import pytest

from recostar.traitement.fusion.fusion_gml import (
    ATTRIBUT_HREF,
    ATTRIBUT_ID,
    ResultatFusion,
    _chemin_sortie_par_defaut,
    _version_schema,
    collecter_identifiants,
    executer_fusion,
    fusionner_arbres,
    remapper_collisions,
)

NS_GML = "{http://www.opengis.net/gml/3.2}"
NS_RECOSTAR = "{http://StaR-Elec.com}"


def _racine(chemin) -> ET.Element:
    """Racine d'un GML produit."""
    racine = DefusedET.parse(str(chemin)).getroot()
    assert racine is not None
    return racine


def _identifiants(racine: ET.Element) -> list[str]:
    """Tous les gml:id de l'arbre, doublons compris."""
    return [identifiant for element in racine.iter() if (identifiant := element.get(ATTRIBUT_ID))]


class TestCollecteIdentifiants:
    """Recensement des gml:id d'un arbre."""

    def test_collecte(self):
        """Chaque gml:id rencontre est recense."""
        racine = ET.Element("racine")
        ET.SubElement(racine, "enfant").set(ATTRIBUT_ID, "a")
        ET.SubElement(racine, "enfant").set(ATTRIBUT_ID, "b")
        assert collecter_identifiants(racine) == {"a", "b"}

    def test_arbre_sans_identifiant(self):
        """Un arbre sans gml:id ne produit aucun identifiant."""
        assert collecter_identifiants(ET.Element("racine")) == set()


class TestRemappageCollisions:
    """Renommage des identifiants deja pris par l'autre fichier."""

    def _arbre(self) -> ET.Element:
        """Arbre portant un identifiant et une reference vers celui-ci."""
        racine = ET.Element("racine")
        reseau = ET.SubElement(racine, f"{NS_RECOSTAR}ReseauUtilite")
        reseau.set(ATTRIBUT_ID, "Reseau")
        reference = ET.SubElement(racine, f"{NS_RECOSTAR}reseau")
        reference.set(ATTRIBUT_HREF, "Reseau")
        return racine

    def test_identifiant_en_collision_renomme(self):
        """Un identifiant deja pris recoit un nouvel identifiant."""
        racine = self._arbre()
        table = remapper_collisions(racine, {"Reseau"})
        assert list(table) == ["Reseau"]
        assert racine[0].get(ATTRIBUT_ID) == table["Reseau"]

    def test_reference_suit_le_renommage(self):
        """Le xlink:href pointant l'identifiant renomme est mis a jour."""
        racine = self._arbre()
        table = remapper_collisions(racine, {"Reseau"})
        assert racine[1].get(ATTRIBUT_HREF) == table["Reseau"]

    def test_fragment_local_suivi(self):
        """La forme '#identifiant' est prise en charge."""
        racine = self._arbre()
        racine[1].set(ATTRIBUT_HREF, "#Reseau")
        table = remapper_collisions(racine, {"Reseau"})
        assert racine[1].get(ATTRIBUT_HREF) == f"#{table['Reseau']}"

    def test_sans_collision_aucun_renommage(self):
        """Un arbre sans identifiant commun est laisse intact."""
        racine = self._arbre()
        assert remapper_collisions(racine, {"AutreChose"}) == {}
        assert racine[0].get(ATTRIBUT_ID) == "Reseau"
        assert racine[1].get(ATTRIBUT_HREF) == "Reseau"

    def test_reference_externe_preservee(self):
        """Une reference de CodeList, qui ne vise aucun gml:id, est preservee."""
        racine = self._arbre()
        nature = ET.SubElement(racine, f"{NS_RECOSTAR}NatureSupport")
        nature.set(ATTRIBUT_HREF, "Poteau")
        remapper_collisions(racine, {"Reseau"})
        assert nature.get(ATTRIBUT_HREF) == "Poteau"

    def test_nouvel_identifiant_valide(self):
        """L'identifiant genere respecte le format xsd:ID (NCName)."""
        table = remapper_collisions(self._arbre(), {"Reseau"})
        genere = table["Reseau"]
        assert genere.startswith("id")
        assert not genere[0].isdigit()


class TestFusionArbres:
    """Versement des featureMember d'un arbre dans l'autre."""

    def _arbre(self, prefixe: str) -> ET.Element:
        """Arbre a trois featureMember dont un Metadata."""
        racine = ET.Element(f"{NS_GML}FeatureCollection")
        for nom in ("Metadata", "ReseauUtilite", "RPD_Aerien_Reco"):
            membre = ET.SubElement(racine, f"{NS_GML}featureMember")
            ET.SubElement(membre, f"{NS_RECOSTAR}{nom}").set(ATTRIBUT_ID, f"{prefixe}_{nom}")
        return racine

    def test_membres_verses(self):
        """Les featureMember du second arbre rejoignent le premier."""
        cible = self._arbre("a")
        nb_ajoutes, nb_ecartes = fusionner_arbres(cible, self._arbre("b"))
        assert (nb_ajoutes, nb_ecartes) == (2, 1)
        assert len(cible.findall(f"{NS_GML}featureMember")) == 5

    def test_metadata_du_second_ecarte(self):
        """Un seul Metadata subsiste, celui du premier fichier."""
        cible = self._arbre("a")
        fusionner_arbres(cible, self._arbre("b"))
        metadata = list(cible.iter(f"{NS_RECOSTAR}Metadata"))
        assert len(metadata) == 1
        assert metadata[0].get(ATTRIBUT_ID) == "a_Metadata"

    def test_reseaux_tous_conserves(self):
        """Les ReseauUtilite des deux fichiers sont conserves."""
        cible = self._arbre("a")
        fusionner_arbres(cible, self._arbre("b"))
        assert len(list(cible.iter(f"{NS_RECOSTAR}ReseauUtilite"))) == 2


class TestVersionSchema:
    """Lecture de la version de schema declaree."""

    def test_url_extraite(self):
        """La declaration associe un namespace a une URL : l'URL est retenue."""
        racine = ET.Element("racine")
        racine.set(
            "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation",
            "http://StaR-Elec.com https://exemple/Schema.xsd",
        )
        assert _version_schema(racine) == "https://exemple/Schema.xsd"

    def test_declaration_absente(self):
        """Sans schemaLocation, aucune version n'est deduite."""
        assert _version_schema(ET.Element("racine")) is None


class TestExecutionComplete:
    """Fusion de bout en bout, depuis les fichiers."""

    def test_projections_identiques(self, gml_a, gml_b, tmp_path):
        """Deux fichiers de meme projection sont fusionnes sans reprojection."""
        sortie = tmp_path / "fusion.gml"
        resultat = executer_fusion(str(gml_a), str(gml_b), chemin_sortie=str(sortie))
        assert resultat.succes
        assert resultat.epsg_sources == ["EPSG:2154", "EPSG:2154"]
        assert resultat.epsg_cible == "EPSG:2154"
        assert resultat.nb_reprojetes == 0

    def test_projection_du_premier_par_defaut(self, gml_a, gml_b_cc47, tmp_path):
        """Sans cible demandee, le premier fichier sert de reference."""
        sortie = tmp_path / "fusion.gml"
        resultat = executer_fusion(str(gml_a), str(gml_b_cc47), chemin_sortie=str(sortie))
        assert resultat.succes
        assert resultat.epsg_cible == "EPSG:2154"
        assert resultat.nb_reprojetes == 1

    def test_cible_explicite_reprojette_les_deux(self, gml_a, gml_b_cc47, tmp_path):
        """Une cible etrangere aux deux fichiers les reprojette tous les deux."""
        sortie = tmp_path / "fusion.gml"
        resultat = executer_fusion(str(gml_a), str(gml_b_cc47), epsg_cible="EPSG:4326", chemin_sortie=str(sortie))
        assert resultat.succes
        assert resultat.epsg_cible == "EPSG:4326"
        assert resultat.nb_reprojetes == 2

    def test_cible_en_urn_ogc(self, gml_a, gml_b, tmp_path):
        """La cible accepte la forme URN OGC."""
        resultat = executer_fusion(
            str(gml_a),
            str(gml_b),
            epsg_cible="urn:ogc:def:crs:EPSG::3947",
            chemin_sortie=str(tmp_path / "f.gml"),
        )
        assert resultat.succes
        assert resultat.epsg_cible == "EPSG:3947"

    def test_identifiants_uniques(self, gml_a, gml_b, tmp_path):
        """Le fichier produit ne porte aucun gml:id en double."""
        sortie = tmp_path / "fusion.gml"
        executer_fusion(str(gml_a), str(gml_b), chemin_sortie=str(sortie))
        identifiants = _identifiants(_racine(sortie))
        assert [nom for nom, nb in Counter(identifiants).items() if nb > 1] == []

    def test_references_resolues(self, gml_a, gml_b, tmp_path):
        """Chaque reseau reference existe bien dans le fichier fusionne."""
        sortie = tmp_path / "fusion.gml"
        executer_fusion(str(gml_a), str(gml_b), chemin_sortie=str(sortie))
        racine = _racine(sortie)
        identifiants = set(_identifiants(racine))
        references = {reference.get(ATTRIBUT_HREF) for reference in racine.iter(f"{NS_RECOSTAR}reseau")}
        assert references <= identifiants
        assert len(references) == 2

    def test_geometries_homologues_superposees(self, gml_a, gml_b_superposable, tmp_path):
        """Deux fichiers decrivant le meme terrain se superposent apres fusion."""
        sortie = tmp_path / "fusion.gml"
        executer_fusion(str(gml_a), str(gml_b_superposable), chemin_sortie=str(sortie))
        listes = [
            [float(valeur) for valeur in element.text.split()]
            for element in _racine(sortie).iter(f"{NS_GML}posList")
            if element.text
        ]
        assert len(listes) == 2
        assert max(abs(a - b) for a, b in zip(listes[0], listes[1], strict=True)) < 0.01

    def test_srs_aligne_sur_la_cible(self, gml_a, gml_b_cc47, tmp_path):
        """Toutes les geometries du fichier produit declarent la projection cible."""
        sortie = tmp_path / "fusion.gml"
        executer_fusion(str(gml_a), str(gml_b_cc47), chemin_sortie=str(sortie))
        srs = {element.get("srsName") for element in _racine(sortie).iter() if element.get("srsName")}
        assert srs == {"EPSG:2154"}

    def test_coordonnees_du_second_transformees(self, gml_a, gml_b_cc47, tmp_path):
        """Les coordonnees du fichier reprojete ne sont plus celles d'origine."""
        sortie = tmp_path / "fusion.gml"
        executer_fusion(str(gml_a), str(gml_b_cc47), chemin_sortie=str(sortie))
        listes = [element.text.split() for element in _racine(sortie).iter(f"{NS_GML}posList") if element.text]
        assert listes[0][:2] == ["650000", "6860000"]
        assert listes[1][:2] != ["650000", "6860000"]

    def test_metadata_unique_et_signale(self, gml_a, gml_b, tmp_path):
        """Le Metadata ecarte est signale dans le compte rendu."""
        sortie = tmp_path / "fusion.gml"
        resultat = executer_fusion(str(gml_a), str(gml_b), chemin_sortie=str(sortie))
        assert len(list(_racine(sortie).iter(f"{NS_RECOSTAR}Metadata"))) == 1
        assert any("Metadata du second fichier" in message for message in resultat.avertissements)

    def test_chemin_sortie_par_defaut(self, gml_a, gml_b):
        """Sans chemin de sortie, le premier fichier est suffixe."""
        resultat = executer_fusion(str(gml_a), str(gml_b))
        assert resultat.succes
        assert resultat.chemin_sortie.endswith("a_fusion.gml")

    @pytest.mark.parametrize("rang", [1, 2])
    def test_fichier_introuvable(self, gml_a, tmp_path, rang):
        """Un chemin invalide est rapporte, quel que soit son rang."""
        absent = str(tmp_path / "absent.gml")
        chemins = [absent, str(gml_a)] if rang == 1 else [str(gml_a), absent]
        resultat = executer_fusion(*chemins)
        assert not resultat.succes
        assert f"GML {rang} introuvable" in resultat.erreur

    def test_cible_non_reconnue(self, gml_a, gml_b):
        """Une cible hors format EPSG est refusee."""
        resultat = executer_fusion(str(gml_a), str(gml_b), epsg_cible="WGS84")
        assert not resultat.succes
        assert "non reconnue" in resultat.erreur

    def test_versions_de_schema_differentes(self, gml_a, gml_autre_version):
        """Deux versions de schema differentes interrompent la fusion."""
        resultat = executer_fusion(str(gml_a), str(gml_autre_version))
        assert not resultat.succes
        assert "Versions de schema differentes" in resultat.erreur

    def test_projection_introuvable(self, gml_a, tmp_path):
        """Un GML muet sur sa projection ne peut pas etre fusionne."""
        muet = tmp_path / "muet.gml"
        muet.write_text(
            '<gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2"/>',
            encoding="utf-8",
        )
        resultat = executer_fusion(str(gml_a), str(muet))
        assert not resultat.succes
        assert "Projection du GML 2 introuvable" in resultat.erreur

    def test_gml_illisible(self, gml_a, tmp_path):
        """Un fichier XML malforme est rapporte comme tel."""
        casse = tmp_path / "casse.gml"
        casse.write_text("<gml:FeatureCollection>", encoding="utf-8")
        resultat = executer_fusion(str(gml_a), str(casse))
        assert not resultat.succes
        assert "GML 2 illisible" in resultat.erreur


class TestResultatFusion:
    """Serialisation du compte rendu."""

    def test_succes_sans_cles_superflues(self):
        """Un resultat nominal n'expose ni erreur ni avertissement."""
        resultat = ResultatFusion()
        resultat.succes = True
        donnees = resultat.vers_dict()
        assert donnees["succes"] is True
        assert "erreur" not in donnees
        assert "avertissements" not in donnees

    def test_compteurs_exposes(self):
        """Les compteurs figurent toujours au compte rendu."""
        donnees = ResultatFusion().vers_dict()
        assert donnees["nb_reprojetes"] == 0
        assert donnees["nb_entites_ajoutees"] == 0
        assert donnees["nb_ids_remappes"] == 0

    def test_nom_de_sortie_derive(self, tmp_path):
        """Le nom par defaut suffixe le premier fichier."""
        entree = tmp_path / "reco.gml"
        assert _chemin_sortie_par_defaut(str(entree)) == str(tmp_path / "reco_fusion.gml")
