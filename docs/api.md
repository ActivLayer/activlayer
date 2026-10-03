# HTTP API

Run the API with `activlayer serve`. `/health` is public; all `/v1` routes require an active user's
token in the `X-ActivLayer-Key` header.

Generate or rotate a token:

```bash
activlayer user token owner@example.com
```

Only a SHA-256 token digest is retained. Issuing another token invalidates the previous one.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness |
| `GET` | `/v1/environment` | Organization and current user |
| `GET` | `/v1/agents` | Published agents |
| `GET` | `/v1/agents/{id}` | Published definition JSON |
| `POST` | `/v1/runs` | Start a durable run |
| `GET` | `/v1/runs` | Recent runs |
| `GET` | `/v1/runs/{id}` | Run state and trace |
| `GET` | `/v1/runs/{id}/events` | Hash-chained events |
| `POST` | `/v1/runs/{id}/resume` | Continue from the durable cursor |
| `POST` | `/v1/runs/{id}/approve` | Record approval and continue |

The live OpenAPI document is served at `/docs`.

