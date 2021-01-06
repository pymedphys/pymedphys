import numpy as np

import tensorflow as tf
import tensorflow.keras.backend as K

epsilon = 1e-5
smooth = 1

# ---------------- BCE ----------------------


def w_bce_loss(y_true, y_pred):
    bce = tf.keras.losses.BinaryCrossentropy()
    smooth = 1e-5
    total_pixels = 512 * 512 * 3
    w = total_pixels / (K.sum(y_true, axis=(0, 1, 2)) + smooth)

    l0 = bce(y_true[..., 0], y_pred[..., 0])
    l1 = bce(y_true[..., 1], y_pred[..., 1])
    l2 = bce(y_true[..., 2], y_pred[..., 2])

    return K.mean(l0, l1, l2)


def bce_dsc_loss(y_true, y_pred):
    bce = tf.keras.losses.BinaryCrossentropy()
    loss = bce(y_true, y_pred) + 2 * dice_loss(y_true, y_pred)
    return loss


def bce_wdsc_loss(y_true, y_pred):
    bce = tf.keras.losses.BinaryCrossentropy()
    loss = bce(y_true, y_pred) + 2 * weighted_dsc_loss(y_true, y_pred)
    return loss


# ---------------- DICE ----------------------


def dsc(y_true, y_pred):
    smooth = 1.0
    y_true_f = K.flatten(y_true)
    y_pred_f = K.flatten(y_pred)
    intersection = K.sum(y_true_f * y_pred_f)
    score = (2.0 * intersection + smooth) / (K.sum(y_true_f) + K.sum(y_pred_f) + smooth)
    return score


def dsc_loss(y_true, y_pred):
    loss = 1 - dsc(y_true, y_pred)
    return loss


def weighted_dsc(y_true, y_pred):
    smooth = 1
    total_pixels = 512 * 512 * 3
    weights = total_pixels / (K.sum(y_true, axis=(0, 1, 2)) + smooth)
    intersection = K.sum(y_true * y_pred, axis=(0, 1, 2))
    union = K.sum(y_true + y_pred, axis=(0, 1, 2))
    w_intersection = K.sum(intersection * weights)
    w_union = K.sum(union * weights)
    return (2 * w_intersection + smooth) / (w_union + smooth)


def weighted_dsc_loss(y_true, y_pred):
    return 1 - weighted_dsc(y_true, y_pred)


def dice_metric(y_true, y_pred, smooth=1e-6):
    "vDSC, DSC, F1 score is the dice soresen coefficient. Higher is better"
    y_pred = tf.keras.backend.round(y_pred)
    intersection = K.sum(y_true * y_pred, axis=[1, 2, 3])
    union = K.sum(y_true, axis=[1, 2, 3]) + K.sum(y_pred, axis=[1, 2, 3])
    dice = K.mean((2 * intersection + smooth) / (union + smooth), axis=0)
    return dice


def iou_coef(y_true, y_pred, smooth=1e-6):
    "Jaccard Index or intersectional overlap coeff. Higher is better"
    intersection = K.sum(K.abs(y_true * y_pred), axis=[1, 2, 3])
    union = K.sum(y_true, [1, 2, 3]) + K.sum(y_pred, [1, 2, 3]) - intersection
    iou = K.mean((intersection + smooth) / (union + smooth), axis=0)
    return iou


# ---------------- TVSKY LOSS ----------------------


def tversky(y_true, y_pred):
    smooth = 1e-5
    y_true_pos = K.flatten(y_true)
    y_pred_pos = K.flatten(y_pred)
    true_pos = K.sum(y_true_pos * y_pred_pos)
    false_neg = K.sum(y_true_pos * (1 - y_pred_pos))
    false_pos = K.sum((1 - y_true_pos) * y_pred_pos)
    alpha = 0.7
    return (true_pos + smooth) / (
        true_pos + alpha * false_neg + (1 - alpha) * false_pos + smooth
    )


def tvsky_loss(y_true, y_pred):
    return 1 - tversky(y_true, y_pred)


def focal_tversky_loss(y_true, y_pred):
    pt_1 = tversky(y_true, y_pred)
    gamma = 0.75
    return K.pow((1 - pt_1), gamma)


def class_tversky(y_true, y_pred):
    smooth = 1

    y_true = K.permute_dimensions(y_true, (3, 1, 2, 0))
    y_pred = K.permute_dimensions(y_pred, (3, 1, 2, 0))

    y_true_pos = K.batch_flatten(y_true)
    y_pred_pos = K.batch_flatten(y_pred)
    true_pos = K.sum(y_true_pos * y_pred_pos, 1)
    false_neg = K.sum(y_true_pos * (1 - y_pred_pos), 1)
    false_pos = K.sum((1 - y_true_pos) * y_pred_pos, 1)
    alpha = 0.7
    return (true_pos + smooth) / (
        true_pos + alpha * false_neg + (1 - alpha) * false_pos + smooth
    )


# channels sensitive loss function
def focal_tversky_loss_c(y_true, y_pred):
    pt_1 = class_tversky(y_true, y_pred)
    gamma = 0.75
    return K.sum(K.pow((1 - pt_1), gamma))


# ---------------- OTHER ----------------------


def confusion(y_true, y_pred):
    smooth = 1
    y_pred_pos = K.clip(y_pred, 0, 1)
    y_pred_neg = 1 - y_pred_pos
    y_pos = K.clip(y_true, 0, 1)
    y_neg = 1 - y_pos
    tp = K.sum(y_pos * y_pred_pos)
    fp = K.sum(y_neg * y_pred_pos)
    fn = K.sum(y_pos * y_pred_neg)
    prec = (tp + smooth) / (tp + fp + smooth)
    recall = (tp + smooth) / (tp + fn + smooth)
    return prec, recall


def tp(y_true, y_pred):
    smooth = 1
    y_pred_pos = K.round(K.clip(y_pred, 0, 1))
    y_pos = K.round(K.clip(y_true, 0, 1))
    tp = (K.sum(y_pos * y_pred_pos) + smooth) / (K.sum(y_pos) + smooth)
    return tp


def tn(y_true, y_pred):
    smooth = 1
    y_pred_pos = K.round(K.clip(y_pred, 0, 1))
    y_pred_neg = 1 - y_pred_pos
    y_pos = K.round(K.clip(y_true, 0, 1))
    y_neg = 1 - y_pos
    tn = (K.sum(y_neg * y_pred_neg) + smooth) / (K.sum(y_neg) + smooth)
    return tn


# ---------------- SURFACE LOSS ----------------------

# from tensorflow.keras import backend as K
# import numpy as np
# import tensorflow as tf
# from scipy.ndimage import distance_transform_edt as distance


# def calc_dist_map(seg):
#     res = np.zeros_like(seg)
#     posmask = seg.astype(np.bool)

#     if posmask.any():
#         negmask = ~posmask
#         res = distance(negmask) * negmask - (distance(posmask) - 1) * posmask

#     return res

# def calc_dist_map_batch(y_true):
#     y_true_numpy = y_true.numpy()
#     return np.array([calc_dist_map(y)
#                      for y in y_true_numpy]).astype(np.float32)

# def surface_loss(y_true, y_pred):
#     y_true_dist_map = tf.py_function(func=calc_dist_map_batch,
#                                      inp=[y_true],
#                                      Tout=tf.float32)
#     multipled = y_pred * y_true_dist_map
#     return K.mean(multipled)

# def surface_dice_loss(y_true, y_pred):
#     return alpha * dsc_loss(y_true, y_pred) + (1-apha) * surface_loss(y_true,
#             y_pred)
