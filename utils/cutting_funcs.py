import sys
import itertools
import random
import time
from typing import List, Tuple

import numpy as np
import networkx as nx

sys.path.append('../')

import qsplit.qsplit_mlrecon_methods as qmm


# (1) idetify cut_nodes and uncut_nodes (nodes incident to a cut and their complement)
# (2) choose "hot nodes": nodes incident to a graph partition,
#       to which we will nonetheless apply a partial mixer in the first mixing layer
# WARNING: this algorithm has combinatorial complexity:
#   O({ #cut_nodes_in_subgraph \choose #max_cuts })
# I am simply assuming that this complexity won't be a problem for now
# if it becomes a problem when we scale up, we should rethink this algorithm
def choose_nodes(graph, subgraphs, cut_edges, max_cuts):
    cut_nodes = []
    for edge in cut_edges:
        cut_nodes.extend(edge)

    # collect subgraph data
    subgraph_A, subgraph_B = subgraphs
    cut_nodes_A = [node for node in subgraph_A.nodes if node in cut_nodes]
    cut_nodes_B = [node for node in subgraph_B.nodes if node in cut_nodes]
    subgraph_cut_nodes = [ (subgraph_A, cut_nodes_A), (subgraph_B, cut_nodes_B) ]

    # compute the cost of each choice of hot nodes
    # hot nodes should all be chosen from one subgraph, so loop over subgraph indices
    choice_cost = {}
    for ext_idx in [ 0, 1 ]:
        # ext_graph: subgraph we're "extending" with nodes from the complement graph
        # ext_cut_nodes: cut_nodes in ext_graph
        ext_graph, ext_cut_nodes = subgraph_cut_nodes[ext_idx]

        # adjacent (complement) graph and cut nodes
        adj_graph, adj_cut_nodes = subgraph_cut_nodes[1-ext_idx]

        # determine the number nodes in adj_cut_nodes that we need to "throw out".
        # nodes that are *not* thrown out are attached to ext_graph in the first mixing layer
        num_to_toss = len(adj_cut_nodes) - max_cuts
        num_to_toss = max(num_to_toss,0)

        # determine size of fragments after circuit cutting.
        # if there are several options (of nodes to toss) with the same "cut cost",
        # these fragment sizes are used to choose between those options
        ext_size = ext_graph.number_of_nodes() + len(adj_cut_nodes) - num_to_toss
        complement_size = subgraphs[1-ext_idx].number_of_nodes()
        frag_sizes = tuple(sorted([ ext_size, complement_size ], reverse = True))

        # if we don't need to throw out any nodes,
        # log a choice_cost of 0 and skip the calculation below
        if num_to_toss == 0:
            choice_cost[ext_idx,()] = (0,) + frag_sizes
            continue

        # for some node (in adj_cut_nodes) that we might throw out
        # (i) determine its neighbors in ext_graph
        # (ii) determine the degrees of those neighbors
        # (iii) add up those degrees
        def single_choice_cost(adj_node):
            return sum([ graph.degree[ext_node]
                         for ext_node in graph.neighbors(adj_node)
                         if ext_node in ext_graph ])

        # loop over all combinations of adjacent nodes that we could throw out
        for toss_nodes in itertools.combinations(adj_cut_nodes, num_to_toss):
             _choice_cost = sum([ single_choice_cost(node) for node in toss_nodes ])
             choice_cost[ext_idx,toss_nodes] = (_choice_cost,) + frag_sizes

    # get the index subgraph we're "extending" and the adjacent nodes we're tossing out
    ext_idx, toss_nodes = min(choice_cost, key = choice_cost.get)
    ext_graph, ext_cut_nodes = subgraph_cut_nodes[ext_idx]

    # determine whether a node in ext_graph has any neighbors in toss_nodes
    def _no_tossed_neighbors(ext_node):
        return not any( neighbor in toss_nodes for neighbor in graph.neighbors(ext_node) )

    # hot nodes = those without neighbors that we are tossing out
    hot_nodes = list(filter(_no_tossed_neighbors, ext_cut_nodes))
    return cut_nodes, hot_nodes


def _is_connected(graph, partition, hot_nodes, subgraph_dict):
    meta_graph = nx.Graph()
    for i in range(len(partition)):
        meta_graph.add_node(i)

    for hot_node in hot_nodes:
        for edge in graph.edges:
            if hot_node in edge:
                subgraph_i = subgraph_dict[edge[0]]
                subgraph_j = subgraph_dict[edge[1]]
                if subgraph_i != subgraph_j:
                    meta_graph.add_edge(subgraph_i, subgraph_j)

    return nx.is_connected(meta_graph)


def _cut_cost(graph, partition, hot_nodes, subgraph_dict, cut_nodes):
    subgraph_appearances = {cut_node: [] for cut_node in cut_nodes}

    for subgraph_idx, subgraph_nodes in enumerate(partition):
        for subgraph_node in subgraph_nodes:
            if (subgraph_node in cut_nodes) and (subgraph_node not in hot_nodes):
                continue
            for partial_mixer_node in list(graph.neighbors(subgraph_node)) + [subgraph_node]:
                if partial_mixer_node in cut_nodes:
                    subgraph_appearances[partial_mixer_node].append(subgraph_idx)

    num_cuts = 0
    for cut_node, appearances in subgraph_appearances.items():
        cut_node_subgraph = subgraph_dict[cut_node]
        for subgraph in set(appearances):
            if cut_node_subgraph != subgraph:
                num_cuts += 1
    return num_cuts


def simple_choose_nodes(graph: nx.Graph, partition: List[List[int]],
                        cut_edges: List[Tuple[int, int]], max_cuts: int,
                        ) -> Tuple[List[int], List[int]]:
    subgraph_dict = {}
    for i, subgraph_nodes in enumerate(partition):
        for node in subgraph_nodes:
            subgraph_dict[node] = i

    cut_nodes = []
    for edge in cut_edges:
        cut_nodes.extend(edge)
    cut_nodes = list(set(cut_nodes))

    # Generate the set of all possible hot node sets
    # NOTE: this is extremely inefficient, for n hot nodes,
    # there are n-choose-1 + n-choose-2 + ... n-choose-n possible hot node sets
    all_possible_hot_nodes = []
    for r in range(1, len(cut_nodes)+1):
        if r > max_cuts:
            break
        for length_r_hot_nodes in itertools.combinations(cut_nodes, r):
            all_possible_hot_nodes.append(length_r_hot_nodes)

    # Eliminate those hot node sets that result in a disconnected graph
    all_connected_hot_nodes = []
    for possible_hot_nodes in all_possible_hot_nodes:
        if _is_connected(graph, partition, possible_hot_nodes, subgraph_dict):
            all_connected_hot_nodes.append(possible_hot_nodes)

    # Eliminate those hot node sets that require cuts > max_cuts
    all_feasible_hot_nodes = []
    for possible_hot_nodes in all_connected_hot_nodes:
        cost = _cut_cost(graph, partition, possible_hot_nodes, subgraph_dict, cut_nodes)
        if cost <= max_cuts:
            all_feasible_hot_nodes.append(possible_hot_nodes)

    # For now, uniform random sampling
    hot_nodes = random.choice(all_feasible_hot_nodes)

    return cut_nodes, list(hot_nodes)


def sim_with_cutting(fragments, wire_path_map, frag_shots, backend, mode="likely",
                     verbose=0):
    """
    A helper function to simulate a fragmented circuit.

    Output:
    probs: dict{bitstring : float}
        Outputs a dictionary containing the simulation results. Keys are the
        bitstrings which were observed and their values are the probability that
        they occurred with.
    """

    # build fragment models
    model_time_start = time.time()

    frag_data = qmm.collect_fragment_data(fragments, wire_path_map,
                                          shots = frag_shots,
                                          tomography_backend = backend)
    direct_models = qmm.direct_fragment_model(frag_data)
    if mode == "direct":
        models = direct_models
    elif mode == "likely":
        likely_models = qmm.maximum_likelihood_model(direct_models)
        models = likely_models
    else:
        raise Exception('Unknown recombination mode:', mode)

    model_time = time.time() - model_time_start

    # recombine models to recover full circuit output
    recombine_time_start = time.time()
    recombined_dist = qmm.recombine_fragment_models(models, wire_path_map)
    recombine_time = time.time() - recombine_time_start

    # print timing info
    if verbose:
        print(f"\tModel time: {model_time:.3f}, Recombine time: {recombine_time:.3f}")

    return recombined_dist
