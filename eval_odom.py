# Copyright (C) Huangying Zhan 2019. All rights reserved.
# -*- coding:utf8 -*-
import argparse

from kitti_odometry import KittiEvalOdom

parser = argparse.ArgumentParser(description='KITTI evaluation')
# parser.add_argument('--maxlenth', type=int, required=True, help="select max evaluate lenth: 800(default), 2000", default=800)
parser.add_argument('--result', type=str, required=True,
                    help="Result directory")
parser.add_argument('--align', type=str, 
                    choices=['scale', 'scale_7dof', '7dof', '6dof'],
                    default=None,
                    help="alignment type")
parser.add_argument('--seqs', 
                    nargs="+",
                    type=int, 
                    help="sequences to be evaluated",
                    default=None)
parser.add_argument('--setlenths', 
                    nargs="+",
                    type=int, 
                    help="lengths(m) to be evaluated",
                    default=[100, 200, 300, 400, 500, 600, 700, 800])
args = parser.parse_args()

eval_tool = KittiEvalOdom(args)
gt_dir = "/home/dlr/Project/kitti-odom-eval/dataset/kitti_odom/gt_poses/"
result_dir = args.result

continue_flag = input("Evaluate result in {}? [y/n]".format(result_dir))
if continue_flag == "y":
    eval_tool.eval(
        gt_dir,
        result_dir,
        alignment=args.align,
        seqs=args.seqs,
        )
else:
    print("Double check the path!")
