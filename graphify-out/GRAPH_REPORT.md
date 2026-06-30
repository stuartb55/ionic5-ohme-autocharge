# Graph Report - ionic5-ohme-autocharge  (2026-06-30)

## Corpus Check
- 94 files · ~54,999 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1031 nodes · 1699 edges · 75 communities (58 shown, 17 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 34 edges (avg confidence: 0.71)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `eab5dbcb`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Poll Loop & Plug-in Detection|Poll Loop & Plug-in Detection]]
- [[_COMMUNITY_API Test Suite|API Test Suite]]
- [[_COMMUNITY_Postgres Persistence Layer|Postgres Persistence Layer]]
- [[_COMMUNITY_Frontend NPM Dependencies|Frontend NPM Dependencies]]
- [[_COMMUNITY_Project Docs & Deployment|Project Docs & Deployment]]
- [[_COMMUNITY_Octopus Test Suite|Octopus Test Suite]]
- [[_COMMUNITY_Runtime Settings Persistence|Runtime Settings Persistence]]
- [[_COMMUNITY_Charge Controls UI|Charge Controls UI]]
- [[_COMMUNITY_Dashboard & Energy Usage UI|Dashboard & Energy Usage UI]]
- [[_COMMUNITY_API Charge & Read Endpoints|API Charge & Read Endpoints]]
- [[_COMMUNITY_Energy Attribution Helpers|Energy Attribution Helpers]]
- [[_COMMUNITY_API Request Models|API Request Models]]
- [[_COMMUNITY_Frontend API Client & Types|Frontend API Client & Types]]
- [[_COMMUNITY_DB Test Suite|DB Test Suite]]
- [[_COMMUNITY_Snapshot Build Tests|Snapshot Build Tests]]
- [[_COMMUNITY_Statistics & Charts UI|Statistics & Charts UI]]
- [[_COMMUNITY_TypeScript Config|TypeScript Config]]
- [[_COMMUNITY_Octopus Tariff & Consumption|Octopus Tariff & Consumption]]
- [[_COMMUNITY_Status UI & Formatters|Status UI & Formatters]]
- [[_COMMUNITY_Statistics & Weekly Digest|Statistics & Weekly Digest]]
- [[_COMMUNITY_Bluelink Test Suite|Bluelink Test Suite]]
- [[_COMMUNITY_App Shell & Theming|App Shell & Theming]]
- [[_COMMUNITY_Settings Editor UI|Settings Editor UI]]
- [[_COMMUNITY_Snapshot & Notification Tests|Snapshot & Notification Tests]]
- [[_COMMUNITY_API App & Snapshot|API App & Snapshot]]
- [[_COMMUNITY_Poll Loop Telemetry & Persistence|Poll Loop Telemetry & Persistence]]
- [[_COMMUNITY_Schedule Timeline UI|Schedule Timeline UI]]
- [[_COMMUNITY_Ohme Client Tests|Ohme Client Tests]]
- [[_COMMUNITY_TS Node Config|TS Node Config]]
- [[_COMMUNITY_Poll & Status Tests|Poll & Status Tests]]
- [[_COMMUNITY_Ntfy Test Suite|Ntfy Test Suite]]
- [[_COMMUNITY_Live SOC Refresh Tests|Live SOC Refresh Tests]]
- [[_COMMUNITY_Efficiency & Digest Tests|Efficiency & Digest Tests]]
- [[_COMMUNITY_DB Fake Pool Fixtures|DB Fake Pool Fixtures]]
- [[_COMMUNITY_Fake DB Cursor Fixture|Fake DB Cursor Fixture]]
- [[_COMMUNITY_Mobile Dashboard Screenshot|Mobile Dashboard Screenshot]]
- [[_COMMUNITY_Desktop Dashboard Screenshot|Desktop Dashboard Screenshot]]
- [[_COMMUNITY_Polling Hook|Polling Hook]]
- [[_COMMUNITY_Config Test Suite|Config Test Suite]]
- [[_COMMUNITY_Vehicle Picker UI|Vehicle Picker UI]]
- [[_COMMUNITY_Access Log Filter Tests|Access Log Filter Tests]]
- [[_COMMUNITY_DB Error-Handling Tests|DB Error-Handling Tests]]
- [[_COMMUNITY_PWA Maskable Icon|PWA Maskable Icon]]
- [[_COMMUNITY_Battery Ring UI|Battery Ring UI]]
- [[_COMMUNITY_Renovate Config|Renovate Config]]
- [[_COMMUNITY_Fake DB Connection Fixture|Fake DB Connection Fixture]]
- [[_COMMUNITY_Quiet Access Log Filter|Quiet Access Log Filter]]
- [[_COMMUNITY_Security Headers Middleware|Security Headers Middleware]]
- [[_COMMUNITY_App Icon Asset|App Icon Asset]]
- [[_COMMUNITY_Apple Touch Icon|Apple Touch Icon]]
- [[_COMMUNITY_PWA Icon (192px)|PWA Icon (192px)]]
- [[_COMMUNITY_PWA Icon (512px)|PWA Icon (512px)]]
- [[_COMMUNITY_Service Worker|Service Worker]]
- [[_COMMUNITY_Live SOC No-Seed Test|Live SOC No-Seed Test]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]

## God Nodes (most connected - your core abstractions)
1. `StatusSnapshot` - 48 edges
2. `AppState` - 31 edges
3. `_charging_client()` - 21 edges
4. `handle_plugin_event()` - 19 edges
5. `compilerOptions` - 18 edges
6. `Hyundai → Ohme Auto-Charge` - 18 edges
7. `_mock_manager()` - 15 edges
8. `_mock_vehicle()` - 15 edges
9. `_mock_ohme_client()` - 14 edges
10. `poll_loop()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `docker-compose.yml (local dev)` --semantically_similar_to--> `docker-compose.prod.yml (home server)`  [INFERRED] [semantically similar]
  docker-compose.yml → docker-compose.prod.yml
- `_QuietAccessLogFilter` --uses--> `StatusSnapshot`  [INFERRED]
  api.py → state.py
- `SecurityHeadersMiddleware` --uses--> `StatusSnapshot`  [INFERRED]
  api.py → state.py
- `TargetUpdate` --uses--> `StatusSnapshot`  [INFERRED]
  api.py → state.py
- `ReadyByUpdate` --uses--> `StatusSnapshot`  [INFERRED]
  api.py → state.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **CI pipeline: test then smoke then publish** — github_workflows_docker_ci_test_job, github_workflows_docker_ci_frontend_test_job, github_workflows_docker_ci_smoke_job, github_workflows_docker_ci_build_backend_job, github_workflows_docker_ci_build_frontend_job [EXTRACTED 0.90]
- **Three-service deployment stack** — api, compose_postgres_service, frontend_readme_nginx [INFERRED 0.80]
- **Postgres charging-history schema** — docs_grafana_telemetry_table, docs_grafana_charge_sessions_table, docs_grafana_schedule_snapshots_table, docs_grafana_daily_stats_table, docs_grafana_grid_consumption_table [EXTRACTED 0.90]

## Communities (75 total, 17 thin omitted)

### Community 0 - "Poll Loop & Plug-in Detection"
Cohesion: 0.06
Nodes (63): get_battery_percentage(), _get_manager(), get_vehicle_state(), get_vehicle_state_async(), list_vehicles(), list_vehicles_async(), Return SOC (plus driving range and odometer) for the selected vehicle.      ``ve, Return just the current battery SOC % for the selected vehicle. (+55 more)

### Community 2 - "Postgres Persistence Layer"
Cohesion: 0.08
Nodes (33): close(), get_all_sessions(), get_grid_consumption(), get_miles_driven(), get_recent_sessions(), get_soh_history(), get_telemetry_between(), init() (+25 more)

### Community 3 - "Frontend NPM Dependencies"
Cohesion: 0.05
Nodes (36): dependencies, react, react-dom, description, devDependencies, eslint, @eslint/js, eslint-plugin-react-hooks (+28 more)

### Community 4 - "Project Docs & Deployment"
Cohesion: 0.09
Nodes (25): docker-compose.yml (local dev), Postgres published on loopback only, Bundled Postgres service, docker-compose.prod.yml (home server), FastAPI + uvicorn, hyundai-kia-connect-api, ohme library, psycopg (Postgres driver) (+17 more)

### Community 6 - "Octopus Test Suite"
Cohesion: 0.14
Nodes (27): _enable(), _enable_consumption(), _make_mock_session(), _make_mock_session_seq(), _rate(), Minimal stand-in for ohme.utils.ChargeSlot (start/end/energy)., A session whose successive ``.get`` calls return successive payloads — for     t, _Slot (+19 more)

### Community 7 - "Runtime Settings Persistence"
Cohesion: 0.11
Nodes (27): _load(), load_day_targets(), load_ready_by(), load_session_active(), load_target(), load_vehicle_id(), parse_hhmm(), Runtime-adjustable settings, persisted to a small JSON file.  Holds the dashboar (+19 more)

### Community 8 - "Charge Controls UI"
Cohesion: 0.19
Nodes (10): StatusResponse, Action, ChargeControls(), Props, scheduleFixture, sessionsFixture, statisticsFixture, statusFixture (+2 more)

### Community 9 - "Dashboard & Energy Usage UI"
Cohesion: 0.12
Nodes (15): EnergyUsageResponse, TariffResponse, PollingState, usePolling(), Banner(), Dashboard(), HeaderMeta(), EnergyUsageSection() (+7 more)

### Community 10 - "API Charge & Read Endpoints"
Cohesion: 0.09
Nodes (23): _charge_action(), get_energy_usage(), get_schedule(), get_sessions(), get_soh_history(), get_status(), get_tariff(), get_vehicles() (+15 more)

### Community 11 - "Energy Attribution Helpers"
Cohesion: 0.13
Nodes (21): attribute_car_kwh(), _canon(), merge_usage(), _parse(), datetime, Pure helpers for the household-vs-car energy breakdown.  The whole-house grid im, Parse an ISO timestamp (or pass through a datetime) to an aware UTC datetime., Canonical UTC ISO key for a half-hour boundary, so the car buckets and the     O (+13 more)

### Community 12 - "API Request Models"
Cohesion: 0.09
Nodes (24): DayTargetsUpdate, MaxChargeUpdate, Request body for PUT /api/charge/max-charge., Toggle Ohme's max-charge (boost) mode.      Enabling abandons the smart schedule, Request body for PUT /api/settings/target., Request body for PUT /api/settings/ready-by.      ``readyBy`` is a 24h ``HH:MM``, Request body for PUT /api/settings/day-targets.      ``dayTargets`` maps weekday, Request body for PUT /api/settings/vehicle (null selects the first vehicle). (+16 more)

### Community 13 - "Frontend API Client & Types"
Cohesion: 0.10
Nodes (26): api, ApiError, errorFor(), getJson(), postJson(), putJson(), RefreshResponse, REQUESTED_WITH (+18 more)

### Community 14 - "DB Test Suite"
Cohesion: 0.08
Nodes (3): Tests for the optional Postgres persistence layer.  No real database is used. We, test_record_telemetry_maps_snapshot_fields(), test_writes_are_noops_when_disabled()

### Community 15 - "Snapshot Build Tests"
Cohesion: 0.10
Nodes (22): _charging_client(), _slot(), test_build_snapshot_falls_back_to_client_battery_before_first_plugin(), test_build_snapshot_includes_lock_and_location_when_connected(), test_build_snapshot_includes_range_when_connected(), test_build_snapshot_includes_soh_when_connected(), test_build_snapshot_no_cost_when_disconnected(), test_build_snapshot_no_cost_without_price() (+14 more)

### Community 16 - "Statistics & Charts UI"
Cohesion: 0.14
Nodes (19): DailyStat, StatisticsResponse, EnergyBarChart(), METRIC_COLOR, Props, CHART_METRICS, CHART_TITLE, DeltaBadge() (+11 more)

### Community 17 - "TypeScript Config"
Cohesion: 0.10
Nodes (19): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleResolution, noEmit (+11 more)

### Community 18 - "Octopus Tariff & Consumption"
Cohesion: 0.15
Nodes (19): _auth_headers(), consumption_is_enabled(), cost_for_slots(), _discover_meter(), fetch_consumption(), fetch_rates(), is_enabled(), _parse() (+11 more)

### Community 19 - "Status UI & Formatters"
Cohesion: 0.27
Nodes (12): ConnectionBadge(), ScheduleSection(), StatusSection(), formatFinishTime(), formatKwh(), formatMiles(), formatMoney(), formatPower() (+4 more)

### Community 20 - "Statistics & Weekly Digest"
Cohesion: 0.17
Nodes (18): _cache_avg_price(), _compute_efficiency(), _format_digest(), get_statistics(), _maybe_send_weekly_digest(), _money(), parse_summary(), _persist_daily_stats() (+10 more)

### Community 21 - "Bluelink Test Suite"
Cohesion: 0.21
Nodes (20): _mock_manager(), _mock_vehicle(), _get_manager should reuse the same VehicleManager instance across calls., A slow SDK read must not hang the caller — wait_for raises TimeoutError., test_calls_refresh_and_update_on_manager(), test_get_vehicle_state_async_returns_state(), test_get_vehicle_state_async_times_out(), test_get_vehicle_state_selects_by_id() (+12 more)

### Community 22 - "App Shell & Theming"
Cohesion: 0.19
Nodes (11): App(), OPTIONS, ThemeToggle(), root, registerServiceWorker(), applyTheme(), getStoredTheme(), prefersDark() (+3 more)

### Community 23 - "Settings Editor UI"
Cohesion: 0.18
Nodes (9): DAYS, DayTargetsEditor(), Props, Props, ReadyByEditor(), Props, TargetEditor(), SaveAction (+1 more)

### Community 24 - "Snapshot & Notification Tests"
Cohesion: 0.11
Nodes (17): Latest known vehicle + charger state. All fields JSON-serialisable., StatusSnapshot, reset_state(), test_no_finish_notification_without_charging_transition(), test_notifies_when_charging_finishes(), test_notifies_when_short_topup_finishes_from_plugged_in(), test_set_target_does_not_reapply_when_disconnected(), test_set_target_falls_back_to_plugin_soc_when_bluelink_fails() (+9 more)

### Community 26 - "API App & Snapshot"
Cohesion: 0.15
Nodes (16): build_snapshot(), export_sessions(), _iso(), lifespan(), _now_local(), datetime, HTTP API for the autocharge dashboard.  This is the production entrypoint for th, Download the *full* charge-session history as a CSV or JSON file.      Unlike `` (+8 more)

### Community 27 - "Poll Loop Telemetry & Persistence"
Cohesion: 0.14
Nodes (14): _make_client_with_retry(), _maybe_notify_finished(), _maybe_record_telemetry(), _maybe_refresh_live_soc(), _next_poll_delay(), _persist_grid_consumption(), poll_loop(), Fetch recent Octopus household consumption and upsert the car/house split. (+6 more)

### Community 28 - "Schedule Timeline UI"
Cohesion: 0.32
Nodes (8): ChargeSlot, ScheduleTimeline(), buildTimeline(), ceilToHour(), floorToHour(), slots, Timeline, TimelineSegment

### Community 29 - "Ohme Client Tests"
Cohesion: 0.11
Nodes (22): ChargerStatus, get_charger_status(), is_charging(), is_connected(), make_client(), Async wrapper around the ohmepy library (PyPI: ohme)., Refresh the charge session and return the charger's status.      The network ref, True when the car is physically plugged into the Ohme charger. (+14 more)

### Community 31 - "TS Node Config"
Cohesion: 0.20
Nodes (9): compilerOptions, allowSyntheticDefaultImports, module, moduleResolution, noEmit, skipLibCheck, strict, types (+1 more)

### Community 32 - "Poll & Status Tests"
Cohesion: 0.20
Nodes (10): _populate_snapshot(), test_consecutive_failures_count_and_reset(), test_day_targets_in_status_config(), test_health_reports_last_error(), test_poll_failure_preserves_snapshot_and_reports_error(), test_ready_by_reflected_in_status(), test_schedule_returns_slots(), test_set_target_reflected_in_status() (+2 more)

### Community 33 - "Ntfy Test Suite"
Cohesion: 0.22
Nodes (10): Send a notification via ntfy. No-ops silently if NTFY_TOPIC is not configured., send(), _make_mock_session(), test_logs_warning_on_non_200_but_does_not_raise(), test_no_auth_header_when_token_not_set(), test_no_extra_headers_by_default(), test_sends_bearer_token_when_configured(), test_sends_correct_url_and_body() (+2 more)

### Community 34 - "Live SOC Refresh Tests"
Cohesion: 0.22
Nodes (9): Build a Bluelink VehicleState for patching bluelink.get_vehicle_state., Restart-mid-session recovery: connected but no held SOC -> fetch once,     even, test_live_soc_refreshes_when_charging_and_due(), test_live_soc_refreshes_when_reading_is_stale(), test_live_soc_seeds_when_connected_without_reading(), test_set_ready_by_passes_target_time_to_ohme(), test_set_target_does_not_reapply_when_fresh_soc_at_target(), test_set_target_reapplies_to_ohme_with_fresh_soc() (+1 more)

### Community 35 - "Efficiency & Digest Tests"
Cohesion: 0.22
Nodes (9): An Ohme client whose summary reports a fixed total energy, no daily rows., _summary_client(), test_statistics_efficiency_null_when_no_odometer_span(), test_statistics_efficiency_null_when_persistence_disabled(), test_statistics_includes_efficiency_when_data_available(), test_weekly_digest_disabled_without_ntfy(), test_weekly_digest_not_resent_same_day(), test_weekly_digest_sends_on_schedule() (+1 more)

### Community 36 - "DB Fake Pool Fixtures"
Cohesion: 0.25
Nodes (5): fake_pool(), _FakeConn, _FakePool, Install a fake pool into db and tear it down afterwards., test_get_miles_driven_none_when_insufficient_data()

### Community 38 - "Mobile Dashboard Screenshot"
Cohesion: 0.38
Nodes (7): Charging history bar chart card, Teal circular battery SOC ring, Battery ring status card, Blue gradient background theme, Narrow mobile dashboard layout, App header with lightning bolt icon, Secondary info/text card

### Community 39 - "Desktop Dashboard Screenshot"
Cohesion: 0.43
Nodes (7): Circular battery SOC ring (teal), Battery ring / charge status card (top-left), Wide desktop dashboard layout, Blue header bar with lightning-bolt logo, Bar-chart history card (bottom-left), Bar-chart statistics card (bottom-right), Tariff / details info card (top-right)

### Community 40 - "Polling Hook"
Cohesion: 0.07
Nodes (27): Datasource, Example panels, Grafana / Postgres history, Ready-made dashboard, Tables, API endpoints, Charging history & Grafana (optional), Configuration (+19 more)

### Community 41 - "Config Test Suite"
Cohesion: 0.43
Nodes (6): Startup validation of required environment variables.  config.py is imported onc, Yield a callable that re-imports config; restores the real module after., reimport_config(), test_all_vars_present_imports_cleanly(), test_empty_value_counts_as_missing(), test_missing_vars_produce_one_clear_message()

### Community 42 - "Vehicle Picker UI"
Cohesion: 0.53
Nodes (4): Vehicle, Props, FLEET, VehiclePicker()

### Community 43 - "Access Log Filter Tests"
Cohesion: 0.33
Nodes (6): _access_record(), LogRecord, test_quiet_filter_drops_successful_polling_gets(), test_quiet_filter_ignores_query_string(), test_quiet_filter_keeps_other_paths_and_methods(), test_quiet_filter_keeps_polling_endpoint_errors()

### Community 44 - "DB Error-Handling Tests"
Cohesion: 0.33
Nodes (5): _BoomPool, test_get_recent_sessions_none_on_error(), test_get_soh_history_none_on_error(), test_prune_telemetry_swallows_errors(), test_record_session_swallows_errors()

### Community 45 - "PWA Maskable Icon"
Cohesion: 0.60
Nodes (5): Solid blue full-bleed background, EV charging app identity, PWA Maskable Icon (512px), White lightning bolt glyph, Maskable centered safe-zone

### Community 46 - "Battery Ring UI"
Cohesion: 0.60
Nodes (3): BatteryRing(), Props, ringColor()

### Community 47 - "Renovate Config"
Cohesion: 0.40
Nodes (4): extends, packageRules, platformAutomerge, $schema

### Community 49 - "Quiet Access Log Filter"
Cohesion: 0.50
Nodes (3): LogRecord, _QuietAccessLogFilter, Suppress uvicorn access-log lines for successful GETs to polling endpoints.

### Community 50 - "Security Headers Middleware"
Cohesion: 0.50
Nodes (3): Add a baseline set of security headers to every response., SecurityHeadersMiddleware, BaseHTTPMiddleware

### Community 51 - "App Icon Asset"
Cohesion: 0.67
Nodes (4): Autocharge App Icon, Blue Rounded Square Background (#2563eb), EV Charging Concept, White Lightning Bolt Glyph

### Community 53 - "Apple Touch Icon"
Cohesion: 1.00
Nodes (3): Ohme autocharge dashboard app identity, Lightning bolt symbol (EV charging / electricity), Apple touch icon: white lightning bolt on rounded blue square

### Community 54 - "PWA Icon (192px)"
Cohesion: 1.00
Nodes (3): Ohme autocharge PWA brand identity, PWA app icon (192px) — white lightning bolt on blue rounded square, Lightning bolt symbol denoting EV charging/electricity

### Community 55 - "PWA Icon (512px)"
Cohesion: 1.00
Nodes (3): EV Charging Dashboard App Identity, PWA App Icon (512px), White Lightning Bolt Glyph

### Community 62 - "Community 62"
Cohesion: 0.10
Nodes (8): Tests for the JSON-file-backed runtime settings.  Each test points ``settings.SE, Write an arbitrary JSON payload directly, bypassing the setters., test_day_targets_filters_malformed_and_out_of_range(), test_load_ready_by_ignores_invalid_persisted_value(), test_load_target_none_on_non_numeric(), test_load_tolerates_non_dict_top_level(), test_load_vehicle_id_none_for_empty_or_non_string(), _write_raw()

### Community 63 - "Community 63"
Cohesion: 0.05
Nodes (33): AppState, Any, In-memory state shared between the polling loop and the HTTP API.  The poll loop, The active charge target: the runtime override if set, else the env default., Set the runtime charge-target override (does not persist; see settings.save_targ, Set the runtime ready-by time (does not persist; see settings.save_ready_by)., Set the per-weekday target overrides (does not persist; see settings.save_day_ta, Set the runtime vehicle selection (does not persist; see settings.save_vehicle_i (+25 more)

### Community 64 - "Community 64"
Cohesion: 0.18
Nodes (9): Architecture, Commands, Configuration, Docker, Git workflow, graphify, Single-worker constraint, Testing (+1 more)

### Community 66 - "Community 66"
Cohesion: 0.67
Nodes (3): frontend index.html (SPA shell + PWA meta), React 18 + TypeScript + Vite stack, Installable PWA / service worker

### Community 69 - "Community 69"
Cohesion: 0.67
Nodes (3): _on_poll_task_done(), Log loudly if the poll loop ever exits unexpectedly.      /api/health reports th, Task

## Knowledge Gaps
- **149 isolated node(s):** `name`, `version`, `private`, `type`, `description` (+144 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **17 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `StatusSnapshot` connect `Snapshot & Notification Tests` to `Poll & Status Tests`, `API Test Suite`, `Live SOC Refresh Tests`, `DB Fake Pool Fixtures`, `Fake DB Cursor Fixture`, `API Request Models`, `DB Error-Handling Tests`, `DB Test Suite`, `Fake DB Connection Fixture`, `Quiet Access Log Filter`, `Security Headers Middleware`, `API App & Snapshot`, `Poll Loop Telemetry & Persistence`, `Community 63`?**
  _High betweenness centrality (0.117) - this node is a cross-community bridge._
- **Why does `AppState` connect `Community 63` to `Snapshot & Notification Tests`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Why does `_FakeCursor` connect `Fake DB Cursor Fixture` to `Snapshot & Notification Tests`, `DB Fake Pool Fixtures`, `DB Test Suite`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **Are the 12 inferred relationships involving `StatusSnapshot` (e.g. with `DayTargetsUpdate` and `MaxChargeUpdate`) actually correct?**
  _`StatusSnapshot` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `HTTP API for the autocharge dashboard.  This is the production entrypoint for th`, `Suppress uvicorn access-log lines for successful GETs to polling endpoints.`, `Seconds to wait before the next poll.      Healthy (no failures): the normal POL` to the rest of the system?**
  _308 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Poll Loop & Plug-in Detection` be split into smaller, more focused modules?**
  _Cohesion score 0.056265984654731455 - nodes in this community are weakly interconnected._
- **Should `API Test Suite` be split into smaller, more focused modules?**
  _Cohesion score 0.030303030303030304 - nodes in this community are weakly interconnected._