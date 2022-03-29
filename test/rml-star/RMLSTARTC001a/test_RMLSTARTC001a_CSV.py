__author__ = "Julián Arenas-Guerrero"
__credits__ = ["Julián Arenas-Guerrero"]

__license__ = "Apache-2.0"
__maintainer__ = "Julián Arenas-Guerrero"
__email__ = "arenas.guerrero.julian@outlook.com"


import os
import morph_kgc

from pyoxigraph import Store


def test_RMLSTARTC001a():
    with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'output.nq')) as file:
        triples = file.readlines()
    g = [triple[:-2] for triple in triples]

    mapping_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'mapping.ttl')
    config = f'[DataSource]\nmappings={mapping_path}'

    g_morph = morph_kgc.materialize_set(config)

    assert set(g) == set(g_morph)
