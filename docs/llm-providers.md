# LLM providers

ActivLayer talks to model servers through the OpenAI-compatible models and chat-completions APIs.
Model inference is a replaceable capability; governance and persistence do not depend on a vendor.

## Ollama

Start Ollama and pull a model, then configure its compatibility endpoint:

```bash
ollama pull qwen3:8b
activlayer llm add local --type ollama --model qwen3:8b
activlayer llm test local --prompt "Return the word ready."
```

The default endpoint is `http://localhost:11434/v1`.

## vLLM

```bash
vllm serve Qwen/Qwen3-8B --api-key local-key
activlayer llm add gpu \
  --type vllm \
  --model Qwen/Qwen3-8B \
  --api-key local-key
```

The default endpoint is `http://localhost:8000/v1`.

## llama.cpp

Start `llama-server` with its OpenAI-compatible API, then configure:

```bash
activlayer llm add edge --type llama-cpp --model local-model
```

The default endpoint is `http://localhost:8080/v1`.

## Custom endpoints

```bash
export MODEL_API_KEY="..."
activlayer llm add custom \
  --type openai-compatible \
  --base-url https://models.example.com/v1 \
  --model organization-model \
  --api-key-env MODEL_API_KEY
```

Use `data.config.provider` on an AI node to override the environment's active provider. Supported AI
configuration includes `prompt`, `provider`, `temperature`, `max_tokens`, and bounded retry settings.

