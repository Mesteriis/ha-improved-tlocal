# ImprovedTLocal Implementation Plan

## Vision

Build a new Home Assistant custom integration that makes local Tuya management
predictable instead of guess-based.

ImprovedTLocal should provide:

- reliable local discovery
- explainable device matching by `mac`, `ip`, `device_id`, `local_key`, and protocol
- template-driven entity creation
- safe apply/reload workflows
- first-class diagnostics and recovery UX

The goal is not to clone `localtuya` line by line.
The goal is to build a better operator experience and a better device
reconciliation layer with clean architecture and strong safety defaults.

## Product Goals

1. Auto-discover candidate Tuya devices on LAN with usable confidence scoring.
2. Correlate cloud inventory, historical state, ARP/DHCP/router data, and live TCP probes.
3. Generate entities from device templates instead of one-off handwritten mappings.
4. Keep stable device identity and entity IDs across IP changes and partial outages.
5. Show users why a device was or was not matched.
6. Support dry-run, apply, rollback, and re-verify workflows.
7. Provide a usable UI for onboarding, review, templates, and diagnostics.

## Non-Goals For Initial Versions

- full protocol rewrite of every Tuya transport path
- support for every exotic Tuya category in v0.1
- cloudless first-time provisioning of unknown devices
- replacing every mature HA pattern with custom UI immediately

## Core Principles

### Local-first, cloud-assisted

Cloud is allowed for metadata, inventory, product mapping, and recovery hints.
Runtime control should remain local whenever the device supports it.

### Explainable matching

Every match must record:

- what signals were used
- what confidence score was assigned
- what fallback path was taken
- why competing candidates were rejected

### Safe mutation

No silent writes into the HA config entry store.
Every write path must support:

- preflight validation
- backup
- diff preview
- post-apply verification

### Stable identity

`device_id` alone is not enough.
Identity should be tracked as a composite of:

- `device_id`
- `mac`
- `product_id` / `model_id`
- last known successful `ip`
- last known successful `protocol_version`

### Template-first entity generation

Entity layouts should come from versioned templates, with inheritance and
device-specific overrides, instead of hand-written per-device hacks.

## Main User Stories

### New device onboarding

User adds a Tuya device to the network.
ImprovedTLocal detects it, correlates it with cloud inventory, proposes a match,
shows a confidence score, previews entities, and applies the config.

### IP drift recovery

A device changes IP.
ImprovedTLocal detects the new endpoint, verifies the device by key/protocol,
updates binding, and preserves existing HA entities.

### Unknown local endpoint

A device is online in Tuya Cloud but not matched locally.
ImprovedTLocal shows diagnostics:

- cloud reachable
- local endpoint not found
- key mismatch
- protocol mismatch
- conflicting host candidate

### Template override

A product family is partially supported, but a specific device needs a custom
entity set.
User can clone a template, override DPs, preview result, and pin it to the device.

## Architecture

## Layer 1: Inventory Engine

Responsible for collecting normalized device facts from multiple sources.

Inputs:

- Tuya Cloud inventory
- Tuya Cloud device metadata
- live LAN TCP port scan
- UDP discovery when available
- ARP cache
- DHCP leases or router export
- previous successful bindings
- HA device/entity registries

Outputs:

- normalized `InventoryDevice` records
- normalized `NetworkEndpoint` records
- unresolved conflict list

Planned modules:

- `inventory/cloud.py`
- `inventory/lan_scan.py`
- `inventory/network_cache.py`
- `inventory/history.py`
- `inventory/normalize.py`

## Layer 2: Matcher

Responsible for correlation and scoring.

Signals:

- exact `mac` match
- verified `device_id + local_key + protocol`
- historical successful `ip`
- matching `product_id` / `model_id`
- DP signature similarity
- endpoint conflict penalties

Outputs:

- `Matched`
- `Tentative`
- `Conflict`
- `Unmatched`

Each result must include a rationale payload.

Planned modules:

- `matcher/models.py`
- `matcher/scoring.py`
- `matcher/strategies.py`
- `matcher/explain.py`

## Layer 3: Template Registry

Responsible for entity layouts and platform generation.

Template hierarchy:

- category base template
- product template
- model template
- device override

Template responsibilities:

- canonical entity set
- DP mapping
- platform config
- naming policy
- optional attributes and feature flags

Planned storage:

- JSON or YAML template files under `custom_components/improved_tlocal/templates/`
- runtime override storage for user-customized templates

Planned modules:

- `templates/registry.py`
- `templates/resolver.py`
- `templates/validator.py`

## Layer 4: Runtime

Responsible for active device sessions and HA platform entities.

Responsibilities:

- session lifecycle
- reconnect and endpoint rebinding
- state updates
- service calls
- health signals

Planned modules:

- `runtime/device_session.py`
- `runtime/coordinator.py`
- `runtime/rebinder.py`
- `runtime/health.py`

## Layer 5: UI / Operator Experience

Responsibilities:

- onboarding wizard
- match review screen
- diagnostics screen
- template preview and override flow
- recovery actions

UI surfaces:

- config flow
- options flow
- diagnostics
- repair issues
- optional Lovelace panel later

Planned modules:

- `config_flow.py`
- `repairs.py`
- `diagnostics.py`
- `frontend/` only after MVP is stable

## Data Model

## InventoryDevice

Fields:

- `device_id`
- `name`
- `category`
- `product_id`
- `model`
- `model_id`
- `mac`
- `uuid`
- `local_key`
- `cloud_online`
- `dp_schema`
- `template_candidates`

## NetworkEndpoint

Fields:

- `ip`
- `port`
- `protocol_version_candidates`
- `mac`
- `scan_source`
- `last_seen_at`
- `fingerprint`

## BindingRecord

Fields:

- `device_id`
- `mac`
- `bound_ip`
- `bound_protocol_version`
- `template_id`
- `confidence`
- `verified_at`
- `verification_method`
- `failure_streak`

## MatchResult

Fields:

- `device_id`
- `candidate_ip`
- `score`
- `status`
- `reasons`
- `conflicts`
- `recommended_action`

## Storage Strategy

Need two storage layers.

### Immutable-ish source snapshots

For audit/debug:

- last cloud inventory snapshot
- last LAN scan snapshot
- last matcher run snapshot

### Mutable runtime registry

For actual operation:

- binding history
- template assignments
- manual overrides
- ignored devices
- pinned identity rules

Likely storage approach:

- HA storage helpers via `.storage/improved_tlocal.*`
- human-readable exports for debug and backup

## MVP Scope

## v0.1

Goal:
Create a real backbone for discovery and diagnostics without yet owning every
runtime platform.

Deliverables:

- integration scaffold
- internal storage model
- cloud inventory fetch
- LAN TCP probe
- matcher prototype
- dry-run report
- diagnostics export

Acceptance:

- user can run discovery
- integration produces a structured match report
- report explains unmatched devices

## v0.2

Goal:
Support safe binding and template-backed generation for the most common device classes.

Deliverables:

- template registry
- `light`, `switch`, `cover`, `sensor` MVP
- apply with backup and verification
- endpoint rebinding logic

Acceptance:

- common bulbs/plugs/covers can be onboarded from UI
- IP drift can be repaired without deleting entities

## v0.3

Goal:
Make the product operable day to day.

Deliverables:

- config flow onboarding wizard
- options flow
- repair issues for conflicts/unmatched devices
- health entities
- better diagnostics

Acceptance:

- user can manage devices without editing raw JSON
- support workflow is visible and debuggable

## Functional Areas

## Discovery

- cloud fetch
- LAN scan
- optional ARP/DHCP import
- endpoint verification
- stale endpoint pruning

## Matching

- scored matching
- conflict detection
- explain output
- historical memory
- pinned identity rules

## Templates

- built-in templates
- product inheritance
- device override
- preview before apply
- template validation

## Runtime

- local sessions
- periodic health check
- auto-rebind
- safe reload

## Diagnostics

- unmatched reason codes
- key mismatch detection
- protocol mismatch detection
- offline vs cloud-only distinction
- exportable report

## UI

- onboarding queue
- apply preview
- retry failed matches
- ignore device
- pin IP / pin MAC / pin template

## Initial Device Focus

Prioritize what already exists in this environment:

- bulbs / RGB lights
- smart plugs with power metrics
- covers / shutters
- selected sensors that expose standard DP sets

Defer until later:

- cameras
- IR bridges
- alarms
- gateways and sub-device ecosystems

## Proposed File Layout

```text
custom_components/improved_tlocal/
  __init__.py
  manifest.json
  const.py
  config_flow.py
  coordinator.py
  diagnostics.py
  repairs.py
  models.py
  storage.py
  inventory/
  matcher/
  runtime/
  templates/
  translations/
```

## Open Questions

1. Should transport reuse `tinytuya`, `localtuya` internals, or a dedicated thin adapter?
2. How much router/DHCP integration is acceptable for the first release?
3. Do we preserve existing `entity_id` values automatically during migration from `localtuya`?
4. How much template editing should be in config flow versus diagnostics/options?
5. Should unmatched devices create repair issues immediately, or only after repeated failures?

## Recommended Next Implementation Step

Start with `v0.1` only:

- create domain constants and storage layout
- implement inventory snapshot collection
- implement LAN endpoint scan
- implement matcher models and confidence report
- expose one service for dry-run discovery

That keeps the first coded slice small, testable, and directly useful before UI
and platform entities are added.
