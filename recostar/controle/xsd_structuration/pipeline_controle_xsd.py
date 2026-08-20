#!/usr/bin/env python3
"""
Pipeline de contrôle de structuration XSD des fichiers GML RecoStaR.

Orchestre l'exécution séquentielle des cinq contrôles de structuration sur un
même fichier GML. Chaque contrôle est exécuté indépendamment : un échec (par
exemple l'indisponibilité du XSD pour la validation native) n'empêche pas
l'exécution des contrôles suivants. Chaque contrôle écrit son propre rapport
JSON et le pipeline produit un rapport global agrégé.

Les codes des contrôles suivent la version contrôlée : **E110 à E114 en V1.1**,
**E010 à E014 en V1.0**. La version est résolue une seule fois en amont puis
propagée aux cinq contrôles, garantissant une version homogène et des codes
cohérents entre les rapports individuels et le rapport global.

Contrôles enchaînés (rang → code V1.1 / V1.0) :
    1. Ordre de structure des objets RPD     — E110 / E010
    2. Règles métier conditionnelles         — E111 / E011
    3. Validation XSD native via lxml        — E112 / E012
    4. En-tête, namespaces, unicité gml:id   — E113 / E013
    5. Valeurs des champs                    — E114 / E014

Entrée  : Fichier GML RecoStaR à contrôler
Sortie  : Un rapport JSON par contrôle + un rapport global agrégé

Usage :
    python pipeline_controle_xsd.py <fichier.gml> [--output-dir <repertoire>]
        [--xsd <chemin.xsd>] [--cache-dir <repertoire>] [--offline]
        [--version {auto,1.0,1.1}]
"""

import argparse
import json
import os
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import controle_e110
import controle_e111
import controle_e112
import controle_e113
import controle_e114
from cli_version import JETON_AUTO, ajouter_argument_version, resoudre_profil_cli
from codes_controle import (
    NB_CONTROLES,
    RANG_ENTETE,
    RANG_METIER,
    RANG_ORDRE,
    RANG_VALEURS,
    RANG_XSD_NATIF,
    codes_version,
    identite_controle,
)
from priorites_structuration import (
    CONFORME,
    NON_CONFORME,
    compter_bloquantes,
    statut_conformite,
    ventiler_par_priorite,
)
from versions import VERSIONS_SUPPORTEES
from versions.profil import ProfilVersion

# Sévérité considérée comme bloquante pour la conformité.
SEVERITE_ERREUR = "ERREUR"

# Codes des contrôles, toutes versions supportées confondues. Une exécution
# n'en produit que cinq (ceux de la version contrôlée), mais le registre des
# libellés (controle/familles_controle.py) doit tous les connaître.
NOMS_CONTROLES: tuple[str, ...] = tuple(code for version in VERSIONS_SUPPORTEES for code in codes_version(version))

# Nom du rapport global agrégé (suffixe ajouté au nom du fichier GML).
SUFFIXE_RAPPORT_GLOBAL: str = "_controle_xsd_global.json"


# ---------------------------------------------------------------------------
# Construction des résumés de contrôle
# ---------------------------------------------------------------------------


def _resumer(type_controle: str, erreurs: list[Any], chemin_rapport: Path) -> dict[str, Any]:
    """Construit le résumé d'un contrôle réussi à partir de sa liste d'erreurs.

    Tous les contrôles (E110-E114) sont mono-sévérité : la ventilation par
    sévérité ne comporte que des entrées ERREUR. La **priorité**, elle, varie :
    deux règles seulement dérogent au niveau bloquant (cf.
    `priorites_structuration`), et seules les erreurs bloquantes invalident la
    conformité.

    `anomalies_par_priorite` est la clé lue par `synthese_controles` pour
    ventiler la famille dans le rapport PDF ; `nb_erreurs` y reste le total
    toutes priorités confondues.
    """
    par_severite: dict[str, int] = {}
    for erreur in erreurs:
        par_severite[erreur.severite] = par_severite.get(erreur.severite, 0) + 1

    nb_erreurs = par_severite.get(SEVERITE_ERREUR, 0)
    par_priorite = ventiler_par_priorite(erreurs)
    return {
        "succes": True,
        "type_controle": type_controle,
        "conformite": statut_conformite(par_priorite),
        "nb_erreurs": nb_erreurs,
        "nb_erreurs_bloquantes": compter_bloquantes(par_priorite),
        "nb_par_severite": par_severite,
        "anomalies_par_priorite": par_priorite,
        "rapport": str(chemin_rapport),
    }


def _echec(type_controle: str, message: str) -> dict[str, Any]:
    """Construit le résumé d'un contrôle qui n'a pas pu s'exécuter."""
    return {"succes": False, "type_controle": type_controle, "erreur": message}


def _proteger(type_controle: str, action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Exécute un contrôle en isolant ses erreurs pour ne pas bloquer le pipeline.

    Un contrôle peut échouer pour des raisons variées (XML mal formé, XSD non
    compilable, dépendance réseau indisponible). L'exception est convertie en
    résumé d'échec afin que les contrôles suivants s'exécutent malgré tout.
    """
    try:
        return action()
    except Exception as exc:  # orchestrateur : un échec ne doit pas bloquer les contrôles suivants
        return _echec(type_controle, str(exc))


# ---------------------------------------------------------------------------
# Exécution individuelle de chaque contrôle
# ---------------------------------------------------------------------------


def _executer_ordre(chemin_gml: Path, sortie: Path | None, profil: ProfilVersion) -> dict[str, Any]:
    """Exécute le contrôle d'ordre de structure des objets RPD (E110 / E010)."""
    erreurs = controle_e110.AnalyseurGML(chemin_gml, profil).analyser()
    chemin = controle_e110.generer_rapport(chemin_gml, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_ORDRE).type_controle, erreurs, chemin)


def _executer_metier(chemin_gml: Path, sortie: Path | None, profil: ProfilVersion) -> dict[str, Any]:
    """Exécute le contrôle des règles métier conditionnelles (E111 / E011)."""
    erreurs = controle_e111.AnalyseurGML(chemin_gml, profil).analyser()
    chemin = controle_e111.generer_rapport(chemin_gml, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_METIER).type_controle, erreurs, chemin)


def _executer_xsd_natif(
    chemin_gml: Path,
    sortie: Path | None,
    chemin_xsd: Path,
    cache_dir: Path | None,
    offline: bool,
    profil: ProfilVersion,
) -> dict[str, Any]:
    """Exécute le contrôle de validation XSD native via lxml (E112 / E012)."""
    validateur = controle_e112.ValidateurXsd(chemin_xsd, cache_dir=cache_dir, mode_offline=offline)
    erreurs = validateur.valider(chemin_gml)
    chemin = controle_e112.generer_rapport(chemin_gml, chemin_xsd, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_XSD_NATIF).type_controle, erreurs, chemin)


def _executer_entete(chemin_gml: Path, sortie: Path | None, profil: ProfilVersion) -> dict[str, Any]:
    """Exécute le contrôle d'en-tête, namespaces et métadonnées (E113 / E013)."""
    erreurs = controle_e113.AnalyseurEntete(chemin_gml, profil).analyser()
    chemin = controle_e113.generer_rapport(chemin_gml, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_ENTETE).type_controle, erreurs, chemin)


def _executer_valeurs(chemin_gml: Path, sortie: Path | None, profil: ProfilVersion) -> dict[str, Any]:
    """Exécute le contrôle des valeurs des champs (E114 / E014)."""
    erreurs = controle_e114.AnalyseurValeurs(chemin_gml, profil).analyser()
    chemin = controle_e114.generer_rapport(chemin_gml, erreurs, sortie, profil.code)
    return _resumer(identite_controle(profil.code, RANG_VALEURS).type_controle, erreurs, chemin)


def _construire_controles(
    chemin_gml: Path,
    sortie: Path | None,
    xsd: Path,
    cache_dir: Path | None,
    offline: bool,
    profil: ProfilVersion,
) -> dict[str, dict[str, Any]]:
    """Exécute les cinq contrôles et les indexe sous le code de la version.

    Les clés du rapport global suivent la version contrôlée : E110 à E114 en
    V1.1, E010 à E014 en V1.0.
    """
    # Actions indexées par rang : l'ordre du tuple est l'ordre d'exécution.
    actions: tuple[Callable[[], dict[str, Any]], ...] = (
        lambda: _executer_ordre(chemin_gml, sortie, profil),
        lambda: _executer_metier(chemin_gml, sortie, profil),
        lambda: _executer_xsd_natif(chemin_gml, sortie, xsd, cache_dir, offline, profil),
        lambda: _executer_entete(chemin_gml, sortie, profil),
        lambda: _executer_valeurs(chemin_gml, sortie, profil),
    )

    resultats: dict[str, dict[str, Any]] = {}
    for rang in range(NB_CONTROLES):
        identite = identite_controle(profil.code, rang)
        resultats[identite.code] = _proteger(identite.type_controle, actions[rang])
    return resultats


# ---------------------------------------------------------------------------
# Orchestration du pipeline
# ---------------------------------------------------------------------------


def _ecrire_rapport_global(chemin_gml: Path, sortie: Path | None, rapport: dict[str, Any]) -> Path:
    """Écrit le rapport global agrégé sur disque et retourne son chemin."""
    dossier = sortie if sortie is not None else chemin_gml.parent
    chemin = dossier / (chemin_gml.stem + SUFFIXE_RAPPORT_GLOBAL)
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(rapport, fichier, ensure_ascii=False, indent=2)
    return chemin


def executer_pipeline(
    chemin_gml: Path,
    sortie: Path | None = None,
    chemin_xsd: Path | None = None,
    cache_dir: Path | None = None,
    offline: bool = False,
    profil: ProfilVersion | None = None,
) -> dict[str, Any]:
    """Exécute l'ensemble des contrôles de structuration XSD sur un fichier GML.

    Chaque contrôle est exécuté indépendamment ; un échec n'empêche pas
    l'exécution des suivants. Les résumés sont centralisés avec le nombre
    total d'erreurs bloquantes et la conformité globale.

    Le `profil` de version est résolu une seule fois en amont puis propagé à
    tous les contrôles, garantissant une version homogène. S'il n'est pas
    fourni, la version est **détectée depuis le fichier GML** (repli sur la
    version par défaut si l'en-tête est absent ou illisible), afin que les
    appels programmatiques — dont le pipeline global — contrôlent chaque
    fichier dans sa propre version. Les clés du dictionnaire `controles` sont
    les codes de cette version : E110 à E114 en V1.1, E010 à E014 en V1.0.
    """
    chemin_gml = chemin_gml.resolve()
    if not chemin_gml.is_file():
        return {"succes": False, "erreur": f"Fichier introuvable : {chemin_gml}"}

    if sortie is not None:
        sortie = sortie.resolve()
        os.makedirs(sortie, exist_ok=True)

    profil_actif = profil if profil is not None else resoudre_profil_cli(chemin_gml, JETON_AUTO)
    # XSD explicite prioritaire ; sinon XSD officiel de la version active.
    xsd = chemin_xsd if chemin_xsd is not None else profil_actif.chemin_xsd

    controles = _construire_controles(chemin_gml, sortie, xsd, cache_dir, offline, profil_actif)

    reussis = [r for r in controles.values() if r.get("succes")]
    nb_erreurs_total = sum(r.get("nb_erreurs", 0) for r in reussis)
    # La conformité globale ne retient que les erreurs bloquantes : une anomalie
    # majeure ou mineure est comptée et listée, mais ne déclasse pas le fichier
    # (même règle qu'au niveau famille, cf. synthese_controles).
    nb_erreurs_bloquantes = sum(r.get("nb_erreurs_bloquantes", 0) for r in reussis)
    controles_en_echec = [code for code, r in controles.items() if not r.get("succes")]
    conforme = nb_erreurs_bloquantes == 0 and not controles_en_echec

    rapport: dict[str, Any] = {
        "succes": True,
        "fichier": str(chemin_gml.resolve()),
        "date_controle": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "version_controlee": profil_actif.code,
        "controles": controles,
        "nb_erreurs_total": nb_erreurs_total,
        "nb_erreurs_bloquantes": nb_erreurs_bloquantes,
        "controles_en_echec": controles_en_echec,
        "conformite_globale": CONFORME if conforme else NON_CONFORME,
    }
    rapport["rapport_global"] = str(_ecrire_rapport_global(chemin_gml, sortie, rapport))
    return rapport


# ---------------------------------------------------------------------------
# Point d'entrée CLI
# ---------------------------------------------------------------------------


def _construire_parseur() -> argparse.ArgumentParser:
    """Construit et retourne le parseur d'arguments CLI."""
    parseur = argparse.ArgumentParser(
        description=(
            "Pipeline de contrôle de structuration XSD : exécute les cinq "
            "contrôles de structuration sur un fichier GML RecoStaR et agrège "
            "leurs rapports (E110 à E114 en V1.1, E010 à E014 en V1.0)."
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
        help=("Répertoire de sortie pour les rapports JSON (par défaut : même répertoire que le fichier GML)"),
    )
    parseur.add_argument(
        "--xsd",
        type=Path,
        default=None,
        metavar="CHEMIN_XSD",
        help=("Chemin du XSD utilisé par E112 (par défaut : XSD officiel de la version contrôlée, voir --version)."),
    )
    ajouter_argument_version(parseur)
    parseur.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        metavar="REPERTOIRE",
        help="Répertoire des XSD externes en cache local (utilisé par E112).",
    )
    parseur.add_argument(
        "--offline",
        action="store_true",
        help="Désactive l'accès réseau lors de la compilation du XSD (E112).",
    )
    return parseur


def _valider_arguments(args: argparse.Namespace) -> None:
    """Vérifie la validité des arguments CLI. Termine le programme si invalides."""
    args.fichier_gml = args.fichier_gml.resolve()
    if not args.fichier_gml.exists() or not args.fichier_gml.is_file():
        print(
            f"Erreur : le fichier '{args.fichier_gml}' n'existe pas.",
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
    """Point d'entrée principal du pipeline de contrôles XSD."""
    parseur = _construire_parseur()
    args = parseur.parse_args()
    _valider_arguments(args)

    profil = resoudre_profil_cli(args.fichier_gml, args.version)
    print(f"Pipeline de controle XSD du fichier : {args.fichier_gml}")
    print(f"Version controlee : {profil.code}")

    resultat = executer_pipeline(
        args.fichier_gml,
        sortie=args.output_dir,
        chemin_xsd=args.xsd,
        cache_dir=args.cache_dir,
        offline=args.offline,
        profil=profil,
    )

    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
