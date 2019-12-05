import argparse
import os
from io import BytesIO

import numpy as np
import pandas as pd
import torch
from PIL import Image

from models import get_model
from myutils.common import yaml_util
from myutils.pytorch import module_util
from structure.transformer import DataSizeLogger
from utils import coco_util, main_util


def get_argparser():
    argparser = argparse.ArgumentParser(description=__doc__)
    argparser.add_argument('--config', required=True, help='yaml config file')
    argparser.add_argument('--device', default='cuda', help='device')
    argparser.add_argument('--json', help='dictionary to overwrite config')
    argparser.add_argument('-model_params', help='dictionary to overwrite config')
    argparser.add_argument('--modules', nargs='+', help='list of specific modules you want to count parameters')
    argparser.add_argument('--data_size', help='dataset split name to analyze data size')
    argparser.add_argument('--bottleneck_size', help='dataset split name to analyze size of bottleneck in model')
    return argparser


def analyze_model_params(model, module_paths):
    print('Analyzing model parameters')
    print('[Whole model]')
    print('# parameters: {}'.format(module_util.count_params(model)))
    if module_paths is None or len(module_paths) == 0:
        return

    print('[Specified module(s)]')
    modules = module_util.get_components(module_paths)
    pair_list = list()
    for module, module_path in zip(modules, module_paths):
        pair_list.append([module_path, module_util.count_params(module)])

    data_frame = pd.DataFrame(pair_list)
    print('Total # parameters: {}'.format(data_frame[1].sum()))
    print(data_frame)


def summarize_data_sizes(data_sizes, title):
    data_sizes = np.array(data_sizes)
    print('[{}]'.format(title))
    print('Data size:\t{:.4f} ± {:.4f} [KB]'.format(data_sizes.mean(), data_sizes.std()))
    print('# Files:\t{}\n'.format(len(data_sizes)))


def analyze_data_size(dataset_config, split_name='test'):
    print('Analyzing {} data size'.format(split_name))
    split_config = dataset_config['splits'][split_name]
    dataset = coco_util.get_coco(split_config['images'], split_config['annotations'], None,
                                 split_config['remove_non_annotated_imgs'], split_config['jpeg_quality'])

    coco = dataset.coco
    org_data_size_list = list()
    comp_data_size_list = list()
    for index in range(len(dataset.ids)):
        img_id = dataset.ids[index]
        path = coco.loadImgs(img_id)[0]['file_name']
        img = Image.open(os.path.join(dataset.root, path)).convert('RGB')
        img_buffer = BytesIO()
        img.save(img_buffer, 'JPEG', quality=95)
        # Original data size [KB]
        org_data_size_list.append(img_buffer.tell() / 1024)
        img_buffer.close()
        if dataset.jpeg_quality is not None:
            img_buffer = BytesIO()
            img.save(img_buffer, 'JPEG', quality=dataset.jpeg_quality)
            # JPEG-compressed data size [KB]
            comp_data_size_list.append(img_buffer.tell() / 1024)
            img_buffer.close()

    summarize_data_sizes(org_data_size_list, 'Original')
    if len(comp_data_size_list) > 0:
        summarize_data_sizes(comp_data_size_list, 'JPEG quality = {}'.format(dataset.jpeg_quality))


def analyze_bottleneck_size(model, data_size_logger, dataset_config, split_name='test'):
    print('Analyzing size of bottleneck in model for {} dataset'.format(split_name))
    split_config = dataset_config['splits'][split_name]
    dataset = coco_util.get_coco(split_config['images'], split_config['annotations'], None,
                                 split_config['remove_non_annotated_imgs'], split_config['jpeg_quality'])
    data_loader = torch.utils.data.SequentialSampler(dataset)
    with torch.no_grad():
        for images, _ in data_loader:
            model(images)

    data_sizes, quantized_data_sizes = data_size_logger.get_data()
    summarize_data_sizes(data_sizes, 'Bottleneck')
    if quantized_data_sizes[0] is not None:
        summarize_data_sizes(quantized_data_sizes, 'Quantized Bottleneck')


def main(args):
    config = yaml_util.load_yaml_file(args.config)
    if args.json is not None:
        main_util.overwrite_config(config, args.json)

    device = torch.device(args.device)
    print(args)
    if args.model_params:
        model = get_model(config['model'], device)
        analyze_model_params(model, args.modules)

    if args.data_size is not None:
        analyze_data_size(config['dataset'], split_name=args.data_size)

    if args.bottleneck_size is not None:
        data_size_logger = DataSizeLogger()
        model = get_model(config['student_model'], device, bottleneck_transformer=data_size_logger)
        analyze_bottleneck_size(model, data_size_logger, config['dataset'], split_name=args.bottleneck_size)


if __name__ == '__main__':
    parser = get_argparser()
    main(parser.parse_args())
