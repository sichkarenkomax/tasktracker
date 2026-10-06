"""Tasks module.

The first functional module of the platform (docs/architecture.md, section 13).
Layout follows section 64: ``models`` -> ``schemas`` -> ``repository`` ->
``service`` -> ``api``, plus ``manifest``, ``permissions`` and ``events``.

Nothing here is imported by ``app.core``: the module reaches the platform
through Core's services and the event bus, which is what allows it to be
disabled by ``ENABLED_MODULES`` without touching the platform itself.
"""
