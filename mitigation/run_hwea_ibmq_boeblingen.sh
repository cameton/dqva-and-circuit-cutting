# NOTE: toggle here to change max qc size, max clusters
echo "Generate evaluator input"
python generate_evaluator_input.py --min-qubit 2 --max-qubit 9 --max-clusters 3 --device-name ibmq_boeblingen --circuit-type hwea 2>&1 | tee ./logs/hwea_generator_logs.txt

{
echo "Running saturated hardware evaluator"
mpiexec -n 2 python evaluator_prob.py --device-name ibmq_boeblingen --circuit-type hwea --shots-mode saturated --evaluation-method hardware
echo "Running job submittor"
python hardware_job_submittor.py --device-name ibmq_boeblingen --circuit-type hwea --shots-mode saturated 2>&1 | tee ./logs/hwea_hw_job_submittor_logs.txt
echo "Running reconstruction"
python uniter_prob.py --device-name ibmq_boeblingen --circuit-type hwea --shots-mode saturated --evaluation-method hardware 2>&1 | tee ./logs/hwea_uniter_logs.txt
} &
P1=$!

{
echo "Running sametotal hardware evaluator"
mpiexec -n 2 python evaluator_prob.py --device-name ibmq_boeblingen --circuit-type hwea --shots-mode sametotal --evaluation-method hardware
echo "Running job submittor"
python hardware_job_submittor.py --device-name ibmq_boeblingen --circuit-type hwea --shots-mode sametotal 2>&1 | tee ./logs/hwea_hw_job_submittor_logs.txt
echo "Running reconstruction"
python uniter_prob.py --device-name ibmq_boeblingen --circuit-type hwea --shots-mode sametotal --evaluation-method hardware 2>&1 | tee ./logs/hwea_uniter_logs.txt
} &
P2=$!

wait $P1 $P2
echo "hwea ibmq_boeblingen DONE"

# echo "Running saturated noisy qasm evaluator"
# mpiexec -n 5 python evaluator_prob.py --device-name ibmq_boeblingen --circuit-type hwea --shots-mode saturated --evaluation-method noisy_qasm_simulator
# echo "Running reconstruction"
# python uniter_prob.py --device-name ibmq_boeblingen --circuit-type hwea --shots-mode saturated --evaluation-method noisy_qasm_simulator 2>&1 | tee ./logs/hwea_uniter_logs.txt

# echo "Running sametotal noisy qasm evaluator"
# mpiexec -n 5 python evaluator_prob.py --device-name ibmq_boeblingen --circuit-type hwea --shots-mode sametotal --evaluation-method noisy_qasm_simulator
# echo "Running reconstruction"
# python uniter_prob.py --device-name ibmq_boeblingen --circuit-type hwea --shots-mode sametotal --evaluation-method noisy_qasm_simulator 2>&1 | tee ./logs/hwea_uniter_logs.txt

# echo "Running evaluator evaluator"
# mpiexec -n 5 python evaluator_prob.py --device-name ibmq_boeblingen --circuit-type hwea --evaluation-method statevector_simulator
# echo "Running reconstruction"
# python uniter_prob.py --device-name ibmq_boeblingen --circuit-type hwea --evaluation-method statevector_simulator 2>&1 | tee ./logs/hwea_uniter_logs.txt

# python plot.py