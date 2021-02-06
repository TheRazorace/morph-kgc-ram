""" Morph-KGC """

__author__ = "Julián Arenas-Guerrero"
__copyright__ = "Copyright (C) 2020 Julián Arenas-Guerrero"
__credits__ = ["Julián Arenas-Guerrero"]

__license__ = "Apache-2.0"
__maintainer__ = "Julián Arenas-Guerrero"
__email__ = "arenas.guerrero.julian@outlook.com"


import logging
import time
import pandas as pd
import multiprocessing as mp

from itertools import repeat
from urllib.parse import quote

from data_sources import relational_source
import utils


def _get_references_in_mapping_rule(mapping_rule, only_subject_map=False):
    references = []
    if mapping_rule['subject_template']:
        references.extend(utils.get_references_in_template(str(mapping_rule['subject_template'])))
    elif mapping_rule['subject_reference']:
        references.append(str(mapping_rule['subject_reference']))

    if not only_subject_map:
        if mapping_rule['predicate_template']:
            references.extend(utils.get_references_in_template(str(mapping_rule['predicate_template'])))
        elif mapping_rule['predicate_reference']:
            references.append(str(mapping_rule['predicate_reference']))
        if mapping_rule['object_template']:
            references.extend(utils.get_references_in_template(str(mapping_rule['object_template'])))
        elif mapping_rule['object_reference']:
            references.append(str(mapping_rule['object_reference']))

    return set(references)


def _materialize_template(results_df, template, columns_alias='', termtype='http://www.w3.org/ns/r2rml#IRI', language_tag='', datatype=''):
    references = utils.get_references_in_template(str(template))

    if str(termtype).strip() == 'http://www.w3.org/ns/r2rml#Literal':
        results_df['triple'] = results_df['triple'] + '"'
    else:
        results_df['triple'] = results_df['triple'] + '<'

    for reference in references:
        results_df['reference_results'] = results_df[columns_alias + reference]

        if str(termtype).strip() == 'http://www.w3.org/ns/r2rml#IRI':
            results_df['reference_results'] = results_df['reference_results'].apply(lambda x: quote(x))

        splitted_template = template.split('{' + reference + '}')
        results_df['triple'] = results_df['triple'] + splitted_template[0]
        results_df['triple'] = results_df['triple'] + results_df['reference_results']
        template = str('{' + reference + '}').join(splitted_template[1:])

    if str(termtype).strip() == 'http://www.w3.org/ns/r2rml#Literal':
        results_df['triple'] = results_df['triple'] + '"'
        if language_tag:
            results_df['triple'] = results_df['triple'] + '@' + language_tag + ' '
        elif datatype:
            results_df['triple'] = results_df['triple'] + '^^<' + datatype + '> '
        else:
            results_df['triple'] = results_df['triple'] + ' '
    else:
        results_df['triple'] = results_df['triple'] + '> '

    return results_df


def _materialize_reference(results_df, reference, columns_alias='', termtype='http://www.w3.org/ns/r2rml#Literal', language_tag='', datatype=''):
    results_df['reference_results'] = results_df[columns_alias + str(reference)]

    if str(termtype).strip() == 'http://www.w3.org/ns/r2rml#IRI':
        results_df['reference_results'] = results_df['reference_results'].apply(lambda x: quote(x, safe='://'))
        results_df['triple'] = results_df['triple'] + '<' + results_df['reference_results'] + '> '
    elif str(termtype).strip() == 'http://www.w3.org/ns/r2rml#Literal':
        results_df['triple'] = results_df['triple'] + '"' + results_df['reference_results'] + '"'
        if language_tag:
            results_df['triple'] = results_df['triple'] + '@' + language_tag + ' '
        elif datatype:
            results_df['triple'] = results_df['triple'] + '^^<' + datatype + '> '
        else:
            results_df['triple'] = results_df['triple'] + ' '

    return results_df


def _materialize_constant(results_df, constant, termtype='http://www.w3.org/ns/r2rml#IRI', language_tag='', datatype=''):
    if str(termtype).strip() == 'http://www.w3.org/ns/r2rml#Literal':
        complete_constant = '"' + constant + '"'

        if language_tag:
            complete_constant = complete_constant + '@' + language_tag + ' '
        elif datatype:
            complete_constant = complete_constant + '^^<' + datatype + '> '
        else:
            complete_constant = complete_constant + ' '
    else:
        complete_constant = '<' + str(constant) + '> '

    results_df['triple'] = results_df['triple'] + complete_constant

    return results_df


def _materialize_join_mapping_rule_terms(results_df, mapping_rule, parent_triples_map_rule):
    results_df['triple'] = ''
    if mapping_rule['subject_template']:
        results_df = _materialize_template(
            results_df, mapping_rule['subject_template'], termtype=mapping_rule['subject_termtype'],
            columns_alias='child_')
    elif mapping_rule['subject_constant']:
        results_df = _materialize_constant(results_df, mapping_rule['subject_constant'],
                                           termtype=mapping_rule['subject_termtype'])
    elif mapping_rule['subject_reference']:
        results_df = _materialize_reference(
            results_df, mapping_rule['subject_reference'], termtype=mapping_rule['subject_termtype'],
            columns_alias='child_')
    if mapping_rule['predicate_template']:
        results_df = _materialize_template(
            results_df, mapping_rule['predicate_template'], columns_alias='child_')
    elif mapping_rule['predicate_constant']:
        results_df = _materialize_constant(results_df, mapping_rule['predicate_constant'])
    elif mapping_rule['predicate_reference']:
        results_df = _materialize_reference(
            results_df, mapping_rule['predicate_reference'], columns_alias='child_')
    if parent_triples_map_rule['subject_template']:
        results_df = _materialize_template(
            results_df, parent_triples_map_rule['subject_template'],
            termtype=parent_triples_map_rule['subject_termtype'], columns_alias='parent_')
    elif parent_triples_map_rule['subject_constant']:
        results_df = _materialize_constant(results_df, parent_triples_map_rule['subject_constant'],
                                           termtype=parent_triples_map_rule['subject_termtype'])
    elif parent_triples_map_rule['subject_reference']:
        results_df = _materialize_reference(
            results_df, parent_triples_map_rule['subject_reference'],
            termtype=parent_triples_map_rule['subject_termtype'], columns_alias='parent_')

    return set(results_df['triple'])


def _materialize_mapping_rule_terms(results_df, mapping_rule):
    results_df['triple'] = ''
    if mapping_rule['subject_template']:
        results_df = _materialize_template(results_df, mapping_rule['subject_template'],
                                           termtype=mapping_rule['subject_termtype'])
    elif mapping_rule['subject_constant']:
        results_df = _materialize_constant(results_df, mapping_rule['subject_constant'],
                                           termtype=mapping_rule['subject_termtype'])
    elif mapping_rule['subject_reference']:
        results_df = _materialize_reference(results_df, mapping_rule['subject_reference'],
                                            termtype=mapping_rule['subject_termtype'])
    if mapping_rule['predicate_template']:
        results_df = _materialize_template(results_df, mapping_rule['predicate_template'])
    elif mapping_rule['predicate_constant']:
        results_df = _materialize_constant(results_df, mapping_rule['predicate_constant'])
    elif mapping_rule['predicate_reference']:
        results_df = _materialize_reference(results_df, mapping_rule['predicate_reference'])
    if mapping_rule['object_template']:
        results_df = _materialize_template(results_df, mapping_rule['object_template'],
                                           termtype=mapping_rule['object_termtype'],
                                           language_tag=mapping_rule['object_language'],
                                           datatype=mapping_rule['object_datatype'])
    elif mapping_rule['object_constant']:
        results_df = _materialize_constant(results_df, mapping_rule['object_constant'],
                                           termtype=mapping_rule['object_termtype'],
                                           language_tag=mapping_rule['object_language'],
                                           datatype=mapping_rule['object_datatype'])
    elif mapping_rule['object_reference']:
        results_df = _materialize_reference(results_df, mapping_rule['object_reference'],
                                            termtype=mapping_rule['object_termtype'],
                                            language_tag=mapping_rule['object_language'],
                                            datatype=mapping_rule['object_datatype'])

    return set(results_df['triple'])


def _materialize_mapping_rule(mapping_rule, subject_maps_df, config):
    triples = set()

    references = _get_references_in_mapping_rule(mapping_rule)

    if mapping_rule['object_parent_triples_map']:
        parent_triples_map_rule = \
            subject_maps_df[subject_maps_df.triples_map_id == mapping_rule['object_parent_triples_map']].iloc[0]
        parent_references = _get_references_in_mapping_rule(parent_triples_map_rule, only_subject_map=True)

        for key, join_condition in eval(mapping_rule['join_conditions']).items():
            parent_references.add(join_condition['parent_value'])
            references.add(join_condition['child_value'])

        sql_query = relational_source.build_sql_join_query(config, mapping_rule, parent_triples_map_rule,
                                                                 references, parent_references)
        db_connection = relational_source.relational_db_connection(config, mapping_rule['source_name'])
        for query_results_chunk_df in pd.read_sql(sql_query, con=db_connection, chunksize=int(config.get('CONFIGURATION', 'chunksize')), coerce_float=config.getboolean('CONFIGURATION', 'coerce_float')):
            query_results_chunk_df = utils.dataframe_columns_to_str(query_results_chunk_df)
            triples.update(_materialize_join_mapping_rule_terms(query_results_chunk_df, mapping_rule, parent_triples_map_rule))
        db_connection.close()

    else:
        sql_query = relational_source.build_sql_query(config, mapping_rule, references)
        db_connection = relational_source.relational_db_connection(config, mapping_rule['source_name'])
        for query_results_chunk_df in pd.read_sql(sql_query, con=db_connection, chunksize=int(config.get('CONFIGURATION', 'chunksize')), coerce_float=config.getboolean('CONFIGURATION', 'coerce_float')):
            query_results_chunk_df = utils.dataframe_columns_to_str(query_results_chunk_df)
            triples.update(_materialize_mapping_rule_terms(query_results_chunk_df, mapping_rule))
        db_connection.close()

    return triples


def materialize_mapping_partition(mapping_partition, subject_maps_df, config):
    triples = set()
    for i, mapping_rule in mapping_partition.iterrows():
        triples.update(_materialize_mapping_rule(mapping_rule, subject_maps_df, config))
    utils.triples_to_file(triples, config, mapping_partition.iloc[0]['mapping_partition'])

    return len(triples)


def materialize(mappings_df, config):
    subject_maps_df = utils.get_subject_maps(mappings_df)
    mapping_partitions = [group for _, group in mappings_df.groupby(by='mapping_partition')]

    utils.prepare_output_dir(config, len(mapping_partitions))

    if int(config.get('CONFIGURATION', 'number_of_processes')) == 1:
        num_triples = 0
        for mapping_partition in mapping_partitions:
            num_triples += materialize_mapping_partition(mapping_partition, subject_maps_df, config)
    else:
        pool = mp.Pool(int(config.get('CONFIGURATION', 'number_of_processes')))
        num_triples = sum(pool.starmap(materialize_mapping_partition, zip(mapping_partitions, repeat(subject_maps_df), repeat(config))))

    logging.info(str(num_triples) + ' triples generated in total.')

    if len(mapping_partitions) > 1:
        # if there is more than one mapping partitions, unify the parts
        utils.unify_triple_files(config)
