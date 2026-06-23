"""REST API surface (Experience/control plane) — P0-T11.

Thin HTTP layer over the platform: create tenant/project/profile, list/trigger
work items, list runs/artifacts/events/trace-edges, decide gates. Business logic
lives in the domain services (`trigger_phase`, `decide_gate`, `create_tenant`);
these views only parse, scope by tenant, call the service, and serialize.
"""
