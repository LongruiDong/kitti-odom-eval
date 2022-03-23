# Copyright (C) Huangying Zhan 2019. All rights reserved.
# -*- coding:utf8 -*-
import argparse

from kitti_odometry import KittiEvalOdom

parser = argparse.ArgumentParser(description='KITTI ablation for submmit')
parser.add_argument('--fullresult', type=str, required=True,
                    help="our full Result directory")
parser.add_argument('--dpolresult', type=str, required=True,
                    help="directoin only Result directory")
parser.add_argument('--seqs', 
                    nargs="+",
                    type=int, 
                    help="sequences to be evaluated",
                    default=None)
args = parser.parse_args()

eval_tool = KittiEvalOdom()

full_dir = args.fullresult
dpol_dir = args.dpolresult

eval_tool.rotcomp(full_dir, dpol_dir, 
                    seqs=args.seqs)
