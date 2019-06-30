import numpy as np
import copy
import networkx as nx
from qiskit import QuantumCircuit
from qiskit.dagcircuit.exceptions import DAGCircuitError
from qiskit.dagcircuit.dagnode import DAGNode
from qiskit.circuit import Measure
from qiskit.circuit.quantumregister import QuantumRegister
from qiskit.circuit.classicalregister import ClassicalRegister

def cut_single_edge(original_dag, wire, source_node_idx):
    """Cut a single edge in the original_dag.

    Args:
        wire (Qubit): wire to cut in original_dag
        source_node_idx (int): #op nodes in front of the edge to cut

    Returns:
        DAGCircuit: dag circuit after cutting

    Raises:
        DAGCircuitError: if a leaf node is connected to multiple outputs

    """

    cut_dag = copy.deepcopy(original_dag)

    cut_dag._check_bits([wire], cut_dag.output_map)

    original_out_node = cut_dag.output_map[wire]
    ie = list(cut_dag._multi_graph.predecessors(original_out_node))
    if len(ie) != 1:
        raise DAGCircuitError("output node has multiple in-edges")

    source_node = list(cut_dag.nodes_on_wire(wire=wire, only_ops=True))[source_node_idx]
    dest_node = list(cut_dag.nodes_on_wire(wire=wire, only_ops=True))[source_node_idx+1]

    cut_dag._multi_graph.remove_edge(source_node, dest_node)

    return cut_dag

def cut_edges(original_dag, positions):
    '''Cut multiple edges in the original_dag.

    Args:
        original_dag (DAGCircuit): original dag circuit to cut
        positions (list): list of cutting positions in (qubit, source noce idx) tuples

    Returns:
        DAGCircuit: dag circuit after cutting

    Raises:
        dag after cutting is not successfully splitted

    '''
    cut_dag = copy.deepcopy(original_dag)
    path_order_dict = {}
    for wire in cut_dag.wires:
        path_order_dict[wire] = []

    for position in positions:
        wire, source_node_idx = position
        source_node = list(cut_dag.nodes_on_wire(wire=wire, only_ops=True))[source_node_idx]
        dest_node = list(cut_dag.nodes_on_wire(wire=wire, only_ops=True))[source_node_idx+1]
        cut_dag._multi_graph.remove_edge(source_node, dest_node)
        path_order_dict[wire].append((source_node, dest_node))
    num_components = nx.number_weakly_connected_components(cut_dag._multi_graph)
    if num_components<2:
        raise Exception('Not a split, cut_dag only has %d component' % num_components)
    
    components = list(nx.weakly_connected_components(cut_dag._multi_graph))
    for wire in path_order_dict:
        path = []
        path_order_dict[wire].reverse()
        for link in path_order_dict[wire]:
            source_node = link[0]
            dest_node = link[1]
            for component_idx, component in enumerate(components):
                if source_node in component:
                    source_circ_idx = component_idx
                if dest_node in component:
                    dest_circ_idx = component_idx
            path.append((source_circ_idx, dest_circ_idx))
        path_order_dict[wire] = path
    return cut_dag, path_order_dict

def complete_path_calc(path_order_dict, input_wires_mapping, translation_dict, sub_reg_dicts):
    complete_path_map = {}
    cl_measure_idx = [0 for reg_dict in sub_reg_dicts]
    for wire in path_order_dict:
        complete_path_map[wire] = []
        for link in path_order_dict[wire]:
            source_sub_circ_idx = link[0]
            translation_dict_key = (wire, source_sub_circ_idx)
            qubit_in_tuple = translation_dict[translation_dict_key]
            reg_dict = sub_reg_dicts[source_sub_circ_idx]
            clbit_out_tuple = reg_dict['measure_' + wire[0].name][cl_measure_idx[source_sub_circ_idx]]
            cl_measure_idx[source_sub_circ_idx] += 1
            complete_path_map[wire].append((source_sub_circ_idx, qubit_in_tuple, clbit_out_tuple))

            dest_sub_circ_idx = link[1]
            translation_dict_key = (wire, dest_sub_circ_idx)
            qubit_in_tuple = translation_dict[translation_dict_key]
            complete_path_map[wire].append((dest_sub_circ_idx, qubit_in_tuple))
    return complete_path_map

def update_reg_dict(reg_dict, qubit_tuple, add_measure=False, add_ancilla=False, add_input=False):
    measure_register_name = 'measure_' + qubit_tuple[0].name
    ancilla_register_name = 'ancilla_' + qubit_tuple[0].name
    input_register_name = qubit_tuple[0].name

    if add_measure:
        if measure_register_name in reg_dict:
            reg_dict[measure_register_name] = ClassicalRegister(reg_dict[measure_register_name].size+1, measure_register_name)
        else:
            reg_dict[measure_register_name] = ClassicalRegister(1, measure_register_name)

    if add_ancilla:
        if ancilla_register_name in reg_dict:
            reg_dict[ancilla_register_name] = QuantumRegister(reg_dict[ancilla_register_name].size+1, ancilla_register_name)
        else:
            reg_dict[ancilla_register_name] = QuantumRegister(1, ancilla_register_name)
    
    if add_input:
        if input_register_name in reg_dict:
            reg_dict[input_register_name] = QuantumRegister(reg_dict[input_register_name].size+1, input_register_name)
        else:
            reg_dict[input_register_name] = QuantumRegister(1, input_register_name)
    return reg_dict

def sub_circ_reg_counter(cut_dag, in_out_arg_dict):
    '''Count #registers required in each component.

    Args:
        cut_dag (DAGCircuit): dag circuit after being cut
        in_out_arg_dict (dict): in_out_arg of each wire in each component

    Returns:
        list: list of dict object for # and type of registers in each component.
        key: name of register. value: QuantumRegister or ClassicalRegister

        dict: a dictionary for input wires from the original dag into each component
        key: DAGNode of input wires in original circuit. value: (sub circuit index, bit tuple in the sub circuit)

    '''
    components = list(nx.weakly_connected_components(cut_dag._multi_graph))
    reg_dicts = []
    for component_idx, component in enumerate(components):
        reg_dict = {}
        for key in in_out_arg_dict:
            if key[1] == component_idx:
                has_in, has_out, has_arg = in_out_arg_dict[key]
                add_measure = not has_out and has_arg
                add_ancilla = not has_in and has_arg
                add_input = has_in and has_arg
                reg_dict = update_reg_dict(reg_dict=reg_dict, qubit_tuple=key[0],
                add_measure=add_measure, add_ancilla=add_ancilla, add_input=add_input)
        reg_dicts.append(reg_dict)
    
    input_wires_mapping = {}
    input_reg_idx = [0 for reg_dict in reg_dicts]
    for component_idx, component in enumerate(components):
        for key in in_out_arg_dict:
            if key[1] == component_idx:
                has_in, has_out, has_arg = in_out_arg_dict[key]
                add_input = has_in and has_arg
                if add_input:
                    input_register_name = key[0][0].name
                    input_wires_mapping[key[0]] = (component_idx, 
                    reg_dicts[component_idx][input_register_name][input_reg_idx[component_idx]])
                    input_reg_idx[component_idx] += 1
    return reg_dicts, input_wires_mapping

def contains_wire_nodes(cut_dag):
    components = list(nx.weakly_connected_components(cut_dag._multi_graph))
    
    in_out_arg_dict = {}

    for node in cut_dag.nodes():
        if node.type == 'in':
            # Iterate through all input wires
            for component_idx, component in enumerate(components):
                dict_key = (node.wire, component_idx)
                has_in = False
                has_out = False
                has_arg = False
                for component_node in component:
                    if component_node.type == 'in':
                        if component_node.wire == node.wire:
                            has_in = True
                    elif component_node.type == 'out':
                        if component_node.wire == node.wire:
                            has_out = True
                    elif component_node.type == 'op':
                        if node.wire in component_node.qargs:
                            has_arg = True
                dict_val = (has_in, has_out, has_arg)
                in_out_arg_dict[dict_key] = dict_val
    return in_out_arg_dict

def translation_dict_calc(input_wires_mapping, components, in_out_arg_dict, sub_reg_dicts):
    translation_dict = {}
    cl_measure_idx = [0 for component in components]
    ancilla_idx = [0 for component in components]

    for input_wire in input_wires_mapping:
        for component_idx, component in enumerate(components):
            has_in, has_out, has_arg = in_out_arg_dict[(input_wire, component_idx)]
            if has_arg:
                # Case 001
                if not has_in and not has_out:
                    ancilla_qubit = sub_reg_dicts[component_idx]['ancilla_' + input_wire[0].name][ancilla_idx[component_idx]]
                    measure_clbit = sub_reg_dicts[component_idx]['measure_' + input_wire[0].name][cl_measure_idx[component_idx]]
                    ancilla_idx[component_idx] += 1
                    cl_measure_idx[component_idx] += 1
                    translation_dict_key = (input_wire, component_idx)
                    translation_dict_val = ancilla_qubit
                    translation_dict[translation_dict_key] = translation_dict_val
                # Case 011
                if not has_in and has_out:
                    ancilla_qubit = sub_reg_dicts[component_idx]['ancilla_' + input_wire[0].name][ancilla_idx[component_idx]]
                    ancilla_idx[component_idx] += 1
                    translation_dict_key = (input_wire, component_idx)
                    translation_dict_val = ancilla_qubit
                    translation_dict[translation_dict_key] = translation_dict_val
                # Case 101
                if has_in and not has_out:
                    translated_qubit = input_wires_mapping[input_wire][1]
                    measure_clbit = sub_reg_dicts[component_idx]['measure_' + input_wire[0].name][cl_measure_idx[component_idx]]
                    cl_measure_idx[component_idx] += 1
                    translation_dict_key = (input_wire, component_idx)
                    translation_dict_val = translated_qubit
                    translation_dict[translation_dict_key] = translation_dict_val
                # Case 111
                if has_in and has_out:
                    translated_qubit = input_wires_mapping[input_wire][1]
                    translation_dict_key = (input_wire, component_idx)
                    translation_dict_val = translated_qubit
                    translation_dict[translation_dict_key] = translation_dict_val
    return translation_dict

def generate_sub_circs(cut_dag, positions):
    # wires_being_cut = [x[0] for x in positions]
    in_out_arg_dict = contains_wire_nodes(cut_dag)
    sub_reg_dicts, input_wires_mapping = sub_circ_reg_counter(cut_dag, in_out_arg_dict)
    components = list(nx.weakly_connected_components(cut_dag._multi_graph))
    translation_dict = translation_dict_calc(input_wires_mapping, components, in_out_arg_dict, sub_reg_dicts)

    sub_circs = []
    # print('input wires mapping:\n', input_wires_mapping)
    # print('sub_reg_dicts calculation:\n', sub_reg_dicts)

    # print('translation_dict:')
    # [print(key, translation_dict[key]) for key in translation_dict]

    for component_idx, reg_dict in enumerate(sub_reg_dicts):
        # print('Begin component ', component_idx)
        sub_circ = QuantumCircuit()
        # print('reg_dict: ', reg_dict)
        
        ''' Add the registers '''
        for reg in reg_dict.values():
            sub_circ.add_register(reg)
        # print('added registers in the sub circuit:', sub_circ.qregs, sub_circ.cregs)
        
        ''' Update qargs of nodes '''
        for node in cut_dag.topological_op_nodes():
            if node in components[component_idx]:
                # Component op nodes in topological order
                old_args = node.qargs
                new_args = []
                # print('updating node', node.name)
                for x in old_args:
                    translation_dict_key = (x, component_idx)
                    new_args.append(translation_dict[translation_dict_key])
                node.qargs = new_args
                sub_circ.append(instruction=node.op, qargs=node.qargs, cargs=node.cargs)
        # print('finished component %d\n' % component_idx)
        sub_circs.append(sub_circ)
    return sub_circs