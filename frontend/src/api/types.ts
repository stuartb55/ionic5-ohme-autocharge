// Types mirror the JSON returned by the FastAPI backend (api.py).

export type ChargerStatus =
  | 'unplugged'
  | 'pending_approval'
  | 'charging'
  | 'plugged_in'
  | 'paused'
  | 'finished'
  | 'unknown';

export interface StatusResponse {
  vehicle: {
    name: string | null;
    batteryPercent: number | null;
    /** Estimated driving range in miles at the last plug-in, or null. */
    rangeMiles: number | null;
    /** Battery state of health (%) at the last plug-in, or null. */
    sohPercent: number | null;
    /** Read-only lock status, or null when unknown. */
    isLocked: boolean | null;
    /** Last-known GPS location, or null when unknown. */
    location: { latitude: number; longitude: number } | null;
    /** Read-only vehicle health; each field null when the car didn't report it. */
    health: {
      /** 12V auxiliary battery charge (%), or null. */
      auxBatteryPercent: number | null;
      tyrePressureWarning: boolean | null;
      washerFluidWarning: boolean | null;
      keyBatteryWarning: boolean | null;
      /** Labels of any door/bonnet/boot reported open (empty when all closed). */
      openItems: string[];
    };
  };
  charger: {
    status: ChargerStatus;
    connected: boolean;
    online: boolean;
    /** True while Ohme is in max-charge ("boost") mode. */
    maxCharge: boolean;
    model: string | null;
    power: {
      watts: number;
      amps: number;
      volts: number | null;
    };
    targetPercent: number | null;
    sessionEnergyKwh: number;
    /** ISO time the charge is projected to finish (end of the last slot), or null. */
    projectedFinish: string | null;
    /** Total grid energy (kWh) the session is planned to draw. */
    plannedEnergyKwh: number;
    /** Estimated session cost, or null when no price is known. */
    projectedCost: number | null;
    /** Currency for projectedCost. */
    projectedCostCurrency: string | null;
    /** How projectedCost was derived: 'agile' (per-slot Agile rates) or 'average'. */
    projectedCostMethod: 'agile' | 'average' | null;
  };
  config: {
    chargeTarget: number;
    pollIntervalSeconds: number;
    /** Inclusive bounds for the charge target, enforced by the backend. */
    targetMin: number;
    targetMax: number;
    /**
     * Ready-by departure time as "HH:MM" — the user's override if set, else
     * Ohme's own configured time (present even when unplugged), else null.
     */
    readyBy: string | null;
    /** True when readyBy is our stored override rather than Ohme's own time. */
    readyByIsManual: boolean;
    /**
     * Per-weekday target overrides keyed by weekday ("0"=Mon … "6"=Sun). Empty
     * when none set. charger.targetPercent reflects today's effective target.
     */
    dayTargets: Record<string, number>;
  };
  updatedAt: string | null;
  ready: boolean;
  /**
   * Why the backend's most recent Ohme poll failed (e.g. "poll_failed"), or
   * null when it succeeded. When set, the rest of the payload is the last
   * good snapshot rather than a live reading.
   */
  lastError: string | null;
}

export interface ChargeActionResponse {
  ok: boolean;
  /** Charger status after the action. */
  status: ChargerStatus;
  /** Whether max-charge mode is active after the action. */
  maxCharge: boolean;
}

export interface TargetUpdateResponse {
  targetPercent: number;
  /** Whether the new target was written to the persistent settings file. */
  persisted: boolean;
  /** Whether the new target was pushed to Ohme immediately (car plugged in). */
  applied: boolean;
}

export interface ReadyByUpdateResponse {
  /** The new ready-by time ("HH:MM"), or null when cleared. */
  readyBy: string | null;
  persisted: boolean;
  applied: boolean;
}

export interface DayTargetsUpdateResponse {
  /** The new per-weekday overrides keyed by weekday string. */
  dayTargets: Record<string, number>;
  persisted: boolean;
  applied: boolean;
}

export interface Vehicle {
  id: string;
  name: string | null;
  vin: string | null;
  model: string | null;
}

export interface VehiclesResponse {
  vehicles: Vehicle[];
  /** The selected vehicle id, or null when using the first. */
  selected: string | null;
}

export interface VehicleUpdateResponse {
  vehicleId: string | null;
  persisted: boolean;
  applied: boolean;
}

export interface ChargeSlot {
  start: string;
  end: string;
  power: number;
  energy: number;
}

export interface ScheduleResponse {
  slots: ChargeSlot[];
  nextSlotStart: string | null;
  nextSlotEnd: string | null;
  connected: boolean;
  updatedAt: string | null;
}

export interface ChargeSessionEntry {
  id: number;
  pluggedInAt: string | null;
  vehicleName: string | null;
  socPercent: number | null;
  targetPercent: number | null;
  topupPercent: number | null;
  /** "configured" or "skipped_at_target". */
  action: string | null;
  /** Odometer (miles) at plug-in, or null when not reported. */
  odometerMiles: number | null;
  /** Battery state of health (%) at plug-in, or null. */
  sohPercent: number | null;
  actualEnergyKwh: number | null;
  actualCost: number | null;
  costCurrency: string | null;
  costMethod: string | null;
  tariffCoverage: number | null;
  quality: string | null;
  completedAt: string | null;
}

export interface SessionsResponse {
  /** False when Postgres history persistence is disabled — hide the card. */
  enabled: boolean;
  sessions: ChargeSessionEntry[];
}

export interface SessionTelemetryPoint {
  /** Poll timestamp (ISO), or null. */
  at: string | null;
  /** Battery SOC (%) at that poll, or null. */
  socPercent: number | null;
  /** Charge draw (watts) at that poll, or null. */
  powerWatts: number | null;
  /** Cumulative session energy (kWh) at that poll, or null. */
  sessionEnergyKwh: number | null;
}

export interface SessionTelemetryResponse {
  /** False when Postgres persistence is disabled. */
  enabled: boolean;
  /** Per-poll points, oldest first, spanning the session. */
  points: SessionTelemetryPoint[];
}

export interface SohPoint {
  /** Plug-in timestamp (ISO) of the reading, or null. */
  date: string | null;
  /** Battery state of health (%). */
  sohPercent: number;
}

export interface SohHistoryResponse {
  /** False when Postgres history persistence is disabled — hide the card. */
  enabled: boolean;
  /** One point per change in SoH, oldest first. */
  history: SohPoint[];
}

export interface TariffRate {
  from: string;
  to: string | null;
  /** Unit rate in the major currency unit (£/kWh). */
  pricePerKwh: number;
}

export interface TariffResponse {
  /** False when the Agile tariff feature is unconfigured — hide the card. */
  enabled: boolean;
  currency?: string | null;
  /** Upcoming half-hourly rates, oldest first. */
  rates: TariffRate[];
  /** The cheapest upcoming slots (price ascending). */
  cheapest: TariffRate[];
}

export interface EnergyUsageSlot {
  /** Half-hour interval start (ISO). */
  start: string | null;
  /** Half-hour interval end (ISO). */
  end: string | null;
  /** Whole-house grid import for the slot (kWh). */
  importKwh: number | null;
  /** Car charging share of the import (kWh). */
  carKwh: number | null;
  /** Rest-of-house usage = import − car (kWh). */
  houseKwh: number | null;
  /** Import that could not be split confidently because telemetry was incomplete. */
  unattributedKwh: number | null;
  /** Attribution quality for this interval. */
  quality: 'good' | 'timing_adjusted' | 'uncertain_gap' | 'inconsistent' | string;
}

export interface EnergyUsageResponse {
  /** False when consumption is unconfigured or persistence is off — hide the card. */
  enabled: boolean;
  /** The day shown (YYYY-MM-DD), or null when disabled. */
  date: string | null;
  currency?: string | null;
  /** Half-hourly slots for the day, chronological. */
  slots: EnergyUsageSlot[];
  /** Day totals, or null when disabled. */
  totals: { importKwh: number; carKwh: number; houseKwh: number; unattributedKwh: number } | null;
}

export interface DailyStat {
  date: string | null;
  energyKwh: number;
  savings: number;
  cost: number;
  /** True only after the local calendar day has ended. */
  isComplete: boolean;
}

export interface StatisticsResponse {
  rangeDays: number;
  /** True when a validated cached snapshot is shown because Ohme is unavailable. */
  stale: boolean;
  currency: string | null;
  window: {
    from: string;
    toExclusive: string;
    completeThrough: string;
    timezone: string;
  };
  scope: { summary: 'ohme_account' | string; vehicleId: string | null };
  totals: {
    energyKwh: number;
    savingsVsStandard: number;
    costTotal: number;
    averageKwhPrice: number;
    carbonSavedKgVsGasCar: number;
  };
  daily: DailyStat[];
  /**
   * Efficiency for complete charge-to-next-plug-in intervals for one vehicle.
   * It deliberately does not combine account-wide energy with an odometer span.
   */
  efficiency: {
    /** Miles driven across the window (odometer span). */
    milesDriven: number;
    /** Miles per kWh for the matched home-charging intervals. */
    milesPerKwh: number;
    energyKwh: number;
    intervalCount: number;
    vehicleId: string;
    from: string | null;
    to: string | null;
    scope: 'matched_home_charging' | string;
  } | null;
  /**
   * Real-world running cost over the range, from odometer history + spend. Null
   * when persistence is off, nothing was spent, or there's no mileage span.
   */
  runningCost: {
    /** Money spent per mile driven, in `currency`. */
    costPerMile: number;
    /** Miles driven across the window (odometer span). */
    milesDriven: number;
    /** Total spent charging across the window. */
    costTotal: number;
    currency: string;
    intervalCount: number;
    scope: 'matched_actual_home_charging' | string;
  } | null;
  /**
   * Totals for the previous equal-length period, for a period-over-period
   * comparison. Null when the previous window couldn't be fetched.
   */
  comparison: {
    previous: {
      energyKwh: number;
      costTotal: number;
      savingsVsStandard: number;
    };
  } | null;
  metadata: {
    summary: MetricProvenance;
    daily: MetricProvenance;
    efficiency: MetricProvenance;
    runningCost: MetricProvenance;
    comparison: MetricProvenance;
  };
}

export interface MetricProvenance {
  source: string;
  calculationType: string;
  observedAt: string | null;
  completeThrough: string;
  quality: 'complete' | 'measured' | 'actual' | 'unavailable' | 'stale';
  coverage: Record<string, unknown>;
}
