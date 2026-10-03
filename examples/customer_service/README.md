# Customer-service agent organization

This runnable example provisions one `orchestrator` and three specialized `worker` agents:

- `product-advisor` — products, eligibility, features, and pricing
- `service-guide` — accounts, cards, transfers, and digital-service procedures
- `request-resolution` — complaints, disputes, status, and escalation

Each worker receives its own SQLite memory database. All three retrieve approved content from one
shared organization knowledge base with separate products, services, pricing, and procedures
collections. The orchestrator may delegate only to workers listed in its `managed_workers` field.

```bash
python examples/customer_service/provision.py --home .local/customer-service

activlayer --home .local/customer-service agent list --published
activlayer --home .local/customer-service knowledge collection-list
activlayer --home .local/customer-service run start customer-service-orchestrator \
  --input '{"customer_id":"demo-001","request":"What is the monthly account fee?"}'
```

The seeded facts and prices are fictional and illustrative. Replace them with reviewed,
version-controlled organizational content before production use.
