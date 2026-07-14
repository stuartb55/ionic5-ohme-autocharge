"""Typed JSON contracts shared by the dashboard-facing API routes.

Keeping these models outside :mod:`api` makes the public boundary reviewable
without loading polling and lifecycle code.  The frontend contract test checks
their OpenAPI property sets against the corresponding TypeScript interfaces.
"""

from __future__ import annotations

import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

import settings


class StrictRequestModel(BaseModel):
    """Mutation body that fails closed on misspelled or stale fields."""

    model_config = ConfigDict(extra="forbid")


class TargetUpdate(StrictRequestModel):
    targetPercent: int = Field(ge=settings.TARGET_MIN, le=settings.TARGET_MAX)


class ReadyByUpdate(StrictRequestModel):
    readyBy: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):([0-5]\d)$")


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
    readyBy: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):([0-5]\d)$")


class NotificationPreferencesUpdate(StrictRequestModel):
    plugIn: bool
    chargeComplete: bool
    problems: bool
    vehicleHealth: bool
    weeklyDigest: bool
    failurePolls: int = Field(ge=1, le=20)
    minimumChargeKwh: float = Field(ge=0, le=100)
    auxBatteryBelowPercent: Optional[int] = Field(default=None, ge=1, le=100)

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
    vehicleId: Optional[str] = None


class VehicleProfileUpdate(StrictRequestModel):
    vehicleId: str = Field(min_length=1, max_length=200)
    enabled: bool
    targetPercent: int = Field(
        default=80, ge=settings.TARGET_MIN, le=settings.TARGET_MAX
    )
    readyBy: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):([0-5]\d)$")


class MaxChargeUpdate(StrictRequestModel):
    enabled: bool


class ContractModel(BaseModel):
    """Closed response shape: accidental fields must be added deliberately."""

    model_config = ConfigDict(extra="forbid")


PersistenceStatus = Literal["saved", "memory_only"]
ApplyStatus = Literal["applied", "not_connected", "already_at_target", "failed"]


class MutationOutcomeModel(ContractModel):
    persistenceStatus: PersistenceStatus
    applyStatus: ApplyStatus


class TargetUpdateResponseModel(MutationOutcomeModel):
    targetPercent: int


class ReadyByUpdateResponseModel(MutationOutcomeModel):
    readyBy: Optional[str]


class DayTargetsUpdateResponseModel(MutationOutcomeModel):
    dayTargets: dict[str, int]


class TripModeUpdateResponseModel(MutationOutcomeModel):
    enabled: bool
    targetPercent: Optional[int]
    readyBy: Optional[str]


class NotificationPreferencesModel(ContractModel):
    plugIn: bool
    chargeComplete: bool
    problems: bool
    vehicleHealth: bool
    weeklyDigest: bool
    failurePolls: int
    minimumChargeKwh: float
    auxBatteryBelowPercent: Optional[int]
    configured: bool


class NotificationPreferencesUpdateResponseModel(NotificationPreferencesModel):
    persistenceStatus: PersistenceStatus


class VehicleModel(ContractModel):
    id: str
    name: Optional[str]
    model: Optional[str]


class VehiclesResponseModel(ContractModel):
    vehicles: list[VehicleModel]
    selected: Optional[str]


class VehicleUpdateResponseModel(MutationOutcomeModel):
    vehicleId: Optional[str]


class VehicleProfileUpdateResponseModel(MutationOutcomeModel):
    vehicleId: str
    enabled: bool
    targetPercent: Optional[int]
    readyBy: Optional[str]


class LocationModel(ContractModel):
    latitude: float
    longitude: float


class VehicleHealthModel(ContractModel):
    auxBatteryPercent: Optional[int]
    tyrePressureWarning: Optional[bool]
    washerFluidWarning: Optional[bool]
    keyBatteryWarning: Optional[bool]
    openItems: list[str]


class StatusVehicleModel(ContractModel):
    name: Optional[str]
    batteryPercent: Optional[int]
    rangeMiles: Optional[int]
    sohPercent: Optional[int]
    isLocked: Optional[bool]
    location: Optional[LocationModel]
    health: VehicleHealthModel


class ChargerPowerModel(ContractModel):
    watts: float
    amps: float
    volts: Optional[int]


class StatusChargerModel(ContractModel):
    status: str
    connected: bool
    online: bool
    maxCharge: bool
    model: Optional[str]
    power: ChargerPowerModel
    targetPercent: Optional[int]
    sessionEnergyKwh: float
    projectedFinish: Optional[str]
    plannedEnergyKwh: float
    projectedCost: Optional[float]
    projectedCostCurrency: Optional[str]
    projectedCostMethod: Optional[Literal["agile", "average"]]


class TripModeModel(ContractModel):
    enabled: bool
    targetPercent: Optional[int]
    readyBy: Optional[str]


class VehicleProfileModel(ContractModel):
    targetPercent: int
    readyBy: Optional[str]


class StatusConfigModel(ContractModel):
    chargeTarget: int
    pollIntervalSeconds: int
    targetMin: int
    targetMax: int
    readyBy: Optional[str]
    readyByIsManual: bool
    dayTargets: dict[str, int]
    tripMode: TripModeModel
    notifications: NotificationPreferencesModel
    vehicleProfiles: dict[str, VehicleProfileModel]


class AutomationModel(ContractModel):
    state: Literal["idle", "pending", "configured", "error"]
    errorCode: Optional[str]
    lastAttemptAt: Optional[str]


class StatusResponseModel(ContractModel):
    vehicle: StatusVehicleModel
    charger: StatusChargerModel
    config: StatusConfigModel
    updatedAt: Optional[str]
    ready: bool
    automation: AutomationModel
    lastError: Optional[str]


class ChargeSlotModel(ContractModel):
    start: str
    end: str
    power: float
    energy: float


class ScheduleResponseModel(ContractModel):
    slots: list[ChargeSlotModel]
    nextSlotStart: Optional[str]
    nextSlotEnd: Optional[str]
    connected: bool
    updatedAt: Optional[str]


class ChargeSessionEntryModel(ContractModel):
    id: int
    pluggedInAt: Optional[str]
    vehicleName: Optional[str]
    socPercent: Optional[int]
    targetPercent: Optional[int]
    topupPercent: Optional[int]
    action: Optional[str]
    odometerMiles: Optional[int]
    sohPercent: Optional[int]
    actualEnergyKwh: Optional[float]
    actualCost: Optional[float]
    costCurrency: Optional[str]
    costMethod: Optional[str]
    tariffCoverage: Optional[float]
    quality: Optional[str]
    completedAt: Optional[str]


class SessionsResponseModel(ContractModel):
    enabled: bool
    sessions: list[ChargeSessionEntryModel]


class ChargeActionResponseModel(ContractModel):
    ok: bool
    status: str
    maxCharge: bool


class RefreshResponseModel(ContractModel):
    ok: bool
    updatedAt: Optional[str]
    ready: bool


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
    from_: Optional[datetime.datetime] = Field(alias="from")
    to: Optional[datetime.datetime]
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
    vehicleId: Optional[str]


class MetricProvenanceModel(BaseModel):
    source: str
    calculationType: str
    observedAt: Optional[datetime.datetime]
    completeThrough: datetime.datetime
    quality: Literal["complete", "measured", "actual", "unavailable", "stale"]
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
    currency: Optional[str]
    window: StatisticsWindowModel
    scope: StatisticsScopeModel
    totals: StatisticsTotalsModel
    daily: list[DailyStatModel]
    efficiency: Optional[EfficiencyModel]
    runningCost: Optional[RunningCostModel]
    comparison: Optional[ComparisonModel]
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
    ingestedThrough: Optional[datetime.datetime]


class DailyQualityModel(BaseModel):
    completeThrough: Optional[datetime.date]


class StatisticsCacheQualityModel(BaseModel):
    available: bool
    ageSeconds: Optional[int]


class DataQualityResponseModel(BaseModel):
    status: Literal["ok", "attention", "unavailable"]
    generatedAt: datetime.datetime
    persistenceAvailable: bool
    actualCostExpected: bool
    sessions: Optional[SessionQualityModel]
    telemetry: Optional[TelemetryQualityModel]
    consumption: Optional[ConsumptionQualityModel]
    daily: Optional[DailyQualityModel]
    statisticsCache: StatisticsCacheQualityModel


class MonthlyReportDailyModel(BaseModel):
    date: datetime.date
    energyWh: int
    savingsMinor: int
    costMinor: int
    currency: Optional[str]
    source: str
    isComplete: bool
    updatedAt: datetime.datetime


class MonthlyReportSessionModel(BaseModel):
    id: int
    pluggedInAt: datetime.datetime
    completedAt: Optional[datetime.datetime]
    actualEnergyWh: Optional[int]
    actualCostMinor: Optional[int]
    currency: Optional[str]
    quality: str
    vehicleName: Optional[str]
    action: Optional[str]


class MonthlyAccountSummaryModel(BaseModel):
    energyWh: int
    savingsMinor: Optional[int]
    costMinor: Optional[int]
    currency: Optional[str]
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
    actualCostMinor: Optional[int]
    costCurrency: Optional[str]
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
    unpluggedAt: Optional[datetime.datetime]
    completedAt: Optional[datetime.datetime]
    vehicleName: Optional[str]
    sourceObservedAt: Optional[datetime.datetime]
    socPercent: Optional[int]
    targetPercent: Optional[int]
    endSocPercent: Optional[int]
    topupPercent: Optional[int]
    action: Optional[str]
    odometerMiles: Optional[int]
    sohPercent: Optional[int]
    actualEnergyWh: Optional[int]
    actualCostMinor: Optional[int]
    costCurrency: Optional[str]
    costMethod: Optional[str]
    tariffCoverage: Optional[float]
    reconstructedEnergyWh: Optional[int]
    reconciliationDeltaWh: Optional[int]
    completionReason: Optional[str]
    quality: str
    updatedAt: datetime.datetime


class SessionAuditEventModel(BaseModel):
    at: datetime.datetime
    type: str
    details: dict[str, Any]


class SessionAuditScheduleModel(BaseModel):
    recordedAt: datetime.datetime
    nextSlotStart: Optional[datetime.datetime]
    nextSlotEnd: Optional[datetime.datetime]
    slots: list[dict[str, Any]]
    revision: int
    reason: str


class SessionAuditIntervalModel(BaseModel):
    start: datetime.datetime
    end: datetime.datetime
    energyWh: int
    costMinor: Optional[int]
    rateMinorPerKwh: Optional[float]
    currency: Optional[str]
    quality: str
    source: str


class SessionAuditResponseModel(BaseModel):
    session: SessionAuditRecordModel
    events: list[SessionAuditEventModel]
    schedules: list[SessionAuditScheduleModel]
    intervals: list[SessionAuditIntervalModel]
