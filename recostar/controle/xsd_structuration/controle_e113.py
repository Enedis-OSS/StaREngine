#!/usr/bin/env python3
"""
Outil de contrôle E113 : vérification des en-têtes et métadonnées
d'un fichier GML RecoStaR conformément à la spécification V1.1.

Complémentaire de E110 (structure RPD) et E111 (règles métier RPD), E113
encode les exigences PDF §[1] / §[3] / §9 qui portent sur l'enveloppe
GML elle-même : namespaces, schemaLocation, présence et conformité du
Metadata, présence d'au moins un ReseauUtilite, validité du SRS et
unicité des gml:id sur l'ensemble du fichier.

Entrée  : Fichier GML RecoStaR à contrôler
Sortie  : Fichier JSON listant les erreurs d'en-tête détectées

Usage :
    python controle_e113.py <fichier.gml> [--output-dir <repertoire>]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import cast
from xml.etree.ElementTree import (  # nosec B405  # nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
    Element,
    ElementTree,
)

import defusedxml.ElementTree as DefusedET  # type: ignore
from cli_version import ajouter_argument_version, resoudre_profil_cli
from regles_entete import (
    CARDINALITES_ENTETE,
    CODE_CHAMP_HORS_ORDRE,
    CODE_CHAMP_INATTENDU,
    CODE_CHAMP_OBLIGATOIRE_MANQUANT,
    CODE_GML_ID_DUPLIQUE,
    CODE_NAMESPACE_MANQUANT,
    CODE_NAMESPACE_URI_INCORRECTE,
    CODE_OBJET_ENTETE_MANQUANT,
    CODE_OBJET_ENTETE_TROP_NOMBREUX,
    CODE_SCHEMA_LOCATION_MANQUANT,
    CODE_SCHEMA_LOCATION_VERSION_INCORRECTE,
    CODE_SRS_INVALIDE,
    FRAGMENT_URL_MAIN,
    FRAGMENT_URL_XSD_V1_1,
    NAMESPACES_ATTENDUS,
    SEQUENCES_ENTETE,
    SRS_AUTORISES,
    TYPES_ENTETE,
    URI_RECOSTAR,
    ErreurEntete,
)
from sequenceur_xsd import ErreurOrdre, SlotSequence, valider_sequence
from versions import VERSION_DEFAUT, resoudre_profil
from versions.profil import ProfilVersion

# ---------------------------------------------------------------------------
# Namespaces GML et attributs qualifiés
# ---------------------------------------------------------------------------

NS_GML = "http://www.opengis.net/gml/3.2"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"

TAG_FEATURE_MEMBER = f"{{{NS_GML}}}featureMember"
ATTR_GML_ID = f"{{{NS_GML}}}id"
ATTR_SCHEMA_LOCATION = f"{{{NS_XSI}}}schemaLocation"

# Libellé lisible de l'attribut schemaLocation, utilisé tel quel dans les
# rapports d'erreur (forme préfixée, indépendante de l'URI du namespace XSI).
LABEL_SCHEMA_LOCATION = "xsi:schemaLocation"


# ---------------------------------------------------------------------------
# Utilitaires namespace (cohérents avec controle_e110 / controle_e111)
# ---------------------------------------------------------------------------


def _nom_local(tag: str) -> str:
    """Extrait le nom local depuis un tag qualifié '{namespace}localname'."""
    return tag.rsplit("}", 1)[-1]


def _extraire_gml_id(element: Element) -> str:
    """Extrait la valeur de gml:id d'un élément, ou '<sans id>' si absent."""
    return element.get(ATTR_GML_ID, "<sans id>")


# ---------------------------------------------------------------------------
# Mapping des types d'erreur ORDRE -> codes E113
# ---------------------------------------------------------------------------

# Table immuable : ordre ⟶ code E113. Pré-calculée pour éviter une cascade
# d'if/else dans la boucle de conversion des ErreurOrdre.
_CODE_ORDRE_VERS_ENTETE: dict[str, str] = {
    "ELEMENT_REQUIS_MANQUANT": CODE_CHAMP_OBLIGATOIRE_MANQUANT,
    "ORDRE_INCORRECT": CODE_CHAMP_HORS_ORDRE,
    "ELEMENT_INATTENDU": CODE_CHAMP_INATTENDU,
}


def _convertir_erreur_ordre(erreur: ErreurOrdre) -> ErreurEntete:
    """Convertit une ErreurOrdre (E110) en ErreurEntete (E113).

    Le moteur valider_sequence renvoie des ErreurOrdre génériques ; on les
    requalifie ici en codes propres au contrôle E113 pour conserver une
    typologie d'erreur cohérente dans le rapport JSON.
    """
    code = _CODE_ORDRE_VERS_ENTETE.get(erreur.type_erreur, CODE_CHAMP_INATTENDU)
    return ErreurEntete(
        code=code,
        element=erreur.type_rpd,
        valeur_trouvee=erreur.element_trouve,
        valeur_attendue=erreur.element_attendu,
        message=erreur.message,
    )


# ---------------------------------------------------------------------------
# Analyse du fichier GML : namespaces (lecture indépendante via iterparse)
# ---------------------------------------------------------------------------


def _lire_namespaces(chemin_gml: Path) -> dict[str, str]:
    """Lit les déclarations xmlns du fichier GML en respectant la casse.

    iterparse / start-ns est le seul moyen d'accéder aux préfixes tels qu'ils
    sont écrits dans le fichier ; xml.etree perd cette information une fois
    le parsing terminé.
    """
    namespaces: dict[str, str] = {}
    for evenement, donnees in DefusedET.iterparse(  # type: ignore[no-untyped-call]
        str(chemin_gml), events=("start-ns",)
    ):
        if evenement == "start-ns":
            # Sur l'événement 'start-ns', le payload est documenté comme
            # un couple (prefix, uri) ; les stubs xml.etree exposent un type
            # union trop large -> cast explicite pour clarifier l'intention.
            prefixe, uri = cast(tuple[str, str], donnees)
            # Conserve la première occurrence : on ne valide que les
            # déclarations de niveau racine, pas les redéfinitions internes.
            namespaces.setdefault(prefixe, uri)
    return namespaces


def _verifier_namespaces(
    namespaces_trouves: dict[str, str],
    namespaces_attendus: dict[str, str] = NAMESPACES_ATTENDUS,
) -> list[ErreurEntete]:
    """Vérifie la présence et l'exactitude des namespaces attendus."""
    erreurs: list[ErreurEntete] = []
    for prefixe, uri_attendue in namespaces_attendus.items():
        uri_trouvee = namespaces_trouves.get(prefixe)
        if uri_trouvee is None:
            erreurs.append(
                ErreurEntete(
                    code=CODE_NAMESPACE_MANQUANT,
                    element=prefixe,
                    valeur_trouvee=None,
                    valeur_attendue=uri_attendue,
                    message=(f"Déclaration de namespace 'xmlns:{prefixe}' absente (attendue : '{uri_attendue}')"),
                )
            )
        elif uri_trouvee != uri_attendue:
            erreurs.append(
                ErreurEntete(
                    code=CODE_NAMESPACE_URI_INCORRECTE,
                    element=prefixe,
                    valeur_trouvee=uri_trouvee,
                    valeur_attendue=uri_attendue,
                    message=(
                        f"URI du namespace 'xmlns:{prefixe}' incorrecte : '{uri_trouvee}' (attendu : '{uri_attendue}')"
                    ),
                )
            )
    return erreurs


# ---------------------------------------------------------------------------
# Vérification du xsi:schemaLocation
# ---------------------------------------------------------------------------


def _verifier_schema_location(
    racine: Element,
    fragment_url: str = FRAGMENT_URL_XSD_V1_1,
    uri_recostar: str = URI_RECOSTAR,
) -> list[ErreurEntete]:
    """Vérifie la présence et la version du xsi:schemaLocation.

    Le fragment d'URL attendu dépend de la version contrôlée : il est fourni
    par le profil (par défaut, celui de la V1.1).
    """
    valeur = racine.get(ATTR_SCHEMA_LOCATION)
    if not valeur:
        return [
            ErreurEntete(
                code=CODE_SCHEMA_LOCATION_MANQUANT,
                element=LABEL_SCHEMA_LOCATION,
                valeur_trouvee=None,
                valeur_attendue=f"{uri_recostar} <URL XSD contenant '{fragment_url}'>",
                message=(
                    f"Attribut '{LABEL_SCHEMA_LOCATION}' absent de l'élément racine "
                    "(requis par PDF §[1] pour ancrer la version du XSD)"
                ),
            )
        ]

    # Le PDF §[1] interdit explicitement les pointeurs vers la branche 'main'
    # : on traite ce cas avec un message dédié.
    if FRAGMENT_URL_MAIN in valeur:
        return [
            ErreurEntete(
                code=CODE_SCHEMA_LOCATION_VERSION_INCORRECTE,
                element=LABEL_SCHEMA_LOCATION,
                valeur_trouvee=valeur,
                valeur_attendue=f"URL contenant '{fragment_url}'",
                message=(
                    "schemaLocation pointe vers la branche 'main' du XSD : "
                    f"il doit cibler le tag de version (fragment '{fragment_url}')"
                ),
            )
        ]

    if fragment_url not in valeur:
        return [
            ErreurEntete(
                code=CODE_SCHEMA_LOCATION_VERSION_INCORRECTE,
                element=LABEL_SCHEMA_LOCATION,
                valeur_trouvee=valeur,
                valeur_attendue=f"URL contenant '{fragment_url}'",
                message=(f"schemaLocation ne référence pas la version attendue (fragment '{fragment_url}' absent)"),
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Vérification des objets d'en-tête (Metadata, ReseauUtilite)
# ---------------------------------------------------------------------------


def _collecter_objets_entete(
    racine: Element,
    types_entete: frozenset[str] = TYPES_ENTETE,
) -> dict[str, list[Element]]:
    """Regroupe les éléments d'en-tête trouvés dans le GML par type local.

    Parcourt une seule fois les featureMember : optimisation utile sur les
    fichiers volumineux (plusieurs milliers de membres).
    """
    par_type: dict[str, list[Element]] = {t: [] for t in types_entete}
    for membre in racine.iter(TAG_FEATURE_MEMBER):  # type: ignore
        enfants = list(membre)
        if not enfants:
            continue
        element = enfants[0]
        nom = _nom_local(element.tag)
        if nom in types_entete:
            par_type[nom].append(element)
    return par_type


def _verifier_cardinalite(
    nom_type: str,
    objets: list[Element],
    cardinalites: dict[str, tuple[int, int]] = CARDINALITES_ENTETE,
) -> list[ErreurEntete]:
    """Vérifie qu'un type d'en-tête respecte sa cardinalité (min, max)."""
    cardinalite = cardinalites[nom_type]
    nb = len(objets)
    erreurs: list[ErreurEntete] = []

    if nb < cardinalite[0]:
        erreurs.append(
            ErreurEntete(
                code=CODE_OBJET_ENTETE_MANQUANT,
                element=nom_type,
                valeur_trouvee=str(nb),
                valeur_attendue=f"au moins {cardinalite[0]}",
                message=(
                    f"Objet d'en-tête '{nom_type}' absent du fichier "
                    f"(nombre trouvé : {nb}, attendu : au moins {cardinalite[0]})"
                ),
            )
        )
    elif cardinalite[1] != -1 and nb > cardinalite[1]:
        erreurs.append(
            ErreurEntete(
                code=CODE_OBJET_ENTETE_TROP_NOMBREUX,
                element=nom_type,
                valeur_trouvee=str(nb),
                valeur_attendue=f"au plus {cardinalite[1]}",
                message=(f"Objet d'en-tête '{nom_type}' présent {nb} fois (maximum autorisé : {cardinalite[1]})"),
            )
        )
    return erreurs


def _verifier_sequence_objet(
    nom_type: str,
    objet: Element,
    sequences_entete: dict[str, list[SlotSequence]] = SEQUENCES_ENTETE,
) -> list[ErreurEntete]:
    """Valide l'ordre et la complétude des enfants d'un objet d'en-tête.

    Réutilise valider_sequence du moteur E110 en lui passant la table
    des séquences d'en-tête : aucun code d'analyse de séquence n'est dupliqué ici.
    """
    gml_id = _extraire_gml_id(objet)
    noms_enfants = [_nom_local(enfant.tag) for enfant in objet]
    erreurs_ordre = valider_sequence(nom_type, gml_id, noms_enfants, sequences=sequences_entete)
    return [_convertir_erreur_ordre(eo) for eo in erreurs_ordre]


def _verifier_objets_entete(
    racine: Element,
    profil: ProfilVersion,
) -> list[ErreurEntete]:
    """Vérifie cardinalité et conformité de séquence pour Metadata/ReseauUtilite."""
    erreurs: list[ErreurEntete] = []
    objets_par_type = _collecter_objets_entete(racine, profil.types_entete)
    for nom_type, objets in objets_par_type.items():
        erreurs.extend(_verifier_cardinalite(nom_type, objets, profil.cardinalites_entete))
        for objet in objets:
            erreurs.extend(_verifier_sequence_objet(nom_type, objet, profil.sequences_entete))
    return erreurs


# ---------------------------------------------------------------------------
# Vérification du SRS (valeur autorisée dans le Metadata)
# ---------------------------------------------------------------------------


def _extraire_texte_enfant(element: Element, nom_local: str) -> str | None:
    """Retourne le texte normalisé du premier enfant portant ce nom local."""
    for enfant in element:
        if _nom_local(enfant.tag) == nom_local:
            texte = enfant.text
            return texte.strip() if texte else None
    return None


def _verifier_srs(
    racine: Element,
    srs_autorises: frozenset[str] = SRS_AUTORISES,
) -> list[ErreurEntete]:
    """Vérifie que la valeur SRS du Metadata est dans l'énumération autorisée.

    L'énumération autorisée dépend de la version (plus courte en V1.0) : elle
    est fournie par le profil, avec repli sur la liste V1.1 par défaut.
    """
    erreurs: list[ErreurEntete] = []
    for membre in racine.iter(TAG_FEATURE_MEMBER):  # type: ignore
        enfants = list(membre)
        if not enfants:
            continue
        objet = enfants[0]
        if _nom_local(objet.tag) != "Metadata":
            continue
        srs = _extraire_texte_enfant(objet, "SRS")
        # SRS absent → la règle de cardinalité du contrôle de séquence se
        # chargera de signaler le champ manquant : on ne double pas l'erreur.
        if srs is not None and srs not in srs_autorises:
            erreurs.append(
                ErreurEntete(
                    code=CODE_SRS_INVALIDE,
                    element="SRS",
                    valeur_trouvee=srs,
                    valeur_attendue="valeur de l'énumération SRSValue (PDF §10.6.1)",
                    message=(f"Valeur SRS '{srs}' hors de l'énumération autorisée (cf. PDF §10.6.1)"),
                )
            )
    return erreurs


# ---------------------------------------------------------------------------
# Vérification de l'unicité des gml:id sur l'ensemble du fichier
# ---------------------------------------------------------------------------


def _construire_erreur_doublon(gml_id: str, nb_occurrences: int) -> ErreurEntete:
    """Construit l'erreur pour un gml:id rencontré plusieurs fois."""
    return ErreurEntete(
        code=CODE_GML_ID_DUPLIQUE,
        element=gml_id,
        valeur_trouvee=str(nb_occurrences),
        valeur_attendue="1",
        message=(
            f"gml:id '{gml_id}' présent {nb_occurrences} fois dans le fichier (unicité requise par la norme GML 3.2)"
        ),
    )


def _verifier_unicite_gml_id(racine: Element) -> list[ErreurEntete]:
    """Détecte les gml:id dupliqués sur l'ensemble du fichier.

    Un seul passage suffit : on compte les occurrences puis on émet une
    erreur par identifiant en doublon. Complexité O(n).
    """
    compteur: dict[str, int] = {}
    # Accès attribut via variable locale : économise un attribute lookup
    # par itération dans une boucle potentiellement très chaude.
    attr = ATTR_GML_ID
    for element in racine.iter():
        identifiant = element.get(attr)
        if identifiant is not None:
            compteur[identifiant] = compteur.get(identifiant, 0) + 1
    return [_construire_erreur_doublon(gid, nb) for gid, nb in compteur.items() if nb > 1]


# ---------------------------------------------------------------------------
# Orchestration : AnalyseurEntete
# ---------------------------------------------------------------------------


class AnalyseurEntete:
    """Analyse l'en-tête d'un fichier GML RecoStaR et applique le contrôle E113."""

    __slots__ = ("chemin_gml", "profil")

    def __init__(self, chemin_gml: Path, profil: ProfilVersion | None = None) -> None:
        self.chemin_gml = chemin_gml
        # Profil par défaut : V1.1 (comportement historique préservé).
        self.profil = profil if profil is not None else resoudre_profil()

    def analyser(self) -> list[ErreurEntete]:
        """Exécute l'ensemble des contrôles d'en-tête et agrège les erreurs."""
        profil = self.profil
        # Les namespaces sont lus en amont via iterparse (une seule traversée)
        # parce qu'ils ne sont pas accessibles fidèlement sur l'arbre parsé.
        namespaces = _lire_namespaces(self.chemin_gml)
        erreurs: list[ErreurEntete] = _verifier_namespaces(namespaces, profil.namespaces_attendus)

        arbre: ElementTree[Element] = DefusedET.parse(str(self.chemin_gml))
        racine = arbre.getroot()
        # getroot() est annoté `Element | None` par les stubs xml.etree.
        # En pratique, defusedxml.parse() lève une exception si le document
        # est vide : si on arrive ici, racine est non-None. Le narrow type
        # explicite permet à Pylance d'éliminer l'union dans la suite.
        if racine is None:
            return erreurs

        erreurs.extend(_verifier_schema_location(racine, profil.fragment_url_xsd, URI_RECOSTAR))
        erreurs.extend(_verifier_objets_entete(racine, profil))
        erreurs.extend(_verifier_srs(racine, profil.srs_autorises))
        erreurs.extend(_verifier_unicite_gml_id(racine))
        return erreurs


# ---------------------------------------------------------------------------
# Génération du rapport JSON
# ---------------------------------------------------------------------------


def _construire_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurEntete],
    version: str = VERSION_DEFAUT,
) -> dict:
    """Construit le dictionnaire de rapport E113 à sérialiser en JSON."""
    nb_erreurs = len(erreurs)
    conformite = "CONFORME" if nb_erreurs == 0 else "NON_CONFORME"
    return {
        "fichier": str(chemin_gml.resolve()),
        "date_controle": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "niveau": "Forte",
        "type_controle": "E113_ENTETE",
        "version_controlee": version,
        "conformite": conformite,
        "nb_erreurs": nb_erreurs,
        # E113 ne produit que des erreurs : ventilation alignée sur E114.
        "nb_par_severite": {"ERREUR": nb_erreurs} if nb_erreurs else {},
        "erreurs": [e.vers_dict() for e in erreurs],
    }


def _resoudre_chemin_sortie(chemin_gml: Path, repertoire_sortie: Path | None) -> Path:
    """Détermine le chemin du fichier JSON de sortie."""
    dossier = repertoire_sortie if repertoire_sortie else chemin_gml.parent
    nom_json = chemin_gml.stem + "_controle_e113.json"
    return (dossier / nom_json).resolve()


def generer_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurEntete],
    repertoire_sortie: Path | None = None,
    version: str = VERSION_DEFAUT,
) -> Path:
    """Écrit le rapport au format JSON et retourne le chemin du fichier créé."""
    chemin_sortie = _resoudre_chemin_sortie(chemin_gml, repertoire_sortie)
    rapport = _construire_rapport(chemin_gml, erreurs, version)

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
            "Contrôle E113 : vérifie les en-têtes (namespaces, schemaLocation, "
            "Metadata, ReseauUtilite, SRS, unicité gml:id) d'un fichier GML "
            "RecoStaR V1.1."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parseur.add_argument(
        "fichier_gml",
        type=Path,
        help="Fichier GML RecoStaR à contrôler",
    )
    parseur.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        metavar="REPERTOIRE",
        help=("Répertoire de sortie pour le rapport JSON (par défaut : même répertoire que le fichier GML)"),
    )
    ajouter_argument_version(parseur)
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
    """Point d'entrée principal du contrôle E113."""
    parseur = _construire_parseur()
    args = parseur.parse_args()
    _valider_arguments(args)

    profil = resoudre_profil_cli(args.fichier_gml, args.version)
    print(f"Controle E113 du fichier : {args.fichier_gml}")
    print(f"Version controlee        : {profil.code}")

    analyseur = AnalyseurEntete(args.fichier_gml, profil)
    erreurs = analyseur.analyser()

    chemin_rapport = generer_rapport(args.fichier_gml, erreurs, args.output_dir, profil.code)

    nb = len(erreurs)
    statut = "CONFORME" if nb == 0 else f"{nb} erreur(s) d'entete detectee(s)"
    print(f"Resultat : {statut}")
    print(f"Rapport genere : {chemin_rapport}")


if __name__ == "__main__":
    main()
