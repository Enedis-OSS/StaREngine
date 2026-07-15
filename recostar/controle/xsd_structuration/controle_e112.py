#!/usr/bin/env python3
"""
Outil de contrôle E112 : validation XSD native d'un fichier GML RecoStaR.

Complémentaire de :
- E110 (ordre des éléments des objets RPD, réimplémentation Python)
- E111 (règles métier conditionnelles non exprimables en XSD)
- E113 (en-tête, namespaces, métadonnées, unicité gml:id)

E112 délègue toute la vérification structurelle et typée à lxml.etree.XMLSchema
en s'appuyant sur le XSD officiel SchemaStarElecRecoStar.xsd. Les erreurs natives
de lxml (en anglais, typées par des codes SCHEMAV_*) sont reclassées dans une
taxonomie française stable, puis sérialisées dans le format de rapport JSON
homogène à E110/E111/E113.

Dépendance : lxml (>= 4.9). Le XSD RecoStaR importe gml.xsd (OpenGIS) :
la compilation du schéma exige donc un accès réseau au premier appel.

Entrée  : Fichier GML RecoStaR à contrôler
Sortie  : Fichier JSON listant les erreurs détectées par le validateur XSD

Usage :
    python controle_e112.py <fichier.gml> [--xsd <chemin.xsd>] [--output-dir <repertoire>]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import lxml.etree as ET  # type: ignore[import-untyped]
from cli_version import ajouter_argument_version, resoudre_profil_cli
from versions import VERSION_DEFAUT

# ---------------------------------------------------------------------------
# Codes d'erreur de la taxonomie française E112
# ---------------------------------------------------------------------------

# Ces codes encapsulent les SCHEMAV_* de lxml en familles parlantes.
# Un nouveau code ⟶ ajouter une entrée dans _REGLES_CATEGORISATION ci-dessous.
CODE_VALEUR_HORS_ENUMERATION = "VALEUR_HORS_ENUMERATION"
CODE_VALEUR_MOTIF_INVALIDE = "VALEUR_MOTIF_INVALIDE"
CODE_VALEUR_TYPE_INVALIDE = "VALEUR_TYPE_INVALIDE"
CODE_CONTRAINTE_FACETTE_VIOLEE = "CONTRAINTE_FACETTE_VIOLEE"
CODE_ELEMENT_REQUIS_MANQUANT = "ELEMENT_REQUIS_MANQUANT"
CODE_ATTRIBUT_INCONNU = "ATTRIBUT_INCONNU"
CODE_ATTRIBUT_INVALIDE = "ATTRIBUT_INVALIDE"
CODE_RACINE_MANQUANTE = "RACINE_MANQUANTE"
CODE_TYPE_ABSTRAIT_UTILISE = "TYPE_ABSTRAIT_UTILISE"
CODE_STRUCTURE_INVALIDE = "STRUCTURE_INVALIDE"
CODE_AUTRE = "AUTRE"

# Codes liés au parsing du fichier GML lui-même (avant validation XSD).
CODE_XML_MALFORME = "XML_MALFORME"
CODE_XSD_NON_COMPILABLE = "XSD_NON_COMPILABLE"


# ---------------------------------------------------------------------------
# Mapping type_name lxml → code français
# ---------------------------------------------------------------------------

# Tuple immuable de couples (motif, code). Itéré dans l'ordre : la première
# occurrence du motif dans le type_name lxml décide du code.
# Ordre = spécificité décroissante : ATTRUNKNOWN doit précéder ATTR, sans quoi
# tout type_name contenant ATTR matcherait ATTRINVALIDE en priorité.
_REGLES_CATEGORISATION: tuple[tuple[str, str], ...] = (
    ("ENUMERATION", CODE_VALEUR_HORS_ENUMERATION),
    ("PATTERN", CODE_VALEUR_MOTIF_INVALIDE),
    ("DATATYPE", CODE_VALEUR_TYPE_INVALIDE),
    ("VALUE", CODE_VALEUR_TYPE_INVALIDE),
    ("LENGTH", CODE_CONTRAINTE_FACETTE_VIOLEE),
    ("INCLUSIVE", CODE_CONTRAINTE_FACETTE_VIOLEE),
    ("EXCLUSIVE", CODE_CONTRAINTE_FACETTE_VIOLEE),
    ("DIGITS", CODE_CONTRAINTE_FACETTE_VIOLEE),
    ("FACET", CODE_CONTRAINTE_FACETTE_VIOLEE),
    ("MISSING", CODE_ELEMENT_REQUIS_MANQUANT),
    ("ATTRUNKNOWN", CODE_ATTRIBUT_INCONNU),
    ("ATTRINVALID", CODE_ATTRIBUT_INVALIDE),
    ("ATTR", CODE_ATTRIBUT_INVALIDE),
    ("NOROOT", CODE_RACINE_MANQUANTE),
    ("ABSTRACT", CODE_TYPE_ABSTRAIT_UTILISE),
    ("EXTRACONTENT", CODE_STRUCTURE_INVALIDE),
    ("ELEMCONT", CODE_STRUCTURE_INVALIDE),
    ("WRONGELEM", CODE_STRUCTURE_INVALIDE),
    ("ELT", CODE_STRUCTURE_INVALIDE),
    ("COMPLEX_TYPE", CODE_STRUCTURE_INVALIDE),
    ("ELEMENT", CODE_STRUCTURE_INVALIDE),
)


def _categoriser_type_erreur(type_lxml: str | None) -> str:
    """Mappe le type_name lxml vers un code français de la taxonomie E112.

    Recherche linéaire sur une vingtaine d'entrées : O(1) en pratique.
    Le `in` est une opération C-rapide ; cette fonction est volontairement
    sans branchement complexe pour rester très en deçà de la complexité 15.
    """
    if not type_lxml:
        return CODE_AUTRE
    for motif, code in _REGLES_CATEGORISATION:
        if motif in type_lxml:
            return code
    return CODE_AUTRE


# ---------------------------------------------------------------------------
# Chemin XSD par défaut : XSD livré dans le module conversion_V1_1
# ---------------------------------------------------------------------------

# Chemin résolu relativement à ce fichier pour permettre l'exécution depuis
# n'importe quel répertoire courant sans devoir paramétrer le PYTHONPATH.
_CHEMIN_XSD_DEFAUT: Path = (
    Path(__file__).resolve().parent.parent.parent
    / "conversion"
    / "conversion_V1_1"
    / "xsd"
    / "SchemaStarElecRecoStar.xsd"
)

# Cache local des XSD externes (GML 3.2.1, GML 3.3/exr, ISO 19139, XLink, XML)
# importés par SchemaStarElecRecoStar.xsd. Bootstrap unique via le script
# `bootstrap_xsd.py` ; permet une compilation 100% offline du XSD RecoStaR.
# Convention : l'arborescence reproduit l'URL (host/path) pour rendre le
# mapping URI → fichier trivial dans _ResolveurXsdLocal.
_CHEMIN_CACHE_DEFAUT: Path = _CHEMIN_XSD_DEFAUT.parent / "cache"


# ---------------------------------------------------------------------------
# Résolveur XSD : URI HTTP → copie locale
# ---------------------------------------------------------------------------


class _ResolveurXsdLocal(ET.Resolver):
    """Mappe les URI HTTP de schémas externes vers leurs copies locales.

    Pour un URI 'http://schemas.opengis.net/gml/3.2.1/gml.xsd', on cherche
    '<cache>/schemas.opengis.net/gml/3.2.1/gml.xsd'. Si trouvé, on le sert ;
    sinon on retourne None et lxml retombe sur sa résolution par défaut
    (réseau, sauf si `no_network=True` a été passé au parser).

    Ce fallback gracieux permet trois modes d'utilisation :
    - cache complet + no_network : 100% offline déterministe
    - cache partiel + réseau autorisé : économie de bande passante, sûr
    - pas de cache + réseau : équivalent au comportement lxml par défaut
    """

    def __init__(self, cache_dir: Path) -> None:
        super().__init__()
        self._cache_dir = cache_dir

    # Signature imposée par lxml, qui appelle resolve() positionnellement :
    # l'identifiant public est inutilisé ici mais ne peut pas être retiré.
    def resolve(self, url, _public_id, context):  # type: ignore[override]
        if not url or not url.startswith("http"):
            return None
        parsed = urlparse(url)
        # Le mapping suit l'arborescence du téléchargeur ; pas de table.
        local = self._cache_dir / parsed.netloc / parsed.path.lstrip("/")
        if local.is_file():
            return self.resolve_filename(str(local), context)
        return None


# ---------------------------------------------------------------------------
# Type d'erreur E112
# ---------------------------------------------------------------------------


class ErreurXsd:
    """Erreur de validation XSD remontée par lxml, reclassée taxonomie E112."""

    # __slots__ : économie mémoire significative quand le validateur produit
    # de nombreuses erreurs sur un gros fichier non conforme.
    __slots__ = (
        "code",
        "ligne",
        "colonne",
        "xpath",
        "type_lxml",
        "message",
    )

    # Sévérité fixe : une non-conformité XSD est toujours une erreur.
    # Attribut de classe pour homogénéiser le rapport JSON avec E114.
    severite = "ERREUR"

    def __init__(
        self,
        code: str,
        ligne: int | None,
        colonne: int | None,
        xpath: str | None,
        type_lxml: str | None,
        message: str,
    ) -> None:
        self.code = code
        self.ligne = ligne
        self.colonne = colonne
        self.xpath = xpath
        self.type_lxml = type_lxml
        self.message = message

    def vers_dict(self) -> dict:
        """Sérialise l'erreur en dictionnaire pour le rapport JSON."""
        return {
            "code": self.code,
            "severite": self.severite,
            "ligne": self.ligne,
            "colonne": self.colonne,
            "xpath": self.xpath,
            "type_lxml": self.type_lxml,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Conversion d'une entrée du error_log lxml en ErreurXsd
# ---------------------------------------------------------------------------


def _convertir_entree_lxml(entree) -> ErreurXsd:
    """Convertit une _LogEntry lxml en ErreurXsd taxonomie E112.

    Fonction libre (non-méthode) : aucune dépendance à l'état du validateur,
    rend le test unitaire trivial.
    """
    # Les attributs lxml manquants peuvent valoir None ou chaîne vide selon
    # les versions : on normalise systématiquement.
    type_lxml = getattr(entree, "type_name", None) or None
    return ErreurXsd(
        code=_categoriser_type_erreur(type_lxml),
        ligne=getattr(entree, "line", None) or None,
        colonne=getattr(entree, "column", None) or None,
        xpath=getattr(entree, "path", None) or None,
        type_lxml=type_lxml,
        message=getattr(entree, "message", "") or "",
    )


# ---------------------------------------------------------------------------
# Validateur XSD
# ---------------------------------------------------------------------------


class ValidateurXsd:
    """Encapsule la compilation du XSD et la validation de fichiers GML.

    Le schéma est compilé une seule fois à l'instanciation : le coût
    (téléchargement gml.xsd, parsing) est amorti sur les validations
    successives.
    """

    __slots__ = ("chemin_xsd", "_schema")

    def __init__(
        self,
        chemin_xsd: Path,
        cache_dir: Path | None = None,
        mode_offline: bool = False,
    ) -> None:
        """Compile le XSD passé en paramètre.

        Args :
            chemin_xsd   : Chemin du fichier XSD à compiler.
            cache_dir    : Répertoire des copies locales des XSD externes.
                           Par défaut, recherché à côté du XSD dans 'cache/'.
                           S'il n'existe pas, le résolveur n'est pas activé
                           et lxml utilisera le réseau pour les imports.
            mode_offline : Si True, désactive complètement l'accès réseau du
                           parser (équivalent xmlparser no_network=True). La
                           compilation échoue alors si une dépendance manque
                           dans le cache.

        Lève RuntimeError si la compilation échoue (XSD invalide, indisponible,
        ou imports externes non résolvables). Le message d'origine lxml est
        conservé pour aider au diagnostic.
        """
        self.chemin_xsd = chemin_xsd
        cache = cache_dir if cache_dir is not None else _CHEMIN_CACHE_DEFAUT

        # Parser dédié à la compilation du XSD : on y attache le résolveur
        # local si le cache existe. lxml propage ce parser aux imports xs:import.
        # Durcissement : resolve_entities=False et no_network=True neutralisent
        # les attaques XXE et toute résolution réseau d'entités/DTD externes.
        # Les imports xs:import sont résolus via _ResolveurXsdLocal (cache local).
        # Le paramètre mode_offline est conservé pour compatibilité d'API mais
        # n'a plus d'effet : le réseau est toujours désactivé.
        del mode_offline
        parser = ET.XMLParser(
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
        )
        if cache.is_dir():
            parser.resolvers.add(_ResolveurXsdLocal(cache))

        try:
            arbre_xsd = ET.parse(str(chemin_xsd), parser)
            self._schema = ET.XMLSchema(arbre_xsd)
        except (ET.XMLSchemaParseError, ET.XMLSyntaxError, OSError) as exc:
            raise RuntimeError(f"Compilation du XSD '{chemin_xsd}' impossible : {exc}") from exc

    def valider(self, chemin_gml: Path) -> list[ErreurXsd]:
        """Valide un fichier GML contre le XSD compilé.

        Retourne la liste exhaustive des erreurs (vide si conforme). Si le
        fichier GML lui-même n'est pas un XML bien formé, une unique erreur
        de code XML_MALFORME est retournée — la validation XSD ne peut alors
        pas s'exécuter.
        """
        # Parser durci : neutralise XXE et résolution réseau d'entités
        # externes sur l'entrée utilisateur (le XSD a déjà été parsé en amont).
        parser = ET.XMLParser(resolve_entities=False, no_network=True)
        try:
            arbre = ET.parse(str(chemin_gml), parser)
        except ET.XMLSyntaxError as exc:
            return [_construire_erreur_xml_malforme(exc)]

        # validate() retourne bool ; le détail est dans schema.error_log
        # (réinitialisé à chaque appel par lxml).
        self._schema.validate(arbre)
        return [_convertir_entree_lxml(entree) for entree in self._schema.error_log]


def _construire_erreur_xml_malforme(exc: ET.XMLSyntaxError) -> ErreurXsd:
    """Construit une ErreurXsd dédiée pour les fichiers XML mal formés."""
    position = getattr(exc, "position", (None, None))
    ligne, colonne = position if isinstance(position, tuple) else (None, None)
    return ErreurXsd(
        code=CODE_XML_MALFORME,
        ligne=ligne,
        colonne=colonne,
        xpath=None,
        type_lxml=None,
        message=str(exc),
    )


# ---------------------------------------------------------------------------
# Génération du rapport JSON
# ---------------------------------------------------------------------------


def _construire_rapport(
    chemin_gml: Path,
    chemin_xsd: Path,
    erreurs: list[ErreurXsd],
    version: str = VERSION_DEFAUT,
) -> dict:
    """Construit le dictionnaire de rapport E112 à sérialiser en JSON."""
    nb_erreurs = len(erreurs)
    conformite = "CONFORME" if nb_erreurs == 0 else "NON_CONFORME"
    return {
        "fichier": str(chemin_gml.resolve()),
        "xsd": str(chemin_xsd.resolve()),
        "date_controle": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "niveau": "Forte",
        "type_controle": "E112_XSD_NATIF",
        "version_controlee": version,
        "conformite": conformite,
        "nb_erreurs": nb_erreurs,
        # E112 ne produit que des erreurs : ventilation alignée sur E114.
        "nb_par_severite": {"ERREUR": nb_erreurs} if nb_erreurs else {},
        "erreurs": [e.vers_dict() for e in erreurs],
    }


def _resoudre_chemin_sortie(chemin_gml: Path, repertoire_sortie: Path | None) -> Path:
    """Détermine le chemin du fichier JSON de sortie."""
    dossier = repertoire_sortie if repertoire_sortie else chemin_gml.parent
    nom_json = chemin_gml.stem + "_controle_e112.json"
    return (dossier / nom_json).resolve()


def generer_rapport(
    chemin_gml: Path,
    chemin_xsd: Path,
    erreurs: list[ErreurXsd],
    repertoire_sortie: Path | None = None,
    version: str = VERSION_DEFAUT,
) -> Path:
    """Écrit le rapport au format JSON et retourne le chemin du fichier créé."""
    chemin_sortie = _resoudre_chemin_sortie(chemin_gml, repertoire_sortie)
    rapport = _construire_rapport(chemin_gml, chemin_xsd, erreurs, version)

    with open(chemin_sortie, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)
    return chemin_sortie


# ---------------------------------------------------------------------------
# Point d'entrée CLI
# ---------------------------------------------------------------------------


def _construire_parseur() -> argparse.ArgumentParser:
    """Construit et retourne le parseur d'arguments CLI."""
    parseur = argparse.ArgumentParser(
        description=(
            "Contrôle E112 : validation XSD native (via lxml) d'un fichier GML "
            "RecoStaR. Délègue toute la vérification structurelle et typée au "
            "schéma XSD officiel."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parseur.add_argument(
        "fichier_gml",
        type=Path,
        help="Fichier GML RecoStaR à contrôler",
    )
    parseur.add_argument(
        "--xsd",
        type=Path,
        default=None,
        metavar="CHEMIN_XSD",
        help=(
            "Chemin vers le fichier XSD à utiliser. Par défaut, le XSD officiel "
            "de la version contrôlée (voir --version)."
        ),
    )
    ajouter_argument_version(parseur)
    parseur.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        metavar="REPERTOIRE",
        help=("Répertoire de sortie pour le rapport JSON (par défaut : même répertoire que le fichier GML)"),
    )
    parseur.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Désactive totalement l'accès réseau lors de la compilation du "
            "XSD. Nécessite que toutes les dépendances externes soient "
            "présentes dans le cache local (par défaut : "
            f"{_CHEMIN_CACHE_DEFAUT})."
        ),
    )
    parseur.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        metavar="REPERTOIRE",
        help=(f"Répertoire des XSD externes en cache local (par défaut : {_CHEMIN_CACHE_DEFAUT})."),
    )
    return parseur


def _valider_arguments(args: argparse.Namespace) -> None:
    """Vérifie la validité des arguments CLI. Termine le programme si invalides."""
    args.fichier_gml = args.fichier_gml.resolve()
    if not args.fichier_gml.exists():
        print(
            f"Erreur : le fichier '{args.fichier_gml}' n'existe pas.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.fichier_gml.is_file():
        print(
            f"Erreur : '{args.fichier_gml}' n'est pas un fichier.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.output_dir is not None:
        args.output_dir = args.output_dir.resolve()
        if not args.output_dir.is_dir():
            print(
                f"Erreur : le répertoire de sortie '{args.output_dir}' n'existe pas.",
                file=sys.stderr,
            )
            sys.exit(1)


def main() -> None:
    """Point d'entrée principal du contrôle E112."""
    parseur = _construire_parseur()
    args = parseur.parse_args()
    _valider_arguments(args)

    profil = resoudre_profil_cli(args.fichier_gml, args.version)
    # XSD explicite prioritaire ; sinon, XSD officiel de la version détectée.
    chemin_xsd = args.xsd if args.xsd is not None else profil.chemin_xsd
    if not chemin_xsd.exists():
        print(f"Erreur : le fichier XSD '{chemin_xsd}' n'existe pas.", file=sys.stderr)
        sys.exit(1)

    print(f"Controle E112 du fichier : {args.fichier_gml}")
    print(f"Version controlee        : {profil.code}")
    print(f"Schema XSD utilise       : {chemin_xsd}")
    if args.offline:
        print("Mode               : OFFLINE (reseau desactive)")

    try:
        validateur = ValidateurXsd(chemin_xsd, cache_dir=args.cache_dir, mode_offline=args.offline)
    except RuntimeError as exc:
        # XSD non compilable : on émet quand même un rapport avec une erreur
        # explicite, pour cohérence avec les autres contrôles E1xx.
        erreur = ErreurXsd(
            code=CODE_XSD_NON_COMPILABLE,
            ligne=None,
            colonne=None,
            xpath=None,
            type_lxml=None,
            message=str(exc),
        )
        chemin_rapport = generer_rapport(args.fichier_gml, chemin_xsd, [erreur], args.output_dir, profil.code)
        print(f"Echec compilation XSD : {exc}", file=sys.stderr)
        print(f"Rapport genere : {chemin_rapport}")
        sys.exit(1)

    erreurs = validateur.valider(args.fichier_gml)
    chemin_rapport = generer_rapport(args.fichier_gml, chemin_xsd, erreurs, args.output_dir, profil.code)

    nb = len(erreurs)
    statut = "CONFORME" if nb == 0 else f"{nb} erreur(s) XSD detectee(s)"
    print(f"Resultat : {statut}")
    print(f"Rapport genere : {chemin_rapport}")


if __name__ == "__main__":
    main()
