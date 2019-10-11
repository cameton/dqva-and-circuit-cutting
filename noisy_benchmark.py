import pickle
import os
import subprocess
from time import time
import numpy as np
from qcg.generators import gen_supremacy, gen_hwea
import MIQCP_searcher as searcher
import cutter
import evaluator_prob as evaluator
import uniter_prob as uniter
from scipy.stats import wasserstein_distance
from qiskit import Aer, IBMQ, execute
from qiskit.providers.aer import noise
from qiskit.converters import circuit_to_dag, dag_to_circuit
from qiskit.transpiler.passes import NoiseAdaptiveLayout

num_shots = int(1e5)
provider = IBMQ.load_account()
device = provider.get_backend('ibmq_16_melbourne')
properties = device.properties()
coupling_map = device.configuration().coupling_map
noise_model = noise.device.basic_device_noise_model(properties)
basis_gates = noise_model.basis_gates

times = {'searcher':[],'evaluator':[],'uniter':[]}
num_qubits = []
max_qubit = 5
dirname = './data'
if not os.path.exists(dirname):
    os.mkdir(dirname)

for dimension in [[2,3]]:
    i,j = dimension
    print('-'*200)
    print('%d * %d supremacy circuit'%(i,j))

    # Generate a circuit
    circ = gen_supremacy(i,j,8,order='75601234')
    dag = circuit_to_dag(circ)
    noise_mapper = NoiseAdaptiveLayout(properties)
    noise_mapper.run(dag)
    initial_layout = noise_mapper.property_set['layout']
    
    print('Evaluating full circuit')
    sv_noiseless_fc = evaluator.simulate_circ(circ=circ,backend='statevector_simulator',noisy=False,qasm_info=None)

    qasm_info = [None,None,None,num_shots,None]
    qasm_noiseless_fc = evaluator.simulate_circ(circ=circ,backend='qasm_simulator',noisy=False,qasm_info=qasm_info)

    qasm_info = [noise_model,coupling_map,basis_gates,num_shots,None]
    qasm_noisy_fc = evaluator.simulate_circ(circ=circ,backend='qasm_simulator',noisy=True,qasm_info=qasm_info)

    qasm_info = [noise_model,coupling_map,basis_gates,num_shots,initial_layout]
    qasm_noisy_na_fc = evaluator.simulate_circ(circ=circ,backend='qasm_simulator',noisy=True,qasm_info=qasm_info)

    # Looking for a cut
    searcher_begin = time()
    hardness, positions, ancilla, d, num_cluster, m = searcher.find_cuts(circ,num_clusters=range(1,5),hw_max_qubit=max_qubit,evaluator_weight=1)
    searcher_time = time() - searcher_begin
    m.print_stat()

    if len(positions)>0:
        clusters, complete_path_map, K, d = cutter.cut_circuit(circ, positions)
        print('Complete path map:')
        [print(x,complete_path_map[x]) for x in complete_path_map]

        qasm_info = [noise_model,coupling_map,basis_gates,num_shots,initial_layout]
        pickle.dump([clusters,complete_path_map,qasm_info], open('%s/evaluator_input.p'%dirname,'wb'))

        # Evaluate the clusters
        evaluator_begin = time()
        for cluster_idx in range(len(clusters)):
            print('MPI evaluator on cluster %d'%cluster_idx)
            subprocess.call(['mpiexec','-n','5','python','evaluator_prob.py',
            '--cluster-idx','%d'%cluster_idx,
            '--backend','qasm_simulator','--noisy','--dirname','%s'%dirname])
        evaluator_time = time()-evaluator_begin

        all_cluster_prob = []
        for cluster_idx in range(len(clusters)):
            cluster_prob = pickle.load( open('%s/cluster_%d_prob.p'%(dirname,cluster_idx), 'rb' ))
            all_cluster_prob.append(cluster_prob)

        # Reconstruct the circuit
        uniter_begin = time()
        qasm_noisy_na_cutting = uniter.reconstruct(complete_path_map, circ, clusters, all_cluster_prob)
        uniter_time = time()-uniter_begin
    
    else:
        qasm_noisy_na_cutting = evaluator.simulate_circ(circ=circ,backend='qasm_simulator',noisy=True,qasm_info=qasm_info)
        evaluator_time = 0
        uniter_time = 0
    
    qasm_distance = wasserstein_distance(sv_noiseless_fc,qasm_noiseless_fc)
    qasm_noise_distance = wasserstein_distance(sv_noiseless_fc,qasm_noisy_fc)
    qasm_noise_na_distance = wasserstein_distance(sv_noiseless_fc,qasm_noisy_na_fc)
    qasm_noise_na_cutting_distance = wasserstein_distance(sv_noiseless_fc,qasm_noisy_na_cutting)
    
    times['searcher'].append(searcher_time)
    times['evaluator'].append(evaluator_time)
    times['uniter'].append(uniter_time)
    num_qubits.append(i*j)
    print('distance due to qasm = %.3e'%qasm_distance)
    print('distance due to qasm + noise = %.3e'%qasm_noise_distance)
    print('distance due to qasm + noise + noise-adaptive = %.3e'%qasm_noise_na_distance)
    print('distance due to qasm + noise + noise-adaptive + cutting = %.3e'%qasm_noise_na_cutting_distance)
    print('searcher time = %.3f seconds'%searcher_time)
    print('evaluator time = %.3f seconds'%evaluator_time)
    print('uniter time = %.3f seconds'%uniter_time)
    print('-'*200)
print('*'*200)
# print(times)
# print('num qubits:',num_qubits)

# pickle.dump([num_qubits,times,qasm_distances,qasm_noise_distances,qasm_noise_cutting_distances], open('%s/noiseless_fidelity_benchmark.p'%dirname,'wb'))