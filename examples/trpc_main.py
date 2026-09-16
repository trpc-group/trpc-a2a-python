# -*- coding: utf-8 -*-
"""This is server module"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
from typing import List

import trpc
from trpc.log import logger

# import sdk and plugins
# pylint: disable=unused-import
import trpc_naming_polaris as _

# DO NOT remove the plugin below!
import trpc_metrics_runtime as _
# pylint: enable=unused-import

# add the stub to the path
sys.path.append(str(Path(__file__) / "agents"))  # noqa
sys.path.append(str(Path(__file__) / "stub"))  # noqa
sys.path.append(str(Path(__file__)))  # 加入当前路径做包路径

# agents.basic_agent 导入即是注册过程，可以不使用其包做显示调用
import agents.basic_agent as _
# import agents.error_agent as _
# import agents.multiturn_agent as _
# import agents.push_notify_agent as _
# import agents.streaming_agent as _
# import agents.task_push_notify_agent as _ # error

DEFAULT_CONF_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "trpc_python.yaml"))


def parse_args(argv: List[str]):
    """解析命令行参数
    :param argv: 命令行参数
    """
    # argparse parser
    parser = argparse.ArgumentParser(description='TRPC Python Framework Server')
    parser.add_argument('--conf',
                        '-c',
                        default=DEFAULT_CONF_PATH,
                        help='start server with conf, for example: `python3 trpc_main.py  --conf=trpc_python.yaml`')
    try:
        args = parser.parse_args(argv[1:])  # Skip the script name
        if os.path.exists(args.conf):
            print(f"conf_path: {args.conf}")
            return args.conf
        print(f"conf_path: {args.conf} not exists")
        if os.path.exists(DEFAULT_CONF_PATH):
            print(f"use default conf path: {DEFAULT_CONF_PATH}")
            return DEFAULT_CONF_PATH
        print(f"default conf path: {DEFAULT_CONF_PATH} not exists, please check the path")
        sys.exit(1)
    except SystemExit:
        # argparse will call sys.exit() when --help is used or invalid args
        sys.exit(1)


def serve(conf_path: str):
    """启动服务
    :param conf_path: 配置文件路径
    """

    svr = trpc.new(conf_path)
    svr.serve()


def main():
    """主函数"""
    # 加载.env文件中的环境变量
    load_dotenv()
    # 解析命令行参数
    conf_path = parse_args(sys.argv)
    logger.info("load config %s", conf_path)

    # 启动服务
    serve(conf_path)


if __name__ == '__main__':
    sys.exit(main())
