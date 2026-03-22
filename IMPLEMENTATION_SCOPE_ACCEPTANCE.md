# Implementation Scope and Acceptance Criteria

## Objective
Deliver a stable analytics navigation experience and monetization-ready entitlement foundation without regressing current dashboard behavior.

## Scope Freeze

### In Scope (Current Execution Window)
1. Analytics IA: Dashboard summary plus dedicated analytics pages (App Usage, Activity Feed, Insights).
2. Sidebar navigation and active-state consistency across dashboard/analytics routes.
3. Template/state cleanup for per-page rendering and safe JS initialization.
4. Visual consistency pass with current white-card dashboard shell.
5. Monetization gate placeholders in UI for premium-only actions.
6. Backend entitlement resolver used by views/templates/APIs.
7. Billing/subscription primitives integrated at model/service layer (minimal viable integration points).
8. QA pass, docs update, and rollout notes.

### Out of Scope (This Window)
1. Full payment provider production hardening (fraud tooling, tax automation, retries webhooks).
2. New analytics algorithms/ML insight generation beyond current placeholders.
3. Large visual redesign replacing the established dashboard shell.
4. Agent-side binary/distribution workflow changes.

## Non-Negotiable Constraints
1. Preserve current dashboard summary route behavior.
2. Keep backward compatibility for legacy analytics query-param links where practical.
3. Do not break organization filtering and permission boundaries.
4. Keep migrations safe and reversible.

## Definition of Done by Checklist Item

### 1) Freeze scope and acceptance criteria
- Acceptance:
  - This document exists and is committed.
  - In-scope/out-of-scope boundaries are explicit.
  - Each checklist item has a measurable completion criterion.

### 2) Audit current dashboard routes/state
- Acceptance:
  - Route/state inventory documented in implementation notes.
  - Known compatibility paths identified (legacy + new).

### 3) Finalize analytics IA and navigation
- Acceptance:
  - Sidebar information architecture agreed: Dashboard, App Usage, Activity Feed, Insights.
  - Navigation targets map 1:1 to named routes.

### 4) Implement dedicated analytics routes
- Acceptance:
  - Named routes resolve and render without errors.
  - Server context sets analytics view state deterministically.

### 5) Wire sidebar active-state logic
- Acceptance:
  - Correct menu item is active for each analytics route.
  - Legacy query-param route still highlights expected item.

### 6) Refactor dashboard into page states
- Acceptance:
  - Dashboard summary renders on default route.
  - Apps/activity/insights render independently via analytics view state.

### 7) Stabilize JS per-page initialization
- Acceptance:
  - No console/runtime errors when visiting each analytics page directly.
  - JS components initialize only when required DOM is present.

### 8) Align visual system to white-card
- Acceptance:
  - Page sections remain visually consistent with existing white-card shell.
  - No conflicting duplicate navigation affordances remain.

### 9) Add monetization gate placeholders
- Acceptance:
  - Premium-only UI actions show clear upgrade/locked state.
  - No hidden server-only failures for gated actions.

### 10) Add entitlement resolver backend
- Acceptance:
  - Single resolver/service returns entitlement decisions from membership/license state.
  - Views/APIs can consume resolver without duplicating permission logic.

### 11) Integrate billing/subscription primitives
- Acceptance:
  - Subscription status fields/events wired to entitlement decisions.
  - Grace period and downgrade behavior defined and testable.

### 12) Run QA, docs, rollout plan
- Acceptance:
  - Django checks pass.
  - Targeted test pass for modified routes/views.
  - Rollout notes include risk list + rollback path.

## Validation Commands
Run from `nwata_web` unless otherwise noted:

1. `python manage.py check`
2. `python manage.py test dashboard`
3. `python manage.py test api`

## Progress Reporting Format
For each completed item, report:
1. Item number and title.
2. What changed (files and behavior).
3. Validation result (command/test outcome).
4. Risks or follow-up.

## Current Route and State Inventory (Audit Baseline)

### Routes
1. `/dashboard/` -> `dashboard` (default summary, legacy query-param support for analytics views).
2. `/dashboard/analytics/apps/` -> `analytics_app_usage`.
3. `/dashboard/analytics/activity/` -> `analytics_activity_feed`.
4. `/dashboard/analytics/insights/` -> `analytics_insights`.
5. Existing org/profile/API routes remain unchanged and coexist with analytics routes.

### Template State Behavior
1. Sidebar active state resolves from named route and supports legacy `?view=` fallback.
2. Dashboard template branches on `analytics_view` server context:
  - `apps`
  - `activity`
  - `insights`
  - default dashboard summary state
3. Frontend JS includes per-page guards to avoid initializing controls when page-specific DOM is absent.
