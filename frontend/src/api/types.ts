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
  };
  charger: {
    status: ChargerStatus;
    connected: boolean;
    online: boolean;
    model: string | null;
    power: {
      watts: number;
      amps: number;
      volts: number | null;
    };
    targetPercent: number | null;
    sessionEnergyKwh: number;
  };
  config: {
    chargeTarget: number;
    pollIntervalSeconds: number;
  };
  updatedAt: string | null;
  ready: boolean;
}

export interface TargetUpdateResponse {
  targetPercent: number;
  /** Whether the new target was written to the persistent settings file. */
  persisted: boolean;
  /** Whether the new target was pushed to Ohme immediately (car plugged in). */
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
}
