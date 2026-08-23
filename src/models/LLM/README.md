# src.modules.LLM

## File Structure
```
LLM/
├── ChatAgent.py
├── __init__.py
├── README.md
└── utils.py
```

## File Description
### ChatAgent.py
The implementation of `ChatAgent` class.

Key Features:
- **Remote Chat (`remote_chat`)**: Sends a request to a remote LLM API and returns the response. Supports retry and token usage tracking.
- **Batch Remote Chat (`batch_remote_chat`)**: Sends multiple prompts to the remote LLM concurrently using multi-threading.
- **Local Chat (`local_chat`)**: Sends a query to a locally hosted LLM and returns the response.
- **Batch Local Chat (`batch_local_chat`)**: Processes multiple local LLM queries concurrently using a thread pool.
- **Cost Tracking (`update_cost`, `get_cost`, `get_all_cost`)**: Tracks and updates the cost of LLM usage based on token consumption.

### EmbedAgent.py
The implementation of `EmbedAgent` class.

## Key Features:
- **Remote Embedding (`remote_embed`)**: Sends a request to a remote API to generate embeddings for a given text. Supports retries and optional debug information.
- **Batch Remote Embedding (`batch_remote_embed`)**: Processes multiple texts concurrently using multi-threading, sending them to the remote API for embedding.