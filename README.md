# Google quantum supremacy circuit generator
```
python supremacy_generator.py -h
```
for help information

# circuit_cutting
## Getting Started

### Prerequisites

Requires a small change to the Qiskit source code.

After creating a python virtual environment and installing Qiskit,

```
python3 -m venv my_venv

pip install qiskit
```

Modify the file at

```
my_venv/lib/python3.7/site-packages/qiskit/dagcircuit/dagnode.py
```

By adding the following text:

```
@cargs.setter
def cargs(self, new_cargs):
    """Sets the cargs to be the given list of cargs"""
    self.data_dict['cargs'] = new_cargs
```
### variables explanation
complete_path_map
```
key: qubit tuple in the original uncut circuit
value: list(tuple)
(sub circuit index, input qubit tuple in the sub circuit, classical bit tuple to measure to), 
...
(sub circuit index, ancilla qubit tuple)
```
input_wires_mapping
```
key: qubit tuple in the original uncut circuit
value: (tuple) (sub circuit index, input qubit tuple in the sub circuit)
```
translation_dict
```
key: (tuple) (qubit tuple in the original uncut circuit, sub circuit index)
value: (tuple) corresponding qubit tuple in the sub circuit
```
## TODO
### Wei

```
- [] Handle original_dag that already has >1 components
- [x] Easy interface for the uniter
- [x] Cut the circuit into multiple parts
- [] Automatic algorithm to find positions to cut
- [] Is modification to Qiskit source code still needed?
```
### Teague
```
- [] Implement uniter based on sub_circ, wiring, stitches interface
- [] Add quantum_circuit_generator
```
## Future Directions

```
1. Weighted tensor network contraction, considering 'hardness' of each cluster.
```
