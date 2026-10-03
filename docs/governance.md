# Permissions and approvals

ActivLayer treats model output as a proposal. Authority to act comes from explicit runtime controls.

## Least privilege

Assign permissions to tools based on the external effect they can produce. Prefer separate read and
write permissions, for example `catalog.read` and `catalog.write`. Start each run with only the
permissions required for that worker and environment.

If a permission is absent, the runtime records a denial, marks the run failed, and does not invoke
the tool.

## Approval gates

Use `approval=ApprovalPolicy.REQUIRED` for actions that create external side effects, carry financial
or legal significance, publish information, modify access, or require human judgment under policy.

An approval is specific to a run and step. It records an actor and a reason. Applications embedding
the runtime remain responsible for authenticating the actor and deciding who is authorized to
approve.

## Production guidance

- Keep read and write tools separate.
- Make write tools idempotent with a run-derived idempotency key.
- Never pass secrets through worker state or event payloads.
- Treat approval UI and identity verification as part of the security boundary.
- Export events to your observability system and alert on repeated denials or failures.

