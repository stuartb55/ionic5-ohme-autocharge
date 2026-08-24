# Graph Report - ionic5-ohme-autocharge  (2026-08-24)

## Corpus Check
- 134 files · ~119,914 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1717 nodes · 3121 edges · 108 communities (83 shown, 25 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 115 edges (avg confidence: 0.62)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7e45ad80`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Poll Loop & Plug-in Detection|Poll Loop & Plug-in Detection]]
- [[_COMMUNITY_API Test Suite|API Test Suite]]
- [[_COMMUNITY_Postgres Persistence Layer|Postgres Persistence Layer]]
- [[_COMMUNITY_Frontend NPM Dependencies|Frontend NPM Dependencies]]
- [[_COMMUNITY_Project Docs & Deployment|Project Docs & Deployment]]
- [[_COMMUNITY_Community 5|Community 5]]
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
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_API App & Snapshot|API App & Snapshot]]
- [[_COMMUNITY_Poll Loop Telemetry & Persistence|Poll Loop Telemetry & Persistence]]
- [[_COMMUNITY_Schedule Timeline UI|Schedule Timeline UI]]
- [[_COMMUNITY_Ohme Client Tests|Ohme Client Tests]]
- [[_COMMUNITY_Community 30|Community 30]]
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
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Apple Touch Icon|Apple Touch Icon]]
- [[_COMMUNITY_PWA Icon (192px)|PWA Icon (192px)]]
- [[_COMMUNITY_PWA Icon (512px)|PWA Icon (512px)]]
- [[_COMMUNITY_Service Worker|Service Worker]]
- [[_COMMUNITY_Live SOC No-Seed Test|Live SOC No-Seed Test]]
- [[_COMMUNITY_Vite Config|Vite Config]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
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
- [[_COMMUNITY_Community 89|Community 89]]
- [[_COMMUNITY_Community 94|Community 94]]
- [[_COMMUNITY_Community 95|Community 95]]
- [[_COMMUNITY_Community 96|Community 96]]
- [[_COMMUNITY_Community 97|Community 97]]
- [[_COMMUNITY_Community 98|Community 98]]
- [[_COMMUNITY_Community 99|Community 99]]
- [[_COMMUNITY_Community 100|Community 100]]
- [[_COMMUNITY_Community 101|Community 101]]
- [[_COMMUNITY_Community 102|Community 102]]
- [[_COMMUNITY_Community 103|Community 103]]
- [[_COMMUNITY_Community 104|Community 104]]
- [[_COMMUNITY_Community 105|Community 105]]
- [[_COMMUNITY_Community 107|Community 107]]

## God Nodes (most connected - your core abstractions)
1. `StatusSnapshot` - 65 edges
2. `AppState` - 58 edges
3. `SecurityHeadersMiddleware` - 33 edges
4. `_QuietAccessLogFilter` - 32 edges
5. `handle_plugin_event()` - 31 edges
6. `_load()` - 28 edges
7. `_charging_client()` - 27 edges
8. `ContractModel` - 26 edges
9. `_mock_ohme_client()` - 23 edges
10. `_mock_manager()` - 22 edges

## Surprising Connections (you probably didn't know these)
- `docker-compose.yml (local dev)` --semantically_similar_to--> `docker-compose.prod.yml (home server)`  [INFERRED] [semantically similar]
  docker-compose.yml → docker-compose.prod.yml
- `_QuietAccessLogFilter` --uses--> `DataQualityResponseModel`  [INFERRED]
  api.py → api_contracts.py
- `_QuietAccessLogFilter` --uses--> `MonthlyReportResponseModel`  [INFERRED]
  api.py → api_contracts.py
- `_QuietAccessLogFilter` --uses--> `StatisticsResponseModel`  [INFERRED]
  api.py → api_contracts.py
- `_QuietAccessLogFilter` --uses--> `StatusSnapshot`  [INFERRED]
  api.py → state.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **CI pipeline: test then smoke then publish** — github_workflows_docker_ci_test_job, github_workflows_docker_ci_frontend_test_job, github_workflows_docker_ci_smoke_job, github_workflows_docker_ci_build_backend_job, github_workflows_docker_ci_build_frontend_job [EXTRACTED 0.90]
- **Three-service deployment stack** — api, compose_postgres_service, frontend_readme_nginx [INFERRED 0.80]
- **Postgres charging-history schema** — docs_grafana_telemetry_table, docs_grafana_charge_sessions_table, docs_grafana_schedule_snapshots_table, docs_grafana_daily_stats_table, docs_grafana_grid_consumption_table [EXTRACTED 0.90]

## Communities (108 total, 25 thin omitted)

### Community 0 - "Poll Loop & Plug-in Detection"
Cohesion: 0.05
Nodes (81): ensure_pending_sessions(), handle_plugin_event(), load_persisted_settings(), _notify_plugin_failure(), _outbox_timestamp(), PlugInDetector, datetime, Monitors the Ohme charger for a plug-in event, then fetches the vehicle's curren (+73 more)

### Community 2 - "Postgres Persistence Layer"
Cohesion: 0.08
Nodes (25): get_all_sessions(), get_data_quality_summary(), get_session_audit(), get_session_schedule_slots(), get_session_telemetry(), get_soh_history(), Any, All distinct Ohme slots recorded for a durable charging session. (+17 more)

### Community 3 - "Frontend NPM Dependencies"
Cohesion: 0.04
Nodes (44): dependencies, react, react-dom, description, devDependencies, axe-core, @babel/core, @babel/eslint-parser (+36 more)

### Community 4 - "Project Docs & Deployment"
Cohesion: 0.09
Nodes (26): docker-compose.yml (local dev), Postgres published on loopback only, Bundled Postgres service, docker-compose.prod.yml (home server), FastAPI + uvicorn, hyundai-kia-connect-api, ohme library, psycopg (Postgres driver) (+18 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (33): _as_bool(), BluelinkBusyError, _consume_inflight_result(), get_battery_percentage(), _get_manager(), get_vehicle_state(), get_vehicle_state_async(), list_vehicles() (+25 more)

### Community 6 - "Octopus Test Suite"
Cohesion: 0.09
Nodes (34): _cache_meter(), _enable(), _enable_consumption(), _make_mock_session(), _make_mock_session_seq(), _rate(), Minimal stand-in for ohme.utils.ChargeSlot (start/end/energy)., A session whose successive ``.get`` calls return successive payloads — for     t (+26 more)

### Community 7 - "Runtime Settings Persistence"
Cohesion: 0.08
Nodes (41): clear_date_override(), clear_pending_session(), clear_session_marker(), clear_trip_mode(), _load(), load_day_targets(), load_pending_sessions(), load_session_active() (+33 more)

### Community 8 - "Charge Controls UI"
Cohesion: 0.19
Nodes (11): StatisticsResponse, Dashboard(), scheduleFixture, sessionAuditFixture, sessionsFixture, statisticsFixture, statusFixture, handlers (+3 more)

### Community 9 - "Dashboard & Energy Usage UI"
Cohesion: 0.27
Nodes (12): DataQualityResponse, ageLabel(), CheckState, countLabel(), DataQualitySection(), dateLabel(), dateTimeLabel(), homeEnergyCheck() (+4 more)

### Community 10 - "API Charge & Read Endpoints"
Cohesion: 0.06
Nodes (47): _charge_action(), get_energy_usage(), get_schedule(), get_session_telemetry(), get_sessions(), get_soh_history(), get_status(), get_vehicles() (+39 more)

### Community 11 - "Energy Attribution Helpers"
Cohesion: 0.12
Nodes (30): attribute_car_kwh(), _canon(), EnergyAttribution, merge_usage(), _overlapping_slot_keys(), _parse(), datetime, Pure helpers for the household-vs-car energy breakdown.  The whole-house grid im (+22 more)

### Community 12 - "API Request Models"
Cohesion: 0.10
Nodes (42): ChargeActionResponseModel, DayTargetsUpdate, DayTargetsUpdateResponseModel, IntegrationsResponseModel, MaxChargeUpdate, MutationOutcomeModel, NotificationPreferencesUpdate, NotificationPreferencesUpdateResponseModel (+34 more)

### Community 13 - "Frontend API Client & Types"
Cohesion: 0.08
Nodes (38): ApiError, errorFor(), getJson(), postJson(), putJson(), REQUESTED_WITH, VersionResponse, ChargeActionResponse (+30 more)

### Community 15 - "Snapshot Build Tests"
Cohesion: 0.09
Nodes (24): _charging_client(), The manual refresh must re-read the car, not just the charger., A recovered read moves the banner off the stale boot-time failure., _slot(), test_build_snapshot_falls_back_to_client_battery_before_first_plugin(), test_build_snapshot_includes_lock_and_location_when_connected(), test_build_snapshot_includes_range_when_connected(), test_build_snapshot_includes_soh_when_connected() (+16 more)

### Community 16 - "Statistics & Charts UI"
Cohesion: 0.15
Nodes (16): DailyStat, EnergyBarChart(), METRIC_COLOR, Props, CHART_METRICS, CHART_TITLE, DeltaBadge(), Props (+8 more)

### Community 17 - "TypeScript Config"
Cohesion: 0.10
Nodes (19): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleResolution, noEmit (+11 more)

### Community 18 - "Octopus Tariff & Consumption"
Cohesion: 0.09
Nodes (31): Decimal, _auth_headers(), consumption_is_enabled(), cost_for_slots(), _discover_meters(), fetch_consumption(), fetch_rates(), is_enabled() (+23 more)

### Community 19 - "Status UI & Formatters"
Cohesion: 0.12
Nodes (26): ChargerStatus, TariffResponse, BatteryRing(), Props, ringColor(), ConnectionBadge(), ScheduleSection(), dateTime() (+18 more)

### Community 20 - "Statistics & Weekly Digest"
Cohesion: 0.08
Nodes (40): _build_monthly_report(), _cache_avg_price(), _complete_daily_series(), _driving_metrics(), _efficiency(), _format_digest(), get_statistics(), _maybe_send_weekly_digest() (+32 more)

### Community 21 - "Bluelink Test Suite"
Cohesion: 0.15
Nodes (27): _mock_manager(), _mock_vehicle(), _get_manager should reuse the same VehicleManager instance across calls., A slow SDK read must not hang the caller — wait_for raises TimeoutError., test_calls_refresh_and_update_on_manager(), test_get_vehicle_state_async_returns_state(), test_get_vehicle_state_async_times_out(), test_get_vehicle_state_selects_by_id() (+19 more)

### Community 22 - "App Shell & Theming"
Cohesion: 0.19
Nodes (11): App(), OPTIONS, ThemeToggle(), root, registerServiceWorker(), applyTheme(), getStoredTheme(), prefersDark() (+3 more)

### Community 23 - "Settings Editor UI"
Cohesion: 0.09
Nodes (25): Vehicle, VehiclesResponse, ChargeSettingsSection(), Props, DAYS, DayTargetsEditor(), Props, EditablePreferences (+17 more)

### Community 24 - "Snapshot & Notification Tests"
Cohesion: 0.06
Nodes (32): Latest known vehicle + charger state. All fields JSON-serialisable., StatusSnapshot, main(), Exercise the persistence workflow against CI's real PostgreSQL service., A refresh may already have replaced store.status with ``finished``., reset_state(), test_aux_battery_threshold_is_edge_triggered(), test_completion_minimum_suppresses_only_small_charge_alert() (+24 more)

### Community 25 - "Community 25"
Cohesion: 0.11
Nodes (17): close_session(), complete_session(), get_session_attribution_rows(), get_session_id_by_key(), get_single_vehicle_id(), get_unpriced_session_counters(), prune_telemetry(), Optional Postgres persistence for charging history (for Grafana).  Enabled only (+9 more)

### Community 26 - "API App & Snapshot"
Cohesion: 0.22
Nodes (9): export_sessions(), get_monthly_report(), _monthly_report_csv(), _monthly_window(), Resolve an explicit/default month to a DST-safe local half-open window., Flatten report summary and evidence into one spreadsheet-friendly file., Auditable calendar-month account totals and measured home sessions., Download the *full* charge-session history as a CSV or JSON file.      Unlike `` (+1 more)

### Community 27 - "Poll Loop Telemetry & Persistence"
Cohesion: 0.06
Nodes (34): _finalize_finished_session(), get_tariff(), lifespan(), _make_client_with_retry(), _maybe_notify_finished(), _maybe_notify_vehicle_health(), _maybe_record_telemetry(), _maybe_refresh_live_soc() (+26 more)

### Community 28 - "Schedule Timeline UI"
Cohesion: 0.32
Nodes (8): ChargeSlot, ScheduleTimeline(), buildTimeline(), ceilToHour(), floorToHour(), slots, Timeline, TimelineSegment

### Community 29 - "Ohme Client Tests"
Cohesion: 0.09
Nodes (35): bounded(), close_client(), get_charge_summary(), get_charger_status(), is_charging(), is_connected(), make_client(), pause_charge() (+27 more)

### Community 30 - "Community 30"
Cohesion: 0.11
Nodes (19): get_grid_consumption(), get_ingestion_cursor(), get_tariff_rates(), get_telemetry_between(), get_vehicle_driving_metrics(), datetime, Pair each home-charge session with distance driven before the next plug-in., Ordered session-linked telemetry rows in ``[start, end]``.      Feeds :func:`ene (+11 more)

### Community 31 - "TS Node Config"
Cohesion: 0.20
Nodes (9): compilerOptions, allowSyntheticDefaultImports, module, moduleResolution, noEmit, skipLibCheck, strict, types (+1 more)

### Community 32 - "Poll & Status Tests"
Cohesion: 0.08
Nodes (27): _populate_snapshot(), Restart-mid-session recovery: connected but no held SOC -> fetch once,     even, Build a Bluelink VehicleState for patching bluelink.get_vehicle_state., test_active_vehicle_profile_reapplies_immediately(), test_consecutive_failures_count_and_reset(), test_day_targets_in_status_config(), test_failed_live_apply_is_explicit_and_releases_client_lock(), test_health_reports_last_error() (+19 more)

### Community 33 - "Ntfy Test Suite"
Cohesion: 0.22
Nodes (10): Send a notification via ntfy. No-ops silently if NTFY_TOPIC is not configured., send(), _make_mock_session(), test_logs_warning_on_non_200_but_does_not_raise(), test_no_auth_header_when_token_not_set(), test_no_extra_headers_by_default(), test_sends_bearer_token_when_configured(), test_sends_correct_url_and_body() (+2 more)

### Community 34 - "Live SOC Refresh Tests"
Cohesion: 0.50
Nodes (4): get_data_quality(), _grade_consumption_quality(), Add severity and a drill-down day to the raw unsplit-interval counters., Read-only completeness counters for operations and alerting.

### Community 35 - "Efficiency & Digest Tests"
Cohesion: 0.18
Nodes (11): An Ohme client whose summary reports a fixed total energy, no daily rows., _summary_client(), test_statistics_efficiency_null_when_no_odometer_span(), test_statistics_efficiency_null_when_persistence_disabled(), test_statistics_includes_efficiency_when_data_available(), test_statistics_running_cost_null_without_cost(), test_weekly_digest_can_be_disabled_by_preference(), test_weekly_digest_disabled_without_ntfy() (+3 more)

### Community 36 - "DB Fake Pool Fixtures"
Cohesion: 0.29
Nodes (4): Connection returning a different result cursor for each query., _SequenceConn, test_get_monthly_report_rows_maps_exact_units_and_sessions(), test_get_session_audit_maps_all_provenance()

### Community 37 - "Fake DB Cursor Fixture"
Cohesion: 0.15
Nodes (13): fake_pool(), _FakeConn, _FakeCursor, _FakePool, Install a fake pool into db and tear it down afterwards., test_availability_uses_live_pool_state(), test_data_quality_summary_maps_aggregate_counts(), test_get_session_audit_none_for_unknown_or_disabled() (+5 more)

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
Cohesion: 0.36
Nodes (8): Startup validation of required environment variables.  config.py is imported onc, Yield a callable that re-imports config; restores the real module after., reimport_config(), test_all_vars_present_imports_cleanly(), test_empty_value_counts_as_missing(), test_invalid_numeric_settings_fail_fast(), test_invalid_timezone_fails_fast(), test_missing_vars_produce_one_clear_message()

### Community 42 - "Vehicle Picker UI"
Cohesion: 0.07
Nodes (19): ApplyStatus, EnergyUsageResponse, IntegrationStatus, PersistenceStatus, PollingState, usePolling(), Banner(), HeaderMeta() (+11 more)

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
Cohesion: 0.14
Nodes (12): load_ready_by(), load_trip_mode(), load_vehicle_profiles(), parse_hhmm(), Return the persisted ready-by time as ``HH:MM``, or None if unset/invalid., Return the pending one-session trip override, or None when inactive., Return every valid per-vehicle profile; skip malformed entries., Persist the complete vehicle-profile mapping. (+4 more)

### Community 47 - "Renovate Config"
Cohesion: 0.40
Nodes (4): extends, packageRules, platformAutomerge, $schema

### Community 49 - "Quiet Access Log Filter"
Cohesion: 0.08
Nodes (45): AutomationModel, ChargerPowerModel, ChargeSessionEntryModel, ChargeSlotModel, ComparisonModel, ConsumptionQualityModel, ContractModel, DailyQualityModel (+37 more)

### Community 50 - "Security Headers Middleware"
Cohesion: 0.10
Nodes (23): api, SessionTelemetryPoint, COST_METHOD_LABELS, costMethodLabel(), DETAIL_LABELS, DETAIL_VALUE_LABELS, detailLabel(), detailValue() (+15 more)

### Community 51 - "App Icon Asset"
Cohesion: 0.67
Nodes (4): Autocharge App Icon, Blue Rounded Square Background (#2563eb), EV Charging Concept, White Lightning Bolt Glyph

### Community 52 - "Community 52"
Cohesion: 0.22
Nodes (11): close(), init(), is_available(), is_enabled(), Recover optional persistence after startup without blocking charging., Close the pool on shutdown. No-op when never opened., True when history persistence is configured (``DATABASE_URL`` set)., True only when Postgres was configured *and* initialised successfully. (+3 more)

### Community 53 - "Apple Touch Icon"
Cohesion: 1.00
Nodes (3): Ohme autocharge dashboard app identity, Lightning bolt symbol (EV charging / electricity), Apple touch icon: white lightning bolt on rounded blue square

### Community 54 - "PWA Icon (192px)"
Cohesion: 1.00
Nodes (3): Ohme autocharge PWA brand identity, PWA app icon (192px) — white lightning bolt on blue rounded square, Lightning bolt symbol denoting EV charging/electricity

### Community 55 - "PWA Icon (512px)"
Cohesion: 1.00
Nodes (3): EV Charging Dashboard App Identity, PWA App Icon (512px), White Lightning Bolt Glyph

### Community 60 - "Vite Config"
Cohesion: 0.12
Nodes (16): RuntimeError, An unreachable car must not discard a good charger reading., A failed retry must read as fresh, not as the untouched original error., A transient display-read blip must not raise a false alarm., test_charge_control_502_on_upstream_error(), test_get_vehicles_502_on_bluelink_error(), test_live_soc_swallows_bluelink_error_keeps_reading(), test_make_client_with_retry_eventually_succeeds() (+8 more)

### Community 62 - "Community 62"
Cohesion: 0.07
Nodes (13): Tests for the JSON-file-backed runtime settings.  Each test points ``settings.SE, Write an arbitrary JSON payload directly, bypassing the setters., test_date_override_rejects_invalid_values(), test_day_targets_filters_malformed_and_out_of_range(), test_load_ready_by_ignores_invalid_persisted_value(), test_load_target_none_on_non_numeric(), test_load_tolerates_non_dict_top_level(), test_load_trip_mode_rejects_invalid_values() (+5 more)

### Community 63 - "Community 63"
Cohesion: 0.06
Nodes (33): AppState, NotificationPreferences, Process-wide singleton holding the latest snapshot and the Ohme client., The active charge target: the runtime override if set, else the env default., Set the runtime charge-target override (does not persist; see settings.save_targ, Set the runtime ready-by time (does not persist; see settings.save_ready_by)., Set the runtime vehicle selection (does not persist; see settings.save_vehicle_i, The Hyundai vehicle id to read: runtime override, else the env default, else Non (+25 more)

### Community 64 - "Community 64"
Cohesion: 0.18
Nodes (9): Architecture, Commands, Configuration, Docker, Git workflow, graphify, Single-worker constraint, Testing (+1 more)

### Community 65 - "Community 65"
Cohesion: 0.25
Nodes (8): build_snapshot(), _iso(), Translate the live Ohme client state into a serialisable snapshot.      Assumes, Re-read the vehicle from Bluelink on behalf of a manual refresh.      Deliberate, Force an immediate live re-read from Ohme and Bluelink, rebuilding the     cache, refresh(), _refresh_vehicle_state(), VehicleReadStatus

### Community 66 - "Community 66"
Cohesion: 0.67
Nodes (3): frontend index.html (SPA shell + PWA meta), React 18 + TypeScript + Vite stack, Installable PWA / service worker

### Community 67 - "Community 67"
Cohesion: 0.32
Nodes (6): _all_typescript_properties(), Keep the dashboard's TypeScript boundary aligned with FastAPI OpenAPI., Return direct parents and top-level properties for exported interfaces., Catch API fields added, removed, or renamed on either side of the SPA boundary., test_frontend_top_level_contracts_match_openapi(), _typescript_interfaces()

### Community 68 - "Community 68"
Cohesion: 0.33
Nodes (6): Upgrade the configured database to the repository's latest schema., _run_migrations(), main(), migration_config(), Config, Exercise the real Alembic chain against an isolated CI PostgreSQL service.

### Community 69 - "Community 69"
Cohesion: 0.20
Nodes (9): StatusResponse, Action, ChargeControls(), Props, Health, healthy, VehicleHealth(), WARNINGS (+1 more)

### Community 71 - "Community 71"
Cohesion: 0.29
Nodes (6): Backend (Python), Build, test, and lint commands, Copilot Instructions for `ionic5-ohme-autocharge`, Frontend (`frontend/`), High-level architecture, Key repository-specific conventions

### Community 72 - "Community 72"
Cohesion: 0.13
Nodes (10): date, In-memory state shared between the polling loop and the HTTP API.  The poll loop, Current calendar date in the configured home timezone., Clear an elapsed override and report whether state changed., Effective target for the selected or most recently observed vehicle., Trip, dated plan, vehicle profile, weekday override, then base., Stable user-facing provenance for the currently effective target., Weekday (Mon=0 … Sun=6) for "now" in the configured timezone.      Plug-in time (+2 more)

### Community 75 - "Community 75"
Cohesion: 0.18
Nodes (9): Architecture, Commands, Configuration, Docker, Git workflow, graphify, Single-worker constraint, Testing (+1 more)

### Community 76 - "Community 76"
Cohesion: 0.29
Nodes (3): Any, Keep the active session's cumulative energy counter monotonic., Remember the SOC plus driving range, odometer and SoH from a Bluelink read.

### Community 89 - "Community 89"
Cohesion: 0.50
Nodes (4): An Ohme client whose summary reports total energy and a total cost., _summary_client_with_cost(), test_statistics_includes_running_cost_when_data_available(), test_statistics_running_cost_null_without_miles()

### Community 95 - "Community 95"
Cohesion: 0.29
Nodes (6): DateOverride, load_date_override(), Return the dated temporary override, or None when absent or malformed., Persist a dated temporary override, preserving all other settings., Temporary charging defaults tied to one local departure date., save_date_override()

### Community 96 - "Community 96"
Cohesion: 0.67
Nodes (3): _monthly_evidence(), test_monthly_report_csv_is_an_attachment_with_summary_and_evidence(), test_monthly_report_keeps_account_and_measured_session_scopes_separate()

### Community 97 - "Community 97"
Cohesion: 0.67
Nodes (3): _notification_payload(), test_notification_preferences_persist_and_appear_in_status(), test_notification_preferences_reject_invalid_thresholds()

### Community 98 - "Community 98"
Cohesion: 0.29
Nodes (6): load_notification_preferences(), NotificationPreferences, Load validated notification controls, defaulting each malformed field., Persist the complete notification preference set., User-adjustable ntfy categories and evidence-based thresholds., save_notification_preferences()

### Community 99 - "Community 99"
Cohesion: 0.50
Nodes (4): get_recent_sessions(), Return the concrete completeness gaps represented by a session row., Return the most recent charge sessions, newest first.      Returns None when per, _session_review_issues()

### Community 101 - "Community 101"
Cohesion: 0.33
Nodes (6): get_monthly_report_rows(), _minor_factor(), date, Upsert Ohme's per-day totals (energy/savings/cost) keyed by date.      ``daily``, Exact persisted account-day and home-session evidence for ``[start, end)``., record_daily_stats()

### Community 102 - "Community 102"
Cohesion: 0.50
Nodes (4): _consumption_summary(), test_data_quality_alerts_when_unsplit_energy_is_material(), test_data_quality_grades_unsplit_intervals_by_count_without_metered_energy(), test_data_quality_treats_a_few_unsplit_intervals_as_normal()

### Community 105 - "Community 105"
Cohesion: 0.67
Nodes (3): _on_poll_task_done(), Task, Log loudly if the poll loop ever exits unexpectedly.      /api/health reports th

## Knowledge Gaps
- **199 isolated node(s):** `name`, `version`, `private`, `type`, `node` (+194 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **25 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `StatusSnapshot` connect `Snapshot & Notification Tests` to `Poll & Status Tests`, `Community 65`, `Community 98`, `API Test Suite`, `DB Fake Pool Fixtures`, `Fake DB Cursor Fixture`, `Community 72`, `API Request Models`, `Community 76`, `Battery Ring UI`, `DB Test Suite`, `DB Error-Handling Tests`, `Fake DB Connection Fixture`, `Poll Loop Telemetry & Persistence`, `Vite Config`, `Community 95`, `Community 63`?**
  _High betweenness centrality (0.129) - this node is a cross-community bridge._
- **Why does `AppState` connect `Community 63` to `Community 98`, `Community 103`, `Community 72`, `Community 104`, `Community 74`, `Community 107`, `Community 76`, `Battery Ring UI`, `Community 95`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Why does `_reapply_target_if_connected()` connect `API Charge & Read Endpoints` to `Vehicle Picker UI`, `API Request Models`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `StatusSnapshot` (e.g. with `_QuietAccessLogFilter` and `SecurityHeadersMiddleware`) actually correct?**
  _`StatusSnapshot` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `AppState` (e.g. with `DateOverride` and `NotificationPreferences`) actually correct?**
  _`AppState` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 29 inferred relationships involving `SecurityHeadersMiddleware` (e.g. with `ChargeActionResponseModel` and `DataQualityResponseModel`) actually correct?**
  _`SecurityHeadersMiddleware` has 29 INFERRED edges - model-reasoned connections that need verification._
- **Are the 29 inferred relationships involving `_QuietAccessLogFilter` (e.g. with `ChargeActionResponseModel` and `DataQualityResponseModel`) actually correct?**
  _`_QuietAccessLogFilter` has 29 INFERRED edges - model-reasoned connections that need verification._