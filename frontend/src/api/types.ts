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
    /** Estimated session cost (planned energy × recent avg price), or null. */
    projectedCost: number | null;
    /** Currency for projectedCost. */
    projectedCostCurrency: string | null;
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
}

export interface SessionsResponse {
  /** False when Postgres history persistence is disabled — hide the card. */
  enabled: boolean;
  sessions: ChargeSessionEntry[];
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

export interface DailyStat {
  date: string | null;
  energyKwh: number;
  savings: number;
  cost: number;
}

export interface StatisticsResponse {
  rangeDays: number;
  currency: string | null;
  totals: {
    energyKwh: number;
    savingsVsStandard: number;
    costTotal: number;
    averageKwhPrice: number;
    carbonSavedKgVsGasCar: number;
  };
  daily: DailyStat[];
  /**
   * Measured driving efficiency over the range, from odometer history. Null
   * when persistence is off or there isn't enough data to compute it.
   */
  efficiency: {
    /** Miles driven across the window (odometer span). */
    milesDriven: number;
    /** Real-world miles per kWh: milesDriven / energy charged. */
    milesPerKwh: number;
  } | null;
}
