"""Built-in declarative Box types.

Each module here declares one or more :class:`solden.core.workflow_spec.WorkflowSpec`
instances at import time and calls ``register_spec`` on them. Importing this
package (eagerly, from ``main.py``) registers every built-in declared type
before the route layer and the strict-profile allowlist are built.

A new built-in workflow type is added by dropping a module here with a single
spec declaration — zero bespoke store / state-machine / route / migration code.
Tenant-authored types live in the database instead (see the ``workflow_specs``
table and the spec resolver), not in this package.

Empty today: the platform machinery ships first; the proof type is declared in
``tests/test_declarative_workflow.py``.
"""
from __future__ import annotations
