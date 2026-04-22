# utils/behavior_tracker.py
# Legacy Shim: Redacts the old monolith into the new /core Engine layout.

from core.behavior_engine import behavior_engine

# Providing the alias for backward compatibility across handlers.
behavior_tracker = behavior_engine
