"""
Utilitaires de construction de fichiers GML pour les tests E110 / E111 / E113.
"""

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import (  # nosec B405
    Element,
    SubElement,
    tostring,
)

NS_GML = "http://www.opengis.net/gml/3.2"
NS_RECOSTAR = "http://StaR-Elec.com"
NS_XLINK = "http://www.w3.org/1999/xlink"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"

# URL canonique du XSD v1.1 (cf. PDF §[1]).
URL_XSD_V1_1 = "https://gitlab.com/StaR-Elec/StaR-Elec/-/raw/RecoStar-v1.1/RecoStaR/SchemaStarElecRecoStar.xsd"
SCHEMA_LOCATION_V1_1 = f"{NS_RECOSTAR} {URL_XSD_V1_1}"


def _tag_recostar(nom: str) -> str:
    """Tag qualifié RecoStar."""
    return f"{{{NS_RECOSTAR}}}{nom}"


def _tag_gml(nom: str) -> str:
    """Tag qualifié GML."""
    return f"{{{NS_GML}}}{nom}"


def creer_feature_member(type_rpd: str, gml_id: str, enfants: list[str]) -> Element:
    """Crée un élément featureMember avec un objet RPD et ses enfants (sans valeur)."""
    membre = Element(_tag_gml("featureMember"))
    rpd = SubElement(membre, _tag_recostar(type_rpd))
    rpd.set(_tag_gml("id"), gml_id)
    for nom in enfants:
        SubElement(rpd, _tag_recostar(nom))
    return membre


def creer_feature_member_avec_valeurs(
    type_rpd: str,
    gml_id: str,
    enfants_valeurs: list[tuple[str, str | None]],
) -> Element:
    """Crée un featureMember avec valeurs textuelles sur les enfants.

    Variante de creer_feature_member dédiée aux tests E111 (règles métier),
    qui dépendent des valeurs portées par les éléments (Statut, DomaineTension, etc.).

    Args :
        type_rpd        : Nom local du type RPD (sans namespace)
        gml_id          : Valeur de l'attribut gml:id
        enfants_valeurs : Liste de couples (nom_local, valeur_texte ou None)
    """
    membre = Element(_tag_gml("featureMember"))
    rpd = SubElement(membre, _tag_recostar(type_rpd))
    rpd.set(_tag_gml("id"), gml_id)
    for nom, valeur in enfants_valeurs:
        enfant = SubElement(rpd, _tag_recostar(nom))
        # None = élément présent mais sans valeur (cas pathologique testé en E111).
        if valeur is not None:
            enfant.text = valeur
    return membre


def creer_gml_complet(membres: list[Element]) -> bytes:
    """Crée un fichier GML complet (FeatureCollection) à partir d'une liste de membres."""
    racine = Element(_tag_gml("FeatureCollection"))
    for m in membres:
        racine.append(m)
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + tostring(racine, encoding="unicode").encode("utf-8")


# ---------------------------------------------------------------------------
# Helpers spécifiques au contrôle E113 (en-têtes et métadonnées)
# ---------------------------------------------------------------------------


def creer_metadata_conforme(gml_id: str = "metadata_001") -> Element:
    """Crée un featureMember contenant un Metadata avec tous les champs PDF §[3]."""
    return creer_feature_member_avec_valeurs(
        "Metadata",
        gml_id,
        [
            ("Datecreation", "2026-05-25"),
            ("Logiciel", "TestSuite 1.0"),
            ("Producteur", "EntrepriseTest"),
            ("Responsable", "MaitreOuvrageTest"),
            ("SRS", "EPSG:2154"),
        ],
    )


def creer_reseau_utilite_conforme(gml_id: str = "reseau_001") -> Element:
    """Crée un featureMember contenant un ReseauUtilite conforme PDF §9."""
    return creer_feature_member_avec_valeurs(
        "ReseauUtilite",
        gml_id,
        [
            ("Mention", "Récolement informatisé"),
            ("Nom", "AFFAIRE-001"),
            ("Responsable", "Enedis"),
            ("Theme", "ELECTRD"),
        ],
    )


def serialiser_gml_avec_entete(
    membres: list[Element],
    *,
    inclure_namespaces: bool = True,
    inclure_schema_location: bool = True,
    uri_recostar_override: str | None = None,
    schema_location_override: str | None = None,
    prefixe_recostar: str = "RecoStaR",
) -> bytes:
    """Sérialise un GML avec un en-tête contrôlable (pour tester E113).

    Construit la chaîne XML « à la main » plutôt que via Element.tostring car
    xml.etree ne permet pas d'imposer la casse exacte d'un préfixe de namespace
    (« RecoStaR » vs « recostar »), ce qui est précisément ce que E113 doit
    pouvoir détecter. Tous les paramètres ont des valeurs par défaut conformes
    à la spec V1.1 : aucun test n'a besoin de tout repréciser.
    """
    uri_recostar = uri_recostar_override or NS_RECOSTAR
    parties: list[str] = ['<?xml version="1.0" encoding="utf-8"?>']
    declarations: list[str] = [f'xmlns:gml="{NS_GML}"']
    if inclure_namespaces:
        declarations.extend(
            [
                f'xmlns:{prefixe_recostar}="{uri_recostar}"',
                f'xmlns:xlink="{NS_XLINK}"',
                f'xmlns:xsi="{NS_XSI}"',
            ]
        )
    if inclure_schema_location:
        valeur_sl = schema_location_override if schema_location_override is not None else SCHEMA_LOCATION_V1_1
        declarations.append(f'xsi:schemaLocation="{valeur_sl}"')

    parties.append(f"<gml:FeatureCollection {' '.join(declarations)}>")
    for membre in membres:
        parties.append(tostring(membre, encoding="unicode"))
    parties.append("</gml:FeatureCollection>")
    return "\n".join(parties).encode("utf-8")
