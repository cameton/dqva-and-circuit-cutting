#!/usr/bin/env python3

# author: Michael A. Perlin (github.com/perlinm)

import retworkx as rx
import qiskit as qs
import copy

##########################################################################################
# this script cuts a quantum circuit built in qiskit
# cutting is performed using method described in arxiv.org/abs/1904.00102
# developed using qiskit version 0.12.0
##########################################################################################

# get the terminal node of a qubit in a graph
def terminal_node(graph, qubit, termination_type):
    assert( termination_type in [ "in", "out" ] )
    for node in graph._multi_graph.nodes():
        if node.type == termination_type and node.wire == qubit:
            return node

# accept a circuit graph (i.e. in DAG form), and return a list of tuples:
# [ (< subgraph >, < list of wires used in this subgraph >) ]
# note that the subgraph circuits act on the full registers of the original graph circuit
def disjoint_subgraphs(graph, zip_output = True):

    rx_graph = graph._multi_graph

    # identify all subgraphs of nodes
    rx_subgraphs = [ rx_graph.subgraph(list(subgraph_nodes))
                     for subgraph_nodes in rx.weakly_connected_components(rx_graph) ]

    # convert subgraphs of nodes to circuit graphs
    subgraphs = []
    subgraph_wires = []
    for rx_subgraph in rx_subgraphs:
        # make a copy of the full graph, and remove nodes not in this subgraph
        subgraph = copy.deepcopy(graph)
        for node in subgraph.op_nodes():
            if not any( qs.dagcircuit.DAGNode.semantic_eq(node, rx_node)
                        for rx_node in rx_subgraph.nodes() ):
                subgraph.remove_op_node(node)

        # identify wires used in this subgraph circuit
        wires = { node.wire for node in rx_subgraph.nodes() if node.type == "in" }

        subgraphs.append(subgraph)
        subgraph_wires.append(wires)

    if zip_output: return zip(subgraphs, subgraph_wires)
    else: return subgraphs, subgraph_wires

# "trim" a circuit graph (i.e. in DAG form) by eliminating unused bits
# optionally accept a set of all used wires (with a promise that the set is correct)
# return trimmed graph, as well as a dictionary mapping old wires to new ones
def trimmed_graph(graph, graph_wires = None, qreg_name = "q", creg_name = "c"):
    # if we were not told which wires are used, figure it out
    if graph_wires is None:
        graph_wires = set()

        # identify all subgraphs
        rx_subgraphs = rx.connected_component_subgraphs(graph.to_networkx().to_undirected())
        for rx_subgraph in rx_subgraphs:
            # if there is only one edge in this subgraph, ignore it; it is an empty wire
            if len(rx_subgraph.edges()) == 1: continue

            # otherwise, add all wires from input nodes
            graph_wires.update({ node.wire for node in rx_subgraph if node.type == "in" })

    # construct map from old bits to new ones
    # qiskit refuses to construct empty registers, so we have to cover a few possible cases...
    old_qubits = [ wire for wire in graph_wires
                   if type(wire.register) is qs.circuit.quantumregister.QuantumRegister
                   or type(wire.register) is qs.circuit.quantumregister.AncillaRegister ]
    old_clbits = [ wire for wire in graph_wires
                   if type(wire.register) is qs.circuit.classicalregister.ClassicalRegister ]

    if len(old_qubits) > 0 and len(old_clbits) > 0:
        new_qubits = qs.QuantumRegister(len(old_qubits), qreg_name)
        new_clbits = qs.ClassicalRegister(len(old_clbits), creg_name)
        trimmed_circuit = qs.QuantumCircuit(new_qubits, new_clbits)
    elif len(old_qubits) > 0 and len(old_clbits) == 0:
        new_qubits = qs.QuantumRegister(len(old_qubits), qreg_name)
        new_clbits = []
        trimmed_circuit = qs.QuantumCircuit(new_qubits)
    elif len(old_qubits) == 0 and len(old_clbits) > 0:
        new_qubits = []
        new_clbits = qs.ClassicalRegister(len(old_clbits), creg_name)
        trimmed_circuit = qs.QuantumCircuit(new_clbits)
    else:
        trimmed_circuit = qs.QuantumCircuit()

    register_map = list(zip(old_qubits, new_qubits)) + list(zip(old_clbits, new_clbits))
    register_map = { old_bit : new_bit for old_bit, new_bit in register_map }

    # add all operations to the trimmed circuit
    for node in graph.topological_op_nodes():
        new_qargs = [ register_map[qubit] for qubit in node.qargs ]
        new_cargs = [ register_map[clbit] for clbit in node.cargs ]
        trimmed_circuit.append(node.op, qargs = new_qargs, cargs = new_cargs)

    return qs.converters.circuit_to_dag(trimmed_circuit), register_map

# accepts a circuit and list of cuts in the format (wire, op_number),
#   where op_number is the number of operations performed on the wire before the cut
# returns:
# (i) a list of subcircuits (as qiskit QuantumCircuit objects)
# (ii) a "path map", or a dictionary mapping a wire in the original circuit to
#        a list of wires in subcircuits traversed by the original wire:
#      { < wire in original circuit > :
#        [ ( < index of subcircuit  >, < wire in subcircuit > ) ] }
def cut_circuit(circuit, cuts, qreg_name = "q", creg_name = "c"):
    if len(cuts) == 0: return [ circuit.copy() ], {}

    # assert that all cut wires are part of a quantum register
    assert(all( type(wire) is qs.circuit.quantumregister.Qubit
                for wire, _ in cuts ))

    # all wires in the original circuit
    circuit_wires = circuit.qubits + circuit.clbits

    # initialize new qubit register and construct total circuit graph
    new_reg_name = "_".join(set( wire.register.prefix for wire in circuit_wires )) + "_new"
    new_register = qs.QuantumRegister(len(cuts),new_reg_name)
    new_wires = iter(new_register)
    graph = qs.converters.circuit_to_dag(circuit.copy())
    graph.add_qreg(new_register)
    node_idx = { node : idx for node, idx in zip(graph._multi_graph.nodes(),
                                                 graph._multi_graph.node_indexes()) }
    def _add_edge(node1, node2, **kwargs):
        graph._multi_graph.add_edge(node_idx[node1], node_idx[node2], kwargs)
    def _remove_edge(node1, node2, data = None):
        idx1, idx2 = node_idx[node1], node_idx[node2]
        # todo: remove "not data"
        if data is None or len(graph._multi_graph.get_all_edge_data(idx1, idx2)) == 1:
            # there is only one edge between the given nodes
            graph._multi_graph.remove_edge(idx1, idx2)
        else:
            # there are multiple edges between the given nodes
            # determine the index of the given edge and remove it by index
            edge_iterator = zip(graph._multi_graph.edge_list(),
                                graph._multi_graph.edges())
            for edge_idx, ( ( _idx1, _idx2 ), _data ) in enumerate(edge_iterator):
                if _idx1 != idx1 or _idx2 != idx2: continue
                if all( _data[key] == data[key] for key in data.keys() ):
                    graph._multi_graph.remove_edge_from_index(edge_idx)
                    break

    # TODO: deal with barriers properly
    # barriers currently interfere with splitting a graph into subgraphs
    graph.remove_all_ops_named("barrier")

    # tuples identifying which old/new wires to stitch together
    stitches = {}

    # loop over all cuts from last to first
    for cut_wire, cut_location in sorted(cuts, key = lambda cut : -cut[1]):

        # identify terminal node of the wire we're cutting
        cut_wire_out = terminal_node(graph, cut_wire, "out")

        # identify the node before which to cut
        wire_nodes = [ node for node in graph.topological_op_nodes()
                       if cut_wire in node.qargs ]
        cut_node = wire_nodes[cut_location]

        # identify all nodes downstream of this one
        cut_descendants = graph.descendants(cut_node)

        # identify the new wire to use
        new_wire = next(new_wires)
        new_wire_in = terminal_node(graph, new_wire, "in")
        new_wire_out = terminal_node(graph, new_wire, "out")
        _remove_edge(new_wire_in, new_wire_out)

        # replace all edges on this wire as appropriate
        for edge in graph.edges():
            if edge[2]["wire"] != cut_wire: continue

            # if this edge ends at the node at which we're cutting, splice in the new wire
            if cut_wire in edge[0].qargs and edge[1] == cut_node:
                _remove_edge(*edge[:2])
                _add_edge(edge[0], cut_wire_out,
                          name = f"{cut_wire.register.name}[{cut_wire.index}]",
                          wire = cut_wire)
                _add_edge(new_wire_in, edge[1],
                          name = f"{new_wire.register.name}[{new_wire.index}]",
                          wire = new_wire)
                continue # we are definitely done with this edge

            # fix downstream references to the cut wire (in all edges)
            if edge[1] in cut_descendants:
                # there may be multiple edges between the nodes in `edge`
                # so pass all data to `_remove_edge` to remove the correct edge
                _remove_edge(*edge)
                _add_edge(*edge[:2],
                          name = f"{new_wire.register.name}[{new_wire.index}]",
                          wire = new_wire)

            # replace downstream terminal node of the cut wire by that of the new wire
            if edge[1] == cut_wire_out:
                _remove_edge(*edge[:2])
                _add_edge(edge[0], new_wire_out,
                          name = f"{new_wire.register.name}[{new_wire.index}]",
                          wire = new_wire)

        ### end loop over edges

        # fix downstream references to the cut wire (in all nodes)
        for node in [ cut_node ] + list(cut_descendants):
            if node.type == "op" and cut_wire in node.qargs:
                node.qargs[node.qargs.index(cut_wire)] = new_wire

        # fix references to the cut wire in the set of stitches
        stitches = { start if start != cut_wire else new_wire :
                     end if end != cut_wire else new_wire
                     for start, end in stitches.items() }

        # identify the old/new wires to stitch together
        stitches[cut_wire] = new_wire

    ### end loop over cuts

    # split the total circuit graph into subgraphs
    subgraphs, subgraph_wires = disjoint_subgraphs(graph, zip_output = False)

    # trim subgraphs, eliminating unused bits
    trimmed_subgraphs, subgraph_wire_maps \
        = zip(*[ trimmed_graph(subgraph, wires, qreg_name, creg_name)
                 for subgraph, wires in zip(subgraphs, subgraph_wires) ])

    # construct a path map for bits (both quantum and classical) through
    #   the "extended circuit" (i.e. original circuit with ancillas)
    bit_path_map = { circuit_wire : [ circuit_wire ]
                     for circuit_wire in circuit_wires }
    for circuit_wire, path in bit_path_map.items():
        while path[-1] in stitches.keys():
            path.append(stitches[path[-1]])

    # construct a map from wires in the extended circuit to wires in the subcircuits
    subcirc_wire_map = { extended_circuit_wire : ( subcirc_idx, subcirc_wire )
                         for subcirc_idx, wire_map in enumerate(subgraph_wire_maps)
                         for extended_circuit_wire, subcirc_wire in wire_map.items() }

    # construct a path map for wires in the original circuit through subcirc wires
    wire_path_map = { circuit_wire : tuple( subcirc_wire_map[wire] for wire in path )
                      for circuit_wire, path in bit_path_map.items() }

    # convert the subgraphs into QuantumCircuit objects
    subcircuits = [ qs.converters.dag_to_circuit(graph)
                    for graph in trimmed_subgraphs ]
    return subcircuits, wire_path_map
