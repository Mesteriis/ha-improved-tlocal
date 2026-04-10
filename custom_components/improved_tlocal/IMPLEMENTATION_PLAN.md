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

ImprovedTLocal should be treated primarily as a reconciliation and recovery
layer for Tuya-local management, not as a protocol rewrite vanity project.
Its real differentiation is:

- explainable matching
- safe apply and rebind
- migration without blind registry breakage
- diagnostics that tell the operator what actually failed

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
- inventing a brand new template DSL when a Tuya-style device template model is enough

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

`device_id` alone is not enough, but the plan must also not mix three different
identity layers into one record.

ImprovedTLocal must keep these identities separate:

- canonical physical device identity
- mutable network binding identity
- Home Assistant registry identity

Practical rules:

- `ip`, `port`, and `protocol_version` live only in binding state
- `mac` is evidence and a connection signal, not the only source of truth
- HA-facing identity must be stable and deterministic
- migration from `localtuya` cannot rely on automatic `entity_id` preservation across domains
- sub-devices must be modelled explicitly from day one

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

## Architecture Boundary

ImprovedTLocal is not four separate products shipped at once.
Implementation order should be:

1. inventory and reconciliation backbone
2. safe binding and rebinding
3. template resolution
4. UI and operator workflows

Transport, matcher, template engine, and UI should stay as separate layers, but
only one vertical slice should be taken end to end at a time.

## Identity Model

## Canonical Physical Device Identity

Represents the actual Tuya thing, independent of IP drift.

Fields:

- `device_id`
- `product_id`
- `model_id`
- `uuid`
- `mac`
- `parent_device_id`
- `node_id`
- `is_subdevice`
- `transport_scope`
- `power_profile`

## Binding Identity

Represents how the physical device is currently reachable on the network.

Fields:

- `ip`
- `port`
- `protocol_version`
- `protocol_version_candidates`
- `verified_level`
- `verified_at`
- `failure_streak`

## Home Assistant Identity

Represents how the device and entities are persisted in HA registries.

Rules:

- use stable unique identifiers unrelated to IP
- use `identifiers` as the primary device-registry anchor
- treat migration from other domains as an explicit import/migration flow

## Layer 1: Inventory Engine

Responsible for collecting normalized device facts from multiple sources.

Inputs:

- Tuya Cloud inventory
- Tuya Cloud device metadata
- passive HA discovery and DHCP discovery
- live LAN TCP port scan as fallback
- UDP discovery when available
- ARP cache as a weak evidence source
- DHCP leases or router export as optional evidence
- previous successful bindings
- HA device/entity registries

Outputs:

- normalized `InventoryDevice` records
- normalized `NetworkEndpoint` records
- unresolved conflict list

Planned modules:

- `inventory/cloud.py`
- `inventory/dhcp.py`
- `inventory/lan_scan.py`
- `inventory/network_cache.py`
- `inventory/history.py`
- `inventory/normalize.py`

## Layer 2: Matcher

Responsible for correlation, verification, and scoring.

The matcher should be explicitly two-phase:

1. candidate generation
2. live verification
3. ranking and explanation

It must not collapse protocol assumptions too early.

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

Verification levels:

- `unverified`
- `weakly_verified`
- `strongly_verified`
- `degraded`

Protocol-awareness requirements:

- keep `protocol_version_candidates` until real handshake/read validation
- distinguish “endpoint reachable but key uncertain” from “fully verified”
- model `local_key` failures separately from IP drift

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

The template model should stay close to the existing Tuya device-template mental
model instead of introducing a brand new DSL too early.

ImprovedTLocal adds:

- inheritance
- patch overlays
- resolved-template hash
- preview diff before apply

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

- single session owner per physical device
- session lifecycle
- reconnect and endpoint rebinding
- state updates
- service calls
- health signals
- per-device queue and backpressure
- capability flags such as `supports_batch_set`, `single_dp_only`, `max_inflight`

Runtime rules:

- one physical device should not have multiple competing socket owners
- transport operations must be serialized per device
- runtime should assume some devices allow only one TCP session
- batch writes must be opt-in per capability, not default behavior

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

Policy:

- config flow is for onboarding and candidate confirmation
- options flow is for stable settings and controlled overrides
- repairs are for actionable recovery operations only
- diagnostics are read-only exports and explain reports

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
- `parent_device_id`
- `node_id`
- `is_subdevice`
- `transport_scope`
- `power_profile`
- `local_key_ref`
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
- `bound_port`
- `bound_protocol_version`
- `verification_level`
- `template_id`
- `confidence`
- `verified_at`
- `verification_method`
- `failure_streak`

## MatchResult

Fields:

- `device_id`
- `candidate_ip`
- `candidate_port`
- `score`
- `status`
- `reasons`
- `conflicts`
- `recommended_action`

## SecretRef

Sensitive values such as `local_key` should not be copied into every inventory
snapshot or diagnostics blob.

Use a dedicated reference or redacted storage path for:

- `local_key`
- cloud credentials
- any per-device secret material

## Storage Strategy

Need clear separation between persisted state and live runtime state.

### Immutable-ish source snapshots

For audit/debug:

- last cloud inventory snapshot
- last LAN scan snapshot
- last matcher run snapshot

### Persisted stores

For long-lived state:

- binding history
- template assignments
- manual overrides
- ignored devices
- pinned identity rules
- match reports
- migration maps

Likely storage approach:

- Home Assistant `Store[...]`-backed files via `.storage/improved_tlocal.*`
- human-readable exports for debug and backup

### Live runtime state

For in-memory operation only:

- coordinators
- active sessions
- active binding cache
- retry queues
- device health runtime markers

Recommended HA usage:

- stable config in `entry.data` and `entry.options`
- live objects in `ConfigEntry.runtime_data`
- persistent mutable records in typed `Store[...]`
- config entry mutations only through `async_update_entry`

## MVP Scope

## v0.1

Goal:
Ship one end-to-end vertical slice for reconciliation and safe binding.

Deliverables:

- integration scaffold
- one root config entry for integration-wide settings
- persistent binding store
- cloud inventory fetch
- passive-first discovery path
- LAN TCP probe fallback
- matcher prototype with verification levels
- dry-run discovery service
- diagnostics export
- one supported device family end to end: smart plug with power metrics
- IP rebind without entity recreation as a mandatory demo feature

Acceptance:

- user can run discovery
- integration produces a structured match report
- report explains unmatched devices
- one plug class can be discovered, verified, bound, and rebound safely

## v0.2

Goal:
Support safe binding and template-backed generation for the most common device classes.

Deliverables:

- template registry
- `light`, `switch`, `cover`, `sensor` MVP
- apply with backup and verification
- endpoint rebinding logic
- migration/import flow from `localtuya`

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
- passive HA and DHCP discovery first
- LAN scan as fallback and admin service
- optional ARP/DHCP evidence import
- endpoint verification
- stale endpoint pruning
- update host on discovery without treating discovery info as full identity

## Matching

- candidate generation
- live verification
- scored ranking
- conflict detection
- explain output
- historical memory
- pinned identity rules
- protocol-aware verification levels

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
- single session owner per physical device
- per-device command queue
- backpressure and rate-limit policy

## Diagnostics

- unmatched reason codes
- key mismatch detection
- protocol mismatch detection
- offline vs cloud-only distinction
- exportable report
- actionable recovery hints only
- redaction of secret material

## UI

- onboarding queue
- apply preview
- retry failed matches
- ignore device
- pin IP / pin MAC / pin template

## Initial Device Focus

Vertical slice priority for v0.1:

- smart plugs with power metrics

Next expansion targets:

- bulbs / RGB lights
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
  diagnostics.py
  repairs.py
  models.py
  storage.py
  inventory/
  matcher/
  transport/
  runtime/
  templates/
  translations/
```

## Transport Boundary

Business logic should not depend directly on `localtuya` internals.

Use a transport port abstraction and keep the first backend thin:

```python
class TransportPort(Protocol):
    async def probe(self, endpoint, creds) -> ProbeResult: ...
    async def open_session(self, binding) -> DeviceSession: ...
    async def read_dps(self, session, dps: set[int] | None = None) -> DpsSnapshot: ...
    async def write_dps(self, session, payload: dict[int, Any]) -> None: ...
    async def heartbeat(self, session) -> None: ...
```

Current decision:

- transport boundary stays internal but explicit
- first backend should be a thin adapter over TinyTuya capabilities
- do not couple the product architecture to `localtuya` implementation details

## Current Decisions

1. Transport should use a thin adapter boundary, with TinyTuya as the first backend.
2. Router/DHCP integration is optional evidence for early releases, not required for correctness.
3. Migration from `localtuya` needs an explicit import/mapping flow; do not assume automatic `entity_id` continuity across domains.
4. Template editing belongs mainly to options/reconfigure and targeted repair flows, not the initial onboarding path.
5. Repair issues should be raised only after repeated actionable failures, not after one noisy scan.

## Recommended Next Implementation Step

Start with a single vertical slice for `v0.1`:

- create domain constants and storage layout
- implement one root entry plus binding store
- implement inventory snapshot collection
- implement passive-first discovery and LAN fallback scan
- implement matcher models, verification levels, and confidence report
- expose one `discover_dry_run` service from `async_setup`
- support one smart-plug template end to end
- demonstrate IP rebind without entity recreation

That keeps the first coded slice small, testable, and directly useful before UI
and platform entities are added.
