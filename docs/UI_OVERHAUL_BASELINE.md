# DaliJob UI Overhaul Baseline

Date: 2026-08-06

## Purpose

This inventory records the UI behavior and representative states that Phases 0-4 of `UI_OVERHAUL_IMPLEMENTATION_PLAN.md` must preserve while visual foundations, navigation, dashboard, saved jobs, search, and import pages are redesigned.

No client or server process was started for this inventory. Historical screenshots supplied during earlier UI work remain useful references, but a complete desktop/mobile screenshot baseline still requires the application to be run by the user and therefore remains an open Phase 0 item.

## Shared UI Inventory

| Existing pattern | Main selectors or components | Migration target |
| --- | --- | --- |
| Primary action | Global `button`, `.button-link` | Shared `Button` primary variant and compatible link styling |
| Secondary action | `.secondary-button` | Shared secondary and ghost variants |
| Destructive action | Page-specific secondary buttons or confirmation flows | Shared danger variant while preserving confirmations |
| Status and score | `.status-pill`, `.score-badge` | Shared `Badge` and `MatchScoreBadge` |
| Feedback | `.error-banner`, `.status-banner`, `.warning-banner` | `AlertBanner` and `ToastRegion` |
| Empty state | `.empty`, `.saved-jobs-empty-detail` | Shared `EmptyState` |
| Loading state | Plain loading paragraphs | Shared `Skeleton` and `SkeletonRows` |
| Section heading | `.profile-card-header`, `.section-heading` | `SectionHeader` |
| Page heading | Eyebrow, `h1`, and `.lede` repeated in routes | `PageHeader` |
| Action grouping | `.button-row` | `Toolbar` or page/section action region |
| List/detail workspace | Saved jobs, profile, applications, interviews, job search grids | Shared split-pane rules while preserving page ownership |
| Repeated panel | `.profile-card` | Keep only for records or genuinely framed tools; remove from page-level sections incrementally |

## Behavior That Must Not Regress

### Application shell

- Authentication is checked before private navigation is rendered.
- Signed-out users retain public-preview navigation.
- Admin navigation remains conditional on the authenticated role.
- Sign Out terminates the server session and returns the shell to anonymous mode.
- Applications can expand to Materials and Interviews and remember the expansion state.
- Ask Scout receives the current local path in its `from` parameter.

### Dashboard

- Signed-out users receive the public homepage.
- Signed-in users receive Recommended Next Step, setup alerts, application actions, best matches, and recent jobs.
- Best-match links open the saved job's match-data context.
- Refresh reloads the dashboard without changing records.

### Saved jobs

- Active and archived jobs are mutually filtered by the archived-only control.
- Selecting View or Match Data opens the corresponding right-side detail pane.
- Selecting the already open record can be closed through its detail control.
- Bulk Match and Bulk Remove use explicit selection modes.
- Bulk removal retains its destructive confirmation and application-reference protection.
- Jobs without structured data expose Analyze and Match but not unavailable detail actions.
- Manual jobs remain editable through the existing editor and user-edited-job persistence boundary.
- Existing source URLs reuse cached job data where available.
- Signed-out previews never call import, analysis, matching, or persistence APIs.

### Job search

- Search requires keyword and location and currently requests at most ten results.
- Results remain paginated two at a time on the client.
- Selection and viewed-detail state remain independent.
- The detail pane displays normal text rather than a scrolling textarea.
- Import can optionally run matching against one selected resume profile.
- Signed-out previews cannot invoke provider-backed search or import.

### Job list import

- A list URL can be prefilled from an allowlisted local query parameter without auto-submission.
- Discovery selects returned candidates by default.
- Load More merges candidates without duplicating source URLs.
- Provider warnings remain visible before import.
- Matching requires a resume profile when enabled.
- Partial import failures remain visible independently of successful imports.
- Signed-out previews cannot discover, scrape, import, or match jobs.

### Single and manual job creation

- URL import does not save until the user reviews and saves the draft.
- Extraction failures preserve the manual fallback path.
- Manual creation uses user-owned editable job data rather than polluting the shared cache.
- Top-level back navigation returns to Saved Jobs.

## Selector Migration Notes

The following existing selectors remain in `client/app/styles.css` because later phases still consume them. They should be retired only after all consumers migrate:

- `.profile-card` and `.profile-card-header`
- `.button-link`, `.secondary-button`, and `.button-row`
- `.status-pill` and `.score-badge`
- `.error-banner`, `.status-banner`, and `.warning-banner`
- `.saved-jobs-workspace`, `.profile-workspace`, `.applications-workspace`, and `.interviews-workspace`
- `.saved-jobs-detail-pane`, `.profile-detail-pane`, `.applications-detail-pane`, and `.interviews-detail-pane`
- `.metadata`, `.empty`, and `.section-heading`

The Phase 1 stylesheet split is intentionally incremental:

- `client/app/styles/tokens.css` owns design tokens.
- `client/app/styles/overhaul.css` owns migrated foundations, shared components, shell, dashboard, and Phase 4 workflows.
- `client/app/styles.css` remains the legacy entry until later page phases migrate.

## Representative Screenshot Matrix

The following states should be captured when visual verification is available:

| Route | Required states |
| --- | --- |
| `/` | Signed-out, dashboard loading, populated, no setup alerts, dashboard error |
| `/jobs` | Signed-out preview, loading, empty, populated, selected detail, selected match data, bulk match, bulk remove, archived only |
| `/jobs/search` | Signed-out preview, empty search, searching, results page 1, later result page, selected detail, provider warning, import result |
| `/jobs/import-url` | Signed-out, empty URL form, parsing, review draft, extraction warning, extraction failure/manual fallback |
| `/jobs/import` | Signed-out, discovery form, discovering, candidate review, load more, warning, partial import result |
| `/jobs/manual` | Signed-out, empty editor, validation, saved result |
| Application shell | Desktop active routes, expanded Applications, collapsed Applications, admin navigation, mobile drawer open/closed |

Required viewport fixtures:

- `1440x900`
- `1280x800`
- `1024x768`
- `390x844`

## Accessibility Review Matrix

- Keyboard navigation through every sidebar item and subsection.
- Escape closes the mobile drawer and returns focus to the menu trigger.
- Tab and Shift+Tab remain contained while the mobile drawer is open.
- Active navigation exposes `aria-current="page"`.
- Selected job and viewed search result expose a textual selected/viewed indication.
- Loading regions use `aria-busy` or an equivalent accessible label.
- Toast completion uses an `aria-live` region.
- Error feedback uses alert semantics.
- Status and match-score colors are paired with text.
- Reduced-motion mode suppresses navigation, toast, skeleton, and hover motion.
