#!/usr/bin/env python
import argparse, glob, sys, time
from pathlib import Path
from utils import helper_funcs, graph_funcs

def parse_args():
    parser = argparse.ArgumentParser()
    #parser.add_argument('-p', type=str, default=None,
    #                    help='path to DQVA directory')
    parser.add_argument('-g', type=str, default=None,
                        help='Graph file name')
    args = parser.parse_args()
    return args

def main():
    args = parse_args()

    graphfiles = glob.glob(args.g)
    for gfile in graphfiles:
        graphtype = gfile.split('/')[-2]
        graphname = gfile.split('/')[-1].strip('.txt')

        G = graph_funcs.graph_from_file(gfile)
        print('graphtype: {}, graphname: {}'.format(graphtype, graphname))
        print('Loaded graph with {} nodes'.format(len(G.nodes)))

        start = time.time()
        opt_strs, opt_mis = helper_funcs.brute_force_search_memory_efficient(G)
        end = time.time()
        print('Finished brute force search in {:.3f} min'.format((end - start) / 60))

        outdir = 'benchmark_graphs/brute_force_outputs/{}/'.format(graphtype)
        Path(outdir).mkdir(parents=True, exist_ok=True)
        outfile = outdir + graphname + '_brute_force.out'
        with open(outfile, 'w') as fn:
            fn.write('{}, {}\n'.format(graphtype, graphname))
            fn.write('Optimal MIS is {}\n'.format(opt_mis))
            fn.write('Optimal MIS:\n')
            for bitstr in opt_strs:
                fn.write('\t{}, valid: {}\n'.format(bitstr, graph_funcs.is_indset(bitstr, G)))

if __name__ == '__main__':
    main()
