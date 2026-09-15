"""
Modele normalise des resultats de controle.

Les pipelines de famille ne partagent pas le meme format de rapport : les
pipelines GeoJSON (altimetrie, cable, cheminement, projection) exposent
`nombre_anomalies` et une `priorite` scalaire, le pipeline de structuration XSD
expose `nb_erreurs` et une ventilation `anomalies_par_priorite` deja calculee,
et certains controles multi-regles exposent un dictionnaire `priorites`
indexe par type d'anomalie.

Ce module convertit ces formats heterogenes en un modele unique, seul connu du
rapport PDF. La normalisation est une couche d'adaptation en lecture : les
pipelines n'ont pas a etre modifies pour changer d'echelle de priorites.

Depuis le lot 2, la priorite d'une anomalie est **deduite du niveau de son code
d'erreur** (`codes_verificateur.niveau_anomalie`) des que le rapport ventile ses
anomalies par type. La priorite declaree par le controle ne sert plus que de
repli, pour les types dont le code n'est pas encore fixe. Aucune divergence
n'est donc possible entre l'echelle de star-engine et celle du verificateur.

Module pur (aucune E/S) : entierement testable sans jeu de donnees.
"""

from dataclasses import dataclass
from typing import Any

from recostar.controle.codes_verificateur import (
    NIVEAU_BASSE,
    NIVEAU_BLOQUANTE,
    NIVEAU_FORTE,
    NIVEAU_MOYENNE,
    NIVEAUX_DECLASSANTS,
    ORDRE_NIVEAUX,
    niveau_anomalie,
)
from recostar.controle.fonctions_communes.resultats import est_sans_objet

# Echelle de priorites : celle du verificateur RecoStaR, seule en service depuis
# le lot 2. Elle n'est pas redeclaree ici, elle est importee du referentiel, ce
# qui interdit toute derive entre les deux modules.
#   - bloquante : interrompt le traitement ;
#   - forte     : n'interrompt pas, mais le certificat n'est pas conforme ;
#   - moyenne   : n'empeche pas la conformite, a corriger ;
#   - basse     : pour information.
# `bloquante` reste inemployee : star-engine exprime deja l'interruption par le
# statut de famille « Non execute », qui n'a pas a devenir une anomalie.
PRIORITE_BLOQUANTE: str = NIVEAU_BLOQUANTE
PRIORITE_FORTE: str = NIVEAU_FORTE
PRIORITE_MOYENNE: str = NIVEAU_MOYENNE
PRIORITE_BASSE: str = NIVEAU_BASSE

# Repli propre au rapport, hors echelle du verificateur : un controle dont le
# rapport n'annonce aucune priorite et dont l'anomalie n'a pas encore de code.
PRIORITE_INCONNUE: str = "non_precisee"

# Ordre d'affichage, de la plus grave a la moins grave.
ORDRE_PRIORITES: tuple[str, ...] = (*ORDRE_NIVEAUX, PRIORITE_INCONNUE)

# Libelles affiches dans le rapport.
LIBELLES_PRIORITES: dict[str, str] = {
    PRIORITE_BLOQUANTE: "Bloquante",
    PRIORITE_FORTE: "Forte",
    PRIORITE_MOYENNE: "Moyenne",
    PRIORITE_BASSE: "Basse",
    PRIORITE_INCONNUE: "Non précisée",
}

# Seules les anomalies de ces priorites declassent une famille en « Non
# conforme », conformement au lexique du verificateur : une erreur forte rend
# le certificat non conforme, une erreur moyenne ou basse est signalee et
# comptee sans invalider la livraison. Le comportement est preserve par rapport
# a l'echelle precedente : ce qui declassait sous « bloquant » declasse sous
# « forte ».
PRIORITES_DECLASSANTES: frozenset[str] = NIVEAUX_DECLASSANTS

STATUT_CONFORME: str = "Conforme"
STATUT_NON_CONFORME: str = "Non conforme"
# Aucune anomalie bloquante, mais un controle au moins n'a pas pu s'executer :
# la conformite n'est ni infirmee ni verifiable. Le cas est courant et legitime
# (E-5106 sans numero d'affaire, projection sans _metadata.json, couche source
# absente) ;
# le confondre avec « Non conforme » signalerait un defaut inexistant, et avec
# « Conforme » affirmerait une verification non faite.
STATUT_INCOMPLET: str = "Incomplet"
STATUT_NON_EXECUTE: str = "Non exécuté"


@dataclass(frozen=True, slots=True)
class ResultatControle:
    """Resultat normalise d'un controle unitaire.

    `sans_objet` distingue deux conformites que le seul comptage confond : un
    controle qui n'a releve aucune anomalie apres analyse, et un controle qui
    n'avait aucune entite a analyser, sa couche source n'etant pas livree. Les
    deux sont conformes ; seul le second appelle une mention au rapport, que
    `motif` fournit.
    """

    code: str  # "E-5107", "E-6110"...
    libelle: str
    succes: bool
    nombre_anomalies: int
    anomalies_par_priorite: dict[str, int]
    erreur: str | None = None
    sans_objet: bool = False
    motif: str | None = None
    # Codes du verificateur emis par le controle. Renseigne par les seuls
    # controles de structuration, dont le code propre n'est pas un code
    # d'erreur : ils en emettent plusieurs selon la regle enfreinte.
    codes_erreur: tuple[str, ...] = ()

    @property
    def code_affichable(self) -> str:
        """Code porte par la colonne du rapport.

        Les controles dont le code est deja celui du verificateur l'affichent
        tel quel. Les autres affichent les codes qu'ils emettent, abreges
        au-dela de deux pour que la colonne reste lisible.
        """
        if not self.codes_erreur:
            return self.code
        if len(self.codes_erreur) <= 2:
            return ", ".join(self.codes_erreur)
        return f"{self.codes_erreur[0]} \u2026{self.codes_erreur[-1]}"


@dataclass(frozen=True, slots=True)
class ResultatFamille:
    """Resultat normalise d'une famille de controles.

    `execute` a False signale une famille volontairement ignoree (absence de
    donnee d'entree, par exemple) ; `motif` en porte la raison, affichee telle
    quelle dans le rapport pour qu'aucune famille ne disparaisse silencieusement.
    """

    cle: str
    libelle: str
    controles: tuple[ResultatControle, ...] = ()
    execute: bool = True
    motif: str | None = None

    @property
    def nombre_controles(self) -> int:
        """Nombre de controles executes dans la famille."""
        return len(self.controles)

    @property
    def nombre_anomalies(self) -> int:
        """Nombre total d'anomalies, toutes priorites confondues."""
        return sum(c.nombre_anomalies for c in self.controles)

    @property
    def controles_en_echec(self) -> tuple[str, ...]:
        """Codes des controles n'ayant pas pu s'executer."""
        return tuple(c.code for c in self.controles if not c.succes)

    @property
    def controles_sans_objet(self) -> tuple[str, ...]:
        """Codes des controles conformes faute d'entite a controler."""
        return tuple(c.code for c in self.controles if c.sans_objet)

    @property
    def anomalies_par_priorite(self) -> dict[str, int]:
        """Ventilation des anomalies de la famille par priorite."""
        ventilation: dict[str, int] = {}
        for controle in self.controles:
            for priorite, nombre in controle.anomalies_par_priorite.items():
                ventilation[priorite] = ventilation.get(priorite, 0) + nombre
        return ventilation

    @property
    def nombre_anomalies_declassantes(self) -> int:
        """Nombre d'anomalies dont la priorite invalide la conformite."""
        ventilation = self.anomalies_par_priorite
        return sum(ventilation.get(p, 0) for p in PRIORITES_DECLASSANTES)

    @property
    def statut(self) -> str:
        """Statut global de la famille.

        Trois issues, dans cet ordre de priorite :
          - Non conforme : au moins une anomalie declassante, c'est-a-dire
            bloquante. Un defaut avere reste avere meme si la verification est
            par ailleurs incomplete ;
          - Incomplet : aucune anomalie declassante, mais un controle au moins
            n'a pas pu s'executer — la conformite n'est pas verifiable ;
          - Conforme : tous les controles ont abouti sans anomalie declassante.
        """
        if not self.execute:
            return STATUT_NON_EXECUTE
        if self.nombre_anomalies_declassantes > 0:
            return STATUT_NON_CONFORME
        if self.controles_en_echec:
            return STATUT_INCOMPLET
        return STATUT_CONFORME


# ---------------------------------------------------------------------------
# Normalisation des rapports de pipeline
# ---------------------------------------------------------------------------


def nombre_anomalies_rapport(rapport: dict[str, Any]) -> int:
    """Extrait le nombre d'anomalies d'un rapport de controle.

    Accepte les deux conventions du projet : `nombre_anomalies` (pipelines
    GeoJSON) et `nb_erreurs` (pipeline de structuration XSD).
    """
    valeur = rapport.get("nombre_anomalies")
    if valeur is None:
        valeur = rapport.get("nb_erreurs", 0)
    return int(valeur) if isinstance(valeur, (int, float)) else 0


def _ventiler_par_type(
    anomalies_par_type: dict[str, Any],
    code_controle: str | None,
    priorites: dict[str, Any] | None,
    defaut: str,
) -> dict[str, int]:
    """Ventile les anomalies d'un controle en deduisant la priorite de chaque type.

    Le niveau du code d'erreur prime sur toute priorite declaree : c'est lui qui
    fait foi depuis le lot 2. La priorite declaree par le controle — dictionnaire
    `priorites` indexe par type, ou valeur de repli — n'est retenue que pour les
    types dont le code d'erreur n'est pas encore fixe.
    """
    ventilation: dict[str, int] = {}
    for type_anomalie, nombre in anomalies_par_type.items():
        # Une priorite declaree vide retombe sur le defaut plutot que de devenir
        # une categorie a part : `str(None)` aurait ouvert une colonne « None »
        # dans le rapport.
        brute = priorites.get(type_anomalie) if priorites is not None else None
        declaree = str(brute) if brute else defaut
        resolue = niveau_anomalie(code_controle, str(type_anomalie), declaree) if code_controle else None
        priorite = resolue or declaree
        ventilation[priorite] = ventilation.get(priorite, 0) + int(nombre)
    return ventilation


def ventiler_anomalies(
    rapport: dict[str, Any],
    priorite_par_defaut: str | None = None,
    code_controle: str | None = None,
) -> dict[str, int]:
    """Ventile les anomalies d'un rapport de controle par priorite.

    Quatre conventions sont prises en charge, sans cas particulier code en dur,
    de la plus explicite a la plus implicite :
      - `anomalies_par_priorite` (priorite -> nombre) : ventilation deja
        calculee par le pipeline, chaque anomalie portant sa propre priorite
        (pipeline de structuration XSD) ;
      - `anomalies_par_type` (+ `code_controle`) : la priorite est deduite du
        niveau du code d'erreur de chaque type ; le dictionnaire `priorites`
        indexe par type, la `priorite` scalaire puis `priorite_par_defaut` ne
        servent que de repli pour les types encore sans code ;
      - `priorite` scalaire seule : controle qui ne ventile pas par type ;
      - aucune des trois : `priorite_par_defaut` de la famille.
    """
    nombre = nombre_anomalies_rapport(rapport)
    if nombre == 0:
        return {}

    # Ventilation deja etablie a la source : elle fait autorite, aucune
    # priorite n'a a etre rededuite.
    par_priorite = rapport.get("anomalies_par_priorite")
    if isinstance(par_priorite, dict) and par_priorite:
        return {str(priorite): int(nb) for priorite, nb in par_priorite.items()}

    defaut = str(rapport.get("priorite") or priorite_par_defaut or PRIORITE_INCONNUE)

    # Ventilation par type : seule maille a laquelle le code d'erreur — donc la
    # priorite — se resout. Elle est preferee des qu'elle est disponible.
    priorites = rapport.get("priorites")
    anomalies_par_type = rapport.get("anomalies_par_type")
    if isinstance(anomalies_par_type, dict) and anomalies_par_type:
        return _ventiler_par_type(
            anomalies_par_type,
            code_controle,
            priorites if isinstance(priorites, dict) else None,
            defaut,
        )

    return {defaut: nombre}


def _codes_erreur_rapport(rapport: dict[str, Any]) -> tuple[str, ...]:
    """Lit les codes du verificateur declares par un rapport de controle.

    Seuls les controles de structuration renseignent la cle ; son absence
    signifie que le code du controle est deja celui du verificateur.
    """
    codes = rapport.get("codes_erreur")
    if not isinstance(codes, list):
        return ()
    return tuple(str(code) for code in codes if code)


def normaliser_controle(
    code: str,
    libelle: str,
    rapport: dict[str, Any],
    priorite_par_defaut: str | None = None,
) -> ResultatControle:
    """Convertit le rapport d'un controle en ResultatControle normalise.

    Un controle en echec ne porte aucune anomalie exploitable : seul son motif
    d'erreur est conserve.
    """
    succes = bool(rapport.get("succes"))
    if not succes:
        return ResultatControle(
            code=code,
            libelle=libelle,
            succes=False,
            nombre_anomalies=0,
            anomalies_par_priorite={},
            erreur=str(rapport.get("erreur", "Echec non precise")),
        )
    # Un controle prive de sa couche source est conforme sans avoir rien lu : le
    # marqueur et son motif suivent le resultat jusqu'au rapport, ou ils evitent
    # de lire « 0 anomalie » comme le produit d'une verification effective.
    sans_objet = est_sans_objet(rapport)
    return ResultatControle(
        code=code,
        libelle=libelle,
        succes=True,
        nombre_anomalies=nombre_anomalies_rapport(rapport),
        anomalies_par_priorite=ventiler_anomalies(rapport, priorite_par_defaut, code),
        sans_objet=sans_objet,
        motif=str(rapport.get("motif")) if sans_objet else None,
        codes_erreur=_codes_erreur_rapport(rapport),
    )


# ---------------------------------------------------------------------------
# Agregation globale
# ---------------------------------------------------------------------------


def priorites_presentes(familles: tuple[ResultatFamille, ...]) -> tuple[str, ...]:
    """Retourne les priorites effectivement rencontrees, dans l'ordre de gravite.

    Le rapport n'affiche que les colonnes de priorite reellement alimentees :
    afficher des colonnes toujours vides nuirait a la lisibilite.
    """
    presentes: set[str] = set()
    for famille in familles:
        presentes.update(famille.anomalies_par_priorite)
    return tuple(p for p in ORDRE_PRIORITES if p in presentes)


def _statut_global(non_conformes: tuple[str, ...], incompletes: tuple[str, ...]) -> str:
    """Determine le statut global a partir des statuts de famille.

    Meme hierarchie qu'au niveau d'une famille : un defaut avere prime sur une
    verification incomplete.
    """
    if non_conformes:
        return STATUT_NON_CONFORME
    return STATUT_INCOMPLET if incompletes else STATUT_CONFORME


def agreger(familles: tuple[ResultatFamille, ...]) -> dict[str, Any]:
    """Agrege les familles en une synthese globale serialisable en JSON."""
    executees = tuple(f for f in familles if f.execute)
    ventilation: dict[str, int] = {}
    for famille in executees:
        for priorite, nombre in famille.anomalies_par_priorite.items():
            ventilation[priorite] = ventilation.get(priorite, 0) + nombre

    non_conformes = tuple(f.cle for f in executees if f.statut == STATUT_NON_CONFORME)
    incompletes = tuple(f.cle for f in executees if f.statut == STATUT_INCOMPLET)
    return {
        "statut_global": _statut_global(non_conformes, incompletes),
        "familles_non_conformes": non_conformes,
        "familles_incompletes": incompletes,
        "nombre_familles_executees": len(executees),
        "nombre_controles_executes": sum(f.nombre_controles for f in executees),
        "nombre_controles_en_echec": sum(len(f.controles_en_echec) for f in executees),
        "nombre_controles_sans_objet": sum(len(f.controles_sans_objet) for f in executees),
        "nombre_anomalies_total": sum(f.nombre_anomalies for f in executees),
        "anomalies_par_priorite": ventilation,
    }
