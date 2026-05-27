# Roadmap

This roadmap focuses on turning Dataset Review Agent from a strong internal workflow into a polished open-source project.

## Current

- Offline dataset audit pipeline
- Static conflict auto-fix loop
- Model-assisted risk discovery
- Model auto-fix acceptance records
- Local acceptance review platform
- Agent summary with ready-to-export state
- Inline label editing
- Cleaned dataset export
- Re-audit workflow
- Acceptance report generation

## Next

### 1. Better open-source onboarding

- improve bilingual documentation
- add example configs for multiple dataset shapes
- add a short demo video or GIF
- document common deployment patterns

### 2. Better acceptance UX

- clearer run overview
- stronger issue grouping
- before/after label diff view
- better report browsing in the platform
- better filtering for model auto-fix records
- more compact "ready to export" dashboards

### 3. Better dataset governance

- richer issue taxonomies
- stronger writeback workflows
- dataset version comparison
- reusable acceptance templates by project

### 4. Better model integration

- support more OpenAI-compatible multimodal endpoints
- configurable model prompts by task
- better structured validation for model outputs
- multiple model backends for cross-checking
- stronger acceptance logic for partial-confidence auto-fix cases

### 5. Better operations

- production deployment guide
- persistent worker mode
- stronger retry and resume observability
- background task monitoring

## Longer-Term Ideas

- turn the acceptance workflow into a more explicit Agent interface
- add multi-user review support
- add lightweight annotation UI for structured corrections
- add report dashboards across dataset versions
