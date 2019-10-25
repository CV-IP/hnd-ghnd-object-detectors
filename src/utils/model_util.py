import torch
from torch import nn
from torchvision.models import detection

from myutils.common import file_util
from utils import misc_util, yolo_util


def save_ckpt(model, optimizer, lr_scheduler, config, args, output_file_path):
    file_util.make_parent_dirs(output_file_path)
    misc_util.save_on_master({'model': model.state_dict(), 'optimizer': optimizer.state_dict(),
                              'lr_scheduler': lr_scheduler.state_dict(), 'config': config, 'args': args},
                             output_file_path)


def load_ckpt(ckpt_file_path, model=None, optimizer=None, lr_scheduler=None):
    if not file_util.check_if_exists(ckpt_file_path):
        return None, None

    ckpt = torch.load(ckpt_file_path, map_location='cpu')
    if model is not None:
        model.load_state_dict(ckpt['model'])
    if optimizer is not None:
        optimizer.load_state_dict(ckpt['optimizer'])
    if lr_scheduler is not None:
        lr_scheduler.load_state_dict(ckpt['lr_scheduler'])
    return ckpt['config'], ckpt['args']


def get_model(model_config, num_classes):
    model_type = model_config['type']
    ckpt_file_path = model_config['ckpt']
    model_params_config = model_config['params']
    if model_type in detection.__dict__:
        model = detection.__dict__[model_type](num_classes=num_classes, **model_params_config)
    elif model_type.startswith('yolo'):
        model = yolo_util.get_model('cpu', ckpt_file_path, **model_params_config)
    else:
        raise ValueError('model_type `{}` is not expected'.format(model_type))
    load_ckpt(ckpt_file_path, model=model)
    return model


def get_iou_types(model):
    model_without_ddp = model
    if isinstance(model, nn.parallel.DistributedDataParallel):
        model_without_ddp = model.module

    iou_type_list = ['bbox']
    if isinstance(model_without_ddp, detection.MaskRCNN):
        iou_type_list.append('segm')
    if isinstance(model_without_ddp, detection.KeypointRCNN):
        iou_type_list.append('keypoints')
    return iou_type_list
