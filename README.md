# tRPC-A2A-Python

基于 [a2a-sdk](https://github.com/a2aproject/a2a-python) 的 trpc-python 插件，完全兼容 a2a-sdk 的 client/server 接口。

## 快速开始

### 安装

需要 **Python>=3.10** 环境。

```bash
pip install trpc-a2a --index-url https://mirrors.cloud.tencent.com/pypi/simple/
```

如果需要支持 Redis，使用以下安装方法
```bash
pip install trpc-a2a[redis] --index-url https://mirrors.cloud.tencent.com/pypi/simple/
```

### 服务端

配置 `trpc_python.yaml` 如下

```yaml
server:
  service:
    - name: trpc.a2a_test.test_a2a_agent
      protocol: a2a # 注意设置 protocol 为 a2a
      ip: 127.0.0.1
      port: 18080
      network: tcp
      # 如果需要使用 Redis，取消注释以下配置
      # redis_name: trpc.redis.test_example

# 如果需要使用 Redis，添加以下配置
# client:
#   service:
#     - name: trpc.redis.test_example
#       target: ip://127.0.0.1:6379
#       timeout: 5000
#       password: ${redis_password}  # 可选
#       redis:
#         db: 0
```

基于 `TrpcA2AService` 实现业务Agent逻辑：

```python
import trpc
from trpc.trpc_abc.context import Context

from trpc_a2a.server import TrpcA2AService, register_service, get_a2a_request_context

from a2a.types import EventQueue, AgentCard, AgentCapabilities, AgentSkill


class UserAgentService(TrpcA2AService):
    async def get_agent_card(self):
        return AgentCard(
            name="Echo Agent",
            description="A simple echo agent",
            url="", # 推荐设置为空，将会填充为trpc_python.yaml中的ip和port
            version="1.0.0",
            default_input_modes=["text"],
            default_output_modes=["text"],
            capabilities=AgentCapabilities(
                streaming=False, # 是否支持流式
                pushNotifications=False, # 是否支持推送通知
            ),
            skills=[
                AgentSkill(
                    id="greet",
                    name="Greeting",
                    description="Provides friendly greetings",
                    tags=["greeting"],
                ),
            ]
        )
    
    async def execute(self, context: Context, event_queue: EventQueue):
        # 通过 get_a2a_request_context 获取 a2a 请求上下文
        a2a_context = get_a2a_request_context(context)
        # 其他用法跟a2a-sdk的server一致，见a2a-sdk的server文档/examples示例代码/使用指南
        ...

# trpc_main.py里注册服务
agent_svc = UserAgentService()
register_service("trpc.a2a_test.test_a2a_agent", agent_svc)
# 可以通过下面的方式注册自定义的handle
# @fastapi_route("/hello", ["GET"], route_params={'response_model': dict})
# async def hello() -> dict:
#     trpc_ctx = get_trpc_ctx()
#     logger.info(f"Request from {trpc_ctx.remote_ip}")
#     return {"message": "hello world", "remote_ip": trpc_ctx.remote_ip}
```

### 客户端

配置 `trpc_python.yaml` 如下

```yaml
client:
  service:
    - name: trpc.a2a_test.test_a2a_agent
      protocol: a2a
      target: ip://127.0.0.1:18080
      # 北极星使用如下配置
      # target: polaris://trpc.a2a_test.test_a2a_agent
      timeout: 10000 # 请求超时时间(ms)
```

基于 trpc 的 `A2AClient` 实现业务Agent客户端逻辑：

```python
from trpc import config
from trpc.plugin import setup

from trpc_a2a.client import TrpcA2AClient, TrpcA2ACardResolver

# 纯客户端需要初始化trpc环境（服务端不需要）
config.load_global_config("trpc_python.yaml", "utf-8")
setup()

# 获取 agent 信息
resolver = TrpcA2ACardResolver()
resolver_result = await resolver.get_from_agent_service(ctx, "trpc.a2a_test.test_a2a_agent")

# 创建客户端
client = TrpcA2AClient(service_name="trpc.a2a_test.test_a2a_agent", resolver_result=resolver_result)

# 发送消息
# 接口及用法基本跟a2a-sdk的client一致，见a2a-sdk的client文档/examples示例代码/使用指南
response = await client.send_message(ctx, request)
```

## 示例代码

见 [examples](./examples/) 目录。

## 使用指南

### 基础文本通信

**场景描述**：实现简单的文本问答功能，支持问候和回显消息。

**服务端实现要点**：
- 继承 `TrpcA2AService` 类
- 实现 `get_agent_card()` 方法定义 agent 能力
- 实现 `execute()` 方法处理用户输入
- 使用 `TaskUpdater` 管理任务状态和结果

```python
from trpc_a2a.server import TrpcA2AService, get_a2a_request_context
from a2a.types import AgentCard, AgentCapabilities, AgentSkill

class BasicAgentService(TrpcA2AService):
    async def get_agent_card(self) -> AgentCard:
        return AgentCard(
            name="Basic Agent",
            description="A simple basic agent",
            url="",
            version="1.0.0",
            default_input_modes=["text"],
            default_output_modes=["text"],
            capabilities=AgentCapabilities(streaming=True),
            skills=[AgentSkill(id="greet", name="Greeting")]
        )
    
    async def execute(self, context, event_queue):
        a2a_context = get_a2a_request_context(context)
        user_input = a2a_context.get_user_input()
        
        # 处理输入并返回响应
        response = self._process_input(user_input)
        await updater.add_artifact([Part(root=TextPart(text=response))])
        await updater.complete()
```

### 自定义HTTP接口获取tRPC上下文

**场景描述**：在自定义HTTP接口中获取tRPC上下文信息，用于访问请求元数据。

**服务端实现要点**：
- 使用 `get_trpc_ctx()` 获取当前请求的tRPC上下文
- 可以访问 `remote_ip`、`timeout` 等上下文信息
- 支持在任何用户注册的HTTP处理器中调用

```python
from trpc_fastapi import fastapi_route
from trpc_a2a.server import TrpcA2AService, get_trpc_ctx
from trpc.log import logger

@fastapi_route("/custom_endpoint", ["GET"], route_params={'response_model': dict})
async def custom_handler() -> dict:
    # 获取tRPC上下文
    ctx = get_trpc_ctx()
    if ctx:
        logger.info(f"Request from {ctx.remote_ip}")
        logger.info(f"Request timeout: {ctx.timeout}ms")
    return {"status": "ok"}

@fastapi_route("/custom_endpoint", ["POST"], route_params={'response_model': dict})
async def process_data(data: dict):
    # 在任何HTTP处理器中都可以获取tRPC上下文
    ctx = get_trpc_ctx()
    if ctx:
        # 可用于日志记录、监控等场景
        logger.info(f"Processing request from {ctx.remote_ip}")
    return {"result": "processed"}

```

**客户端实现要点**：
- 使用 `TrpcA2ACardResolver` 发现 agent 能力
- 创建 `TrpcA2AClient` 实例
- 支持 `send_message` 和 `send_message_streaming` 两种模式

```python
from trpc_a2a.client import TrpcA2AClient, TrpcA2ACardResolver
from a2a.types import Message, Role, Part, TextPart, SendMessageRequest, MessageSendParams

# 获取 agent 信息
resolver = TrpcA2ACardResolver()
resolver_result = await resolver.get_from_agent_service(ctx, service_name)
client = TrpcA2AClient(service_name=service_name, resolver_result=resolver_result)

# 发送消息
message = Message(role=Role.user, parts=[Part(root=TextPart(text="hello"))])
request = SendMessageRequest(params=MessageSendParams(message=message))
response = await client.send_message(ctx, request)
```

### 流式通信

**场景描述**：实现实时进度更新，适用于长时间运行的任务。

**服务端实现要点**：
- 设置 `streaming=True` 能力
- 使用 `updater.update_status()` 发送进度更新
- 支持任务取消处理

```python
from a2a.utils import new_agent_text_message
from a2a.types import TaskState

async def _run_progress_task(self, updater, context_id, task_id):
    steps = ["Initializing...", "Processing...", "Finalizing..."]
    
    for i, step in enumerate(steps):
        progress = int((i / len(steps)) * 100)
        await updater.update_status(
            TaskState.working,
            new_agent_text_message(f"[{progress}%] {step}", context_id, task_id)
        )
        await asyncio.sleep(1)  # 模拟工作
    
    await updater.complete()
```

**客户端实现要点**：
- 使用 `send_message_streaming` 接收实时更新
- 处理 `TaskStatusUpdateEvent` 和 `TaskArtifactUpdateEvent`
- 支持任务取消操作

```python
from a2a.types import TaskStatusUpdateEvent, TaskArtifactUpdateEvent

async for response in client.send_message_streaming(ctx, streaming_request):
    if isinstance(response.root.result, TaskStatusUpdateEvent):
        # 处理状态更新
        logger.info(f"Status: {response.root.result.status.state}")
    elif isinstance(response.root.result, TaskArtifactUpdateEvent):
        # 处理结果更新
        logger.info(f"Artifact: {response.root.result.artifact.name}")
```

### 多轮对话

**场景描述**：实现需要多次交互的对话场景，如问答游戏。

**服务端实现要点**：
- 维护会话状态管理
- 使用 `TaskState.input_required` 等待用户输入
- 在 `execute()` 中处理任务续接

```python
from a2a.utils import new_task, new_agent_text_message
from a2a.types import TaskState

async def execute(self, context, event_queue):
    a2a_context = get_a2a_request_context(context)
    task = a2a_context.current_task
    
    if not task:
        # 创建新任务，等待用户输入
        task = new_task(a2a_context.message)
        await updater.update_status(
            TaskState.input_required,
            new_agent_text_message("请开始游戏...", task.context_id, task.id),
            final=True
        )
    else:
        # 继续现有任务
        await self._process_user_input(user_input, updater)
```

**客户端实现要点**：
- 保存任务 ID 用于后续交互
- 在消息中包含 `task_id` 字段
- 处理 `input_required` 状态

```python
# 后续消息包含任务ID
if self.current_task_id:
    message.task_id = self.current_task_id

# 检查是否需要输入
if task.status.state == TaskState.input_required:
    logger.info("任务需要额外输入")
```

### 推送通知

**场景描述**：实现异步任务处理，通过 webhook 接收状态更新。

**服务端实现要点**：
- 设置 `pushNotifications=True` 能力
- 使用 `TaskUpdater` 自动发送推送通知
- 支持长时间运行的多步骤任务

```python
async def _handle_multi_step(self, task_id, updater):
    processes = [("Data Validation", 3), ("Processing", 4), ("Delivery", 1)]
    
    for i, (process_name, duration) in enumerate(processes, 1):
        # 每个步骤都会自动触发推送通知
        await updater.update_status(
            TaskState.working,
            new_agent_text_message(f"Step {i}: {process_name}", task_id, task_id)
        )
        await updater.add_artifact([...], name=f"step_{i}")
        await asyncio.sleep(duration)
```

**客户端实现要点**：
- 配置 webhook 服务器接收推送
- 使用 `PushNotificationConfig` 设置回调
- 设置 `blocking=False` 实现异步处理

```python
from a2a.types import PushNotificationConfig, MessageSendConfiguration

# 配置推送通知
push_config = PushNotificationConfig(url=webhook_url, token="auth-token")
configuration = MessageSendConfiguration(
    push_notification_config=push_config,
    blocking=False  # 异步模式
)

# 发送请求后立即返回，通过 webhook 接收更新
response = await client.send_message(ctx, request)
```

### 错误处理

**场景描述**：实现健壮的错误处理机制，包括异常捕获和状态管理。

**服务端实现要点**：
- 使用 try-catch 包装主要逻辑
- 设置 `TaskState.failed` 状态
- 提供有意义的错误信息

```python
try:
    # 主要业务逻辑
    response = self._process_input(user_input)
    await updater.complete()
except Exception as e:
    logger.error(f"处理请求时发生错误: {e}")
    await updater.update_status(
        TaskState.failed,
        new_agent_text_message(f"错误: {str(e)}", task.context_id, task.id),
        final=True
    )
```

**客户端实现要点**：
- 检查任务状态是否为 `failed`
- 处理 TRPC 异常和业务异常
- 实现重试机制（如需要）

```python
from trpc.exceptions import TRPCBaseError
from a2a.types import Task, TaskState

try:
    response = await client.send_message(ctx, request)
    if isinstance(response.root.result, Task):
        if response.root.result.status.state == TaskState.failed:
            logger.error("任务执行失败")
except TRPCBaseError as e:
    logger.error(f"TRPC 错误: {e}")
except Exception as e:
    logger.error(f"其他错误: {e}")
```
