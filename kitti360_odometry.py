# Copyright (C) Huangying Zhan 2019. All rights reserved.
# -*- coding:utf8 -*-
# 针对kt360 test 中的 12 14两个序列
import sophus as sp #李代数变换需要  https://github.com/craigstar/SophusPy
import copy
from matplotlib import pyplot as plt
import numpy as np
import os
from glob import glob


def scale_lse_solver(X, Y):
    """Least-sqaure-error solver
    Compute optimal scaling factor so that s(X)-Y is minimum
    Args:
        X (KxN array): current data
        Y (KxN array): reference data
    Returns:
        scale (float): scaling factor
    """
    scale = np.sum(X * Y)/np.sum(X ** 2)
    return scale


def umeyama_alignment(x, y, with_scale=False):
    """
    Computes the least squares solution parameters of an Sim(m) matrix
    that minimizes the distance between a set of registered points.
    Umeyama, Shinji: Least-squares estimation of transformation parameters
                     between two point patterns. IEEE PAMI, 1991
    :param x: mxn matrix of points, m = dimension, n = nr. of data points
    :param y: mxn matrix of points, m = dimension, n = nr. of data points
    :param with_scale: set to True to align also the scale (default: 1.0 scale)
    :return: r, t, c - rotation matrix, translation vector and scale factor
    """
    if x.shape != y.shape:
        assert False, "x.shape not equal to y.shape"

    # m = dimension, n = nr. of data points
    m, n = x.shape

    # means, eq. 34 and 35
    mean_x = x.mean(axis=1)
    mean_y = y.mean(axis=1)

    # variance, eq. 36
    # "transpose" for column subtraction
    sigma_x = 1.0 / n * (np.linalg.norm(x - mean_x[:, np.newaxis])**2)

    # covariance matrix, eq. 38
    outer_sum = np.zeros((m, m))
    for i in range(n):
        outer_sum += np.outer((y[:, i] - mean_y), (x[:, i] - mean_x))
    cov_xy = np.multiply(1.0 / n, outer_sum)

    # SVD (text betw. eq. 38 and 39)
    u, d, v = np.linalg.svd(cov_xy)

    # S matrix, eq. 43
    s = np.eye(m)
    if np.linalg.det(u) * np.linalg.det(v) < 0.0:
        # Ensure a RHS coordinate system (Kabsch algorithm).
        s[m - 1, m - 1] = -1

    # rotation, eq. 40
    r = u.dot(s).dot(v)

    # scale & translation, eq. 42 and 41
    c = 1 / sigma_x * np.trace(np.diag(d).dot(s)) if with_scale else 1.0
    t = mean_y - np.multiply(c, r.dot(mean_x))

    return r, t, c


def dict_slice(adict, start, end):
    """对字典切片 都是闭区间

    Args:
        adict (dict): _description_
        start (int): 起始位置
        end (int): 终止位置

    Returns:
        _type_: _description_
    """
    keys = adict.keys()
    dict_slice = {}
    for k in list(keys)[start:end+1]: #前闭后开 故+1
        dict_slice[k] = adict[k]
    return dict_slice


class KittiEvalOdom():
    """Evaluate odometry result
    Usage example:
        vo_eval = KittiEvalOdom()
        vo_eval.eval(gt_pose_txt_dir, result_pose_txt_dir)
    """
    def __init__(self, args): #关于评估长度 为了查看闭环的影响  https://github.com/wh200720041/iscloam/issues/11#issuecomment-666942316
        self.rawlengths = [100, 200, 300, 400, 500, 600, 700, 800] # [250, 500, 750, 1000, 1250, 1500, 1750, 2000] [100, 200, 300, 400, 500, 600, 700, 800]
        # maxlen = int(args.maxlenth)
        # ratio = float(maxlen)/max(self.rawlengths)
        # self.lengths = [int(li * ratio) for li in self.rawlengths]
        # Create evaluation list
        if args.setlenths is None:
            self.lengths = self.rawlengths
        else:
            self.lengths = args.setlenths
        print('evaluate lenths: \n', self.lengths)
        self.num_lengths = len(self.lengths)

    def load_poses_from_txt(self, file_name):
        """Load poses from txt (KITTI format)
        Each line in the file should follow one of the following structures
            (1) idx pose(3x4 matrix in terms of 12 numbers)
            (2) pose(3x4 matrix in terms of 12 numbers)

        Args:
            file_name (str): txt file path
        Returns:
            poses (dict): {idx: 4x4 array}
        """
        f = open(file_name, 'r')
        s = f.readlines()
        f.close()
        poses = {}
        for cnt, line in enumerate(s):
            P = np.eye(4)
            line_split = [float(i) for i in line.split(" ") if i!=""]
            withIdx = len(line_split) == 13
            for row in range(3):
                for col in range(4):
                    P[row, col] = line_split[row*4 + col + withIdx]
            if withIdx:
                frame_idx = line_split[0]
            else:
                frame_idx = cnt
            poses[frame_idx] = P
        return poses

    def trajectory_distances(self, poses):
        """Compute distance for each pose w.r.t frame-0
        Args:
            poses (dict): {idx: 4x4 array}
        Returns:
            dist (float list): distance of each pose w.r.t frame-0
        """
        dist = [0]
        sort_frame_idx = sorted(poses.keys())
        for i in range(len(sort_frame_idx)-1):
            cur_frame_idx = sort_frame_idx[i]
            next_frame_idx = sort_frame_idx[i+1]
            P1 = poses[cur_frame_idx]
            P2 = poses[next_frame_idx]
            dx = P1[0, 3] - P2[0, 3]
            dy = P1[1, 3] - P2[1, 3]
            dz = P1[2, 3] - P2[2, 3]
            dist.append(dist[i]+np.sqrt(dx**2+dy**2+dz**2))
        return dist

    def rotation_error(self, pose_error):
        """Compute rotation error
        Args:
            pose_error (4x4 array): relative pose error
        Returns:
            rot_error (float): rotation error rads
        """
        a = pose_error[0, 0]
        b = pose_error[1, 1]
        c = pose_error[2, 2]
        d = 0.5*(a+b+c-1.0)
        rot_error = np.arccos(max(min(d, 1.0), -1.0))
        return rot_error

    def axisangle_error(self, pose_delta_gt, pose_delta_result):
        """Compute error vector of relative pose's axis angle between gt and est: abs(aa(gt)-aa(result))
        Args:
            pose_delta_gt (4x4 array): relative pose of gt
            pose_delta_result (4x4 array): relative pose of result
        Returns:
            aa_error (3x1 array): error vector rads
        """
        R_gt = sp.to_orthogonal(pose_delta_gt[0:3,0:3])
        R_result = sp.to_orthogonal(pose_delta_result[0:3,0:3])
        SO_gt = sp.SO3(R_gt)
        SO_result = sp.SO3(R_result)
        aa_gt = SO_gt.log()
        aa_result = SO_result.log()
        aa_error = np.fabs(aa_gt-aa_result)
        return aa_error

    def translation_error(self, pose_error):
        """Compute translation error
        Args:
            pose_error (4x4 array): relative pose error
        Returns:
            trans_error (float): translation error
        """
        dx = pose_error[0, 3]
        dy = pose_error[1, 3]
        dz = pose_error[2, 3]
        trans_error = np.sqrt(dx**2+dy**2+dz**2)
        return trans_error

    def last_frame_from_segment_length(self, dist, first_frame, length):
        """Find frame (index) that away from the first_frame with
        the required distance
        Args:
            dist (float list): distance of each pose w.r.t frame-0
            first_frame (int): start-frame index
            length (float): required distance
        Returns:
            i (int) / -1: end-frame index. if not found return -1
        """
        for i in range(first_frame, len(dist), 1):
            if dist[i] > (dist[first_frame] + length):
                return i
        return -1

    def calc_sequence_errors(self, poses_gt, poses_result):
        """calculate sequence error
        Args:
            poses_gt (dict): {idx: 4x4 array}, ground truth poses
            poses_result (dict): {idx: 4x4 array}, predicted poses
        Returns:
            err (list list): [first_frame, rotation error, translation error, length, speed, aa_error_x, aa_error_y, aa_error_z]
                - first_frame: frist frame index
                - rotation error: rotation error per length
                - translation error: translation error per length
                - length: evaluation trajectory length
                - speed: car speed (#FIXME: 10FPS is assumed)
                - axis_angle err _x : aa_error[0] per length 
                - axis_angle err _y : aa_error[1] per length
                - axis_angle err _z : aa_error[2] per length
        """
        err = []
        dist = self.trajectory_distances(poses_gt)
        self.step_size = 10 #kitti 10Hz

        for first_frame in range(0, len(poses_gt), self.step_size):
            for i in range(self.num_lengths):
                len_ = self.lengths[i]
                last_frame = self.last_frame_from_segment_length(
                                        dist, first_frame, len_
                                        )

                # Continue if sequence not long enough
                if last_frame == -1 or \
                        not(last_frame in poses_result.keys()) or \
                        not(first_frame in poses_result.keys()):
                    continue

                # compute rotational and translational errors
                pose_delta_gt = np.dot(
                                    np.linalg.inv(poses_gt[first_frame]),
                                    poses_gt[last_frame]
                                    )
                pose_delta_result = np.dot(
                                        np.linalg.inv(poses_result[first_frame]),
                                        poses_result[last_frame]
                                        )
                pose_error = np.dot(
                                np.linalg.inv(pose_delta_result),
                                pose_delta_gt
                                )

                r_err = self.rotation_error(pose_error)
                t_err = self.translation_error(pose_error)

                # 统计一段相对位姿 gt 和 est 之间 旋转向量 各分量的差值
                aa_err = self.axisangle_error(pose_delta_gt, pose_delta_result)
                # compute speed
                num_frames = last_frame - first_frame + 1.0
                speed = len_/(0.1*num_frames)
                # 增加 aa_x aa_y aa_z 上的每m误差rads
                err.append([first_frame, r_err/len_, t_err/len_, len_, speed, aa_err[0]/len_, aa_err[1]/len_, aa_err[2]/len_])
        return err
        
    def save_sequence_errors(self, err, file_name):
        """Save sequence error
        Args:
            err (list list): error information
            file_name (str): txt file for writing errors
        """
        fp = open(file_name, 'w')
        for i in err:
            line_to_write = " ".join([str(j) for j in i])
            fp.writelines(line_to_write+"\n")
        fp.close()

    def compute_overall_err(self, seq_err):
        """Compute average translation & rotation errors
        Args:
            seq_err (list list): [[r_err, t_err],[r_err, t_err],...]  其实还是err 结构体
                - r_err (float): rotation error
                - t_err (float): translation error
        Returns:
            ave_t_err (float): average translation error
            ave_r_err (float): average rotation error
            ave_aa_err_x (float): average axis angle error_x
            ave_aa_err_y (float): average axis angle error_y
            ave_aa_err_z (float): average axis angle error_z
        """
        t_err = 0
        r_err = 0
        aa_err_x = 0
        aa_err_y = 0
        aa_err_z = 0

        seq_len = len(seq_err)

        if seq_len > 0:
            for item in seq_err:
                r_err += item[1]
                t_err += item[2]
                aa_err_x += item[5]
                aa_err_y += item[6]
                aa_err_z += item[7]
            ave_t_err = t_err / seq_len
            ave_r_err = r_err / seq_len
            ave_aa_err_x = aa_err_x / seq_len
            ave_aa_err_y = aa_err_y / seq_len
            ave_aa_err_z = aa_err_z / seq_len
            return ave_t_err, ave_r_err, ave_aa_err_x, ave_aa_err_y, ave_aa_err_z
        else:
            return 0, 0

    def plot_trajectory(self, poses_gt, poses_result, seq):
        """Plot trajectory for both GT and prediction
        Args:
            poses_gt (dict): {idx: 4x4 array}; ground truth poses
            poses_result (dict): {idx: 4x4 array}; predicted poses
            seq (int): sequence index.
        """
        plot_keys = ["Ground Truth", "Ours"]
        fontsize_ = 20

        poses_dict = {}
        poses_dict["Ground Truth"] = poses_gt
        poses_dict["Ours"] = poses_result

        fig = plt.figure()
        ax = plt.gca()
        ax.set_aspect('equal')

        for key in plot_keys:
            pos_xz = []
            frame_idx_list = sorted(poses_dict["Ours"].keys())
            for frame_idx in frame_idx_list:
                # pose = np.linalg.inv(poses_dict[key][frame_idx_list[0]]) @ poses_dict[key][frame_idx]
                pose = poses_dict[key][frame_idx]
                pos_xz.append([pose[0, 3],  pose[2, 3]])
            pos_xz = np.asarray(pos_xz)
            plt.plot(pos_xz[:, 0],  pos_xz[:, 1], label=key)

        plt.legend(loc="upper right", prop={'size': fontsize_})
        plt.xticks(fontsize=fontsize_)
        plt.yticks(fontsize=fontsize_)
        plt.xlabel('x (m)', fontsize=fontsize_)
        plt.ylabel('z (m)', fontsize=fontsize_)
        fig.set_size_inches(10, 10)
        png_title = "sequence_{:02}".format(seq)
        fig_pdf = self.plot_path_dir + "/" + png_title + ".pdf"
        plt.savefig(fig_pdf, bbox_inches='tight', pad_inches=0)
        plt.close(fig)

    def plot_error(self, avg_segment_errs, seq):
        """Plot per-length error
        Args:
            avg_segment_errs (dict): {100:[avg_t_err, avg_r_err, avg_aa_err_x, avg_aa_err_y, avg_aa_err_z],...}
            seq (int): sequence index.
        """
        # Translation error
        plot_y = []
        plot_x = []
        for len_ in self.lengths:
            plot_x.append(len_)
            if len(avg_segment_errs[len_]) > 0:
                plot_y.append(avg_segment_errs[len_][0] * 100)
            else:
                plot_y.append(0)
        fontsize_ = 10
        fig = plt.figure()
        plt.plot(plot_x, plot_y, "bs-", label="Translation Error")
        plt.ylabel('Translation Error (%)', fontsize=fontsize_)
        plt.xlabel('Path Length (m)', fontsize=fontsize_)
        plt.legend(loc="upper right", prop={'size': fontsize_})
        fig.set_size_inches(5, 5)
        fig_pdf = self.plot_error_dir + "/trans_err_{:02}.pdf".format(seq)
        plt.savefig(fig_pdf, bbox_inches='tight', pad_inches=0)
        plt.close(fig)

        # Rotation error
        plot_y = []
        plot_x = []
        for len_ in self.lengths:
            plot_x.append(len_)
            if len(avg_segment_errs[len_]) > 0:
                plot_y.append(avg_segment_errs[len_][1] / np.pi * 180 * 100)
            else:
                plot_y.append(0)
        fontsize_ = 10
        fig = plt.figure()
        plt.plot(plot_x, plot_y, "bs-", label="Rotation Error")
        plt.ylabel('Rotation Error (deg/100m)', fontsize=fontsize_)
        plt.xlabel('Path Length (m)', fontsize=fontsize_)
        plt.legend(loc="upper right", prop={'size': fontsize_})
        fig.set_size_inches(5, 5)
        fig_pdf = self.plot_error_dir + "/rot_err_{:02}.pdf".format(seq)
        plt.savefig(fig_pdf, bbox_inches='tight', pad_inches=0)
        plt.close(fig)

        # add plot 3 figure

        # aa_err_x
        plot_y = []
        plot_x = []
        for len_ in self.lengths:
            plot_x.append(len_)
            if len(avg_segment_errs[len_]) > 0:
                plot_y.append(avg_segment_errs[len_][2] / np.pi * 180 * 100)
            else:
                plot_y.append(0)
        fontsize_ = 10
        fig = plt.figure()
        plt.plot(plot_x, plot_y, "bs-", label="Axisangle Error-x")
        plt.ylabel('Axisangle Error-x (deg/100m)', fontsize=fontsize_)
        plt.xlabel('Path Length (m)', fontsize=fontsize_)
        plt.legend(loc="upper right", prop={'size': fontsize_})
        fig.set_size_inches(5, 5)
        fig_pdf = self.plot_error_dir + "/aa_errx_{:02}.pdf".format(seq)
        plt.savefig(fig_pdf, bbox_inches='tight', pad_inches=0)
        plt.close(fig)
        # aa_err_y
        plot_y = []
        plot_x = []
        for len_ in self.lengths:
            plot_x.append(len_)
            if len(avg_segment_errs[len_]) > 0:
                plot_y.append(avg_segment_errs[len_][3] / np.pi * 180 * 100)
            else:
                plot_y.append(0)
        fontsize_ = 10
        fig = plt.figure()
        plt.plot(plot_x, plot_y, "bs-", label="Axisangle Error-y")
        plt.ylabel('Axisangle Error-y (deg/100m)', fontsize=fontsize_)
        plt.xlabel('Path Length (m)', fontsize=fontsize_)
        plt.legend(loc="upper right", prop={'size': fontsize_})
        fig.set_size_inches(5, 5)
        fig_pdf = self.plot_error_dir + "/aa_erry_{:02}.pdf".format(seq)
        plt.savefig(fig_pdf, bbox_inches='tight', pad_inches=0)
        plt.close(fig)
        # aa_err_z
        plot_y = []
        plot_x = []
        for len_ in self.lengths:
            plot_x.append(len_)
            if len(avg_segment_errs[len_]) > 0:
                plot_y.append(avg_segment_errs[len_][4] / np.pi * 180 * 100)
            else:
                plot_y.append(0)
        fontsize_ = 10
        fig = plt.figure()
        plt.plot(plot_x, plot_y, "bs-", label="Axisangle Error-z")
        plt.ylabel('Axisangle Error-z (deg/100m)', fontsize=fontsize_)
        plt.xlabel('Path Length (m)', fontsize=fontsize_)
        plt.legend(loc="upper right", prop={'size': fontsize_})
        fig.set_size_inches(5, 5)
        fig_pdf = self.plot_error_dir + "/aa_errz_{:02}.pdf".format(seq)
        plt.savefig(fig_pdf, bbox_inches='tight', pad_inches=0)
        plt.close(fig)
    
    def save_error(self, avg_segment_errs, seq):
        """save per-length error
        Args:
            avg_segment_errs (dict): {100:[avg_t_err, avg_r_err, avg_aa_err_x, avg_aa_err_y, avg_aa_err_z],...}
            seq (int): sequence index.
        """
        tl_txt = os.path.join(self.plot_error_dir, '{:02}_tl.txt'.format(seq))
        rl_txt = os.path.join(self.plot_error_dir, '{:02}_rl.txt'.format(seq))
        ax_txt = os.path.join(self.plot_error_dir, '{:02}_ax.txt'.format(seq))
        ay_txt = os.path.join(self.plot_error_dir, '{:02}_ay.txt'.format(seq))
        az_txt = os.path.join(self.plot_error_dir, '{:02}_az.txt'.format(seq))

        ftl = open(tl_txt, 'w')
        frl = open(rl_txt, 'w')
        fax = open(ax_txt, 'w')
        fay = open(ay_txt, 'w')
        faz = open(az_txt, 'w')

        for len_ in self.lengths:
            if len(avg_segment_errs[len_]) > 0:
                ftl.write('{:d} {:.4f}\n'.format(len_, avg_segment_errs[len_][0] * 100))
                frl.write('{:d} {:.4f}\n'.format(len_, avg_segment_errs[len_][1] / np.pi * 180 * 100))
                fax.write('{:d} {:.4f}\n'.format(len_, avg_segment_errs[len_][2] / np.pi * 180 * 100))
                fay.write('{:d} {:.4f}\n'.format(len_, avg_segment_errs[len_][3] / np.pi * 180 * 100))
                faz.write('{:d} {:.4f}\n'.format(len_, avg_segment_errs[len_][4] / np.pi * 180 * 100))
            else:
                pass

        ftl.close()
        frl.close()
        fax.close()
        fay.close()
        faz.close()




    def compute_segment_error(self, seq_errs):
        """This function calculates average errors for different segment.
        Args:
            seq_errs (list list): list of errs; [first_frame, rotation error, translation error, length, speed, aa_error_x, aa_error_y, aa_error_z]
                - first_frame: frist frame index
                - rotation error: rotation error per length
                - translation error: translation error per length
                - length: evaluation trajectory length
                - speed: car speed (#FIXME: 10FPS is assumed)
                - axis_angle err _x : aa_error[0] per length 
                - axis_angle err _y : aa_error[1] per length
                - axis_angle err _z : aa_error[2] per length
        Returns:
            avg_segment_errs (dict): {100:[avg_t_err, avg_r_err, avg_aa_err_x, avg_aa_err_y, avg_aa_err_z],...}    
        """

        segment_errs = {}
        avg_segment_errs = {}
        for len_ in self.lengths:
            segment_errs[len_] = []

        # Get errors
        for err in seq_errs:
            len_ = err[3]
            t_err = err[2]
            r_err = err[1]
            aa_err_x = err[5]
            aa_err_y = err[6]
            aa_err_z = err[7]
            segment_errs[len_].append([t_err, r_err, aa_err_x, aa_err_y, aa_err_z])

        # Compute average
        for len_ in self.lengths:
            if segment_errs[len_] != []:
                avg_t_err = np.mean(np.asarray(segment_errs[len_])[:, 0])
                avg_r_err = np.mean(np.asarray(segment_errs[len_])[:, 1])
                avg_aa_err_x = np.mean(np.asarray(segment_errs[len_])[:, 2])
                avg_aa_err_y = np.mean(np.asarray(segment_errs[len_])[:, 3])
                avg_aa_err_z = np.mean(np.asarray(segment_errs[len_])[:, 4])
                avg_segment_errs[len_] = [avg_t_err, avg_r_err, avg_aa_err_x, avg_aa_err_y, avg_aa_err_z]
            else:
                avg_segment_errs[len_] = []
        return avg_segment_errs

    def compute_ATE(self, gt, pred):
        """Compute RMSE of ATE
        Args:
            gt (4x4 array dict): ground-truth poses
            pred (4x4 array dict): predicted poses
        """
        errors = []
        idx_0 = list(pred.keys())[0]
        gt_0 = gt[idx_0]
        pred_0 = pred[idx_0]

        for i in pred:
            # cur_gt = np.linalg.inv(gt_0) @ gt[i]
            cur_gt = gt[i]
            gt_xyz = cur_gt[:3, 3] 

            # cur_pred = np.linalg.inv(pred_0) @ pred[i]
            cur_pred = pred[i]
            pred_xyz = cur_pred[:3, 3]

            align_err = gt_xyz - pred_xyz

            # print('i: ', i)
            # print("gt: ", gt_xyz)
            # print("pred: ", pred_xyz)
            # input("debug")
            errors.append(np.sqrt(np.sum(align_err ** 2)))
        ate = np.sqrt(np.mean(np.asarray(errors) ** 2))  #ate rmse
        return ate
    
    def compute_RPE(self, gt, pred):
        """Compute RPE
        Args:
            gt (4x4 array dict): ground-truth poses
            pred (4x4 array dict): predicted poses
        Returns:
            rpe_trans
            rpe_rot
        """
        trans_errors = []
        rot_errors = []
        for i in list(pred.keys())[:-1]: # 看来这里默认 间距为1帧 all pair 然后取平均
            gt1 = gt[i]
            gt2 = gt[i+1]
            gt_rel = np.linalg.inv(gt1) @ gt2

            pred1 = pred[i]
            pred2 = pred[i+1]
            pred_rel = np.linalg.inv(pred1) @ pred2
            rel_err = np.linalg.inv(gt_rel) @ pred_rel
            
            trans_errors.append(self.translation_error(rel_err))
            rot_errors.append(self.rotation_error(rel_err))
        # rpe_trans = np.sqrt(np.mean(np.asarray(trans_errors) ** 2)) #rmse
        # rpe_rot = np.sqrt(np.mean(np.asarray(rot_errors) ** 2)) #mean 可选！
        rpe_trans = np.mean(np.asarray(trans_errors))
        rpe_rot = np.mean(np.asarray(rot_errors))
        return rpe_trans, rpe_rot

    def scale_optimization(self, gt, pred):
        """ Optimize scaling factor
        Args:
            gt (4x4 array dict): ground-truth poses
            pred (4x4 array dict): predicted poses
        Returns:
            new_pred (4x4 array dict): predicted poses after optimization
        """
        pred_updated = copy.deepcopy(pred)
        xyz_pred = []
        xyz_ref = []
        for i in pred:
            pose_pred = pred[i]
            pose_ref = gt[i]
            xyz_pred.append(pose_pred[:3, 3])
            xyz_ref.append(pose_ref[:3, 3])
        xyz_pred = np.asarray(xyz_pred)
        xyz_ref = np.asarray(xyz_ref)
        scale = scale_lse_solver(xyz_pred, xyz_ref)
        for i in pred_updated:
            pred_updated[i][:3, 3] *= scale
        return pred_updated
    
    def write_result(self, f, seq, errs):
        """Write result into a txt file
        Args:
            f (IOWrapper)
            seq (int): sequence number
            errs (list): [ave_t_err, ave_r_err, ave_aa_err_x, ave_aa_err_y, ave_aa_err_z, ate, rpe_trans, rpe_rot]
        """
        ave_t_err, ave_r_err, ave_aa_err_x, ave_aa_err_y, ave_aa_err_z, ate, rpe_trans, rpe_rot = errs
        lines = []
        # lines.append("Sequence: \t {} \n".format(seq) )
        # lines.append("Trans. err. (%): \t {:.6f} \n".format(ave_t_err*100))
        # lines.append("Rot. err. (deg/100m): \t {:.6f} \n".format(ave_r_err/np.pi*180*100))
        # lines.append("aa. errx. (deg/100m): \t {:.3f} \n".format(ave_aa_err_x/np.pi*180*100))
        # lines.append("aa. erry. (deg/100m): \t {:.3f} \n".format(ave_aa_err_y/np.pi*180*100))
        # lines.append("aa. errz. (deg/100m): \t {:.3f} \n".format(ave_aa_err_z/np.pi*180*100))
        # lines.append("ATE (m): \t {:.6f} \n".format(ate))
        # lines.append("RPE (m): \t {:.3f} \n".format(rpe_trans))
        # lines.append("RPE (deg): \t {:.3f} \n\n".format(rpe_rot * 180 /np.pi))
        # lines.append("Sequence: \t Trans. err. (%): \t Rot. err. (deg/100m): \t ATE (m): \t RPE (m): \t RPE (deg): \n")
        lines.append("{} \t {:.5f} \t {:.5f} \t {:.5f} \t {:.3f} \t {:.3f} \n".format(seq, ave_t_err*100, ave_r_err/np.pi*180*100, ate, rpe_trans, rpe_rot * 180 /np.pi))
        for line in lines:
            f.writelines(line)


    def eval(self, gt_dir, result_dir, 
                alignment=None,
                seqs=None):
        """Evaulate required/available sequences
        Args:
            gt_dir (str): ground truth poses txt files directory
            result_dir (str): pose predictions txt files directory
            alignment (str): if not None, optimize poses by
                - scale: optimize scale factor for trajectory alignment and evaluation
                - scale_7dof: optimize 7dof for alignment and use scale for trajectory evaluation
                - 7dof: optimize 7dof for alignment and evaluation
                - 6dof: optimize 6dof for alignment and evaluation
            seqs (list/None):
                - None: Evalute all available seqs in result_dir
                - list: list of sequence indexs to be evaluated
        """
        seq_list = ["{:02}".format(i) for i in [12, 14, 20]] #kt360 test 目前只有 12 14两个序列

        # Initialization
        self.gt_dir = gt_dir
        ave_t_errs = []
        ave_r_errs = []
        ave_aa_errs_x = []
        ave_aa_errs_y = []
        ave_aa_errs_z = []
        seq_ate = []
        seq_rpe_trans = []
        seq_rpe_rot = []

        # Create result directory
        error_dir = result_dir + "/errors"
        self.plot_path_dir = result_dir + "/plot_path"
        self.plot_error_dir = result_dir + "/plot_error"
        result_txt = os.path.join(result_dir, "result.txt")
        f = open(result_txt, 'w')
        f.writelines("Sequence: \t Trans. err. (%): \t Rot. err. (deg/100m): \t ATE (m): \t RPE (m): \t RPE (deg): \n")
        if not os.path.exists(error_dir):
            os.makedirs(error_dir)
        if not os.path.exists(self.plot_path_dir):
            os.makedirs(self.plot_path_dir)
        if not os.path.exists(self.plot_error_dir):
            os.makedirs(self.plot_error_dir)

        # Create evaluation list
        if seqs is None:
            available_seqs = sorted(glob(os.path.join(result_dir, "*.txt")))
            self.eval_seqs = [int(i[-6:-4]) for i in available_seqs if i[-6:-4] in seq_list]
        else:
            self.eval_seqs = seqs

        # evaluation
        for i in self.eval_seqs:
            self.cur_seq = i
            # Read pose txt
            self.cur_seq = '{:02}'.format(i)
            file_name = '{:02}.txt'.format(i)

            poses_result = self.load_poses_from_txt(result_dir+"/"+file_name)
            poses_gt = self.load_poses_from_txt(self.gt_dir + "/" + file_name)
            self.result_file_name = result_dir+file_name
            # for lio-sam 可能出现pose_result的长度多于gt的情况 要截取掉多于gt的那些
            len_result = len(poses_result)
            len_gt = len(poses_gt)
            if len_result != len_gt:
                print("WARNING: pose_result len {:d} != pose_gt len {:d}".format(len_result, len_gt))
                if len_result > len_gt:
                    poses_result = dict_slice(poses_result, 0, len_gt-1)
                    print("cut result to len {:d}".format(len(poses_result)))
                else:
                    poses_gt = dict_slice(poses_gt, 0, len_result-1)
                    print("cut gt to len {:d}".format(len(poses_gt)))
                    
            # Pose alignment to first frame first pose is I
            idx_0 = sorted(list(poses_result.keys()))[0]
            pred_0 = poses_result[idx_0]
            gt_0 = poses_gt[idx_0]
            for cnt in poses_result:
                poses_result[cnt] = np.linalg.inv(pred_0) @ poses_result[cnt]
                poses_gt[cnt] = np.linalg.inv(gt_0) @ poses_gt[cnt]

            if alignment == "scale":
                poses_result = self.scale_optimization(poses_gt, poses_result)
            elif alignment == "scale_7dof" or alignment == "7dof" or alignment == "6dof":
                # get XYZ
                xyz_gt = []
                xyz_result = []
                for cnt in poses_result:
                    xyz_gt.append([poses_gt[cnt][0, 3], poses_gt[cnt][1, 3], poses_gt[cnt][2, 3]])
                    xyz_result.append([poses_result[cnt][0, 3], poses_result[cnt][1, 3], poses_result[cnt][2, 3]])
                xyz_gt = np.asarray(xyz_gt).transpose(1, 0)
                xyz_result = np.asarray(xyz_result).transpose(1, 0)

                r, t, scale = umeyama_alignment(xyz_result, xyz_gt, alignment!="6dof")

                align_transformation = np.eye(4)
                align_transformation[:3:, :3] = r
                align_transformation[:3, 3] = t
                
                for cnt in poses_result:
                    poses_result[cnt][:3, 3] *= scale
                    if alignment=="7dof" or alignment=="6dof":
                        poses_result[cnt] = align_transformation @ poses_result[cnt]

            # compute sequence errors add aa_err
            seq_err = self.calc_sequence_errors(poses_gt, poses_result)
            self.save_sequence_errors(seq_err, error_dir + "/" + file_name) # 按照error列表 实际元素保存

            # Compute segment errors add aa_err
            avg_segment_errs = self.compute_segment_error(seq_err)

            # compute overall error kitti metric add aa_err
            ave_t_err, ave_r_err, ave_aa_err_x, ave_aa_err_y, ave_aa_err_z = self.compute_overall_err(seq_err)
            # print("Sequence: " + str(i))
            # print("Translational error (%): ", ave_t_err*100)
            # print("Rotational error (deg/100m): ", ave_r_err/np.pi*180*100)
            # print("aa-x error (deg/100m): ", ave_aa_err_x/np.pi*180*100)
            # print("aa-y error (deg/100m): ", ave_aa_err_y/np.pi*180*100)
            # print("aa-z error (deg/100m): ", ave_aa_err_z/np.pi*180*100)
            ave_t_errs.append(ave_t_err)
            ave_r_errs.append(ave_r_err)
            ave_aa_errs_x.append(ave_aa_err_x)
            ave_aa_errs_y.append(ave_aa_err_y)
            ave_aa_errs_z.append(ave_aa_err_z)

            # Compute ATE
            ate = self.compute_ATE(poses_gt, poses_result)
            seq_ate.append(ate)
            # print("ATE (m): ", ate)

            # Compute RPE
            rpe_trans, rpe_rot = self.compute_RPE(poses_gt, poses_result)
            seq_rpe_trans.append(rpe_trans)
            seq_rpe_rot.append(rpe_rot)
            # print("RPE (m): ", rpe_trans)
            # print("RPE (deg): ", rpe_rot * 180 /np.pi)

            # Plotting
            self.plot_trajectory(poses_gt, poses_result, i)
            self.plot_error(avg_segment_errs, i)
            self.save_error(avg_segment_errs, i) #save stat 便于画图

            # Save result summary
            self.write_result(f, i, [ave_t_err, ave_r_err, ave_aa_err_x, ave_aa_err_y, ave_aa_err_z, ate, rpe_trans, rpe_rot])
            
        f.close()    

        print("-------------------- For Copying ------------------------------")
        print("\nSeq\tTranslation(%)\tRot(°/100m)\t ATE(RMSE m)\n")
        for i in range(len(ave_t_errs)):
            # print("{0:.2f}".format(ave_t_errs[i]*100))
            # print("{0:.2f}".format(ave_r_errs[i]/np.pi*180*100))
            # print("{0:.2f}".format(ave_aa_errs_x[i]/np.pi*180*100))
            # print("{0:.2f}".format(ave_aa_errs_y[i]/np.pi*180*100))
            # print("{0:.2f}".format(ave_aa_errs_z[i]/np.pi*180*100))
            # print("{0:.2f}".format(seq_ate[i]))
            # print("{0:.3f}".format(seq_rpe_trans[i]))
            # print("{0:.3f}".format(seq_rpe_rot[i] * 180 / np.pi))
            seqq = '{:02}'.format(self.eval_seqs[i])
            print("%s  \t%.5f   \t%.5f \t%.5f"%( seqq, ave_t_errs[i]*100, ave_r_errs[i]/np.pi*180*100, seq_ate[i]))
        #计算平均值
        t_avg = np.mean(ave_t_errs) * 100 #11个序列的相对平移误差 %
        r_avg = np.mean(ave_r_errs)/np.pi*180*100 #
        rmse_avg = np.mean(seq_ate)
        print("AVG  \t%.5f   \t%.5f \t%.5f"%( t_avg, r_avg, rmse_avg))


    def rotcomp(self, full_dir, dponly_dir,
                seqs=None):
        """
        为了ablation study 对旋转结果的比较
        两个方法每个距离的误差曲线放在同一个图里 
        full_dir: ourfull
        dponly_dir: localgoptvponly
        seqs: 设置只画给定序列
        """

        seq_list = ["{:02}".format(i) for i in range(0, 11)]

        out_dir = 'result/ablation' 
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
        
        #读取该序列下结果文件
        full_errdir = os.path.join(full_dir,'plot_error')
        dponly_errdir = os.path.join(dponly_dir,'plot_error')
        print('our full: ', full_dir)
        print('directon only: ', dponly_dir)
        # Create evaluation list
        if seqs is None:
            available_seqs = sorted(glob(os.path.join(full_dir, "*.txt")))
            self.eval_seqs = [int(i[-6:-4]) for i in available_seqs if i[-6:-4] in seq_list]
        else:
            self.eval_seqs = seqs
        
        # evaluation
        for i in self.eval_seqs:
            # self.cur_seq = i
            self.cur_seq = '{:02}'.format(i)
            print("Sequence: " + self.cur_seq)
            # aa_x
            aa_errx_full = np.loadtxt(os.path.join(full_errdir,self.cur_seq+'_ax.txt'))
            aa_errx_dpol = np.loadtxt(os.path.join(dponly_errdir,self.cur_seq+'_ax.txt'))
            # aa_y
            aa_erry_full = np.loadtxt(os.path.join(full_errdir,self.cur_seq+'_ay.txt'))
            aa_erry_dpol = np.loadtxt(os.path.join(dponly_errdir,self.cur_seq+'_ay.txt'))
            # aa_z
            aa_errz_full = np.loadtxt(os.path.join(full_errdir,self.cur_seq+'_az.txt'))
            aa_errz_dpol = np.loadtxt(os.path.join(dponly_errdir,self.cur_seq+'_az.txt'))

            # rot
            rot_err_full = np.loadtxt(os.path.join(full_errdir,self.cur_seq+'_rl.txt'))
            rot_err_dpol = np.loadtxt(os.path.join(dponly_errdir,self.cur_seq+'_rl.txt'))
            
            #
            plot_y_f = []
            plot_y_d = []
            plot_x = []
            for j in range(aa_errx_full.shape[0]):
                len_ = aa_errx_full[j,0] #距离
                plot_x.append(len_)
                plot_y_f.append(aa_errx_full[j,1])
                plot_y_d.append(aa_errx_dpol[j,1])
            fontsize_ = 10
            fig = plt.figure()
            plt.plot(plot_x, plot_y_f, "gs-", label="Our FULL")
            plt.plot(plot_x, plot_y_d, "bo-", label="direction only")
            plt.ylabel('Axisangle Error-x (deg/100m)', fontsize=fontsize_)
            plt.xlabel('Path Length (m)', fontsize=fontsize_)
            plt.legend(loc="upper right", prop={'size': fontsize_})
            fig.set_size_inches(5, 5)
            fig_pdf = out_dir + "/aa_errx_{:02}.pdf".format(i)
            plt.savefig(fig_pdf, bbox_inches='tight', pad_inches=0)
            plt.close(fig)

            plot_y_f = []
            plot_y_d = []
            plot_x = []
            for j in range(aa_erry_full.shape[0]):
                len_ = aa_erry_full[j,0] #距离
                plot_x.append(len_)
                plot_y_f.append(aa_erry_full[j,1])
                plot_y_d.append(aa_erry_dpol[j,1])
            fontsize_ = 10
            fig = plt.figure()
            plt.plot(plot_x, plot_y_f, "gs-", label="Our FULL")
            plt.plot(plot_x, plot_y_d, "bo-", label="direction only")
            plt.ylabel('Axisangle Error-y (deg/100m)', fontsize=fontsize_)
            plt.xlabel('Path Length (m)', fontsize=fontsize_)
            plt.legend(loc="upper right", prop={'size': fontsize_})
            fig.set_size_inches(5, 5)
            fig_pdf = out_dir + "/aa_erry_{:02}.pdf".format(i)
            plt.savefig(fig_pdf, bbox_inches='tight', pad_inches=0)
            plt.close(fig)

            plot_y_f = []
            plot_y_d = []
            plot_x = []
            for j in range(aa_errz_full.shape[0]):
                len_ = aa_errz_full[j,0] #距离
                plot_x.append(len_)
                plot_y_f.append(aa_errz_full[j,1])
                plot_y_d.append(aa_errz_dpol[j,1])
            fontsize_ = 10
            fig = plt.figure()
            plt.plot(plot_x, plot_y_f, "gs-", label="Our FULL")
            plt.plot(plot_x, plot_y_d, "bo-", label="direction only")
            plt.ylabel('Axisangle Error-z (deg/100m)', fontsize=fontsize_)
            plt.xlabel('Path Length (m)', fontsize=fontsize_)
            plt.legend(loc="upper right", prop={'size': fontsize_})
            fig.set_size_inches(5, 5)
            fig_pdf = out_dir + "/aa_errz_{:02}.pdf".format(i)
            plt.savefig(fig_pdf, bbox_inches='tight', pad_inches=0)
            plt.close(fig)

            plot_y_f = []
            plot_y_d = []
            plot_x = []
            for j in range(rot_err_full.shape[0]):
                len_ = rot_err_full[j,0] #距离
                plot_x.append(len_)
                plot_y_f.append(rot_err_full[j,1])
                plot_y_d.append(rot_err_dpol[j,1])
            fontsize_ = 10
            fig = plt.figure()
            plt.plot(plot_x, plot_y_f, "gs-", label="Our FULL")
            plt.plot(plot_x, plot_y_d, "bo-", label="direction only")
            plt.ylabel('Rotation Error (deg/100m)', fontsize=fontsize_)
            plt.xlabel('Path Length (m)', fontsize=fontsize_)
            plt.legend(loc="upper right", prop={'size': fontsize_})
            fig.set_size_inches(5, 5)
            fig_pdf = out_dir + "/rot_err_{:02}.pdf".format(i)
            plt.savefig(fig_pdf, bbox_inches='tight', pad_inches=0)
            plt.close(fig)
        
        print("---plot done---")