"""
Configuration pytest pour les tests des controles de projection.
Ajoute le repertoire parent (projection/) et le repertoire courant (tests/)
au chemin de recherche des modules.
"""

import os
import sys

_tests_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_tests_dir)
sys.path.insert(0, _parent_dir)
sys.path.insert(0, _tests_dir)
