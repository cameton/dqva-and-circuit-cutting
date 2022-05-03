#!/usr/bin/env python
import glob
import networkx as nx

dirs = []
for n in [18, 26]:
    temp_dirs = glob.glob('N{}_d3_graphs*'.format(n))
    dirs.extend(temp_dirs)
print('Dirs:', dirs)

for folder in dirs:
    n = int(folder.split('_')[0][1:])
    d = int(folder.split('_')[1][1:])
    print('Nodes: {}, degree: {}'.format(n, d))

    for j in range(50, 60):
        G = nx.random_regular_graph(d, n)
        edges = list(G.edges())

        with open(folder+'/G{}.txt'.format(j+1), 'w') as fn:
            edgestr = ''.join(['{}, '.format(e) for e in edges])
            edgestr = edgestr.strip(', ')
            fn.write(edgestr)

