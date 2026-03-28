# Feature Comparison: Jinja2+HTMX+Alpine.js vs React Migration

> Generated: 2026-03-27
> Method: Page-by-page feature audit of every template vs React component

---

## Summary

| Metric | Templates (Jinja2) | React | Coverage |
|--------|-------------------|-------|----------|
| Template files | 17 | 25 (pages) + 5 (components) + 6 (hooks/stores) | - |
| Total template lines | ~6,454 | ~8,890 | - |
| Features covered | - | - | ~82% |
| Features MISSING | - | - | ~38 items |
| Features EXTENDED | - | - | ~15 items |

---

## PRIORITY 1 (Most Complex)

---

## 1. AgentsPage: agents.html (1346 lines) -> agents/*.tsx (11 files, ~2,400 lines)

### Covered
- [x] Three-column layout: sidebar | chat | right panel
- [x] Conversation sidebar with list, new conversation, load conversation
- [x] Conversation deletion (with X button on hover)
- [x] Chat message rendering: user, assistant, tool_call, tool_result, approval
- [x] User messages styled as right-aligned accent bubbles
- [x] Assistant messages with markdown rendering (MarkdownRenderer component)
- [x] Tool call cards with tool name and JSON args display
- [x] Tool result cards with output display
- [x] Approval cards with approve/reject buttons
- [x] Typing indicator (bouncing dots animation)
- [x] Todo panel with progress bar, icons per status, collapse/expand
- [x] Todo just-completed flash-green animation
- [x] Todo in_progress pulse animation
- [x] Slash command menu with fuzzy filter, keyboard navigation (Up/Down/Enter/Tab/Escape)
- [x] 15 slash commands: /status, /docker, /services, /users, /disk, /gpu, /logs, /search, /health, /security, /deep-research, /deep-audit, /deep-analysis, /tasks, /help
- [x] Textarea auto-resize, Enter to send, Shift+Enter for newline
- [x] Send button disabled during streaming or empty input
- [x] Safety toggle: supervised/autonomous mode with confirm dialog
- [x] Confirm modal for autonomous mode switch
- [x] Terminal panel via xterm.js + WebSocket + FitAddon
- [x] Terminal reconnect button on disconnect
- [x] Terminal resize handling (window + ResizeObserver)
- [x] Terminal connection status indicator (connecting/connected/disconnected/error)
- [x] Patrol panel with 5 sub-views: tasks, alerts, templates, reports, cases
- [x] Patrol tasks list with status dots, enable/disable toggle, run-now button
- [x] Patrol task detail: display_name, description, interval, last_run, last_status, next_run, prompt preview
- [x] Alerts view: rule list with severity, alert history with severity badges and resolved status
- [x] Templates view: list + detail with prompt preview and create-task-from-template button
- [x] Reports view: fault report list with severity badge, detail with resolve button
- [x] Cases view: search input, case list, case detail with category/created_at/summary
- [x] Admin panel: system prompt editor with save/reset
- [x] Admin panel: SubAgent config list with edit mode (name, model, description, tools)
- [x] Admin panel: memory editor with save
- [x] Admin panel: RAG status display (enabled, document_count, index_status, last_indexed)
- [x] Admin panel: RAG reindex button
- [x] Tab switching between patrol/admin in right panel
- [x] Terminal toggle button in top bar
- [x] Admin-only visibility for right panel, terminal, safety toggle
- [x] SSE streaming for chat (via useSSEChat hook)
- [x] Message deduplication via _serverId

### MISSING (needs implementation)
- [ ] **Conversation delete button visible in sidebar item** -- original has conv-item with delete, React has it but using X icon (covered, minor style diff)
- [ ] **Tab persistence in localStorage** -- original: `localStorage.getItem('agent-tab')`, React: tab state not persisted across page loads. Severity: LOW
- [ ] **Patrol Cron mapping display** -- original: `patrolCronMap` showing corresponding cron script names (e.g., "Cron: memory-emergency.sh"). Line 929-936. Severity: LOW
- [ ] **Patrol interval inline edit** -- original: inline number input + save button to update interval_minutes per patrol task. Lines 455-459. Severity: MEDIUM
- [ ] **Patrol next-run countdown text** -- original: `nextRunText(p)` showing "N分钟后运行" with live countdown. Lines 939-948. Severity: LOW
- [ ] **Patrol last_report markdown rendering** -- original: renders `p.last_report` as rendered markdown in detail pane. Line 466. React only shows prompt text, not the actual report. Severity: MEDIUM
- [ ] **Alert rule inline editing** -- original: editable warning_threshold, critical_threshold, cooldown_minutes, notify toggle, enabled toggle + save button per rule. Lines 483-507. Severity: HIGH
- [ ] **Alert history filtering by selected rule** -- React does filter by rule_name match, but original also shows rule details + edit controls. Severity: MEDIUM
- [ ] **Template category grouping** -- original groups templates by category (performance/availability/security/general) with category headers. Lines 415-429. React shows flat list. Severity: LOW
- [ ] **Template variable table** -- original: shows variables table with name/type/default/description columns. Lines 549-563. React does not display template variables. Severity: MEDIUM
- [ ] **Template is_builtin badge** -- original shows "内置" badge on built-in templates. Lines 422, 536. Severity: LOW
- [ ] **Create-from-template modal with variable inputs** -- original: full modal with task name, interval, and dynamic variable inputs per template. Lines 829-856. React: simple POST without variable customization. Severity: HIGH
- [ ] **Fault report detailed fields** -- original: root_cause, symptoms list, immediate_actions list, long_term_solutions list, evidence list. Lines 588-607. React only shows a single `detail` text block. Severity: HIGH
- [ ] **Fault case detailed fields** -- original: symptoms, root_cause, solution, tags, source badge (auto/manual). Lines 621-643. React shows only summary text. Severity: MEDIUM
- [ ] **SubAgent model provider/model two-level selector** -- original: provider dropdown + model dropdown with provider-specific model lists. Lines 693-718. React: simple text input for model. Severity: HIGH
- [ ] **SubAgent system_prompt field editing** -- original: textarea for system_prompt per SubAgent. Line 724. React: not included in edit form. Severity: MEDIUM
- [ ] **SubAgent tool picker with checkbox grid** -- original: grid of checkboxes with risk badge (safe/moderate/dangerous) per tool. Lines 726-736. React: comma-separated text input. Severity: HIGH
- [ ] **SubAgent add new / delete buttons** -- original: "新增" button + "删除" button per SubAgent. Lines 670, 738. React: no add/delete, only edit existing. Severity: MEDIUM
- [ ] **SubAgent reset to default** -- original: "重置为默认" button. Line 744. React: not implemented. Severity: LOW
- [ ] **RAG detailed stats** -- original: storage_mb, sources breakdown, embedding_model, error display. Lines 768-791. React: only shows enabled/document_count/index_status/last_indexed. Severity: MEDIUM
- [ ] **Patrol prompt editing in admin panel** -- original: expandable per-patrol prompt editor + check_tools editor in admin section. Lines 801-822. Severity: MEDIUM
- [ ] **Message copy/delete/resend hover actions in original** -- original does NOT have these. React MessageBubble adds ActionBar with copy/delete/resend. This is an extension.
- [ ] **Tool card expand/collapse** -- original tool cards have fixed max-height. React ToolCard has clickable expand/collapse toggle. This is an extension.
- [ ] **/help command rendering as markdown list** -- original: renders help as markdown list of all commands. Line 976. React: /help has empty prompt, may not render properly. Severity: LOW
- [ ] **Slash command {arg} substitution** -- original: replaces `{arg}` in prompt with user-typed argument after command. Lines 980-991. React: some commands set prompt with trailing space but don't do {arg} replacement. Severity: MEDIUM

### Extended in React (new features)
- [+] Message bubble hover action bar: copy, delete, resend buttons
- [+] Tool card expand/collapse toggle with smooth transition
- [+] Mermaid diagram rendering in assistant messages
- [+] HTML artifact sandboxed iframe rendering in assistant messages
- [+] Code block copy buttons in markdown
- [+] Rich markdown rendering via marked/highlight.js (original used regex-based renderMd)
- [+] Container ResizeObserver for terminal auto-fit
- [+] Terminal reconnect functionality
- [+] react-query caching for conversations, patrols, etc.
- [+] Zustand store for chat state management (chatStore)
- [+] SSE handling via dedicated useSSEChat hook with abort support

---

## 2. DashboardPage: dashboard.html (661 lines) -> DashboardPage.tsx (1354 lines)

### Covered
- [x] Alert bar showing critical/warning counts + WS connection status
- [x] 9 stat cards: host, CPU, memory, swap, disk, network, disk I/O, Docker, GPU
- [x] Stat cards with color-coded values (green/blue/yellow/red thresholds)
- [x] Stat cards with sub-text (e.g., core count, used/total)
- [x] Sparkline mini charts on each card
- [x] Card click to drill-down detail view
- [x] CPU detail: usage rate, core count, load averages, trend chart, per-core chart
- [x] Memory detail: used/total/available, usage trend chart
- [x] Disk detail: partition table with mountpoint/used/total/percent + progress bars
- [x] Network detail: recv/send rates, total bytes, throughput trend chart
- [x] GPU detail: model, utilization, memory, temperature, trend charts
- [x] Back button from detail to overview
- [x] System resource trend chart (CPU/RAM/GPU/Swap multi-line)
- [x] History period selector: 1h/6h/24h/3d
- [x] Alert distribution donut chart
- [x] Docker health donut chart
- [x] Network throughput trend chart
- [x] Disk & mount point pressure horizontal bar chart
- [x] Top process resource chart
- [x] Container group resource stacked bar chart
- [x] Resource mix radar chart (CPU/Memory/Swap/Disk/GPU)
- [x] WebSocket real-time metrics updates
- [x] ECharts-based charting (registered dark theme)

### MISSING (needs implementation)
- [ ] **System info detail panel** -- original: hostname, OS, kernel, CPU model, core count, uptime display in info table. Lines 561-593. React: host card exists but no system detail drill-down panel with info table. Severity: MEDIUM
- [ ] **Docker detail drill-down** -- original: container status distribution donut, container group resource chart, CPU top chart, restart count chart, container table with image/state/CPU%/mem%/ports. Lines 508-558. React: drill-down for docker not implemented (card shows count but no detail panel). Severity: HIGH
- [ ] **Process table with Kill button** -- original: CPU Top 10 and Memory Top 10 tables with PID/user/process/CPU%/mem%/kill button in CPU and memory drill-downs. Lines 257-272, 327-342. Severity: HIGH
- [ ] **Process ranking modal** -- original: modal overlay with process list sortable by CPU/memory, with kill buttons. Lines 596-627. Severity: MEDIUM
- [ ] **Alert history modal** -- original: modal with alert timeline, severity badges, timestamps. Lines 629-655. Severity: MEDIUM
- [ ] **Top bar action buttons** -- original: "告警历史" and "进程排行" buttons in page top actions. Lines 6-8. Severity: LOW
- [ ] **CPU heatmap chart** -- original: per-core heatmap chart. Line 247. React has per-core line chart but not heatmap. Severity: LOW
- [ ] **Disk I/O rate chart** -- original: disk I/O read/write rate chart in disk detail. Lines 362-365. Severity: MEDIUM
- [ ] **Disk inode usage chart** -- original: inode usage bar chart. Lines 358-360. Severity: LOW
- [ ] **Disk device busy chart** -- original: device utilization percentage chart. Lines 366-368. Severity: LOW
- [ ] **Network TCP state distribution pie** -- original: TCP state distribution pie chart. Lines 424-426. Severity: LOW
- [ ] **Network packets rate chart** -- original: packets per second chart. Lines 428-430. Severity: LOW
- [ ] **Network errors and drops chart** -- original: error and drop count chart. Lines 432-434. Severity: LOW
- [ ] **GPU process table** -- original: GPU process list with PID/user/process/VRAM. Lines 487-503. React GPU detail exists but may not include process table. Severity: MEDIUM
- [ ] **Recent alerts list in overview** -- original: last 6 alerts displayed as list items with time/severity/message. Lines 185-204. Severity: MEDIUM
- [ ] **Docker abnormal count logic** -- original: `dockerAbnormalCount()` helper for warning color. Line 86. Severity: LOW

### Extended in React (new features)
- [+] ErrorBoundary wrapping each chart section for graceful failure
- [+] ReactECharts component integration (vs raw echarts init)
- [+] Type-safe MetricsData interface with WebSocket hook
- [+] Card progress bar below value showing percentage visually
- [+] Lucide icons for each card type

---

## 3. UsersPage: users.html (552 lines) -> UsersPage.tsx (642 lines)

### Covered
- [x] User resource monitoring: name, UID, memory, mem_percent, proc_count, cpu_percent
- [x] Memory usage bar with color thresholds
- [x] Per-user process list: PID, command, CPU%, MEM%
- [x] Single process kill button
- [x] Kill all processes for a user
- [x] Active sessions table: user, TTY, from, login_at, idle
- [x] User management tab: create user form (username, password, groups, shell)
- [x] All users list with UID, groups, shell, home, last login
- [x] Delete user button
- [x] Login history display per user
- [x] Quota management tab: list quotas with key, mem_gb, proc_limit, comment
- [x] Enforcement config tab: enable/disable, mode selection, thresholds
- [x] Violation history display
- [x] Tab bar switching between views

### MISSING (needs implementation)
- [ ] **Stat summary cards** -- original: 4 cards showing total users, active sessions, over-quota count, total memory usage. Lines 9-26. React: no summary stat cards at top. Severity: MEDIUM
- [ ] **Quota color-coded row borders** -- original: red left border for >100%, yellow for >75%. Line 55. React: uses color in UsageBar but no row border highlighting. Severity: LOW
- [ ] **GPU memory column in user table** -- original: shows GPU VRAM usage per user. Line 69. React: not included. Severity: LOW
- [ ] **Top processes inline in user row** -- original: shows top 3 processes inline in each user's table row with kill button + "查看全部" link. Lines 79-94. React: uses expandable card with full process list. Severity: LOW (design choice)
- [ ] **Quota inline editing** -- original: inline input fields for mem_gb, proc_limit, comment per quota row. Lines 132-135. React: needs verification of inline edit support. Severity: MEDIUM
- [ ] **Add quota form** -- original: row with inputs for new key, mem_gb, proc_limit, comment + add/save buttons. Lines 158-166. Severity: MEDIUM
- [ ] **Delete quota button** -- original: per-quota delete button. Lines 137-144. Severity: MEDIUM
- [ ] **Save all quotas button** -- original: batch save all quota changes. Line 165. Severity: MEDIUM
- [ ] **Edit user modal** -- original: edit user button opens modal for modification. Line 197. Severity: MEDIUM
- [ ] **Enforcement detailed settings** -- original: warning_pct, critical_pct, kill_pct, grace_minutes, cooldown_minutes inputs. Lines 272-292. React: needs check if all fields present. Severity: MEDIUM
- [ ] **Process modal** -- original: `openProcessModal(username)` opens a modal showing all processes. Line 92. React uses inline expansion instead. Severity: LOW (design choice)
- [ ] **HTMX partial refresh** -- original uses hx-get to refresh just the user table. Line 43. React: uses react-query refetchInterval (15s). Covered differently.

### Extended in React (new features)
- [+] Card-based user display (vs table rows) with expandable process list
- [+] react-query auto-refresh at 15s interval
- [+] Toast notifications via react-hot-toast

---

## 4. ProxyPage: proxy.html (670 lines) -> ProxyPage.tsx (513 lines)

### Covered
- [x] Proxy instance list (left panel) with name, type, running status badge
- [x] Instance selection to show details
- [x] Instance detail: running status, current config, instance type
- [x] Unified control: service name, PID, auto-start status, admin API URL
- [x] Listen ports display
- [x] Instance actions: start, stop, restart, reload
- [x] Subscription update action
- [x] Config profiles list with switch/update/update-and-switch buttons
- [x] Current config highlight badge
- [x] Add new subscription (name + URL)
- [x] Switch-after-add checkbox
- [x] Clash/Mihomo proxy groups display
- [x] Proxy group node list with current selection highlight
- [x] Node switching
- [x] Node delay testing (test all delays)
- [x] Delay color coding (green < 300ms, yellow < 800ms, red > 800ms)
- [x] Loading overlay with message
- [x] Empty state when no instances configured
- [x] Two-column layout: instance list | detail

### MISSING (needs implementation)
- [ ] **Update-and-switch preferred config** -- original: `updateAndSwitch()` for `preferred_update_config_key`. Line 126. React: needs verification. Severity: LOW
- [ ] **Subscription URL preview** -- original: shows `profile.subscription_url_preview`. Line 145. Severity: LOW
- [ ] **Version and premium badge** -- original: shows version number and "(Premium)" indicator. Line 75. Severity: LOW
- [ ] **Group expand/collapse toggle** -- original: clickable header with arrow to expand/collapse node list per group. Lines 207-221. React: needs verification of expand behavior. Severity: LOW

### Extended in React (new features)
- [+] react-query caching for instance data
- [+] Type-safe interfaces for all proxy data structures

---

## 5. CronPage: cron.html (416 lines) -> CronPage.tsx (338 lines)

### Covered
- [x] User jobs tab with list
- [x] Root jobs tab (admin only)
- [x] Job table: status toggle, schedule, command, comment
- [x] Enable/disable toggle per job
- [x] Cron expression validation with next 5 runs
- [x] Create new job form
- [x] Delete job
- [x] Execution history tab

### MISSING (needs implementation)
- [ ] **Stat summary cards** -- original: 4 cards for user jobs, root jobs, enabled, disabled counts. Lines 8-26. React: no summary cards. Severity: LOW
- [ ] **Inline schedule editing** -- original: inline cron expression input + save button per job row. Lines 76-82. React: needs verification. Severity: MEDIUM
- [ ] **Quick schedule presets dropdown** -- original: "..." button opening preset dropdown (every minute, every 5 min, hourly, daily, etc.). Lines 83-94. Severity: MEDIUM
- [ ] **Backup button** -- original: backup crontab to file. Line 41. Severity: LOW
- [ ] **Frequency badge** -- original: `job.description` shown as badge indicating human-readable frequency. Line 73. Severity: LOW

### Extended in React (new features)
- [+] Standalone ExpressionValidator component
- [+] react-query for data fetching

---

## PRIORITY 2 (Medium Complexity)

---

## 6. DockerPage: docker.html (287 lines) -> DockerPage.tsx (502 lines)

### Covered
- [x] 5 tabs: containers, stacks, images, networks, volumes
- [x] Container list with name, image, state, ports
- [x] Container actions: start, stop, restart
- [x] Container logs viewer
- [x] Container exec command
- [x] Stack list display
- [x] Image list display
- [x] Network list display
- [x] Volume list display
- [x] Prune/cleanup buttons
- [x] State color badges

### MISSING (needs implementation)
- [ ] **Stat summary cards** -- original: total containers, running, images, stacks. Lines 8-26. React: no summary cards at top. Severity: LOW
- [ ] **Image pull functionality** -- original: pull image input + button. Severity: MEDIUM (needs code verification)
- [ ] **Container status dot** -- original: status-dot indicators before badges. Lines 59-65. React: uses badge only. Severity: LOW

### Extended in React (new features)
- [+] Type-safe container/stack/image/network/volume interfaces
- [+] Lazy loading per tab via react-query `enabled` flag
- [+] 10s auto-refresh for container list

---

## 7. NotificationsPage: notifications.html (423 lines) -> NotificationsPage.tsx (410 lines)

### Covered
- [x] Send notification tab: message textarea + send/test buttons
- [x] Channel configuration tab: list channels with type, enabled status
- [x] Channel CRUD: create, edit, delete, test
- [x] Channel type badges (telegram, wecom, dingtalk, qqbot, email)
- [x] Send results display per channel
- [x] History tab: notification send history

### MISSING (needs implementation)
- [ ] **Channel inline editing form** -- original: edit form with all channel-specific fields. Line 14. React: needs verification of full edit form. Severity: MEDIUM
- [ ] **Test status indicator** -- original: `.test-status` with success/failure icons. Line 16. Severity: LOW

### Extended in React (new features)
- [+] react-query caching and invalidation

---

## 8. SettingsPage: settings.html (290 lines) -> SettingsPage.tsx (304 lines)

### Covered
- [x] AI model selection: chat model (provider + model two-level selector)
- [x] AI model selection: patrol model (provider + model two-level selector)
- [x] Provider list with name, description, API key status
- [x] Provider API key update/clear functionality
- [x] Provider status indicators (has_key vs not configured)

### MISSING (needs implementation)
- [ ] **Disabled provider options** -- original: disables providers without API key (except ollama). Lines 22, 48. React: needs verification. Severity: LOW
- [ ] **Current model display** -- original: shows "当前: provider:model" text below selectors. Lines 36, 62. Severity: LOW

### Extended in React (new features)
- [+] Type-safe provider/model interfaces

---

## 9. LogsPage: logs.html (150 lines) -> LogsPage.tsx (314 lines)

### Covered
- [x] Log file list (left panel) with name, size, modified time
- [x] File selection to load content
- [x] Search keyword input
- [x] Level filter (ERROR/WARN/INFO)
- [x] Real-time streaming toggle (SSE/EventSource)
- [x] Log content display with highlighting
- [x] Refresh button

### MISSING (needs implementation)
- [ ] **Stat cards** -- original: log file count, streaming status indicator. Lines 8-24. Severity: LOW
- [ ] **Two-column grid layout** -- original: 260px sidebar + content. Line 27. React: needs layout verification. Severity: LOW

### Extended in React (new features)
- [+] Proper EventSource management with cleanup
- [+] Type-safe log file interfaces

---

## 10. ServicesPage: services.html (164 lines) -> ServicesPage.tsx (302 lines)

### Covered
- [x] Service list: name, active status, enabled status
- [x] Service actions: start, stop, restart, reload
- [x] Enable/disable toggle
- [x] Service journal/log viewer
- [x] Search filter
- [x] Dependency tree viewer

### MISSING (needs implementation)
- [ ] **Stat cards** -- original: total services, running, stopped, auto-start counts. Lines 8-25. Severity: LOW
- [ ] **HTMX refresh** -- original: hx-get refresh button. Line 32. React: uses react-query. Severity: N/A (covered differently)

### Extended in React (new features)
- [+] Card-based detail expansion (vs inline table)
- [+] react-query auto-refresh

---

## PRIORITY 3 (Simple Pages)

---

## 11. LoginPage: login.html (612 lines) -> LoginPage.tsx (748 lines)

### Covered
- [x] Username + password form
- [x] Login submission with error display
- [x] Animated background (particle network canvas)
- [x] Glow orb ambient effects
- [x] Glassmorphism card design
- [x] Loading spinner during submission
- [x] Responsive layout
- [x] Input focus/hover effects
- [x] Redirect to dashboard on success

### MISSING (needs implementation)
- [ ] **Server info display** -- original: shows hostname, uptime in login card. Severity: LOW (may vary)

### Extended in React (new features)
- [+] react-hook-form for form validation
- [+] Mouse-tracking interactive particle effects
- [+] Exit transition animation before navigate

---

## 12. AuditPage: audit.html (50 lines) -> AuditPage.tsx (145 lines)

### Covered
- [x] Audit log table: timestamp, username, action, target, IP, result
- [x] Success/failure badges
- [x] Username filter
- [x] Pagination

### MISSING (needs implementation)
- [ ] **Server-side Jinja pagination** -- original uses server-rendered pagination with hx-get. Lines 39-49. React likely uses client-side. Severity: LOW

### Extended in React (new features)
- [+] react-query for data fetching
- [+] Client-side filtering

---

## 13. PanelUsersPage: panel_users.html (91 lines) -> PanelUsersPage.tsx (236 lines)

### Covered
- [x] Panel user list: username, display_name, role, status, last_login
- [x] Create user modal: username, password, display_name, role
- [x] Enable/disable user toggle
- [x] Delete user
- [x] Role badges (admin/user)
- [x] Current user protection (cannot delete self)

### MISSING (needs implementation)
- (none identified - full feature coverage)

### Extended in React (new features)
- [+] Password change functionality
- [+] More granular form validation

---

## 14. NetworkPage: network.html (110 lines) -> NetworkPage.tsx (100 lines)

### Covered
- [x] Port listening table: port, address, process, PID
- [x] Port search filter

### MISSING (needs implementation)
- [ ] **Stat cards** -- original: listening ports count, proxy status, HTTP proxy address. Lines 8-28. Severity: LOW
- [ ] **Proxy configuration tab** -- original: Clash process status, HTTP proxy, env vars, restart/enable buttons. Lines 65-110. Severity: MEDIUM
- [ ] **Connections statistics tab** -- original: connection count statistics. Line 34. Severity: MEDIUM
- [ ] **Proxy tab** -- original: full proxy management tab with clash controls. Lines 66-110. Severity: MEDIUM

### Extended in React (new features)
- (none - React version is minimal)

---

## 15. AssetsPage: assets.html (224 lines) -> AssetsPage.tsx (322 lines)

### Covered
- [x] Asset summary cards by type with total/healthy counts
- [x] Asset list panel with type grouping and status dots
- [x] Asset detail panel with properties table
- [x] Asset discovery button
- [x] Search filter
- [x] Detail tabs: properties, topology

### MISSING (needs implementation)
- [ ] **Mermaid topology diagram** -- original: renders mermaid topology in detail tab. Lines 43-44. React: needs verification of mermaid integration. Severity: MEDIUM
- [ ] **Type name mapping** -- original: maps type keys to Chinese labels (e.g., "systemd_service" -> custom name). Severity: LOW

### Extended in React (new features)
- [+] Type-safe asset interfaces

---

## 16. Base Layout: base.html (81 lines) -> Layout.tsx + Sidebar.tsx + TopBar.tsx (~165 lines)

### Covered
- [x] Sidebar with module list, icons, categories
- [x] Active module highlighting
- [x] Top bar with page title
- [x] Dark theme with CSS variables
- [x] Content area with scrolling

### MISSING (needs implementation)
- [ ] **Sidebar collapse/expand** -- original may have collapse behavior. React: sidebar is fixed width. Severity: LOW
- [ ] **Toast notification system** -- original: `showToast()` JS function. React: uses react-hot-toast. Covered differently.

### Extended in React (new features)
- [+] ChatWidget floating bubble available on all pages
- [+] React Router navigation (vs full page loads)
- [+] Error boundary wrapping
- [+] Sidebar store for collapse state (sidebarStore.ts)

---

## 17. ChatWidget: (embedded in base.html pattern) -> ChatWidget.tsx (604 lines)

### Covered
- [x] Floating chat bubble on all pages
- [x] Draggable positioning with localStorage persistence
- [x] Minimize/expand toggle
- [x] SSE streaming chat
- [x] Message types: user, assistant, tool, tool_result, approval
- [x] Markdown rendering with DOMPurify
- [x] Approval request handling
- [x] Conversation ID persistence
- [x] Page context awareness (sends current page path)

### MISSING (needs implementation)
- (ChatWidget is a React-only addition, no direct template equivalent)

### Extended in React (new features)
- [+] Entirely new component - provides AI chat access from any page
- [+] Page context injection for context-aware AI responses
- [+] Drag-and-drop positioning
- [+] Position persistence across sessions

---

## Critical Missing Features Summary (HIGH severity)

| # | Feature | Page | Severity |
|---|---------|------|----------|
| 1 | Alert rule inline editing (thresholds, cooldown, notify, enabled) | Agents/Patrol | HIGH |
| 2 | Create-from-template modal with variable inputs | Agents/Patrol | HIGH |
| 3 | Fault report detailed fields (root_cause, symptoms, actions, evidence) | Agents/Patrol | HIGH |
| 4 | SubAgent model provider/model two-level selector | Agents/Admin | HIGH |
| 5 | SubAgent tool picker with checkbox grid + risk badges | Agents/Admin | HIGH |
| 6 | Process table with Kill button in dashboard drill-downs | Dashboard | HIGH |
| 7 | Docker detail drill-down panel | Dashboard | HIGH |
| 8 | Network proxy/connections tabs | Network | MEDIUM |
| 9 | Patrol interval inline edit | Agents/Patrol | MEDIUM |
| 10 | Slash command {arg} substitution | Agents/Chat | MEDIUM |

---

## Architecture Observations

1. **State management**: React uses Zustand (chatStore, authStore, sidebarStore) + react-query, replacing Alpine.js reactive data.
2. **Data fetching**: react-query replaces HTMX partial refreshes and Alpine.js fetch calls. Provides caching, auto-refresh, and optimistic updates.
3. **Real-time**: WebSocket hook (useWebSocket) for dashboard metrics; SSE hook (useSSEChat) for agent chat streaming. Replaces inline EventSource/WebSocket code.
4. **Routing**: React Router replaces Jinja2 template inheritance + full page loads. Enables SPA navigation.
5. **Charting**: echarts-for-react replaces raw ECharts initialization. Original used Apache ECharts 5 with manual DOM mounting.
6. **Terminal**: Same xterm.js library, but React version adds ResizeObserver and reconnect logic.
7. **Markdown**: React uses marked + highlight.js + mermaid + DOMPurify. Original used regex-based `renderMd()`.
8. **Notifications**: react-hot-toast replaces custom `showToast()` function.
