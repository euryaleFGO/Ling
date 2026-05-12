"""
DiffSinger 歌声合成推理脚本

作为独立子进程运行，与主项目依赖隔离。
通过 JSON 参数文件接收输入，输出 WAV 文件。
"""

import argparse
import json
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('diffsinger-infer')


def main():
    parser = argparse.ArgumentParser(description='DiffSinger 歌声合成推理')
    parser.add_argument('--params', required=True, help='输入参数 JSON 文件路径')
    parser.add_argument('--output', required=True, help='输出 WAV 文件路径')
    parser.add_argument('--diffsinger-root', required=True, help='DiffSinger 仓库根目录')
    parser.add_argument('--exp-name', default='opencpop', help='实验名称')
    parser.add_argument('--vocoder-ckpt', default='', help='NSF-HiFiGAN vocoder 路径')
    parser.add_argument('--device', default='cuda', help='推理设备')
    args = parser.parse_args()

    # 读取参数
    with open(args.params, 'r', encoding='utf-8') as f:
        params = json.load(f)

    logger.info(f"开始推理: exp={args.exp_name}, device={args.device}")
    logger.info(f"参数: {json.dumps(params, ensure_ascii=False)[:200]}...")

    # 添加 DiffSinger 到 Python 路径
    diffsinger_root = os.path.abspath(args.diffsinger_root)
    if diffsinger_root not in sys.path:
        sys.path.insert(0, diffsinger_root)

    # 设置 hparams（DiffSinger 需要通过 sys.argv 传递配置）
    original_argv = sys.argv
    sys.argv = [
        'infer.py',
        '--exp_name', args.exp_name,
        '--infer',
    ]
    if args.vocoder_ckpt:
        sys.argv.extend(['--vocoder_ckpt', args.vocoder_ckpt])

    try:
        # 导入 DiffSinger 模块
        from utils.hparams import set_hparams
        hparams = set_hparams()

        from inference.ds_acoustic import DiffSingerAcousticInfer

        # 初始化推理器
        inferencer = DiffSingerAcousticInfer(device=args.device)

        # 确保输出目录存在
        output_dir = os.path.dirname(os.path.abspath(args.output))
        os.makedirs(output_dir, exist_ok=True)

        # 标题（文件名不含扩展名）
        title = os.path.splitext(os.path.basename(args.output))[0]

        # 运行推理
        inferencer.run_inference(
            params=[params],
            out_dir=output_dir,
            title=title,
        )

        # DiffSinger 输出的文件名可能是 title.wav 或 title_0.wav
        expected_output = os.path.join(output_dir, f"{title}.wav")
        alt_output = os.path.join(output_dir, f"{title}_0.wav")

        if os.path.exists(expected_output):
            if expected_output != args.output:
                os.rename(expected_output, args.output)
            logger.info(f"推理完成: {args.output}")
        elif os.path.exists(alt_output):
            os.rename(alt_output, args.output)
            logger.info(f"推理完成: {args.output}")
        else:
            # 查找任何生成的 wav 文件
            import glob
            wavs = glob.glob(os.path.join(output_dir, f"{title}*.wav"))
            if wavs:
                os.rename(wavs[0], args.output)
                logger.info(f"推理完成: {args.output}")
            else:
                logger.error(f"未找到输出文件: {expected_output}")
                sys.exit(1)

    except Exception as e:
        logger.error(f"推理失败: {e}", exc_info=True)
        sys.exit(1)
    finally:
        sys.argv = original_argv


if __name__ == '__main__':
    main()
