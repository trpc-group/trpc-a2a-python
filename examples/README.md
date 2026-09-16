# tRPC-A2A Examples

This directory contains examples demonstrating tRPC-A2A usage.

## Usage

### Running Server

You can start the trpc_a2a server with different agent types:

```bash
# 
# Start with basic agent (default)
python examples/trpc_main.py

```

### Running Client Examples

You can use trpc_a2a client to test server:

```bash
# Run basic agent example
python examples/clients/basic_client.py

# Run basic agent example(without configuring client in yaml)
python examples/clients/basic_client_without_yaml.py

# Run streaming agent example (includes task cancellation even it is running)
python examples/clients/streaming_client.py

# Run multi-turn conversation example
python examples/clients/multiturn_client.py

# Run error handling example
python examples/clients/error_client.py

# Run push notify agent
python examples/clients/push_notify_client.py

# Run push task notify agent
python examples/clients/task_push_notify_client.py
```
