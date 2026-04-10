# ImprovedTLocal

ImprovedTLocal is a Home Assistant custom integration focused on making local
Tuya management explainable and maintainable.

Current scope:

- integration scaffold
- implementation plan
- repository metadata for HACS
- GitHub Actions for validation and release packaging

Planned scope:

- local discovery
- matcher with confidence scoring
- template-based entity generation
- safe apply and rollback flows
- diagnostics and repair UX

## Repository Layout

- `custom_components/improved_tlocal`: Home Assistant integration source
- `custom_components/improved_tlocal/IMPLEMENTATION_PLAN.md`: product and architecture plan

## Installation

1. Copy `custom_components/improved_tlocal` into your Home Assistant config.
2. Restart Home Assistant.
3. Add the integration once config flow/runtime are implemented.

For now, the repository is an implementation scaffold rather than a complete
runtime integration.
