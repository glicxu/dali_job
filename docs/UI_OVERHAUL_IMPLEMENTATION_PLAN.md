# DaliJob UI Overhaul Implementation Plan

Status: in progress. Phases 1-8 were implemented on 2026-08-06. Phase 9 implementation and automated hardening are complete, but full desktop/tablet/mobile screenshots and hands-on visual regression remain open because the development servers were intentionally not started. The Phase 0 inventory is complete with the same screenshot exception. This frontend redesign does not require a database migration or intentional API behavior changes.

## Purpose

DaliJob has grown into a capable career-management application, but its visual presentation has not grown at the same rate. The current interface relies heavily on white bordered panels, gray metadata, dark rectangular buttons, and nearly identical spacing across unrelated workflows. This makes the application feel plain and gives primary actions, supporting information, warnings, and low-priority details similar visual weight.

This plan defines a comprehensive UI overhaul that makes DaliJob feel like a polished member of the Dalifin ecosystem. The redesign will use a blue-led visual identity, stronger information hierarchy, clearer workflow guidance, and reusable frontend components while preserving the current client/server boundary and existing product behavior.

The target is a professional career workspace rather than a decorative marketing site. The application should remain efficient for repeated use, readable with large amounts of job and resume data, and clear about the next action a user should take.

## Goals

1. Establish a recognizable blue-led Dalifin visual identity.
2. Guide attention through deliberate hierarchy instead of giving every section equal emphasis.
3. Make navigation state, primary actions, selected records, and workflow status immediately visible.
4. Replace repeated one-off styling with reusable design tokens and interface components.
5. Improve the highest-value workflows: dashboard, saved jobs, job search, applications, resume profiles, and matching.
6. Preserve dense, efficient list/detail workflows without turning operational pages into marketing layouts.
7. Improve responsive behavior, keyboard use, focus visibility, loading states, and empty states.
8. Keep the redesign incremental so each phase can be reviewed without breaking the entire client.

## Non-Goals

- Rewriting the Next.js application in another frontend framework.
- Replacing the server API or changing database ownership boundaries.
- Adding unrelated product functionality during visual redesign work.
- Introducing a large component framework solely to obtain default styling.
- Making every surface blue or adding color without semantic purpose.
- Filling operational pages with oversized hero sections, decorative illustrations, or excessive animation.
- Hiding advanced workflows in favor of an oversimplified interface.
- Changing the public-preview authorization rules or exposing private data to signed-out visitors.

## Current-State Findings

The current UI has several structural causes behind the criticism that it is too simple and visually plain:

1. `client/app/styles.css` is a single stylesheet of more than 2,600 lines, with repeated literal colors and page-specific rules mixed with global component rules.
2. Most sections use the same white background, gray border, six-pixel radius, and similar padding.
3. Primary and secondary actions are often differentiated only by a dark or light gray fill.
4. Top-level sidebar links do not consistently show the active route even though `AppShell` already reads the pathname.
5. Navigation uses text without familiar icons, section labels, or a strong selected-page treatment.
6. Page headings, filters, actions, records, and detail panes do not follow one reusable layout contract.
7. Loading feedback is often plain text rather than a stable skeleton or progress state.
8. Empty states describe missing content but do not always make the next useful action visually obvious.
9. Existing list/detail layouts are functionally useful, but their selected rows and detail panes need stronger visual relationship.
10. Mobile currently stacks the sidebar above the page instead of providing a dedicated compact navigation pattern.
11. The application-expansion symbol in `AppShell` contains a corrupted character and should be replaced with a standard icon.

## Design Principles

### 1. Blue identifies DaliJob

Blue should own brand recognition, current navigation, selected records, links, primary buttons, focus rings, and informational states. Multiple blue values may be used for hierarchy, but large regions should not be filled with slightly different blues only for decoration.

### 2. Semantic colors retain meaning

Supporting colors prevent a one-note palette and communicate state:

- Green: successful outcomes, completed tasks, strong matches, accepted offers.
- Amber: recommended next steps, deadlines, incomplete setup, review needed.
- Coral/red: destructive actions, overdue items, rejected applications, errors.
- Cool off-white: the default neutral foundation for page backgrounds and quiet workspace surfaces, replacing a uniform gray canvas.
- Neutral gray is reserved for secondary text, disabled controls, borders, dividers, and inactive states rather than used as the dominant background color.

### 3. Hierarchy before decoration

Each page should clearly answer:

1. Where am I?
2. What requires attention?
3. What is the primary action?
4. What information is supporting detail?

Color, typography, spacing, alignment, and density should all reinforce those answers.

### 4. Cards represent records, not entire pages

Cards should be reserved for repeated jobs, applications, resumes, alerts, and other discrete records. Page sections should usually be unframed layouts, full-width bands, toolbars, or sections separated by spacing and dividers. Cards must not be nested inside decorative cards.

### 5. Workflows remain compact

DaliJob is an operational application. Saved jobs, applications, documents, interviews, and analytics should prioritize scanning, comparison, and repeated action. Compact rows, split panes, tables, segmented controls, and status indicators are preferable to oversized text and decorative composition.

### 6. Motion explains change

Animation should be limited to approximately 150-200 milliseconds and used for navigation expansion, selection, panel disclosure, loading completion, and toast entry. `prefers-reduced-motion` must disable nonessential motion.

## Blue-Led Color System

The exact values should be validated for WCAG contrast before implementation. The initial token proposal is:

| Token | Value | Use |
| --- | --- | --- |
| `--brand-950` | `#102A43` | Sidebar and high-contrast brand surfaces |
| `--brand-900` | `#123B66` | Sidebar hover and strong headings |
| `--brand-800` | `#174F8A` | Pressed controls and selected navigation |
| `--brand-700` | `#1F5FAF` | Primary actions and active indicators |
| `--brand-600` | `#2F73D9` | Links, focus, and interactive emphasis |
| `--brand-200` | `#BFD7F7` | Selected borders and progress tracks |
| `--brand-100` | `#DCEBFF` | Selected-row and informational backgrounds |
| `--brand-50` | `#F2F7FF` | Subtle page bands and hover backgrounds |
| `--surface-page` | `#F6F8FB` | Cool off-white main application background |
| `--surface-raised` | `#FFFFFF` | Records, menus, and detail surfaces |
| `--text-strong` | `#172B3A` | Main text |
| `--text-muted` | `#5E6F7F` | Metadata and secondary text |
| `--border-default` | `#D7E0E8` | Neutral boundaries |
| `--success-700` | `#1F7A5A` | Success and positive outcomes |
| `--success-50` | `#EAF7F1` | Success background |
| `--warning-700` | `#A76500` | Warnings and recommended steps |
| `--warning-50` | `#FFF6DA` | Warning background |
| `--danger-700` | `#B9384E` | Errors and destructive actions |
| `--danger-50` | `#FDECEF` | Error background |

Rules:

- Primary blue buttons must remain readable at normal and hover states.
- Status colors must always be paired with text or an icon and never be the only signal.
- Match scores should use semantic ranges, not ten unrelated colors.
- The default neutral canvas must read as a cool off-white rather than a uniform gray; gray should support hierarchy instead of dominating the page.
- Background colors should be light enough to preserve a quiet professional workspace.
- Gradients, decorative blue glows, and blue-on-blue low-contrast text are not part of the design system.

## Typography

Use a modern interface stack with reliable local fallbacks:

```css
font-family: Inter, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
```

Initial type scale:

| Role | Size | Weight |
| --- | ---: | ---: |
| Page title | 30-32px | 700 |
| Major section heading | 20px | 700 |
| Compact panel heading | 16-18px | 700 |
| Body | 15-16px | 400-500 |
| Compact row text | 14px | 400-600 |
| Metadata and badge | 12-13px | 500-700 |

Typography rules:

- Do not scale fonts based on viewport width.
- Use zero letter spacing except where existing accessibility requirements demand otherwise.
- Limit uppercase text to short labels such as status or section eyebrows.
- Keep body line height between approximately `1.45` and `1.6`.
- Long titles must wrap without colliding with actions or badges.

## Spacing, Radius, And Elevation

Use a four-pixel spacing foundation with named tokens for `4`, `8`, `12`, `16`, `24`, `32`, and `40` pixels.

- Controls: six-pixel radius.
- Cards and panels: eight-pixel maximum radius.
- Status badges: pill shape is acceptable because they represent compact state.
- Shadows: subtle and reserved for sticky panes, menus, dialogs, and elevated calls to action.
- Borders: use dividers for section structure and avoid boxing every subsection.

## Application Shell

### Desktop sidebar

- Increase the sidebar width to approximately `248px`.
- Use `--brand-950` as the main background.
- Add the DaliJob wordmark as the first-viewport product signal.
- Add icons from `lucide-react` for recognizable navigation items.
- Add small section labels to group navigation:
  - Career: Home, Resume Profile, Jobs, Job Search, Match.
  - Pipeline: Applications, Materials, Interviews.
  - Workspace: Documents, Analytics.
- Keep Account, Admin when authorized, and Sign Out in a bottom-aligned utility region.
- Replace the corrupted expansion glyph with `ChevronDown`.
- Mark the active route with a lighter blue fill, left indicator, icon color, and `aria-current="page"`.
- Preserve the smooth Applications subsection expansion and reduced-motion behavior.

### Ask Scout

- Keep Ask Scout available globally to authenticated users.
- Present it as a full-width sidebar action with a message or sparkle icon.
- Use a clearly different brand-blue treatment from ordinary navigation without making it appear destructive or urgent.
- Preserve the dedicated Ask Scout page and current-path handoff.

### Mobile navigation

- Replace the stacked full sidebar with a compact top application bar and an accessible navigation drawer.
- Keep the brand, current page, and menu trigger visible.
- Trap focus while the drawer is open and restore focus when it closes.
- Ensure Ask Scout remains reachable without covering primary page controls.

## Shared Page Layout

Every authenticated page should use a common structure:

1. Optional breadcrumb or back action.
2. Page header containing title, concise context, and a primary action.
3. Optional status, filter, or segmented-control toolbar.
4. Main workflow content.
5. Empty, loading, error, or success feedback in stable locations.

The header should not be enclosed in a decorative card. Detail pages may use a narrow breadcrumb row followed by the page title and action group.

## Shared Components

Create reusable components before redesigning individual pages:

### Navigation and layout

- `AppSidebar`
- `MobileAppHeader`
- `PageHeader`
- `Breadcrumbs`
- `WorkspaceSplitPane`
- `SectionHeader`
- `Toolbar`

### Controls

- `Button` variants: primary, secondary, ghost, danger, icon.
- `IconButton` with tooltip and accessible label.
- `SegmentedControl`
- `SelectField`, `TextField`, and `TextAreaField`
- `Checkbox` and `Toggle`
- `Menu` for sets of secondary actions.

### Feedback and data display

- `StatusBadge`
- `MatchScoreBadge`
- `AlertBanner`
- `ToastRegion`
- `EmptyState`
- `SkeletonRow` and `SkeletonPanel`
- `RecordRow`
- `DetailSection`
- `Stat`
- `ProgressBar`
- `ConfirmDialog`

Component rules:

- Use Lucide icons rather than manually drawn SVGs or text glyphs.
- Icon-only controls require a tooltip and accessible label.
- Button dimensions must remain stable during loading.
- Destructive actions must not share the primary blue style.
- Empty and loading states must not resize the surrounding layout unexpectedly.

## Page Redesign Requirements

### Home dashboard

- Keep Recommended Next Step as the strongest visual element below the page header.
- Use a light amber attention band with one primary action, not a dark promotional card.
- Keep setup alerts compact and visually secondary to the recommendation.
- Add a compact summary strip for active applications, upcoming actions, saved jobs needing analysis, and strong matches when the API supports the data already available.
- Present application actions as the first working list after setup information.
- Present Best Matches and Recently Saved Jobs as compact repeated rows with score/status badges.
- Do not place page sections inside nested cards.

### Resume Profile

- Preserve the left list and right detail workspace on desktop.
- Make resume rows easier to scan with title, default status, update date, and short summary.
- Make the selected resume unmistakable through blue selection treatment.
- Render the right side like a readable professional resume when not editing.
- Separate view and edit modes so form fields do not dominate normal viewing.
- Keep Import Resume as a separate, compact action section above the workspace.

### Saved Jobs

- Preserve the current list/detail layout because it supports comparison well.
- Introduce a filter and action toolbar above the list.
- Place match score, job title, company, location, deadline, and analysis state in a predictable row hierarchy.
- Use score bands consistently:
  - `0-4`: low compatibility.
  - `5-7`: moderate compatibility.
  - `8-10`: strong compatibility.
- Highlight the selected job with a blue edge, background, and `aria-selected` state.
- Keep Match as the primary row action; move less-used actions into a menu where practical.
- Keep the stored source description viewable without requiring AI analysis; reserve Analyze for generating the structured job profile.
- Give the sticky detail pane a clear header and section navigation for long job profiles.
- Keep archived mode visually distinct and explicit.

### Job Search

- Use a compact search toolbar with keyword, location, and Search aligned as one unit.
- Separate search state from result state with whitespace and a divider rather than another large wrapper card.
- Preserve the result-list/detail-pane relationship.
- Highlight the viewed result and selected import checkboxes independently.
- Keep pagination directly below the result list.
- Make Import Selected the clear final action after selection.

### Job URL and list import

- Retain dedicated pages and top back navigation.
- Use a simple step sequence: provide source, review extraction, save selected jobs.
- Display loading progress and extraction warnings near the current step.
- Avoid showing raw JSON unless the user opens an advanced disclosure.
- Keep manual fallback visible when extraction cannot proceed.

### Applications

- Keep the current list/detail behavior as the default List view.
- Add a segmented List/Board control only after the shared redesign is stable.
- In List view, emphasize status, next action, due date, priority, company, and job title.
- In a future Board view, use status columns with stable widths and horizontal overflow on small screens; do not implement drag-and-drop until status-update accessibility is designed.
- Make the selected application clear and keep the side preview read-only.
- Keep View/Edit as the transition to the full application page.
- Use a status rail or compact timeline on the full detail page.
- Keep materials, tasks, notes, interviews, and timeline collapsed until requested, as currently intended.

### Match

- Make the result score and recommendation the first visual focus after matching.
- Use a stable score block or progress visualization rather than a decorative chart.
- Present matched and missing skills in clearly differentiated sections.
- Present supported and unsupported requirements as evidence rows, not raw JSON.
- Place the low-score save decision above detailed comparison data.
- Preserve bulk matching while showing per-job progress and result state.

### Documents

- Replace repeated document cards with a compact table or structured file list.
- Show document-type icon, title, current version, updated date, and actions.
- Move secondary actions into a menu when row space is constrained.
- Use a right-side preview pane or modal only when document rendering is available and secure.

### Interviews

- Preserve the list/detail workspace.
- Emphasize the next scheduled interview and incomplete preparation.
- Use interview type, status, date, and application as the row hierarchy.
- Make generated preparation sections easy to scan and collapse.
- Keep journal notes visually quieter than interview logistics and preparation actions.

### Analytics

- Keep filters compact and sticky when useful.
- Give KPI values stronger typographic hierarchy while keeping definitions accessible.
- Use blue for the primary data series and semantic colors only for outcomes.
- Add legends and text values so color is never the only signal.
- Reduce excessive boxed KPI styling by using a single summary band with dividers.
- Preserve table access to exact values.

### Materials

- Preserve application/document-version provenance.
- Use a version rail or compact history list and a focused document editor.
- Visually distinguish generated, edited, and attached versions.
- Keep source evidence behind an explicit disclosure.

### Ask Scout

- Keep the page compact and task-oriented.
- Style the prompt as the primary input and responses as normal page content rather than chat bubbles.
- Use route-action buttons with icons and clear destination labels.
- Preserve the passive advisory behavior and do not make Scout appear to execute actions.

### Account and Admin

- Separate account identity, security, destructive account controls, and diagnostic tools into clearly labeled sections.
- Keep Delete Account in a danger zone with explicit confirmation.
- Keep administrator reports dense and operational rather than adopting dashboard decoration.
- Continue hiding administrator navigation from non-admin users while enforcing authorization on the server.

### Public previews and authentication

- Make DaliJob the first prominent signal on the signed-out homepage.
- Show real product workflow previews rather than generic feature cards where possible.
- Keep Login/Register consistently visible.
- Preview pages should visually resemble their authenticated versions but clearly disable protected controls and explain that login is required.
- Do not expose AI actions, provider calls, private records, or uploaded content before authentication.

## State Design

Every major workflow must define:

- Initial empty state with one recommended action.
- Loading state using stable skeleton dimensions.
- Partial-data state.
- Success confirmation, preferably through a toast plus updated visible data.
- Validation error near the responsible field.
- Page-level failure with a retry action when appropriate.
- Disabled state with an explanation when an action requires another prerequisite.
- Archived or inactive state when applicable.

Feedback text must be concise and must not expose server traces, provider details, or raw exceptions.

## Responsive Requirements

Validate at minimum:

- Wide desktop: `1440x900`.
- Standard desktop: `1280x800`.
- Tablet/narrow desktop: `1024x768`.
- Mobile: `390x844`.

Rules:

- List/detail workspaces collapse to one column below the defined workspace breakpoint.
- Detail panes must follow the selected list record without creating inaccessible horizontal overflow.
- Toolbars may wrap, but primary actions must remain visible and labels must not be truncated ambiguously.
- Tables may scroll horizontally inside their own region; the page itself must not scroll horizontally.
- Fixed Ask Scout and navigation controls must not cover page actions or text.
- Long job titles, company names, URLs, and resume titles must wrap or truncate with an accessible full-value affordance.

## Accessibility Requirements

1. Meet WCAG AA contrast for normal text, controls, status badges, and focus indicators.
2. Add `aria-current="page"` to active navigation.
3. Add `aria-selected` to selected list records where appropriate.
4. Keep keyboard order aligned with visual order.
5. Make drawers, dialogs, menus, and disclosures fully keyboard accessible.
6. Do not use color as the only status signal.
7. Preserve reduced-motion support.
8. Keep minimum practical pointer targets near 40 pixels for primary interactive controls.
9. Associate validation errors with their fields.
10. Announce asynchronous save, import, and matching completion through an appropriate live region.

## Frontend Architecture

### Dependencies

Add `lucide-react` for interface icons. Avoid introducing a broad component framework unless a later review demonstrates that maintaining primitives internally is more expensive than adopting one.

### Styling organization

Keep CSS variables and normal CSS to remain sympathetic to the current codebase, but split the stylesheet incrementally:

```text
client/app/styles/
  tokens.css
  base.css
  shell.css
  components.css
  pages/
    dashboard.css
    profile.css
    jobs.css
    applications.css
    match.css
    documents.css
    interviews.css
    analytics.css
```

`client/app/styles.css` may remain the ordered entry point that imports these files. Existing selectors should be moved only while the related component is redesigned; a single mechanical rewrite of all CSS is not required.

### Component organization

```text
client/components/ui/
  AlertBanner.tsx
  Badge.tsx
  Button.tsx
  ConfirmDialog.tsx
  EmptyState.tsx
  Field.tsx
  IconButton.tsx
  PageHeader.tsx
  RecordRow.tsx
  SegmentedControl.tsx
  Skeleton.tsx
  ToastRegion.tsx
  Toolbar.tsx
  WorkspaceSplitPane.tsx
```

Components should remain narrowly scoped. Do not create one universal component with many unrelated boolean properties.

## Testing Strategy

### Automated checks

- Run `npm run lint`.
- Run `npm test`.
- Run `npm run build`.
- Add component-level tests for stateful primitives where practical.
- Add tests for active navigation, drawer behavior, segmented controls, dialogs, and protected preview states.
- Preserve all existing API contract and security-header tests.

### Visual verification

- Capture Playwright screenshots for the required desktop, tablet, and mobile sizes.
- Verify Home, Resume Profile, Jobs, Job Search, Applications, Match, Documents, Interviews, Analytics, Ask Scout, Account, and public preview states.
- Check empty, loading, populated, selected, error, archived, and disabled states.
- Verify no incoherent overlap, clipped text, blank panes, or unintended horizontal page scrolling.
- Compare screenshots after every page phase rather than waiting until the end.

### Accessibility verification

- Complete a keyboard-only pass.
- Inspect focus order and visible focus.
- Run automated accessibility checks where supported.
- Verify labels and status announcements with a screen reader on core workflows.
- Verify high zoom and reduced-motion behavior.

## Implementation Phases

### Phase 0: Baseline and inventory

- [ ] Capture current screenshots for all major pages at desktop and mobile sizes.
- [x] Inventory repeated controls, cards, badges, alerts, empty states, and layouts.
- [x] Record existing page-specific interaction behavior that must not regress.
- [x] Identify CSS selectors that can be retired only after their consuming pages migrate.
- [x] Define screenshot and accessibility review fixtures with representative data.

Phase 0 inventory is recorded in `docs/UI_OVERHAUL_BASELINE.md`. Screenshot routes, states, viewports, and accessibility checks are defined there. Actual baseline capture remains open because the client and server were not started during this implementation.

### Phase 1: Design foundations

- [x] Add color, typography, spacing, radius, shadow, and motion tokens.
- [x] Add the blue-led Dalifin palette and semantic status tokens.
- [x] Add `lucide-react`.
- [x] Implement shared Button, IconButton, Badge, Alert, Field, EmptyState, Skeleton, and Toast primitives.
- [x] Implement PageHeader, Toolbar, SectionHeader, and WorkspaceSplitPane.
- [x] Add shared focus, hover, disabled, loading, and reduced-motion behavior.
- [x] Begin splitting `styles.css` without changing unrelated page behavior.

Phase 1 introduced `client/app/styles/tokens.css`, `client/app/styles/overhaul.css`, and shared primitives under `client/components/ui/`. The legacy stylesheet remains in place for pages scheduled in Phases 5-8 and can be retired incrementally.

### Phase 2: Application shell and navigation

- [x] Redesign the desktop sidebar.
- [x] Add icons, section labels, active-route styling, and `aria-current`.
- [x] Replace the corrupted application-expansion glyph.
- [x] Keep Account, Admin, and Sign Out in a bottom utility area.
- [x] Redesign the Ask Scout launcher.
- [x] Implement the mobile header and accessible navigation drawer.
- [x] Apply the shared content width and page-header layout.

Phase 2 added grouped Career, Pipeline, and Workspace navigation, Lucide icons, route-aware selection, a full-width Ask Scout action, a bottom utility region, and a mobile drawer with Escape handling, focus containment, scrim dismissal, and focus restoration.

### Phase 3: Home and system feedback

- [x] Redesign Recommended Next Step as the strongest dashboard action.
- [x] Redesign setup alerts as compact supporting items.
- [x] Redesign application actions, best matches, and recently saved jobs.
- [x] Add shared skeleton loading and empty states.
- [x] Add the toast region and migrate dashboard feedback.
- [x] Verify signed-in and public home experiences.

Phase 3 preserves both authenticated and public branches, promotes Recommended Next Step through a semantic amber band, removes unnecessary section cards, and uses shared score badges, empty states, skeletons, and refresh confirmation.

### Phase 4: Jobs and search workflows

- [x] Redesign Saved Jobs list, toolbar, selected state, and detail pane.
- [x] Redesign match-score and job-status badges.
- [x] Redesign archive and bulk-selection modes.
- [x] Redesign Job Search form, results, detail pane, selection, and pagination.
- [x] Redesign single URL import, list import, and manual job entry.
- [x] Preserve extraction warnings, manual fallback, and protected preview states.

Phase 4 preserves the existing APIs and behavior while applying shared page headers, semantic match bands, selection treatments, toolbars, responsive result tables, sticky detail panes, loading feedback, warnings, and protected signed-out previews.

Saved source descriptions are available in a dedicated read-only detail view before analysis. Structured Profile and Match Data views remain separate so viewing source text never triggers OpenAI usage.

Phases 1-4 verification on 2026-08-06: `npm run lint`, all nine client tests, and `npm run build` passed. No development server was started, so final browser screenshots and visual interaction review remain part of the open Phase 0 and Phase 9 work.

### Phase 5: Applications and interviews

- [x] Redesign the Applications list/detail workspace.
- [x] Redesign application status, stage, priority, and next-action presentation.
- [x] Redesign the full application detail and edit page.
- [x] Redesign collapsed materials, tasks, notes, interviews, and timeline sections.
- [x] Redesign Interviews list, detail pane, preparation guides, and journal notes.
- [x] Evaluate List/Board mode after the default List view is stable.

Phase 5 applies semantic status and priority badges, compact filters, selected-row treatments, shared loading and empty states, clearer read-only previews, and redesigned collapsible detail sections. Board mode was evaluated and deferred: the current number of workflow states and the existing detail-heavy interaction favor the more accessible list/detail view until drag-and-drop stage management becomes a demonstrated user need.

### Phase 6: Resume profiles and matching

- [x] Redesign resume import and parse-review states.
- [x] Redesign resume profile list, default marker, and selection state.
- [x] Add readable resume view mode and separate edit mode.
- [x] Redesign Match source controls and single/bulk matching progress.
- [x] Redesign score, evidence, missing requirements, and recommendations.
- [x] Verify low-score save decisions and existing token-saving guards.

Phase 6 adds a professional read-only resume presentation with explicit Edit mode, keeps default and selected profiles visually distinct, and separates match-source configuration from evidence results. The no-resume guard still blocks provider calls, and matches below 5 still require an explicit save decision.

### Phase 7: Documents, materials, and analytics

- [x] Redesign the document library as a structured file list or table.
- [x] Redesign document version actions and preview behavior.
- [x] Redesign application material history, editor, and provenance display.
- [x] Redesign analytics filters, KPI band, charts, definitions, and tables.
- [x] Verify exact values remain available independently of color or charts.

Phase 7 presents document name, latest version, type, and actions in stable columns; preserves extracted-text preview and version replacement; and makes material provenance and history explicit. Analytics retains exact counts, percentages, sample sizes, average and median durations, and accessible trend labels independently of visual color or bar length.

Phases 5-7 verification on 2026-08-06: `npm run lint`, all twelve client tests, CSS token validation, `git diff --check`, and `npm run build` passed. No development server was started, so final browser screenshots and hands-on interaction review remain part of Phases 0 and 9.

### Phase 8: Ask Scout, account, admin, and public previews

- [x] Redesign Ask Scout while preserving passive advisory behavior.
- [x] Redesign authentication and account security sections.
- [x] Redesign account deletion danger controls.
- [x] Redesign administrator reports and diagnostic links.
- [x] Apply the visual system consistently to public preview pages.
- [x] Verify protected actions remain disabled and provider calls remain blocked when signed out.

Phase 8 gives Ask Scout a focused advisory workspace, makes its passive role explicit, and uses semantic result badges without enabling direct actions. Authentication now separates session, security, and destructive controls; account reports and administrator diagnostics use the shared hierarchy and feedback components; and signed-out pages retain clearly disabled previews. Static regression coverage verifies that protected page guards return preview or login guidance before authenticated implementations are rendered.

### Phase 9: Responsive and accessibility hardening

- [ ] Complete desktop, tablet, and mobile screenshot verification.
- [x] Complete keyboard and focus-order review.
- [x] Verify contrast and status redundancy.
- [x] Verify reduced motion.
- [x] Verify long text and localization-resistant layouts.
- [x] Remove obsolete selectors and duplicate color literals.
- [x] Run lint, tests, CSS token validation, and the production build.
- [ ] Complete final hands-on browser visual regression review.

Phase 9 adds responsive account, Scout, admin, operation, and diagnostic layouts; global long-content wrapping; resilient preformatted-text handling; keyboard-visible focus; a focus-trapped mobile drawer; and reduced-motion overrides. Repeated neutral, disabled, focus, skeleton, and text-on-brand colors now use design tokens, while obsolete component-specific status selectors were removed. Automated contrast checks cover the core page text, muted text, and primary action combinations, and status remains communicated with text rather than color alone.

Phases 8-9 automated verification on 2026-08-06: `npm run lint`, all sixteen client tests, CSS token validation, `git diff --check`, and `npm run build` passed. The build compiled all 22 routes. No development server was started, so viewport screenshots and final hands-on visual regression remain the only open Phase 9 verification tasks.

## Acceptance Criteria

The overhaul is complete when:

1. DaliJob has a consistent blue-led Dalifin identity without relying on blue for every semantic state.
2. Every page has a clear title, primary action, and information hierarchy.
3. Active navigation and selected records are immediately recognizable.
4. Primary, secondary, destructive, and icon actions use consistent components.
5. Repeated records use compact, scannable layouts and page sections are not unnecessarily card-wrapped.
6. Core list/detail workflows remain efficient on desktop and usable on mobile.
7. Loading, empty, success, warning, error, disabled, and archived states are designed consistently.
8. Ask Scout remains visible without obscuring application controls.
9. No UI exposes private data or enables protected provider actions before authentication.
10. All major pages pass desktop and mobile screenshot review without overlap, clipping, blank regions, or horizontal page overflow.
11. Keyboard navigation, focus visibility, reduced motion, and WCAG AA contrast are verified for core workflows.
12. Client lint, tests, and production build pass.

## Recommended Delivery Order

Implement Phases 0 through 2 first and review the shell before changing individual workflows. The new navigation, tokens, typography, shared controls, and page headers will produce the largest immediate visual improvement and establish the rules every later page should follow. Home and Saved Jobs should then be the first redesigned pages because they demonstrate both dashboard hierarchy and the core list/detail workflow.
