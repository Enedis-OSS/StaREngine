"""
Pipeline complet RecoStaR : GML -> GeoJSON -> controles -> longueurs -> GML.

Point d'entree unique enchainant les quatre etapes du traitement d'un
recolement, chacune consommant la sortie de la precedente :

    1. conversion_entrante  conversion/conversion_V1_1/recostar_to_geojson.py
    2. controle             controle/pipeline_globale.py
    3. longueurs            traitement/calcul_longueurs/pipeline.py
    4. conversion_sortante  conversion/conversion_V1_1/geojson_to_recostar.py

Arborescence produite dans le repertoire de sortie :

    <sortie>/
    ├── geojson/                  etape 1 : fichiers RPD_*.geojson
    ├── controle/                 etape 2 : rapports de controle + PDF de synthese
    ├── rapport/                  etape 3 : resultats_longueurs.json + PDF
    ├── <nom>_regenere.gml        etape 4 : GML reconstruit depuis les GeoJSON
    └── rapport_pipeline.json     synthese des quatre etapes

Traitement par lot (--lot) : chaque GML du dossier designe est traite
independamment, dans son propre sous-dossier nomme d'apres le GML :

    <sortie>/
    ├── <nom_gml_1>/              arborescence complete du premier recolement
    ├── <nom_gml_2>/              arborescence complete du second
    └── rapport_lot.json          synthese du lot

L'echec d'un GML n'interrompt pas le lot : les recolements sont independants
les uns des autres, et interrompre priverait l'utilisateur des resultats deja
acquis. Les echecs sont recenses dans le rapport de lot.

Les etapes sont executees dans des sous-processus dedies. Ce choix n'est pas
une precaution de style : les quatre scripts s'importent a plat, inserent leur
propre repertoire dans sys.path et exposent des modules de meme nom
(recostar_to_geojson, utils_geojson). Les charger dans un processus unique les
ferait se masquer mutuellement. Deux d'entre eux appellent en outre sys.exit()
et lisent sys.argv, sans exposer d'API de fonction utilisable.

Arret a la premiere etape en echec : chaque etape consommant la sortie de la
precedente, poursuivre produirait des resultats calcules sur des donnees
absentes ou partielles. La politique est isolee dans `_interrompre_apres`.

Etapes : declarees dans ETAPES (point d'extension unique), sur le patron du
registre familles_controle.FAMILLES.

Usage CLI :
    python pipeline_complet.py --gml <fichier.gml> [--sortie <chemin>]
                               [--gml-sortie <fichier.gml>]
                               [--numero_affaire <numero>] [--srs <EPSG:XXXX>]
                               [--commentaire]
    python pipeline_complet.py --lot <dossier> [--sortie <chemin>]
                               [--numero_affaire <numero>] [--srs <EPSG:XXXX>]
                               [--commentaire]
"""

import argparse
import json
import subprocess  # nosec B404
import sys
from collections.abc import Callable
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from time import perf_counter
from typing import Any

# Racine du paquet recostar (repertoire de ce module).
RACINE: Path = Path(__file__).resolve().parent

# Nom du dossier de travail cree a cote du GML lorsque --sortie est omis.
DOSSIER_TRAVAIL_DEFAUT: str = "pipeline_recostar"

# Sous-dossier recevant les GeoJSON produits a l'etape 1 et relus aux etapes 2 a 4.
DOSSIER_GEOJSON: str = "geojson"

# Suffixe du GML regenere lorsque --gml-sortie est omis.
SUFFIXE_GML_SORTIE: str = "_regenere.gml"

# Nom du rapport de synthese des quatre etapes.
FICHIER_RAPPORT: str = "rapport_pipeline.json"

# Nom du rapport de synthese d'un traitement par lot.
FICHIER_RAPPORT_LOT: str = "rapport_lot.json"

# Extension des fichiers retenus par le traitement par lot. La comparaison est
# faite en minuscules : les GML livres portent indifferemment .gml ou .GML.
EXTENSION_GML: str = ".gml"

# Nombre de caracteres de trace conserves par etape en echec. Borne la taille du
# rapport : une trace Python complete depasserait la centaine de lignes.
TAILLE_MAX_TRACE: int = 2000

# Modes d'etape : determinent la construction de la ligne de commande.
MODE_GML_VERS_GEOJSON: str = "gml_vers_geojson"
MODE_CONTROLE: str = "controle"
MODE_LONGUEURS: str = "longueurs"
MODE_GEOJSON_VERS_GML: str = "geojson_vers_gml"


@dataclass(frozen=True, slots=True)
class EtapePipeline:
    """Declaration d'une etape du pipeline.

    - `script` : chemin du script, relatif a RACINE ;
    - `mode` : cle de CONSTRUCTEURS_ARGUMENTS fournissant ses arguments ;
    - `sortie_json` : l'etape serialise un rapport JSON sur sa sortie standard,
      qui est alors analyse et repris dans le rapport global.
    """

    cle: str
    libelle: str
    script: str
    mode: str
    sortie_json: bool = False


# Registre des etapes, dans l'ordre d'execution.
ETAPES: tuple[EtapePipeline, ...] = (
    EtapePipeline(
        cle="conversion_entrante",
        libelle="Conversion GML vers GeoJSON",
        script="conversion/conversion_V1_1/recostar_to_geojson.py",
        mode=MODE_GML_VERS_GEOJSON,
    ),
    EtapePipeline(
        cle="controle",
        libelle="Controles qualite",
        script="controle/pipeline_globale.py",
        mode=MODE_CONTROLE,
        sortie_json=True,
    ),
    EtapePipeline(
        cle="longueurs",
        libelle="Calcul des longueurs de cables",
        script="traitement/calcul_longueurs/pipeline.py",
        mode=MODE_LONGUEURS,
        sortie_json=True,
    ),
    EtapePipeline(
        cle="conversion_sortante",
        libelle="Conversion GeoJSON vers GML",
        script="conversion/conversion_V1_1/geojson_to_recostar.py",
        mode=MODE_GEOJSON_VERS_GML,
    ),
)


@dataclass(frozen=True, slots=True)
class ContexteOrchestration:
    """Chemins resolus une seule fois et partages par toutes les etapes."""

    gml_entree: Path
    racine_sortie: Path
    dossier_geojson: Path
    gml_sortie: Path
    numero_affaire: str | None = None
    srs: str | None = None
    commentaire_vide: bool = False


@dataclass(frozen=True, slots=True)
class ResultatEtape:
    """Resultat d'execution d'une etape.

    `rapport` reprend le JSON produit par l'etape lorsqu'elle en emet un ;
    `trace` n'est renseigne qu'en cas d'echec, tronque a TAILLE_MAX_TRACE.
    """

    cle: str
    libelle: str
    execute: bool = False
    code_retour: int | None = None
    motif: str | None = None
    duree_s: float = 0.0
    rapport: dict[str, Any] | None = None
    trace: str | None = None

    def vers_dict(self) -> dict[str, Any]:
        """Convertit le resultat en structure serialisable en JSON."""
        resultat: dict[str, Any] = {
            "libelle": self.libelle,
            "execute": self.execute,
            "code_retour": self.code_retour,
            "duree_s": self.duree_s,
        }
        for cle, valeur in (("motif", self.motif), ("rapport", self.rapport), ("trace", self.trace)):
            if valeur is not None:
                resultat[cle] = valeur
        return resultat


# ---------------------------------------------------------------------------
# Construction des lignes de commande
# ---------------------------------------------------------------------------


def _arguments_gml_vers_geojson(contexte: ContexteOrchestration) -> list[str]:
    """Arguments positionnels de recostar_to_geojson.py : GML source, dossier cible."""
    return [str(contexte.gml_entree), str(contexte.dossier_geojson)]


def _arguments_controle(contexte: ContexteOrchestration) -> list[str]:
    """Arguments de pipeline_globale.py.

    Le GML source est transmis explicitement : le dossier produit a l'etape 1 ne
    contient que des GeoJSON, la detection automatique de pipeline_globale
    ecarterait donc la famille structuration avec le motif "Aucun fichier GML".
    """
    arguments = [
        "--repertoire",
        str(contexte.dossier_geojson),
        "--sortie",
        str(contexte.racine_sortie),
        "--gml",
        str(contexte.gml_entree),
    ]
    if contexte.numero_affaire is not None:
        arguments += ["--numero_affaire", contexte.numero_affaire]
    return arguments


def _arguments_longueurs(contexte: ContexteOrchestration) -> list[str]:
    """Arguments de pipeline.py : les rapports sont ecrits dans <sortie>/rapport/."""
    return [
        "--chemin-geojson",
        str(contexte.dossier_geojson),
        "--chemin-sortie",
        str(contexte.racine_sortie),
    ]


def _arguments_geojson_vers_gml(contexte: ContexteOrchestration) -> list[str]:
    """Arguments de geojson_to_recostar.py : dossier GeoJSON, GML cible.

    Le CRS n'est transmis que s'il est impose : a defaut, le script le detecte
    depuis les GeoJSON, ce qui preserve celui du GML d'origine.

    --commentaire est un drapeau : il n'est ajoute que s'il est demande, la
    generation d'une balise Commentaire vide relevant d'un choix explicite de
    l'utilisateur (evolution V1.1 du standard).
    """
    arguments = [str(contexte.dossier_geojson), str(contexte.gml_sortie)]
    if contexte.srs is not None:
        arguments += ["--srs", contexte.srs]
    if contexte.commentaire_vide:
        arguments.append("--commentaire")
    return arguments


# Mode -> constructeur d'arguments. dict : lookup O(1), et ajouter un mode se
# fait sans modifier executer_etape.
CONSTRUCTEURS_ARGUMENTS: dict[str, Callable[[ContexteOrchestration], list[str]]] = {
    MODE_GML_VERS_GEOJSON: _arguments_gml_vers_geojson,
    MODE_CONTROLE: _arguments_controle,
    MODE_LONGUEURS: _arguments_longueurs,
    MODE_GEOJSON_VERS_GML: _arguments_geojson_vers_gml,
}


# ---------------------------------------------------------------------------
# Execution d'une etape
# ---------------------------------------------------------------------------


def _analyser_sortie_json(texte: str) -> dict[str, Any] | None:
    """Extrait l'objet JSON emis par une etape sur sa sortie standard.

    Le texte de progression eventuellement present avant l'objet est ignore.
    Retourne None si aucun objet exploitable n'est trouve : ce n'est pas une
    erreur, le rapport global reste utilisable sans le detail de l'etape.
    """
    debut = texte.find("{")
    if debut < 0:
        return None
    try:
        # Le fragment commence par '{' : json.loads renvoie necessairement un
        # dict, ou leve. Aucun autre type n'est atteignable, d'ou l'absence de
        # verification de type sur le resultat.
        return json.loads(texte[debut:])
    except json.JSONDecodeError:
        return None


def _motif_echec(processus: "subprocess.CompletedProcess[str]") -> str:
    """Derive un motif d'echec lisible depuis les flux du sous-processus.

    stderr est privilegie : les quatre scripts y ecrivent leurs erreurs fatales.
    Seule la derniere ligne utile est retenue, la trace complete etant conservee
    a part dans le rapport.
    """
    for flux in (processus.stderr, processus.stdout):
        lignes = [ligne.strip() for ligne in (flux or "").splitlines() if ligne.strip()]
        if lignes:
            return lignes[-1]
    return f"Code de retour {processus.returncode}"


def _tronquer_trace(processus: "subprocess.CompletedProcess[str]") -> str | None:
    """Retourne la fin de la sortie d'erreur, bornee a TAILLE_MAX_TRACE."""
    trace = (processus.stderr or "").strip()
    if not trace:
        return None
    return trace[-TAILLE_MAX_TRACE:]


def _resultat_echec(
    etape: EtapePipeline,
    processus: "subprocess.CompletedProcess[str]",
    duree_s: float,
    motif: str,
    rapport: dict[str, Any] | None = None,
) -> ResultatEtape:
    """Assemble le resultat d'une etape en echec."""
    return ResultatEtape(
        cle=etape.cle,
        libelle=etape.libelle,
        execute=False,
        code_retour=processus.returncode,
        motif=motif,
        duree_s=duree_s,
        rapport=rapport,
        trace=_tronquer_trace(processus),
    )


def executer_etape(etape: EtapePipeline, contexte: ContexteOrchestration) -> ResultatEtape:
    """Execute une etape dans un sous-processus et normalise son resultat.

    Le meme interpreteur que l'orchestrateur est utilise (sys.executable), afin
    que l'environnement virtuel Poetry actif soit celui des sous-processus.
    """
    chemin_script = RACINE / etape.script
    if not chemin_script.is_file():
        return ResultatEtape(etape.cle, etape.libelle, motif=f"Script introuvable : {chemin_script}")

    commande = [sys.executable, str(chemin_script), *CONSTRUCTEURS_ARGUMENTS[etape.mode](contexte)]
    debut = perf_counter()
    # La commande est construite en interne a partir du registre ETAPES, jamais
    # a partir d'une entree utilisateur libre, et executee sans shell.
    processus = subprocess.run(commande, capture_output=True, text=True, check=False)  # nosec B603
    duree_s = round(perf_counter() - debut, 3)

    if processus.returncode != 0:
        return _resultat_echec(etape, processus, duree_s, _motif_echec(processus))

    rapport = _analyser_sortie_json(processus.stdout) if etape.sortie_json else None
    # pipeline_globale.py et pipeline.py sortent avec le code 0 meme en echec :
    # leur succes se lit dans le champ "succes" du rapport JSON, pas ailleurs.
    if rapport is not None and not rapport.get("succes", True):
        motif = str(rapport.get("erreur", "Echec non precise"))
        return _resultat_echec(etape, processus, duree_s, motif, rapport)

    return ResultatEtape(
        cle=etape.cle,
        libelle=etape.libelle,
        execute=True,
        code_retour=0,
        duree_s=duree_s,
        rapport=rapport,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def construire_contexte(
    gml_entree: str,
    sortie: str | None = None,
    gml_sortie: str | None = None,
    numero_affaire: str | None = None,
    srs: str | None = None,
    commentaire_vide: bool = False,
) -> tuple[ContexteOrchestration | None, str | None]:
    """Valide le GML d'entree et resout l'arborescence de travail.

    Retourne (contexte, erreur) ; le contexte vaut None si le GML est
    introuvable. Le dossier des GeoJSON est cree des a present : l'etape 1 le
    remplit, les trois suivantes le relisent.
    """
    chemin_gml = Path(gml_entree).resolve()
    if not chemin_gml.is_file():
        return None, f"Fichier GML introuvable : {chemin_gml}"

    if sortie is not None:
        racine_sortie = Path(sortie).resolve()
    else:
        racine_sortie = chemin_gml.parent / DOSSIER_TRAVAIL_DEFAUT

    dossier_geojson = racine_sortie / DOSSIER_GEOJSON
    dossier_geojson.mkdir(parents=True, exist_ok=True)

    if gml_sortie is not None:
        chemin_gml_sortie = Path(gml_sortie).resolve()
    else:
        chemin_gml_sortie = racine_sortie / f"{chemin_gml.stem}{SUFFIXE_GML_SORTIE}"

    contexte = ContexteOrchestration(
        gml_entree=chemin_gml,
        racine_sortie=racine_sortie,
        dossier_geojson=dossier_geojson,
        gml_sortie=chemin_gml_sortie,
        numero_affaire=numero_affaire,
        srs=srs,
        commentaire_vide=commentaire_vide,
    )
    return contexte, None


def _interrompre_apres(resultat: ResultatEtape) -> bool:
    """Indique si l'echec d'une etape doit interrompre le pipeline.

    Politique actuelle : arret systematique. Chaque etape consomme la sortie de
    la precedente, poursuivre calculerait des resultats sur des donnees absentes
    ou partielles. Assouplir la politique (par exemple tolerer l'echec des
    etapes de rapport, controle et longueurs, pour regenerer le GML malgre tout)
    se fait ici et nulle part ailleurs.
    """
    return not resultat.execute


def executer_pipeline(
    gml_entree: str,
    sortie: str | None = None,
    gml_sortie: str | None = None,
    numero_affaire: str | None = None,
    srs: str | None = None,
    commentaire_vide: bool = False,
) -> dict[str, Any]:
    """Execute les quatre etapes et produit le rapport de synthese.

    Le rapport est egalement ecrit dans <sortie>/rapport_pipeline.json lorsque
    l'arborescence a pu etre resolue.
    """
    contexte, erreur = construire_contexte(
        gml_entree,
        sortie,
        gml_sortie,
        numero_affaire,
        srs,
        commentaire_vide,
    )
    if contexte is None:
        return {"succes": False, "erreur": erreur, "etapes": {}}

    resultats: list[ResultatEtape] = []
    for etape in ETAPES:
        resultat = executer_etape(etape, contexte)
        resultats.append(resultat)
        if _interrompre_apres(resultat):
            break

    return _assembler_rapport(contexte, tuple(resultats))


def _assembler_rapport(
    contexte: ContexteOrchestration,
    resultats: tuple[ResultatEtape, ...],
) -> dict[str, Any]:
    """Assemble le rapport global et le persiste dans le repertoire de sortie."""
    executees = tuple(r for r in resultats if r.execute)
    rapport: dict[str, Any] = {
        "succes": len(executees) == len(ETAPES),
        "gml_entree": str(contexte.gml_entree),
        "sortie": str(contexte.racine_sortie),
        "dossier_geojson": str(contexte.dossier_geojson),
        "gml_sortie": str(contexte.gml_sortie),
        "nombre_etapes": len(ETAPES),
        "etapes_executees": len(executees),
        "duree_totale_s": round(sum(r.duree_s for r in resultats), 3),
        "etapes": {r.cle: r.vers_dict() for r in resultats},
        "etapes_ignorees": [e.cle for e in ETAPES[len(resultats) :]],
    }

    chemin_rapport = contexte.racine_sortie / FICHIER_RAPPORT
    with open(chemin_rapport, "w", encoding="utf-8") as fichier:
        json.dump(rapport, fichier, ensure_ascii=False, indent=2)
    rapport["rapport_pipeline"] = str(chemin_rapport)
    return rapport


# ---------------------------------------------------------------------------
# Traitement par lot
# ---------------------------------------------------------------------------


def lister_gml_du_lot(dossier: Path) -> list[Path]:
    """Liste triee des GML contenus directement dans le dossier.

    Le parcours n'est pas recursif : un lot est un dossier de livraison plat.
    L'extension est comparee en minuscules, les GML livres portant
    indifferemment .gml ou .GML. Le tri rend l'ordre de traitement — et donc le
    rapport de lot — reproductible d'une execution a l'autre.
    """
    return sorted(
        (chemin for chemin in dossier.iterdir() if chemin.is_file() and chemin.suffix.lower() == EXTENSION_GML),
        key=lambda chemin: chemin.name,
    )


def _nom_dossier_traitement(gml: Path, noms_utilises: set[str]) -> str:
    """Derive du nom du GML un nom de sous-dossier unique dans le lot.

    Deux fichiers peuvent partager le meme radical sans etre identiques
    (Reseau.gml et Reseau.GML) : le second serait ecrase par le premier. Un
    indice est alors suffixe. L'appartenance est testee sur un set, en O(1).
    """
    nom = gml.stem
    if nom not in noms_utilises:
        noms_utilises.add(nom)
        return nom
    for indice in count(2):
        candidat = f"{nom}_{indice}"
        if candidat not in noms_utilises:
            noms_utilises.add(candidat)
            return candidat
    raise AssertionError  # pragma: no cover - count() est infini


def executer_lot(
    dossier_lot: str,
    sortie: str | None = None,
    numero_affaire: str | None = None,
    srs: str | None = None,
    commentaire_vide: bool = False,
) -> dict[str, Any]:
    """Traite tous les GML d'un dossier, chacun dans son propre sous-dossier.

    Un echec n'interrompt pas le lot : les recolements sont independants, et
    s'arreter priverait l'utilisateur des resultats deja acquis. Chaque rapport
    individuel est conserve tel quel dans `traitements`, et reste egalement
    accessible dans le sous-dossier du GML concerne.
    """
    chemin_lot = Path(dossier_lot).resolve()
    if not chemin_lot.is_dir():
        return {"succes": False, "erreur": f"Dossier de lot introuvable : {chemin_lot}", "traitements": {}}

    fichiers = lister_gml_du_lot(chemin_lot)
    if not fichiers:
        return {"succes": False, "erreur": f"Aucun fichier GML dans : {chemin_lot}", "traitements": {}}

    racine_sortie = Path(sortie).resolve() if sortie is not None else chemin_lot / DOSSIER_TRAVAIL_DEFAUT
    racine_sortie.mkdir(parents=True, exist_ok=True)

    debut = perf_counter()
    noms_utilises: set[str] = set()
    traitements: dict[str, dict[str, Any]] = {}
    for gml in fichiers:
        nom = _nom_dossier_traitement(gml, noms_utilises)
        traitements[nom] = executer_pipeline(
            str(gml),
            str(racine_sortie / nom),
            None,
            numero_affaire,
            srs,
            commentaire_vide,
        )
    duree_totale_s = round(perf_counter() - debut, 3)

    return _assembler_rapport_lot(chemin_lot, racine_sortie, traitements, duree_totale_s)


def _assembler_rapport_lot(
    chemin_lot: Path,
    racine_sortie: Path,
    traitements: dict[str, dict[str, Any]],
    duree_totale_s: float,
) -> dict[str, Any]:
    """Assemble le rapport du lot et le persiste dans le repertoire de sortie."""
    echecs = [nom for nom, rapport in traitements.items() if not rapport.get("succes")]
    rapport: dict[str, Any] = {
        "succes": not echecs,
        "mode": "lot",
        "dossier_lot": str(chemin_lot),
        "sortie": str(racine_sortie),
        "nombre_gml": len(traitements),
        "nombre_reussis": len(traitements) - len(echecs),
        "nombre_echoues": len(echecs),
        "gml_en_echec": echecs,
        "duree_totale_s": duree_totale_s,
        "traitements": traitements,
    }

    chemin_rapport = racine_sortie / FICHIER_RAPPORT_LOT
    with open(chemin_rapport, "w", encoding="utf-8") as fichier:
        json.dump(rapport, fichier, ensure_ascii=False, indent=2)
    rapport["rapport_lot"] = str(chemin_rapport)
    return rapport


def _executer_selon_mode(arguments: argparse.Namespace) -> dict[str, Any]:
    """Aiguille vers le traitement unitaire ou par lot selon la source fournie.

    Le groupe exclusif requis d'argparse garantit qu'exactement l'une des deux
    sources est renseignee : aucun cas par defaut n'est a traiter ici.
    """
    if arguments.lot is not None:
        return executer_lot(
            arguments.lot,
            arguments.sortie,
            arguments.numero_affaire,
            arguments.srs,
            arguments.commentaire_vide,
        )
    return executer_pipeline(
        arguments.gml,
        arguments.sortie,
        arguments.gml_sortie,
        arguments.numero_affaire,
        arguments.srs,
        arguments.commentaire_vide,
    )


def main() -> None:
    """Point d'entree CLI du pipeline complet RecoStaR."""
    parseur = argparse.ArgumentParser(
        description=(
            "Pipeline complet RecoStaR : convertit un GML en GeoJSON, execute les "
            "controles qualite et le calcul des longueurs, puis regenere le GML."
        )
    )
    # --gml et --lot designent la source : un fichier ou un dossier. Le groupe
    # exclusif requis rend l'incompatibilite explicite dans l'aide et fait
    # rejeter les deux cas fautifs par argparse, sans code de validation.
    source = parseur.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--gml",
        default=None,
        help="Fichier GML RecoStaR a traiter",
    )
    source.add_argument(
        "--lot",
        default=None,
        help=(
            "Dossier contenant plusieurs GML a traiter : chacun produit son propre "
            "sous-dossier de resultats. L'echec d'un GML n'interrompt pas le lot."
        ),
    )
    parseur.add_argument(
        "--sortie",
        default=None,
        help=(
            "Repertoire de travail recevant l'arborescence produite "
            f"(defaut : dossier {DOSSIER_TRAVAIL_DEFAUT}/ a cote du GML ou du dossier de lot)"
        ),
    )
    parseur.add_argument(
        "--gml-sortie",
        default=None,
        help=f"Fichier GML regenere (defaut : <nom du GML>{SUFFIXE_GML_SORTIE} dans le repertoire de sortie)",
    )
    parseur.add_argument(
        "--numero_affaire",
        default=None,
        help="Numero d'affaire pour le controle d'emprise DR (E303)",
    )
    parseur.add_argument(
        "--srs",
        default=None,
        help="Forcer le CRS du GML regenere (ex: EPSG:2154). A defaut, detecte depuis les GeoJSON.",
    )
    parseur.add_argument(
        "--commentaire",
        dest="commentaire_vide",
        action="store_true",
        default=False,
        help=(
            "Ajoute une balise Commentaire vide aux entites du GML regenere qui n'en "
            "possedent pas (evolution V1.1 du standard). Transmis a la conversion sortante."
        ),
    )
    arguments = parseur.parse_args()
    if arguments.lot is not None and arguments.gml_sortie is not None:
        # Un lot produit un GML par recolement : un nom de fichier unique ne
        # peut pas les designer tous.
        parseur.error("--gml-sortie est incompatible avec --lot")

    resultat = _executer_selon_mode(arguments)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    if not resultat["succes"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
