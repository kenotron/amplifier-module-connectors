---
bundle:
  name: amplifier-connector-slack-dev
  version: 1.0.0
  description: Opinionated slim Amplifier starter — cherry-picked behaviors, no bloat.

includes:
  # ── Ecosystem expert (registers @amplifier: namespace) ──────────────────────
  - bundle: git+https://github.com/microsoft/amplifier@main#subdirectory=behaviors/amplifier-expert.yaml

  # ── Foundation behaviors (registers @foundation: namespace without full bundle) ─
  - bundle: git+https://github.com/microsoft/amplifier-foundation@main#subdirectory=behaviors/agents.yaml
  - bundle: git+https://github.com/microsoft/amplifier-foundation@main#subdirectory=behaviors/sessions.yaml
  - bundle: git+https://github.com/microsoft/amplifier-foundation@main#subdirectory=behaviors/streaming-ui.yaml
  - bundle: git+https://github.com/microsoft/amplifier-foundation@main#subdirectory=behaviors/status-context.yaml
  - bundle: git+https://github.com/microsoft/amplifier-foundation@main#subdirectory=behaviors/todo-reminder.yaml
  - bundle: git+https://github.com/microsoft/amplifier-foundation@main#subdirectory=behaviors/redaction.yaml

  # ── Workflow & methodology ───────────────────────────────────────────────────
  - bundle: git+https://github.com/microsoft/amplifier-bundle-recipes@main#subdirectory=behaviors/recipes.yaml
  - bundle: git+https://github.com/microsoft/amplifier-bundle-modes@main
  - bundle: git+https://github.com/microsoft/amplifier-bundle-skills@main#subdirectory=behaviors/skills.yaml

  # ── File editing (apply_patch tool) ─────────────────────────────────────────
  - bundle: git+https://github.com/microsoft/amplifier-bundle-filesystem@main#subdirectory=behaviors/apply-patch.yaml

  # ── Memory / engram ──────────────────────────────────────────────────────────
  - bundle: git+https://github.com/kenotron-ms/engram@main#subdirectory=behaviors/engram.yaml

session:
  orchestrator:
    module: loop-streaming
    source: git+https://github.com/microsoft/amplifier-module-loop-streaming@main
    config:
      extended_thinking: true
  context:
    module: context-simple
    source: git+https://github.com/microsoft/amplifier-module-context-simple@main
    config:
      max_tokens: 200000
      compact_threshold: 0.8
      auto_compact: true

tools:
  - module: tool-filesystem
    source: git+https://github.com/microsoft/amplifier-module-tool-filesystem@main
  - module: tool-bash
    source: git+https://github.com/microsoft/amplifier-module-tool-bash@main
  - module: tool-web
    source: git+https://github.com/microsoft/amplifier-module-tool-web@main
  - module: tool-search
    source: git+https://github.com/microsoft/amplifier-module-tool-search@main
  # NOTE: delegate tool comes from agents behavior above

agents:
  include:
    # Note: amplifier-expert comes via included behavior above
    - foundation:bug-hunter
    - foundation:explorer
    - foundation:file-ops
    - foundation:git-ops
    - foundation:modular-builder
    - foundation:web-research
    - foundation:zen-architect
---

@foundation:context/shared/common-system-base.md
