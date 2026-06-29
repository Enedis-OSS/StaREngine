"""
Tests unitaires du module controle_e112.
Couvre la catégorisation des erreurs lxml, la validation XSD native et la
génération du rapport JSON.

Stratégie : un XSD synthétique minimal (sans imports externes) est compilé
à la session pour exercer chaque branche du validateur sans dépendre du
réseau ni du XSD RecoStaR réel.
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from controle_e112 import (
    CODE_AUTRE,
    CODE_ELEMENT_REQUIS_MANQUANT,
    CODE_STRUCTURE_INVALIDE,
    CODE_VALEUR_HORS_ENUMERATION,
    CODE_VALEUR_MOTIF_INVALIDE,
    CODE_VALEUR_TYPE_INVALIDE,
    CODE_XML_MALFORME,
    CODE_XSD_NON_COMPILABLE,
    ErreurXsd,
    ValidateurXsd,
    _categoriser_type_erreur,
    _construire_rapport,
    _ResolveurXsdLocal,
    _resoudre_chemin_sortie,
    generer_rapport,
)

# ---------------------------------------------------------------------------
# XSD synthétique utilisé par la plupart des tests
# ---------------------------------------------------------------------------

# Schéma minimaliste : pas d'import → pas de réseau requis. Couvre les cas
# pertinents pour exercer la taxonomie E112 (enum, type, motif, manquant,
# extracontent).
_XSD_TEST = """<?xml version="1.0" encoding="utf-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="http://test.local"
           xmlns:t="http://test.local"
           elementFormDefault="qualified">

  <xs:simpleType name="StatutType">
    <xs:restriction base="xs:string">
      <xs:enumeration value="Actif"/>
      <xs:enumeration value="Inactif"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:simpleType name="CodeType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[A-Z]{3}-[0-9]{3}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="Racine">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="Nombre" type="xs:integer"/>
        <xs:element name="Statut" type="t:StatutType"/>
        <xs:element name="Code" type="t:CodeType" minOccurs="0"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""


@pytest.fixture(scope="session")
def chemin_xsd_test(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Écrit le XSD synthétique sur disque, partagé pour toute la session."""
    chemin = tmp_path_factory.mktemp("xsd") / "test.xsd"
    chemin.write_text(_XSD_TEST, encoding="utf-8")
    return chemin


@pytest.fixture(scope="session")
def validateur(chemin_xsd_test: Path) -> ValidateurXsd:
    """Validateur compilé une fois pour toute la session (compilation coûteuse)."""
    return ValidateurXsd(chemin_xsd_test)


@pytest.fixture
def ecrire_gml(tmp_path: Path) -> Callable[[str], Path]:
    """Factory : écrit un contenu XML dans un fichier temporaire et le retourne."""

    def factory(contenu: str) -> Path:
        chemin = tmp_path / "test.gml"
        chemin.write_text(contenu, encoding="utf-8")
        return chemin

    return factory


def _racine_valide() -> str:
    """Contenu XML conforme au XSD synthétique."""
    return """<?xml version="1.0" encoding="utf-8"?>
<Racine xmlns="http://test.local">
  <Nombre>42</Nombre>
  <Statut>Actif</Statut>
</Racine>
"""


# ---------------------------------------------------------------------------
# Tests de la catégorisation des erreurs lxml
# ---------------------------------------------------------------------------


class TestCategoriserTypeErreur:
    """Mapping type_name lxml → code français."""

    def test_enumeration_detectee(self):
        assert _categoriser_type_erreur("SCHEMAV_CVC_ENUMERATION_VALID") == CODE_VALEUR_HORS_ENUMERATION

    def test_pattern_detecte(self):
        assert _categoriser_type_erreur("SCHEMAV_CVC_PATTERN_VALID") == CODE_VALEUR_MOTIF_INVALIDE

    def test_datatype_detecte(self):
        assert _categoriser_type_erreur("SCHEMAV_CVC_DATATYPE_VALID_1_2_1") == CODE_VALEUR_TYPE_INVALIDE

    def test_missing_detecte(self):
        assert _categoriser_type_erreur("SCHEMAV_MISSING") == CODE_ELEMENT_REQUIS_MANQUANT

    def test_extracontent_detecte_comme_structure(self):
        assert _categoriser_type_erreur("SCHEMAV_EXTRACONTENT") == CODE_STRUCTURE_INVALIDE

    def test_elt_detecte_comme_structure(self):
        """Toute erreur de validation d'élément (CVC_ELT_*) est classée structure."""
        assert _categoriser_type_erreur("SCHEMAV_CVC_ELT_5_1_1") == CODE_STRUCTURE_INVALIDE

    def test_complex_type_avant_datatype_pour_complex(self):
        """COMPLEX_TYPE est tagué structure ; aucune collision avec VALUE."""
        assert _categoriser_type_erreur("SCHEMAV_CVC_COMPLEX_TYPE_2_4") == CODE_STRUCTURE_INVALIDE

    def test_attrunknown_prend_le_pas_sur_attr(self):
        """L'ordre des règles place ATTRUNKNOWN avant ATTR (spécificité)."""
        from controle_e112 import CODE_ATTRIBUT_INCONNU

        assert _categoriser_type_erreur("SCHEMAV_CVC_ATTRUNKNOWN") == CODE_ATTRIBUT_INCONNU

    def test_none_retourne_autre(self):
        assert _categoriser_type_erreur(None) == CODE_AUTRE

    def test_chaine_vide_retourne_autre(self):
        assert _categoriser_type_erreur("") == CODE_AUTRE

    def test_type_inconnu_retombe_sur_autre(self):
        assert _categoriser_type_erreur("SOMETHING_TOTALLY_NEW") == CODE_AUTRE


# ---------------------------------------------------------------------------
# Tests d'ErreurXsd
# ---------------------------------------------------------------------------


class TestErreurXsd:
    """Comportement de la classe d'erreur."""

    def test_vers_dict_champs_complets(self):
        err = ErreurXsd(
            code="CODE_X",
            ligne=10,
            colonne=5,
            xpath="/Racine/Statut",
            type_lxml="SCHEMAV_CVC_ENUMERATION_VALID",
            message="enum violation",
        )
        attendus = {
            "code",
            "severite",
            "ligne",
            "colonne",
            "xpath",
            "type_lxml",
            "message",
        }
        assert set(err.vers_dict().keys()) == attendus

    def test_vers_dict_valeurs_correctes(self):
        err = ErreurXsd("C", 1, 2, "/x", "T", "M")
        d = err.vers_dict()
        assert d["code"] == "C"
        assert d["ligne"] == 1
        assert d["colonne"] == 2
        assert d["xpath"] == "/x"
        assert d["type_lxml"] == "T"
        assert d["message"] == "M"

    def test_optionnels_acceptent_none(self):
        err = ErreurXsd("C", None, None, None, None, "msg")
        d = err.vers_dict()
        assert d["ligne"] is None
        assert d["colonne"] is None
        assert d["xpath"] is None
        assert d["type_lxml"] is None

    def test_slots_interdit_attributs_dynamiques(self):
        err = ErreurXsd("C", 1, 1, "/x", "T", "M")
        with pytest.raises(AttributeError):
            err.attribut_inconnu = "x"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tests du ValidateurXsd : compilation
# ---------------------------------------------------------------------------


class TestCompilation:
    """Compilation du XSD."""

    def test_compilation_xsd_valide(self, chemin_xsd_test: Path):
        """Un XSD valide compile sans erreur."""
        validateur = ValidateurXsd(chemin_xsd_test)
        assert validateur.chemin_xsd == chemin_xsd_test

    def test_compilation_xsd_introuvable(self, tmp_path: Path):
        """Un XSD inexistant lève RuntimeError clair."""
        with pytest.raises(RuntimeError, match="Compilation du XSD"):
            ValidateurXsd(tmp_path / "absent.xsd")

    def test_compilation_xsd_malforme(self, tmp_path: Path):
        """Un XSD syntaxiquement invalide lève RuntimeError."""
        chemin = tmp_path / "mauvais.xsd"
        chemin.write_text("<not-an-xsd/>", encoding="utf-8")
        with pytest.raises(RuntimeError, match="Compilation du XSD"):
            ValidateurXsd(chemin)


# ---------------------------------------------------------------------------
# Tests du ValidateurXsd : cas valides
# ---------------------------------------------------------------------------


class TestValidationConforme:
    """Cas nominaux : aucun message d'erreur attendu."""

    def test_xml_conforme_aucune_erreur(self, validateur: ValidateurXsd, ecrire_gml):
        chemin = ecrire_gml(_racine_valide())
        assert validateur.valider(chemin) == []

    def test_element_optionnel_present_aucune_erreur(self, validateur: ValidateurXsd, ecrire_gml):
        """Le champ optionnel `Code` peut être présent s'il respecte le motif."""
        contenu = """<?xml version="1.0" encoding="utf-8"?>
<Racine xmlns="http://test.local">
  <Nombre>1</Nombre>
  <Statut>Inactif</Statut>
  <Code>ABC-123</Code>
</Racine>
"""
        assert validateur.valider(ecrire_gml(contenu)) == []


# ---------------------------------------------------------------------------
# Tests du ValidateurXsd : cas invalides (un type de violation par classe)
# ---------------------------------------------------------------------------


class TestValidationEnumeration:
    """Détection d'une valeur hors énumération."""

    def test_statut_hors_enum_detecte(self, validateur: ValidateurXsd, ecrire_gml):
        contenu = """<?xml version="1.0" encoding="utf-8"?>
<Racine xmlns="http://test.local">
  <Nombre>1</Nombre>
  <Statut>ValeurInvalide</Statut>
</Racine>
"""
        erreurs = validateur.valider(ecrire_gml(contenu))
        assert any(e.code == CODE_VALEUR_HORS_ENUMERATION for e in erreurs)


class TestValidationType:
    """Détection d'une valeur de type incompatible."""

    def test_integer_attend_non_numerique(self, validateur: ValidateurXsd, ecrire_gml):
        contenu = """<?xml version="1.0" encoding="utf-8"?>
<Racine xmlns="http://test.local">
  <Nombre>pas_un_entier</Nombre>
  <Statut>Actif</Statut>
</Racine>
"""
        erreurs = validateur.valider(ecrire_gml(contenu))
        assert any(e.code == CODE_VALEUR_TYPE_INVALIDE for e in erreurs)


class TestValidationMotif:
    """Détection d'une chaîne ne respectant pas un xs:pattern."""

    def test_code_ne_respecte_pas_le_motif(self, validateur: ValidateurXsd, ecrire_gml):
        contenu = """<?xml version="1.0" encoding="utf-8"?>
<Racine xmlns="http://test.local">
  <Nombre>1</Nombre>
  <Statut>Actif</Statut>
  <Code>mauvais_format</Code>
</Racine>
"""
        erreurs = validateur.valider(ecrire_gml(contenu))
        assert any(e.code == CODE_VALEUR_MOTIF_INVALIDE for e in erreurs)


class TestValidationElementManquant:
    """Détection d'un élément requis absent."""

    def test_statut_manquant(self, validateur: ValidateurXsd, ecrire_gml):
        contenu = """<?xml version="1.0" encoding="utf-8"?>
<Racine xmlns="http://test.local">
  <Nombre>1</Nombre>
</Racine>
"""
        erreurs = validateur.valider(ecrire_gml(contenu))
        # Selon lxml, l'élément manquant est signalé via SCHEMAV_MISSING
        # OU via la famille CVC_COMPLEX_TYPE (structure invalide).
        codes = {e.code for e in erreurs}
        assert codes & {CODE_ELEMENT_REQUIS_MANQUANT, CODE_STRUCTURE_INVALIDE}


class TestValidationStructure:
    """Détection d'un contenu surnuméraire ou hors ordre."""

    def test_element_etranger_detecte(self, validateur: ValidateurXsd, ecrire_gml):
        contenu = """<?xml version="1.0" encoding="utf-8"?>
<Racine xmlns="http://test.local">
  <Nombre>1</Nombre>
  <Statut>Actif</Statut>
  <ElementInconnu>x</ElementInconnu>
</Racine>
"""
        erreurs = validateur.valider(ecrire_gml(contenu))
        assert any(e.code == CODE_STRUCTURE_INVALIDE for e in erreurs)


class TestValidationXmlMalforme:
    """Cas particulier : XML non bien formé en entrée."""

    def test_xml_invalide_renvoie_xml_malforme(self, validateur: ValidateurXsd, ecrire_gml):
        contenu = "<Racine><Statut>Actif</Racine>"  # balise non fermée
        erreurs = validateur.valider(ecrire_gml(contenu))
        assert len(erreurs) == 1
        assert erreurs[0].code == CODE_XML_MALFORME


class TestErreursMultiples:
    """Plusieurs violations dans un même fichier remontent toutes."""

    def test_deux_violations_distinctes(self, validateur: ValidateurXsd, ecrire_gml):
        contenu = """<?xml version="1.0" encoding="utf-8"?>
<Racine xmlns="http://test.local">
  <Nombre>pas_un_entier</Nombre>
  <Statut>ValeurInvalide</Statut>
</Racine>
"""
        erreurs = validateur.valider(ecrire_gml(contenu))
        codes = {e.code for e in erreurs}
        assert CODE_VALEUR_TYPE_INVALIDE in codes
        assert CODE_VALEUR_HORS_ENUMERATION in codes


# ---------------------------------------------------------------------------
# Tests de la génération du rapport JSON
# ---------------------------------------------------------------------------


class TestGenererRapport:
    """Sérialisation du rapport JSON."""

    @pytest.fixture
    def chemin_gml_vide(self, tmp_path: Path) -> Path:
        chemin = tmp_path / "vide.gml"
        chemin.touch()
        return chemin

    def _erreur_test(self) -> ErreurXsd:
        return ErreurXsd(
            code=CODE_VALEUR_HORS_ENUMERATION,
            ligne=10,
            colonne=5,
            xpath="/Racine/Statut",
            type_lxml="SCHEMAV_CVC_ENUMERATION_VALID",
            message="violation",
        )

    def test_fichier_cree(self, chemin_gml_vide, chemin_xsd_test):
        chemin = generer_rapport(chemin_gml_vide, chemin_xsd_test, [], chemin_gml_vide.parent)
        assert chemin.exists()
        assert chemin.suffix == ".json"

    def test_nom_suffixe_e112(self, chemin_gml_vide, chemin_xsd_test):
        chemin = generer_rapport(chemin_gml_vide, chemin_xsd_test, [], chemin_gml_vide.parent)
        assert "_controle_e112" in chemin.name

    def test_rapport_conforme_si_aucune_erreur(self, chemin_gml_vide, chemin_xsd_test):
        chemin = generer_rapport(chemin_gml_vide, chemin_xsd_test, [], chemin_gml_vide.parent)
        with open(chemin, encoding="utf-8") as f:
            rapport = json.load(f)
        assert rapport["conformite"] == "CONFORME"
        assert rapport["nb_erreurs"] == 0

    def test_rapport_non_conforme_avec_erreurs(self, chemin_gml_vide, chemin_xsd_test):
        chemin = generer_rapport(
            chemin_gml_vide,
            chemin_xsd_test,
            [self._erreur_test()],
            chemin_gml_vide.parent,
        )
        with open(chemin, encoding="utf-8") as f:
            rapport = json.load(f)
        assert rapport["conformite"] == "NON_CONFORME"
        assert rapport["nb_erreurs"] == 1

    def test_champ_type_controle(self, chemin_gml_vide, chemin_xsd_test):
        rapport = _construire_rapport(chemin_gml_vide, chemin_xsd_test, [])
        assert rapport["type_controle"] == "E112_XSD_NATIF"

    def test_champs_attendus_presents(self, chemin_gml_vide, chemin_xsd_test):
        rapport = _construire_rapport(chemin_gml_vide, chemin_xsd_test, [])
        attendus = {
            "fichier",
            "xsd",
            "date_controle",
            "niveau",
            "type_controle",
            "version_controlee",
            "conformite",
            "nb_erreurs",
            "nb_par_severite",
            "erreurs",
        }
        assert set(rapport.keys()) == attendus

    def test_xsd_reference_dans_rapport(self, chemin_gml_vide, chemin_xsd_test):
        """Le rapport documente le XSD utilisé pour la validation."""
        rapport = _construire_rapport(chemin_gml_vide, chemin_xsd_test, [])
        assert rapport["xsd"] == str(chemin_xsd_test.resolve())

    def test_erreurs_serialisees(self, chemin_gml_vide, chemin_xsd_test):
        chemin = generer_rapport(
            chemin_gml_vide,
            chemin_xsd_test,
            [self._erreur_test()],
            chemin_gml_vide.parent,
        )
        with open(chemin, encoding="utf-8") as f:
            rapport = json.load(f)
        err = rapport["erreurs"][0]
        assert err["code"] == CODE_VALEUR_HORS_ENUMERATION
        assert err["ligne"] == 10
        assert err["xpath"] == "/Racine/Statut"

    def test_chemin_sans_repertoire_sortie(self, tmp_path: Path):
        chemin_gml = tmp_path / "fichier.gml"
        chemin = _resoudre_chemin_sortie(chemin_gml, None)
        assert chemin.parent == chemin_gml.parent

    def test_chemin_avec_repertoire_sortie(self, tmp_path: Path):
        chemin_gml = tmp_path / "fichier.gml"
        dossier = tmp_path / "out"
        dossier.mkdir()
        chemin = _resoudre_chemin_sortie(chemin_gml, dossier)
        assert chemin.parent == dossier


# ---------------------------------------------------------------------------
# Code XSD_NON_COMPILABLE : couverture pour la traçabilité
# ---------------------------------------------------------------------------


class TestResolveurXsdLocal:
    """Mapping URI HTTP → fichier local via _ResolveurXsdLocal."""

    @pytest.fixture
    def cache_dir(self, tmp_path: Path) -> Path:
        """Petit cache synthétique reproduisant la convention host/path."""
        racine = tmp_path / "cache"
        chemin_xsd = racine / "schemas.opengis.net" / "gml" / "3.2.1" / "gml.xsd"
        chemin_xsd.parent.mkdir(parents=True)
        chemin_xsd.write_text("<xs:schema/>", encoding="utf-8")
        return racine

    def test_uri_cachee_resolue_localement(self, cache_dir: Path):
        """Une URI dont la copie locale existe doit être servie depuis le cache."""
        resolveur = _ResolveurXsdLocal(cache_dir)
        resultat = resolveur.resolve("http://schemas.opengis.net/gml/3.2.1/gml.xsd", None, None)
        # resolve_filename retourne un objet opaque non-None si succès.
        assert resultat is not None

    def test_uri_non_cachee_retourne_none(self, cache_dir: Path):
        """Une URI absente du cache retourne None (fallback réseau lxml)."""
        resolveur = _ResolveurXsdLocal(cache_dir)
        assert resolveur.resolve("http://schemas.opengis.net/inexistant.xsd", None, None) is None

    def test_uri_non_http_ignoree(self, cache_dir: Path):
        """Les URIs file:// ou autres non-http sont déférées à lxml."""
        resolveur = _ResolveurXsdLocal(cache_dir)
        assert resolveur.resolve("file:///tmp/x.xsd", None, None) is None

    def test_url_none_retourne_none(self, cache_dir: Path):
        """Une URL None (cas possible selon le contexte lxml) ne lève pas."""
        resolveur = _ResolveurXsdLocal(cache_dir)
        assert resolveur.resolve(None, None, None) is None

    def test_url_vide_retourne_none(self, cache_dir: Path):
        resolveur = _ResolveurXsdLocal(cache_dir)
        assert resolveur.resolve("", None, None) is None


class TestValidateurCacheEtOffline:
    """Intégration cache + mode offline sur le validateur."""

    def test_compilation_sans_cache_existant(self, chemin_xsd_test: Path, tmp_path: Path):
        """Si le cache_dir n'existe pas, le validateur compile quand même
        (le XSD synthétique n'a aucun import externe à résoudre)."""
        cache_inexistant = tmp_path / "cache_absent"
        validateur = ValidateurXsd(chemin_xsd_test, cache_dir=cache_inexistant)
        assert validateur.chemin_xsd == chemin_xsd_test

    def test_compilation_offline_strict_sans_imports(self, chemin_xsd_test: Path):
        """mode_offline=True compile correctement un XSD sans dépendance externe."""
        validateur = ValidateurXsd(chemin_xsd_test, mode_offline=True)
        assert validateur.chemin_xsd == chemin_xsd_test


class TestCodeXsdNonCompilable:
    """Le code CODE_XSD_NON_COMPILABLE est utilisé par le CLI en mode dégradé."""

    def test_code_est_distinct(self):
        """Code différent des autres pour permettre un filtre dédié côté rapport."""
        autres = {
            CODE_VALEUR_HORS_ENUMERATION,
            CODE_VALEUR_TYPE_INVALIDE,
            CODE_VALEUR_MOTIF_INVALIDE,
            CODE_ELEMENT_REQUIS_MANQUANT,
            CODE_STRUCTURE_INVALIDE,
            CODE_XML_MALFORME,
            CODE_AUTRE,
        }
        assert CODE_XSD_NON_COMPILABLE not in autres
