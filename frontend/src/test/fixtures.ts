import type {
  ScheduleResponse,
  SessionsResponse,
  StatisticsResponse,
  StatusResponse,
} from '../api/types';

export const statusFixture: StatusResponse = {
  vehicle: { name: 'Hyundai IONIQ 5', batteryPercent: 62, rangeMiles: 180 },
  charger: {
    status: 'charging',
    connected: true,
    online: true,
    maxCharge: false,
    model: 'Home Pro',
    power: { watts: 7400, amps: 32, volts: 230 },
    targetPercent: 80,
    sessionEnergyKwh: 4.5,
    projectedFinish: '2026-06-02T05:00:00+01:00',
  },
  config: {
    chargeTarget: 80,
    pollIntervalSeconds: 180,
    targetMin: 10,
    targetMax: 100,
    readyBy: null,
  },
  updatedAt: '2026-06-02T00:05:00+01:00',
  ready: true,
  lastError: null,
};

export const scheduleFixture: ScheduleResponse = {
  slots: [
    { start: '2026-06-02T01:00:00+01:00', end: '2026-06-02T03:30:00+01:00', power: 7.4, energy: 18.5 },
    { start: '2026-06-02T04:30:00+01:00', end: '2026-06-02T05:00:00+01:00', power: 7.4, energy: 3.7 },
  ],
  nextSlotStart: '2026-06-02T01:00:00+01:00',
  nextSlotEnd: '2026-06-02T03:30:00+01:00',
  connected: true,
  updatedAt: '2026-06-02T00:05:00+01:00',
};

export const sessionsFixture: SessionsResponse = {
  enabled: true,
  sessions: [
    {
      id: 3,
      pluggedInAt: '2026-06-01T21:42:00+01:00',
      vehicleName: 'Hyundai IONIQ 5',
      socPercent: 54,
      targetPercent: 80,
      topupPercent: 26,
      action: 'configured',
      odometerMiles: 12450,
    },
    {
      id: 2,
      pluggedInAt: '2026-05-31T19:05:00+01:00',
      vehicleName: 'Hyundai IONIQ 5',
      socPercent: 85,
      targetPercent: 80,
      topupPercent: 0,
      action: 'skipped_at_target',
      odometerMiles: 12380,
    },
  ],
};

export const statisticsFixture: StatisticsResponse = {
  rangeDays: 7,
  currency: 'GBP',
  totals: {
    energyKwh: 42,
    savingsVsStandard: 8.4,
    costTotal: 5.25,
    averageKwhPrice: 0.125,
    carbonSavedKgVsGasCar: 12,
  },
  daily: [
    { date: '2026-05-27', energyKwh: 6.2, savings: 1.1, cost: 0.8 },
    { date: '2026-05-28', energyKwh: 0, savings: 0, cost: 0 },
    { date: '2026-05-29', energyKwh: 8.5, savings: 1.7, cost: 1.1 },
    { date: '2026-05-30', energyKwh: 12.1, savings: 2.4, cost: 1.5 },
    { date: '2026-05-31', energyKwh: 3.4, savings: 0.6, cost: 0.4 },
    { date: '2026-06-01', energyKwh: 0, savings: 0, cost: 0 },
    { date: '2026-06-02', energyKwh: 11.8, savings: 2.6, cost: 0.95 },
  ],
  efficiency: null,
};
