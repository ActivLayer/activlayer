# Extensions

An extension is a small object with `name`, `version`, and an `install(runtime)` method. Installation
registers reusable workers and can perform application-specific setup.

```python
from activlayer import Runtime, install

class SupportExtension:
    name = "support"
    version = "1"

    def install(self, runtime: Runtime) -> None:
        runtime.register(support_worker)

runtime = Runtime()
install(runtime, SupportExtension())
```

Keep extensions explicit. They should not collect telemetry, access the network, modify global
configuration, or register hidden capabilities without clearly documenting that behavior.

