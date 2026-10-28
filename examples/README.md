# tRPC-A2A 示例

本示例起一个 A2A agent，客户端用 tRPC 的 A2A 协议发文本。默认 agent 是 Basic Agent，服务名 `trpc.a2a_test.test_a2a_agent`，监听 `127.0.0.1:18080`。

## 关键特性

- **问候和回显**：`hello` 返回问候，`echo: ...` 原样带回后半句
- **普通发送和流式发送**：同一个输入各走一遍 `send_message` 和 `send_message_streaming`
- **两种客户端**：一份读 YAML 里的 service name，一份不读 YAML、直接连 `http://127.0.0.1:18080`
- **同端口上的 HTTP 路由**：每个 agent 都挂了 `GET /hello`

关键文件：

- [trpc_main.py](trpc_main.py)：`--agent` 选定一个模块，导入时完成 `register_service`，再 `create_server` + `serve`
- [agents/basic_agent.py](agents/basic_agent.py)：默认服务。`execute` 里问候或回显，并注册 `GET /hello`
- [clients/basic_client.py](clients/basic_client.py)：读 [clients/trpc_python.yaml](clients/trpc_python.yaml)，按 service name 发现 agent card
- [clients/basic_client_without_yaml.py](clients/basic_client_without_yaml.py)：`get_from_agent_url` 直连 `http://127.0.0.1:18080`
- [run_examples.sh](run_examples.sh)：按场景起服务、等 18080、跑对应客户端、停服务
- `trpc_python*.yaml`：每种进程模型一份，A2A 都听 `127.0.0.1:18080`

调用关系：

```text
basic_client.py / basic_client_without_yaml.py
└── :18080  trpc.a2a_test.test_a2a_agent
    └── BasicAgentService.execute
```

## 关键代码解释

- `trpc_main.py` 在 `create_server` 之前按 `--agent` 导入一个模块，默认 `basic`。`register_service` 写在模块顶层，导入即完成注册。六个 agent 用的是同一个服务名，所以一次只导入一个。
- `BasicAgentService.execute` 用 `get_a2a_request_context` 取用户文本。包含 `hello` / `hi` / `hey` / `greet` 时回问候；以 `echo:` 开头时回 `You said: ...`。
- `basic_client.py` 的 `TrpcConfig.load("examples/clients/trpc_python.yaml")` 相对当前工作目录。从仓库根目录启动才能找到这份配置。
- `basic_client_without_yaml.py` 只 `init_plugins()`，agent 地址写在脚本里的 `http://127.0.0.1:18080`。

其余 agent 与客户端成对，服务名相同。要换一套时，给 `trpc_main.py` 加上 `--agent`，再从仓库根目录跑同名客户端。一键脚本按场景做这件事：

| Agent | `--agent` | 客户端 | 在测什么 |
| --- | --- | --- | --- |
| `agents/streaming_agent.py` | `streaming` | `clients/streaming_client.py` | 流式进度，以及任务还在跑时取消 |
| `agents/multiturn_agent.py` | `multiturn` | `clients/multiturn_client.py` | 多轮问答，会话状态留在进程里 |
| `agents/error_agent.py` | `error` | `clients/error_client.py` | 任务失败和异常 |
| `agents/push_notify_agent.py` | `push_notify` | `clients/push_notify_client.py` | 推送通知，客户端 webhook 听 `19080` |
| `agents/task_push_notify_agent.py` | `task_push_notify` | `clients/task_push_notify_client.py` | 按任务设置推送配置，客户端 webhook 听 `19081` |

## 环境要求

- Python >= 3.10
- macOS 或 Linux
- 本机 18080 空闲。`push` 还要 19080 空闲，`task_push` 还要 19081 空闲
- 在仓库根目录安装：`pip install -e .`。安装说明见上级 [README.zh_CN.md](../README.zh_CN.md)

## 运行步骤

在 `examples` 目录下：

```bash
./run_examples.sh list
./run_examples.sh
./run_examples.sh basic trpc_python_multi_process_merge.yaml
./run_examples.sh streaming
./run_examples.sh multiturn
./run_examples.sh error
./run_examples.sh push
./run_examples.sh task_push
./run_examples.sh modes
./run_examples.sh all
```

`./run_examples.sh` 和 `./run_examples.sh basic` 一样，用 [trpc_python.yaml](trpc_python.yaml)。`basic` 后面可以换成本目录里的另一份 YAML，或一个绝对路径。`streaming`、`multiturn`、`error`、`push`、`task_push` 固定用这份 YAML：取消和多轮会话留在进程里。`modes` 按下面表格的顺序，对每份配置跑一遍 `basic`。`all` 先跑这六个功能场景，再跑 `modes`。

解释器按 `$PYTHON`、`../.venv/bin/python`、`../venv/bin/python`、`python3` 的顺序选。服务日志写在 `examples/.server_run.log`。上一级目录里有 `trpc_sdk` 包时，脚本把它的父目录放在 `PYTHONPATH` 前面。脚本会设置 `NO_PROXY=localhost,127.0.0.1`。

手动两步，效果和默认的 `basic` 相同。客户端要在仓库根目录执行：

```bash
# 终端 1，当前目录是 examples
python trpc_main.py -c trpc_python.yaml
python trpc_main.py -c trpc_python.yaml --agent streaming

# 终端 2，当前目录是仓库根目录
python examples/clients/basic_client.py
python examples/clients/basic_client_without_yaml.py
python examples/clients/streaming_client.py
```

| 配置 | `global.processmodel` | uvicorn |
| --- | --- | --- |
| `trpc_python.yaml` | 不写。单进程，一个事件循环 | 服务进程里一个线程 |
| `trpc_python_single_process_merge.yaml` | `single_process`，`handle_num: 2` | serving thread 0 起一个 |
| `trpc_python_single_process_separate.yaml` | `single_process`，`io_handle_type: separate`，`io_num: 1`，`handle_num: 2` | serving thread 0 起一个。A2A 处理不进 handler 线程 |
| `trpc_python_multi_process_separate.yaml` | `multi_process`，`io_handle_type: separate`，`handle_num: 2` | 每个 rpc task 一个。两个 rpc task 用 `SO_REUSEPORT` 听 18080 |
| `trpc_python_multi_process_merge.yaml` | `multi_process`，`io_handle_type: merge`，`handle_num: 2` | 每个 worker 一个，用 `SO_REUSEPORT` 听 18080 |

## 运行结果

`./run_examples.sh` 对两个客户端检查进程退出码。每个客户端自己会发两条消息：`Hello` 和 `echo: test message`，每条都走一遍普通发送和流式发送。四次都成功时，日志里有 `Overall result: ✅ PASSED`，脚本再打印 `[PASS]`。

`Hello` 的回复是 `Hello! I'm your tRPC-A2A agent. How can I help you today?`。`echo: test message` 的回复是 `You said: test message`。

`GET http://127.0.0.1:18080/hello` 返回 `{"message":"hello world","remote_ip":...}`。`basic` 会请求这个路由，正文里要有 `hello world`。

`streaming`、`multiturn`、`error`、`push`、`task_push` 看对应客户端的退出码。成功时日志里有 `Overall result: ✅ PASSED`，脚本再打印 `[PASS]`。

## 适用场景

- 确认插件注册、agent card、`send_message`、流式发送和 `GET /hello` 在默认配置下可用
- 用 `streaming`、`multiturn`、`error`、`push`、`task_push` 确认取消、多轮、失败和推送
- 换 YAML 之后确认 18080 仍然由对应进程模型里的 uvicorn 提供 Basic Agent

## 需要注意什么

1. **客户端从仓库根目录启动**。读 YAML 的客户端按当前目录找 `examples/clients/trpc_python.yaml`。一键脚本已经切到仓库根目录再跑客户端。
2. **一次只导入一个 agent**。六个模块注册的服务名都是 `trpc.a2a_test.test_a2a_agent`。用 `--agent` 选择，不要同时导入多个。
3. **端口**。五份配置都占用 18080。`push` 的 webhook 占用 19080，`task_push` 占用 19081。一键脚本发现端口已被占用会直接失败。
