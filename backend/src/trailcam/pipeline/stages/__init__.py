"""Pipeline stages. Each module registers its job handlers on import.

M0 ships only ``system.selftest``; ingest and vision stages arrive in M1 and M2 (DESIGN §9, §10).
"""

from trailcam.pipeline.stages import selftest

__all__ = ["selftest"]
