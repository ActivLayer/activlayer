# Core concepts

## Worker

A `Worker` is a named, versioned sequence of durable steps. It describes the work to perform without
coupling the definition to a hosting service or model provider.

## Tool

A `Tool` wraps a normal Python callable and declares the permission required to use it and whether a
human approval is required. Keep tools narrow, deterministic where practical, and safe to retry.

## Step

A `Step` binds a tool to arguments derived from the run state. Its output is stored before execution
advances. Steps have bounded retry behavior.

## Run

A `Run` is one durable execution of a worker. The runtime stores input, outputs, the current step,
permissions, attempts, status, and any terminal error.

## Permission

A permission is an application-defined string such as `orders.read` or `orders.write`. The runtime
checks it immediately before calling a tool. Start workers with the smallest required set.

## Approval

An approval is an explicit decision attached to a run and step. Protected tools cannot execute until
the runtime has a recorded approval. The actor and reason are preserved in the event history.

## Event

Events describe run creation, step execution, permission decisions, approval decisions, and terminal
state. Each event includes the hash of the preceding event, making later alteration detectable.

