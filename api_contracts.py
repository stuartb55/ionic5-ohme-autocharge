"""Typed JSON contracts shared by the dashboard-facing API routes.

Keeping these models outside :mod:`api` makes the public boundary reviewable
without loading polling and lifecycle code.  The frontend contract test checks
their OpenAPI property sets against the corresponding TypeScript interfaces.
"""

from __future__ import annotations

import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

import settings


class StrictRequestModel(BaseModel):
    """Mutation body that fails closed on misspelled or stale fields."""

    model_config = ConfigDict(extra="forbid")


class TargetUpdate(StrictRequestModel):
    targetPercent: int = Field(ge=settings.TARGET_MIN, le=settings.TARGET_MAX)


class ReadyByUpdate(StrictRequestModel):
    readyBy: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):([0-5]\d)$")


class DayTargetsUpdate(StrictRequestModel):
    dayTargets: dict[int, int]

    @field_validator("dayTargets")
    @classmethod
    def _check_bounds(cls, value: dict[int, int]) -> dict[int, int]:
        for day, percentage in value.items():
            if not 0 <= day <= 6:
                raise ValueError("weekday must be 0 (Mon) to 6 (Sun)")
            if not settings.TARGET_MIN <= percentage <= settings.TARGET_MAX:
                raise ValueError(
                    f"target must be {settings.TARGET_MIN}–{settings.TARGET_MAX}"
                )
        return value


class TripModeUpdate(StrictRequestModel):
    enabled: bool
    targetPercent: int = Field(
        default=100, ge=settings.TARGET_MIN, le=settings.TARGET_MAX
    )
    readyBy: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):([0-5]\d)$")


class TomorrowOverrideUpdate(StrictRequestModel):
    enabled: bool
    targetPercent: int = Field(
        default=80, ge=settings.TARGET_MIN, le=settings.TARGET_MAX
    )
    readyBy: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):([0-5]\d)$")


class NotificationPreferencesUpdate(StrictRequestModel):
    plugIn: bool
    chargeComplete: bool
    problems: bool
    vehicleHealth: bool
    weeklyDigest: bool
    failurePolls: int = Field(ge=1, le=20)
    minimumChargeKwh: float = Field(ge=0, le=100)
    auxBatteryBelowPercent: int | None = Field(default=None, ge=1, le=100)

    def to_settings(self) -> settings.NotificationPreferences:
        return settings.NotificationPreferences(
            plug_in=self.plugIn,
            charge_complete=self.chargeComplete,
            problems=self.problems,
            vehicle_health=self.vehicleHealth,
            weekly_digest=self.weeklyDigest,
            failure_polls=self.failurePolls,
            minimum_charge_kwh=self.minimumChargeKwh,
            aux_battery_below_percent=self.auxBatteryBelowPercent,
        )


class VehicleUpdate(StrictRequestModel):
    vehicleId: str | None = None


class VehicleProfileUpdate(StrictRequestModel):
    vehicleId: str = Field(min_length=1, max_length=200)
    enabled: bool
    targetPercent: int = Field(
        default=80, ge=settings.TARGET_MIN, le=settings.TARGET_MAX
    )
    readyBy: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):([0-5]\d)$")


class MaxChargeUpdate(StrictRequestModel):
    enabled: bool


class ContractModel(BaseModel):
    """Closed response shape: accidental fields must be added deliberately."""

    model_config = ConfigDict(extra="forbid")


PersistenceStatus = Literal["saved", "memory_only"]
ApplyStatus = Literal["applied", "not_connected", "already_at_target", "failed"]
# Outcome of the Bluelink re-read a manual refresh performs alongside the Ohme
# one. Reported separately because the two upstreams fail independently: the
# charger reading can be fresh while the car is unreachable.
VehicleReadStatus = Literal["ok", "failed"]


class MutationOutcomeModel(ContractModel):
    persistenceStatus: PersistenceStatus
    applyStatus: ApplyStatus


class TargetUpdateResponseModel(MutationOutcomeModel):
    targetPercent: int


class ReadyByUpdateResponseModel(MutationOutcomeModel):
    readyBy: str | None


class DayTargetsUpdateResponseModel(MutationOutcomeModel):
    dayTargets: dict[str, int]


class TripModeUpdateResponseModel(MutationOutcomeModel):
    enabled: bool
    targetPercent: int | None
    readyBy: str | None


class TomorrowOverrideUpdateResponseModel(MutationOutcomeModel):
    enabled: bool
    date: datetime.date | None
    targetPercent: int | None
    readyBy: str | None


class NotificationPreferencesModel(ContractModel):
    plugIn: bool
    chargeComplete: bool
    problems: bool
    vehicleHealth: bool
    weeklyDigest: bool
    failurePolls: int
    minimumChargeKwh: float
    auxBatteryBelowPercent: int | None
    configured: bool


class NotificationPreferencesUpdateResponseModel(NotificationPreferencesModel):
    persistenceStatus: PersistenceStatus


class VehicleModel(ContractModel):
    id: str
    name: str | None
    model: str | None


class VehiclesResponseModel(ContractModel):
    vehicles: list[VehicleModel]
    selected: str | None


class VehicleUpdateResponseModel(MutationOutcomeModel):
    vehicleId: str | None


class VehicleProfileUpdateResponseModel(MutationOutcomeModel):
    vehicleId: str
    enabled: bool
    targetPercent: int | None
    readyBy: str | None


class LocationModel(ContractModel):
    latitude: float
    longitude: float


class VehicleHealthModel(ContractModel):
    auxBatteryPercent: int | None
    tyrePressureWarning: bool | None
    washerFluidWarning: bool | None
    keyBatteryWarning: bool | None
    openItems: list[str]


class StatusVehicleModel(ContractModel):
    name: str | None
    batteryPercent: int | None
    rangeMiles: int | None
    sohPercent: int | None
    isLocked: bool | None
    location: LocationModel | None
    health: VehicleHealthModel


class ChargerPowerModel(ContractModel):
    watts: float
    amps: float
    volts: int | None


class StatusChargerModel(ContractModel):
    status: str
    connected: bool
    online: bool
    maxCharge: bool
    model: str | None
    power: ChargerPowerModel
    targetPercent: int | None
    sessionEnergyKwh: float
    projectedFinish: str | None
    plannedEnergyKwh: float
    projectedCost: float | None
    projectedCostCurrency: str | None
    projectedCostMethod: Literal["agile", "intelligent_go", "average"] | None


class TripModeModel(ContractModel):
    enabled: bool
    targetPercent: int | None
    readyBy: str | None


class TomorrowOverrideModel(ContractModel):
    enabled: bool
    date: datetime.date | None
    targetPercent: int | None
    readyBy: str | None


class VehicleProfileModel(ContractModel):
    targetPercent: int
    readyBy: str | None


class StatusConfigModel(ContractModel):
    chargeTarget: int
    pollIntervalSeconds: int
    timezone: str
    targetMin: int
    targetMax: int
    readyBy: str | None
    readyByIsManual: bool
    effectiveTarget: int
    effectiveReadyBy: str | None
    effectiveTargetSource: Literal[
        "trip", "tomorrow", "vehicle_profile", "weekday", "default"
    ]
    effectiveReadyBySource: Literal[
        "trip", "tomorrow", "vehicle_profile", "default", "ohme", "none"
    ]
    dayTargets: dict[str, int]
    tripMode: TripModeModel
    tomorrowOverride: TomorrowOverrideModel
    notifications: NotificationPreferencesModel
    vehicleProfiles: dict[str, VehicleProfileModel]


class IntegrationHealthModel(ContractModel):
    id: Literal["ohme", "bluelink", "history", "tariff", "energy", "notifications"]
    name: str
    configured: bool
    status: Literal["healthy", "configured", "attention", "disabled"]
    detail: str


class IntegrationsResponseModel(ContractModel):
    integrations: list[IntegrationHealthModel]


class AutomationModel(ContractModel):
    state: Literal["idle", "pending", "configured", "error"]
    errorCode: str | None
    lastAttemptAt: str | None


class StatusResponseModel(ContractModel):
    vehicle: StatusVehicleModel
    charger: StatusChargerModel
    config: StatusConfigModel
    updatedAt: str | None
    ready: bool
    automation: AutomationModel
    lastError: str | None


class ChargeSlotModel(ContractModel):
    start: str
    end: str
    power: float
    energy: float


class ScheduleResponseModel(ContractModel):
    slots: list[ChargeSlotModel]
    nextSlotStart: str | None
    nextSlotEnd: str | None
    connected: bool
    updatedAt: str | None
    timezone: str


class ChargeSessionEntryModel(ContractModel):
    id: int
    pluggedInAt: str | None
    vehicleName: str | None
    socPercent: int | None
    targetPercent: int | None
    topupPercent: int | None
    action: str | None
    odometerMiles: int | None
    sohPercent: int | None
    actualEnergyKwh: float | None
    actualCost: float | None
    costCurrency: str | None
    costMethod: str | None
    tariffCoverage: float | None
    quality: str | None
    completedAt: str | None
    reviewIssues: list[Literal["missing_energy", "missing_cost"]]


class SessionsResponseModel(ContractModel):
    enabled: bool
    review: Literal["missing_energy", "missing_cost", "any"] | None
    sessions: list[ChargeSessionEntryModel]


class ChargeActionResponseModel(ContractModel):
    ok: bool
    status: str
    maxCharge: bool


class RefreshResponseModel(ContractModel):
    ok: bool
    updatedAt: str | None
    ready: bool
    # "ok" is a successful Bluelink re-read, "failed" a charger-only refresh.
    vehicle: VehicleReadStatus


class StatisticsWindowModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: datetime.datetime = Field(alias="from")
    toExclusive: datetime.datetime
    completeThrough: datetime.datetime
    timezone: str


class StatisticsTotalsModel(BaseModel):
    energyKwh: float
    savingsVsStandard: float
    costTotal: float
    averageKwhPrice: float
    carbonSavedKgVsGasCar: float


class DailyStatModel(BaseModel):
    date: datetime.date
    energyKwh: float
    savings: float
    cost: float
    isComplete: bool


class EfficiencyModel(BaseModel):
    milesDriven: int
    milesPerKwh: float
    energyKwh: float
    intervalCount: int
    vehicleId: str
    model_config = ConfigDict(populate_by_name=True)
    from_: datetime.datetime | None = Field(alias="from")
    to: datetime.datetime | None
    scope: Literal["matched_home_charging"]


class RunningCostModel(BaseModel):
    costPerMile: float
    milesDriven: int
    costTotal: float
    currency: str
    intervalCount: int
    scope: Literal["matched_actual_home_charging"]


class PreviousTotalsModel(BaseModel):
    energyKwh: float
    costTotal: float
    savingsVsStandard: float


class ComparisonModel(BaseModel):
    previous: PreviousTotalsModel


class StatisticsScopeModel(BaseModel):
    summary: Literal["ohme_account"]
    vehicleId: str | None


class MetricProvenanceModel(BaseModel):
    source: str
    calculationType: str
    observedAt: datetime.datetime | None
    completeThrough: datetime.datetime
    quality: Literal[
        "complete", "partial", "measured", "actual", "unavailable", "stale"
    ]
    coverage: dict[str, Any]


class StatisticsMetadataModel(BaseModel):
    summary: MetricProvenanceModel
    daily: MetricProvenanceModel
    efficiency: MetricProvenanceModel
    runningCost: MetricProvenanceModel
    comparison: MetricProvenanceModel


class StatisticsResponseModel(BaseModel):
    rangeDays: int
    stale: bool = False
    currency: str | None
    window: StatisticsWindowModel
    scope: StatisticsScopeModel
    totals: StatisticsTotalsModel
    daily: list[DailyStatModel]
    efficiency: EfficiencyModel | None
    runningCost: RunningCostModel | None
    comparison: ComparisonModel | None
    metadata: StatisticsMetadataModel


class SessionQualityModel(BaseModel):
    total: int
    completed: int
    missingActualEnergy: int
    missingActualCost: int


class TelemetryQualityModel(BaseModel):
    unlinkedLast24h: int


class ConsumptionQualityModel(BaseModel):
    uncertainLast30d: int
    ingestedThrough: datetime.datetime | None
    totalLast30d: int = 0
    importKwhLast30d: float = 0.0
    unattributedKwhLast30d: float = 0.0
    #: Local (``config.TIMEZONE``) day of the most recent unsplit interval, so the
    #: dashboard can open the House vs car chart on a day that shows the gap.
    lastUncertainDate: datetime.date | None = None
    #: True only when the unsplit energy is a material share of the window's
    #: import. A handful of intervals is expected and is not a fault to fix.
    needsAttention: bool = False


class DailyQualityModel(BaseModel):
    completeThrough: datetime.date | None


class StatisticsCacheQualityModel(BaseModel):
    available: bool
    ageSeconds: int | None


class DataQualityResponseModel(BaseModel):
    status: Literal["ok", "attention", "unavailable"]
    generatedAt: datetime.datetime
    persistenceAvailable: bool
    actualCostExpected: bool
    consumptionConfigured: bool
    sessions: SessionQualityModel | None
    telemetry: TelemetryQualityModel | None
    consumption: ConsumptionQualityModel | None
    daily: DailyQualityModel | None
    statisticsCache: StatisticsCacheQualityModel


class MonthlyReportDailyModel(BaseModel):
    date: datetime.date
    energyWh: int
    savingsMinor: int
    costMinor: int
    currency: str | None
    source: str
    isComplete: bool
    updatedAt: datetime.datetime


class MonthlyReportSessionModel(BaseModel):
    id: int
    pluggedInAt: datetime.datetime
    completedAt: datetime.datetime | None
    actualEnergyWh: int | None
    actualCostMinor: int | None
    currency: str | None
    quality: str
    vehicleName: str | None
    action: str | None


class MonthlyAccountSummaryModel(BaseModel):
    energyWh: int
    savingsMinor: int | None
    costMinor: int | None
    currency: str | None
    completeDays: int
    expectedDays: int
    missingDays: int
    quality: Literal["complete", "partial", "unavailable", "mixed_currency"]


class MonthlySessionSummaryModel(BaseModel):
    total: int
    configuredCompleted: int
    measuredEnergyCount: int
    measuredEnergyWh: int
    actualCostCount: int
    actualCostMinor: int | None
    costCurrency: str | None
    actualCostExpected: bool
    missingActualEnergy: int
    missingActualCost: int
    qualityCounts: dict[str, int]


class MonthlyReportResponseModel(BaseModel):
    month: str
    timezone: str
    from_: datetime.datetime = Field(alias="from")
    toExclusive: datetime.datetime
    generatedAt: datetime.datetime
    account: MonthlyAccountSummaryModel
    homeSessions: MonthlySessionSummaryModel
    daily: list[MonthlyReportDailyModel]
    sessions: list[MonthlyReportSessionModel]

    model_config = ConfigDict(populate_by_name=True)


class SessionAuditRecordModel(BaseModel):
    id: int
    pluggedInAt: datetime.datetime
    unpluggedAt: datetime.datetime | None
    completedAt: datetime.datetime | None
    vehicleName: str | None
    sourceObservedAt: datetime.datetime | None
    socPercent: int | None
    targetPercent: int | None
    endSocPercent: int | None
    topupPercent: int | None
    action: str | None
    odometerMiles: int | None
    sohPercent: int | None
    actualEnergyWh: int | None
    actualCostMinor: int | None
    costCurrency: str | None
    costMethod: str | None
    tariffCoverage: float | None
    reconstructedEnergyWh: int | None
    reconciliationDeltaWh: int | None
    completionReason: str | None
    quality: str
    updatedAt: datetime.datetime


class SessionAuditEventModel(BaseModel):
    at: datetime.datetime
    type: str
    details: dict[str, Any]


class SessionAuditScheduleModel(BaseModel):
    recordedAt: datetime.datetime
    nextSlotStart: datetime.datetime | None
    nextSlotEnd: datetime.datetime | None
    slots: list[dict[str, Any]]
    revision: int
    reason: str


class SessionAuditIntervalModel(BaseModel):
    start: datetime.datetime
    end: datetime.datetime
    energyWh: int
    costMinor: int | None
    rateMinorPerKwh: float | None
    currency: str | None
    quality: str
    source: str


class SessionAuditResponseModel(BaseModel):
    session: SessionAuditRecordModel
    events: list[SessionAuditEventModel]
    schedules: list[SessionAuditScheduleModel]
    intervals: list[SessionAuditIntervalModel]
