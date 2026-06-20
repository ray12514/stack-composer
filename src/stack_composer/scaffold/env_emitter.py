from __future__ import annotations


def emit_env_stub(gpu: bool = False) -> str:
    spec_line = "    - {{ spec }} amdgpu_target={{ lane.gpu_arch }}" if gpu else "    - {{ spec }}"
    return "\n".join(
        [
            "# TODO(scaffold): Review lane-level Spack settings before use.",
            "# Rendered by {{ renderer_identity.name }} {{ renderer_identity.version }}",
            "spack:",
            "  view: {{ view_root }}",
            "  include:",
            "{% for scope in scopes %}",
            "    - {{ scope }}",
            "{% endfor %}",
            "  specs:",
            "{% for spec in specs %}",
            spec_line,
            "{% endfor %}",
            "",
        ]
    )
