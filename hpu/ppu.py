from qiskit import QuantumCircuit
from cutqc.initialization import check_valid
from cutqc.cutter import find_cuts
from cutqc.evaluator import find_subcircuit_O_rho_qubits, find_all_combinations, get_subcircuit_instance
from cutqc.post_process import get_combinations, build
from hpu.component import ComponentInterface

class PPU(ComponentInterface):
    '''
    Pre-processing Unit
    cuts an input circuit
    returns the cut_solution found and control signals for the MUX to attribute shots
    '''
    def __init__(self, config):
        self.max_subcircuit_qubit = config['max_subcircuit_qubit']
        self.num_subcircuits = config['num_subcircuits']
        self.max_cuts = config['max_cuts']
        self.verbose = config['verbose']

    def run(self, circuit):
        assert isinstance(circuit,QuantumCircuit)
        valid = check_valid(circuit=circuit)
        assert valid
        self.circuit = circuit

        cut_solution = find_cuts(circuit=self.circuit,
        max_subcircuit_qubit=self.max_subcircuit_qubit,
        num_subcircuits=self.num_subcircuits,
        max_cuts=self.max_cuts,verbose=self.verbose)
        if len(cut_solution)>0:
            full_circuit = cut_solution['circuit']
            subcircuits = cut_solution['subcircuits']
            complete_path_map = cut_solution['complete_path_map']

            circ_dict = {}
            all_indexed_combinations = {}
            for subcircuit_idx, subcircuit in enumerate(subcircuits):
                O_qubits, rho_qubits = find_subcircuit_O_rho_qubits(complete_path_map=complete_path_map,subcircuit_idx=subcircuit_idx)
                combinations, indexed_combinations = find_all_combinations(O_qubits, rho_qubits, subcircuit.qubits)
                circ_dict.update(get_subcircuit_instance(subcircuit_idx=subcircuit_idx,subcircuit=subcircuit, combinations=combinations))
                all_indexed_combinations[subcircuit_idx] = indexed_combinations
            cut_solution['subcircuit_instances'] = circ_dict
            cut_solution['all_indexed_combinations'] = all_indexed_combinations

            O_rho_pairs, combinations = get_combinations(complete_path_map=complete_path_map)
            kronecker_terms, _ = build(full_circuit=full_circuit, combinations=combinations,
            O_rho_pairs=O_rho_pairs, subcircuits=subcircuits, all_indexed_combinations=all_indexed_combinations)
            cut_solution['kronecker_terms'] = kronecker_terms

        self.cut_solution = cut_solution

    def get_output(self):
        return self.cut_solution

    def close(self):
        pass