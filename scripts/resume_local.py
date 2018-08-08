import json
import os

import torch
from absl import flags

from adept.containers import Local
from adept.utils.script_helpers import make_agent, make_network, get_head_shapes, make_env
from adept.utils.util import dotdict
from adept.utils.logging import make_log_id, make_logger, print_ascii_logo, log_args, write_args_file, ModelSaver
from tensorboardX import SummaryWriter

# hack to use argparse for SC2
FLAGS = flags.FLAGS
FLAGS(['local.py'])


def main(args):
    epoch_dir = os.path.split(args.network_file)[0]
    initial_count = int(os.path.split(epoch_dir)[-1])
    network_file = args.network_file
    optimizer_file = args.optimizer_file
    args_file_path = args.args_file
    with open(args.args_file, 'r') as args_file:
        args = dotdict(json.load(args_file))

    print_ascii_logo()
    log_id = make_log_id(args.tag, args.mode_name, args.agent, args.network)
    log_id_dir = os.path.join(args.log_dir, args.env_id, log_id)

    os.makedirs(log_id_dir)
    logger = make_logger('Local', os.path.join(log_id_dir, 'train_log.txt'))
    summary_writer = SummaryWriter(log_id_dir)
    saver = ModelSaver(args.nb_top_model, log_id_dir)

    log_args(logger, args)
    write_args_file(log_id_dir, args)
    logger.info('Resuming training from {} epoch {}'.format(args_file_path, initial_count))

    # construct env
    env = make_env(args, args.seed)

    # construct network
    torch.manual_seed(args.seed)
    network_head_shapes = get_head_shapes(env.action_space, env.engine, args)
    network = make_network(env.observation_space, network_head_shapes, args)
    network.load_state_dict(torch.load(network_file))

    # construct agent
    os.environ['CUDA_VISIBLE_DEVICES'] = str(args.gpu_id)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    torch.backends.cudnn.benchmark = True
    agent = make_agent(network, device, env.engine, args)

    # Construct the Container
    def make_optimizer(params):
        opt = torch.optim.RMSprop(params, lr=args.learning_rate, eps=1e-5, alpha=0.99)
        if args.optimizer_file is not None:
            opt.load_state_dict(torch.load(optimizer_file))
        return opt

    container = Local(agent, env, device, make_optimizer, args.epoch_len, args.nb_env, logger, summary_writer, saver)
    try:
        container.run(args.max_train_steps + initial_count, initial_count)
    finally:
        env.close()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='AdeptRL Local Mode')
    parser.add_argument(
        '--network-file',
        help='path to args file (.../logs/<env-id>/<log-id>/<epoch>/model.pth)'
    )
    parser.add_argument(
        '--args-file',
        help='path to args file (.../logs/<env-id>/<log-id>/args.json)'
    )
    parser.add_argument(
        '--optimizer-file', default=None,
        help='path to args file (.../logs/<env-id>/<log-id>/<epoch>/optimizer.pth)'
    )
    args = parser.parse_args()
    args.mode_name = 'Local'
    main(args)
