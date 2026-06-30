# Graph Report - .  (2026-06-30)

## Corpus Check
- 104 files · ~51,910 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 923 nodes · 1586 edges · 62 communities (57 shown, 5 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 45 edges (avg confidence: 0.74)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Poll Loop & Plug-in Detection|Poll Loop & Plug-in Detection]]
- [[_COMMUNITY_API Test Suite|API Test Suite]]
- [[_COMMUNITY_Postgres Persistence Layer|Postgres Persistence Layer]]
- [[_COMMUNITY_Frontend NPM Dependencies|Frontend NPM Dependencies]]
- [[_COMMUNITY_Project Docs & Deployment|Project Docs & Deployment]]
- [[_COMMUNITY_AppState Store|AppState Store]]
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
- [[_COMMUNITY_Bluelink Vehicle API|Bluelink Vehicle API]]
- [[_COMMUNITY_API App & Snapshot|API App & Snapshot]]
- [[_COMMUNITY_Poll Loop Telemetry & Persistence|Poll Loop Telemetry & Persistence]]
- [[_COMMUNITY_Schedule Timeline UI|Schedule Timeline UI]]
- [[_COMMUNITY_Ohme Client Tests|Ohme Client Tests]]
- [[_COMMUNITY_Sessions & SoH History UI|Sessions & SoH History UI]]
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
- [[_COMMUNITY_Poll Task Watchdog|Poll Task Watchdog]]
- [[_COMMUNITY_Apple Touch Icon|Apple Touch Icon]]
- [[_COMMUNITY_PWA Icon (192px)|PWA Icon (192px)]]
- [[_COMMUNITY_PWA Icon (512px)|PWA Icon (512px)]]
- [[_COMMUNITY_Service Worker|Service Worker]]
- [[_COMMUNITY_Live SOC No-Seed Test|Live SOC No-Seed Test]]

## God Nodes (most connected - your core abstractions)
1. `StatusSnapshot` - 43 edges
2. `_charging_client()` - 21 edges
3. `handle_plugin_event()` - 20 edges
4. `compilerOptions` - 18 edges
5. `AppState` - 16 edges
6. `_mock_manager()` - 14 edges
7. `_mock_vehicle()` - 14 edges
8. `_mock_ohme_client()` - 13 edges
9. `_load()` - 12 edges
10. `_vstate()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `How it works (plug-in detection flow)` --conceptually_related_to--> `handle_plugin_event()`  [INFERRED]
  README.md → main.py
- `Security model (trusted LAN, CSRF header)` --semantically_similar_to--> `Postgres published on loopback only`  [INFERRED] [semantically similar]
  README.md → docker-compose.yml
- `docker-compose.yml (local dev)` --semantically_similar_to--> `docker-compose.prod.yml (home server)`  [INFERRED] [semantically similar]
  docker-compose.yml → docker-compose.prod.yml
- `_QuietAccessLogFilter` --uses--> `StatusSnapshot`  [INFERRED]
  api.py → state.py
- `SecurityHeadersMiddleware` --uses--> `StatusSnapshot`  [INFERRED]
  api.py → state.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **CI pipeline: test then smoke then publish** — github_workflows_docker_ci_test_job, github_workflows_docker_ci_frontend_test_job, github_workflows_docker_ci_smoke_job, github_workflows_docker_ci_build_backend_job, github_workflows_docker_ci_build_frontend_job [EXTRACTED 0.90]
- **Three-service deployment stack** — api, compose_postgres_service, frontend_readme_nginx [INFERRED 0.80]
- **Postgres charging-history schema** — docs_grafana_telemetry_table, docs_grafana_charge_sessions_table, docs_grafana_schedule_snapshots_table, docs_grafana_daily_stats_table, docs_grafana_grid_consumption_table [EXTRACTED 0.90]

## Communities (62 total, 5 thin omitted)

### Community 0 - "Poll Loop & Plug-in Detection"
Cohesion: 0.06
Nodes (57): Thin pipeline architecture, handle_plugin_event(), load_persisted_settings(), _notify_plugin_failure(), PlugInDetector, Monitors the Ohme charger for a plug-in event, then fetches the vehicle's curren, Alert once per plug-in session that handling it is failing.      The poll loop r, Tracks plug/unplug transitions and fires :func:`handle_plugin_event` once     pe (+49 more)

### Community 2 - "Postgres Persistence Layer"
Cohesion: 0.07
Nodes (37): close(), get_grid_consumption(), get_miles_driven(), get_recent_sessions(), get_soh_history(), get_telemetry_between(), init(), is_enabled() (+29 more)

### Community 3 - "Frontend NPM Dependencies"
Cohesion: 0.05
Nodes (36): dependencies, react, react-dom, description, devDependencies, eslint, @eslint/js, eslint-plugin-react-hooks (+28 more)

### Community 4 - "Project Docs & Deployment"
Cohesion: 0.07
Nodes (35): CLAUDE.md project guidance, One-branch-per-change git workflow, Single-worker constraint, docker-compose.yml (local dev), Postgres published on loopback only, Bundled Postgres service, docker-compose.prod.yml (home server), FastAPI + uvicorn (+27 more)

### Community 5 - "AppState Store"
Cohesion: 0.06
Nodes (17): AppState, Any, The active charge target: the runtime override if set, else the env default., Set the runtime charge-target override (does not persist; see settings.save_targ, Set the runtime ready-by time (does not persist; see settings.save_ready_by)., Set the per-weekday target overrides (does not persist; see settings.save_day_ta, Set the runtime vehicle selection (does not persist; see settings.save_vehicle_i, The Hyundai vehicle id to read: runtime override, else the env default, else Non (+9 more)

### Community 6 - "Octopus Test Suite"
Cohesion: 0.14
Nodes (27): _enable(), _enable_consumption(), _make_mock_session(), _make_mock_session_seq(), _rate(), Minimal stand-in for ohme.utils.ChargeSlot (start/end/energy)., A session whose successive ``.get`` calls return successive payloads — for     t, _Slot (+19 more)

### Community 7 - "Runtime Settings Persistence"
Cohesion: 0.11
Nodes (27): _load(), load_day_targets(), load_ready_by(), load_session_active(), load_target(), load_vehicle_id(), parse_hhmm(), Runtime-adjustable settings, persisted to a small JSON file.  Holds the dashboar (+19 more)

### Community 8 - "Charge Controls UI"
Cohesion: 0.14
Nodes (13): api, StatisticsResponse, StatusResponse, Action, ChargeControls(), Props, scheduleFixture, sessionsFixture (+5 more)

### Community 9 - "Dashboard & Energy Usage UI"
Cohesion: 0.15
Nodes (15): EnergyUsageResponse, TariffResponse, Banner(), HeaderMeta(), EnergyUsageSection(), formatDay(), shiftDate(), data (+7 more)

### Community 10 - "API Charge & Read Endpoints"
Cohesion: 0.09
Nodes (25): _charge_action(), get_energy_usage(), get_schedule(), get_sessions(), get_soh_history(), get_status(), get_tariff(), get_vehicles() (+17 more)

### Community 11 - "Energy Attribution Helpers"
Cohesion: 0.13
Nodes (21): attribute_car_kwh(), _canon(), merge_usage(), _parse(), datetime, Pure helpers for the household-vs-car energy breakdown.  The whole-house grid im, Parse an ISO timestamp (or pass through a datetime) to an aware UTC datetime., Canonical UTC ISO key for a half-hour boundary, so the car buckets and the     O (+13 more)

### Community 12 - "API Request Models"
Cohesion: 0.10
Nodes (22): DayTargetsUpdate, MaxChargeUpdate, Request body for PUT /api/charge/max-charge., Request body for PUT /api/settings/target., Request body for PUT /api/settings/ready-by.      ``readyBy`` is a 24h ``HH:MM``, Request body for PUT /api/settings/day-targets.      ``dayTargets`` maps weekday, Request body for PUT /api/settings/vehicle (null selects the first vehicle)., Push the current effective target/ready-by to Ohme if the car is plugged in. (+14 more)

### Community 13 - "Frontend API Client & Types"
Cohesion: 0.13
Nodes (20): ApiError, errorFor(), getJson(), postJson(), putJson(), RefreshResponse, REQUESTED_WITH, VersionResponse (+12 more)

### Community 14 - "DB Test Suite"
Cohesion: 0.09
Nodes (3): Tests for the optional Postgres persistence layer.  No real database is used. We, test_record_telemetry_maps_snapshot_fields(), test_writes_are_noops_when_disabled()

### Community 15 - "Snapshot Build Tests"
Cohesion: 0.10
Nodes (22): _charging_client(), _slot(), test_build_snapshot_falls_back_to_client_battery_before_first_plugin(), test_build_snapshot_includes_lock_and_location_when_connected(), test_build_snapshot_includes_range_when_connected(), test_build_snapshot_includes_soh_when_connected(), test_build_snapshot_no_cost_when_disconnected(), test_build_snapshot_no_cost_without_price() (+14 more)

### Community 16 - "Statistics & Charts UI"
Cohesion: 0.17
Nodes (16): DailyStat, EnergyBarChart(), METRIC_COLOR, Props, CHART_METRICS, CHART_TITLE, DeltaBadge(), Props (+8 more)

### Community 17 - "TypeScript Config"
Cohesion: 0.10
Nodes (19): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleResolution, noEmit (+11 more)

### Community 18 - "Octopus Tariff & Consumption"
Cohesion: 0.15
Nodes (19): _auth_headers(), consumption_is_enabled(), cost_for_slots(), _discover_meter(), fetch_consumption(), fetch_rates(), is_enabled(), _parse() (+11 more)

### Community 19 - "Status UI & Formatters"
Cohesion: 0.26
Nodes (13): ChargerStatus, ConnectionBadge(), StatisticsSection(), StatusSection(), formatFinishTime(), formatKwh(), formatMiles(), formatMoney() (+5 more)

### Community 20 - "Statistics & Weekly Digest"
Cohesion: 0.17
Nodes (18): _cache_avg_price(), _compute_efficiency(), _format_digest(), get_statistics(), _maybe_send_weekly_digest(), _money(), parse_summary(), _persist_daily_stats() (+10 more)

### Community 21 - "Bluelink Test Suite"
Cohesion: 0.28
Nodes (17): _mock_manager(), _mock_vehicle(), _get_manager should reuse the same VehicleManager instance across calls., test_calls_refresh_and_update_on_manager(), test_get_vehicle_state_selects_by_id(), test_list_vehicles_maps_fields(), test_raises_runtime_error_when_no_vehicles(), test_raises_runtime_error_when_soc_is_none() (+9 more)

### Community 22 - "App Shell & Theming"
Cohesion: 0.19
Nodes (11): App(), OPTIONS, ThemeToggle(), root, registerServiceWorker(), applyTheme(), getStoredTheme(), prefersDark() (+3 more)

### Community 23 - "Settings Editor UI"
Cohesion: 0.18
Nodes (9): DAYS, DayTargetsEditor(), Props, Props, ReadyByEditor(), Props, TargetEditor(), SaveAction (+1 more)

### Community 24 - "Snapshot & Notification Tests"
Cohesion: 0.12
Nodes (16): Latest known vehicle + charger state. All fields JSON-serialisable., StatusSnapshot, reset_state(), test_no_finish_notification_without_charging_transition(), test_notifies_when_charging_finishes(), test_notifies_when_short_topup_finishes_from_plugged_in(), test_set_target_does_not_reapply_when_disconnected(), test_set_target_falls_back_to_plugin_soc_when_bluelink_fails() (+8 more)

### Community 25 - "Bluelink Vehicle API"
Cohesion: 0.20
Nodes (14): get_battery_percentage(), _get_manager(), get_vehicle_state(), list_vehicles(), Return just the current battery SOC % for the selected vehicle., A snapshot of the vehicle read from Bluelink at a point in time.      ``range_mi, Convert an SDK distance (value + unit string) to whole miles, or None.      Defe, Pick the configured vehicle by id, falling back to the first one. (+6 more)

### Community 26 - "API App & Snapshot"
Cohesion: 0.20
Nodes (13): build_snapshot(), _iso(), lifespan(), _now_local(), datetime, HTTP API for the autocharge dashboard.  This is the production entrypoint for th, Current time in the configured timezone (host-local if it's unset/bad)., Force an immediate live re-read from Ohme and rebuild the cached snapshot. (+5 more)

### Community 27 - "Poll Loop Telemetry & Persistence"
Cohesion: 0.17
Nodes (12): _make_client_with_retry(), _maybe_notify_finished(), _maybe_record_telemetry(), _maybe_refresh_live_soc(), _persist_grid_consumption(), poll_loop(), Create the Ohme client, retrying forever with exponential backoff., Re-read the SOC from Bluelink so the battery ring shows the real value.      Fir (+4 more)

### Community 28 - "Schedule Timeline UI"
Cohesion: 0.32
Nodes (8): ChargeSlot, ScheduleTimeline(), buildTimeline(), ceilToHour(), floorToHour(), slots, Timeline, TimelineSegment

### Community 29 - "Ohme Client Tests"
Cohesion: 0.29
Nodes (7): _mock_client(), test_get_charger_status_calls_get_charge_session(), test_get_charger_status_defaults_to_unplugged_on_malformed_session(), test_get_charger_status_returns_status(), test_set_target_calls_methods_in_correct_order(), test_set_target_passes_correct_values(), test_set_target_passes_ready_by_time()

### Community 30 - "Sessions & SoH History UI"
Cohesion: 0.29
Nodes (5): SohHistoryResponse, ACTION_LABEL, SessionsSection(), SohTrendSection(), formatDateShort()

### Community 31 - "TS Node Config"
Cohesion: 0.20
Nodes (9): compilerOptions, allowSyntheticDefaultImports, module, moduleResolution, noEmit, skipLibCheck, strict, types (+1 more)

### Community 32 - "Poll & Status Tests"
Cohesion: 0.20
Nodes (10): _populate_snapshot(), test_consecutive_failures_count_and_reset(), test_day_targets_in_status_config(), test_health_reports_last_error(), test_poll_failure_preserves_snapshot_and_reports_error(), test_ready_by_reflected_in_status(), test_schedule_returns_slots(), test_set_target_reflected_in_status() (+2 more)

### Community 33 - "Ntfy Test Suite"
Cohesion: 0.33
Nodes (7): _make_mock_session(), test_logs_warning_on_non_200_but_does_not_raise(), test_no_auth_header_when_token_not_set(), test_no_extra_headers_by_default(), test_sends_bearer_token_when_configured(), test_sends_correct_url_and_body(), test_title_and_priority_sent_as_headers()

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
Cohesion: 0.33
Nodes (3): PollingState, usePolling(), Dashboard()

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

### Community 52 - "Poll Task Watchdog"
Cohesion: 0.67
Nodes (3): _on_poll_task_done(), Log loudly if the poll loop ever exits unexpectedly.      /api/health reports th, Task

### Community 53 - "Apple Touch Icon"
Cohesion: 1.00
Nodes (3): Ohme autocharge dashboard app identity, Lightning bolt symbol (EV charging / electricity), Apple touch icon: white lightning bolt on rounded blue square

### Community 54 - "PWA Icon (192px)"
Cohesion: 1.00
Nodes (3): Ohme autocharge PWA brand identity, PWA app icon (192px) — white lightning bolt on blue rounded square, Lightning bolt symbol denoting EV charging/electricity

### Community 55 - "PWA Icon (512px)"
Cohesion: 1.00
Nodes (3): EV Charging Dashboard App Identity, PWA App Icon (512px), White Lightning Bolt Glyph

## Knowledge Gaps
- **101 isolated node(s):** `name`, `version`, `private`, `type`, `description` (+96 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ChargerStatus` connect `Status UI & Formatters` to `Poll Loop & Plug-in Detection`, `Ohme Client Tests`, `Frontend API Client & Types`?**
  _High betweenness centrality (0.272) - this node is a cross-community bridge._
- **Why does `get_charger_status()` connect `Poll Loop & Plug-in Detection` to `Status UI & Formatters`?**
  _High betweenness centrality (0.092) - this node is a cross-community bridge._
- **Why does `is_connected()` connect `Poll Loop & Plug-in Detection` to `Status UI & Formatters`?**
  _High betweenness centrality (0.090) - this node is a cross-community bridge._
- **Are the 12 inferred relationships involving `StatusSnapshot` (e.g. with `DayTargetsUpdate` and `MaxChargeUpdate`) actually correct?**
  _`StatusSnapshot` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `HTTP API for the autocharge dashboard.  This is the production entrypoint for th`, `Suppress uvicorn access-log lines for successful GETs to polling endpoints.`, `Translate the live Ohme client state into a serialisable snapshot.      Assumes` to the rest of the system?**
  _247 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Poll Loop & Plug-in Detection` be split into smaller, more focused modules?**
  _Cohesion score 0.0574400723654455 - nodes in this community are weakly interconnected._
- **Should `API Test Suite` be split into smaller, more focused modules?**
  _Cohesion score 0.03333333333333333 - nodes in this community are weakly interconnected._