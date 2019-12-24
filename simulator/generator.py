import pickle
import os
from time import time
import numpy as np
from qcg.generators import gen_supremacy, gen_hwea, gen_BV, gen_qft, gen_sycamore
import utils.MIQCP_searcher as searcher
import utils.cutter as cutter
from utils.helper_fun import evaluate_circ, get_evaluator_info, get_circ_saturated_shots, reverseBits, get_filename, read_file, factor_int
import argparse
from qiskit import IBMQ
import copy
import math

def gen_secret(num_qubit):
    num_digit = num_qubit-1
    num = 2**num_digit-1
    num = bin(num)[2:]
    num_with_zeros = str(num).zfill(num_digit)
    return num_with_zeros

def evaluate_full_circ(circ, total_shots, device_name, fields):
    print('evaluate fc starts here')
    uniform_p = 1.0/np.power(2,len(circ.qubits))
    uniform_prob = [uniform_p for i in range(np.power(2,len(circ.qubits)))]
    fc_evaluations = {}

    if 'sv_noiseless' in fields:
        print('Evaluating fc state vector')
        sv_noiseless_fc = evaluate_circ(circ=circ,backend='statevector_simulator',evaluator_info=None)
    else:
        sv_noiseless_fc = uniform_prob
    
    if 'qasm' in fields:
        print('Evaluating fc qasm, %d shots'%total_shots)
        qasm_evaluator_info = {'num_shots':total_shots}
        qasm_noiseless_fc = evaluate_circ(circ=circ,backend='noiseless_qasm_simulator',evaluator_info=qasm_evaluator_info)
    else:
        qasm_noiseless_fc = uniform_prob

    if 'qasm+noise' in fields:
        print('Evaluating fc qasm + noise, %d shots'%total_shots)
        qasm_noise_evaluator_info = get_evaluator_info(circ=circ,device_name=device_name,
        fields=['device','basis_gates','coupling_map','properties','initial_layout','noise_model'])
        qasm_noise_evaluator_info['num_shots'] = total_shots
        execute_begin = time()
        qasm_noisy_fc = evaluate_circ(circ=circ,backend='noisy_qasm_simulator',evaluator_info=qasm_noise_evaluator_info)
        print('%.3e seconds'%(time()-execute_begin))
    else:
        qasm_noisy_fc = uniform_prob

    fc_evaluations.update({'sv_noiseless':sv_noiseless_fc,
    'qasm':qasm_noiseless_fc,
    'qasm+noise':qasm_noisy_fc})
    print('evaluate fc ends here')

    return fc_evaluations

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='generate evaluator inputs')
    parser.add_argument('--min-qubit', metavar='N', type=int,help='Benchmark minimum number of HW qubits')
    parser.add_argument('--max-qubit', metavar='N', type=int,help='Benchmark maximum number of HW qubits')
    parser.add_argument('--max-clusters', metavar='N', type=int,help='max number of clusters to split into')
    parser.add_argument('--device-name', metavar='S',type=str,help='IBM device')
    parser.add_argument('--circuit-type', metavar='S', type=str,help='which circuit input file to run')
    args = parser.parse_args()

    assert args.circuit_type in ['supremacy','hwea','bv','qft','sycamore']

    dirname, evaluator_input_filename = get_filename(experiment_name='simulator',circuit_type=args.circuit_type,device_name=args.device_name,field='evaluator_input',evaluation_method=None,shots_mode=None)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    print('-'*50,'Generator','-'*50,flush=True)
    evaluator_input = read_file(dirname+evaluator_input_filename)
    print('Existing cases :',evaluator_input.keys())

    evaluator_info = get_evaluator_info(circ=None,device_name=args.device_name,fields=['properties','device'])
    device_size = len(evaluator_info['properties'].qubits)

    # NOTE: toggle circuits to benchmark
    dimension_l = np.arange(3,11)
    cases_to_run = {}
    counter = 1
    total_cases = (args.max_qubit-args.min_qubit+1)*len(dimension_l)
    for cluster_max_qubit in range(args.min_qubit,args.max_qubit+1):
        for dimension in dimension_l:
            i,j = factor_int(dimension)
            full_circuit_size = i*j
            case = (cluster_max_qubit,full_circuit_size)
            if full_circuit_size<=cluster_max_qubit or full_circuit_size>device_size or (cluster_max_qubit-1)*args.max_clusters<full_circuit_size:
                print('Case {} skipped'.format(case))
                print('%d/%d cases'%(counter,total_cases))
                counter += 1
                print('-'*100)
                continue
            
            if case in evaluator_input:
                print('Case {} exists'.format(case))
                print('%d/%d cases'%(counter,total_cases))
                counter += 1
                print('-'*100)
                continue
            else:
                print('-'*100)
                print('Case {}'.format(case))
                case_dict = {}
                for existing_case in evaluator_input:
                    if full_circuit_size == existing_case[1]:
                        case_dict['full_circ'] = evaluator_input[existing_case]['full_circ']
                        case_dict['fc_shots'] = evaluator_input[existing_case]['fc_shots']
                        case_dict['fc_evaluations'] = evaluator_input[existing_case]['fc_evaluations']
                        break
                    else:
                        continue
                if case_dict != {}:
                    print('Use existing full circuit')
                    full_circ = case_dict['full_circ']

                    searcher_begin = time()
                    hardness, positions, ancilla, d, num_cluster, m = searcher.find_cuts(circ=full_circ,reconstructor_runtime_params=[4.275e-9,6.863e-1],reconstructor_weight=0,
                    num_clusters=range(2,min(len(full_circ.qubits),args.max_clusters)+1),cluster_max_qubit=cluster_max_qubit)
                    searcher_time = time() - searcher_begin
                    if m == None:
                        print('Case {} is not feasible'.format(case))
                        print('%d/%d cases'%(counter,total_cases))
                        counter += 1
                        print('-'*100)
                        continue
                    else:
                        m.print_stat()
                        clusters, complete_path_map, K, d = cutter.cut_circuit(full_circ, positions)
                        case_dict['searcher_time'] = searcher_time
                        case_dict['clusters'] = clusters
                        case_dict['complete_path_map'] = complete_path_map
                        pickle.dump({case:case_dict},open(dirname+evaluator_input_filename,'ab'))
                        print('Case {} added'.format(case))
                        print('%d/%d cases'%(counter,total_cases))
                        counter += 1
                        evaluator_input = read_file(dirname+evaluator_input_filename)
                        print('-'*100)
                else:
                    print('Generate new full circuit')
                    if args.circuit_type == 'supremacy':
                        full_circ = gen_supremacy(i,j,8)
                    elif args.circuit_type == 'hwea':
                        full_circ = gen_hwea(i*j,1)
                    elif args.circuit_type == 'bv':
                        full_circ = gen_BV(gen_secret(i*j),barriers=False)
                    elif args.circuit_type == 'qft':
                        full_circ = gen_qft(width=i*j, barriers=False)
                    elif args.circuit_type == 'sycamore':
                        full_circ = gen_sycamore(i,j,8)
                    searcher_begin = time()
                    hardness, positions, ancilla, d, num_cluster, m = searcher.find_cuts(circ=full_circ,reconstructor_runtime_params=[4.275e-9,6.863e-1],reconstructor_weight=0,
                    num_clusters=range(2,min(len(full_circ.qubits),args.max_clusters)+1),cluster_max_qubit=cluster_max_qubit)
                    searcher_time = time() - searcher_begin
                    if m == None:
                        print('Case {} is not feasible'.format(case))
                        print('%d/%d cases'%(counter,total_cases))
                        counter += 1
                        print('-'*100)
                        continue
                    else:
                        m.print_stat()
                        clusters, complete_path_map, K, d = cutter.cut_circuit(full_circ, positions)
                        fc_shots = get_circ_saturated_shots(circs=[full_circ],device_name=args.device_name)[0]
                        print('saturated fc shots = %d'%(fc_shots),flush=True)
                        case_dict['full_circ'] = full_circ
                        case_dict['fc_shots'] = fc_shots
                        case_dict['searcher_time'] = searcher_time
                        case_dict['clusters'] = clusters
                        case_dict['complete_path_map'] = complete_path_map
                        fields_to_run = ['sv_noiseless','qasm','qasm+noise']
                        fc_evaluations = evaluate_full_circ(circ=full_circ,total_shots=fc_shots,device_name=args.device_name,fields=fields_to_run)
                        case_dict['fc_evaluations'] = fc_evaluations
                        pickle.dump({case:case_dict},open(dirname+evaluator_input_filename,'ab'))
                        print('Case {} added'.format(case))
                        print('%d/%d cases'%(counter,total_cases))
                        counter += 1
                        evaluator_input = read_file(dirname+evaluator_input_filename)
                        print('-'*100)