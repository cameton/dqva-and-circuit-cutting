from qcg.generators import gen_supremacy, gen_hwea
import MIQCP_searcher as searcher
import cutter
import pickle
import os

circ = gen_supremacy(4,4,8)
hardness, positions, ancilla, d, num_cluster, m = searcher.find_cuts(circ,num_clusters=range(1,5),hw_max_qubit=9)
m.print_stat()
clusters, complete_path_map, K, d = cutter.cut_circuit(circ, positions)
print('Complete path map:')
[print(x,complete_path_map[x]) for x in complete_path_map]
print('*'*200)

dirname = './data'
if not os.path.exists(dirname):
    os.mkdir(dirname)
pickle.dump(circ, open( '%s/full_circ.p'%dirname, 'wb' ) )
pickle.dump(complete_path_map, open( '%s/cpm.p'%dirname, 'wb' ) )
for i, cluster in enumerate(clusters):
    pickle.dump(cluster, open( '%s/cluster_%d_circ.p'%(dirname,i), 'wb' ) )