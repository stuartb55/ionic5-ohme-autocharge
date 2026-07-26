import type { DataQualityResponse } from '../api/types';

export function dataQualityIssueCount(data: DataQualityResponse) {
  if (data.status === 'unavailable') return 0;
  return [
    (data.sessions?.missingActualEnergy ?? 0) > 0,
    data.actualCostExpected && (data.sessions?.missingActualCost ?? 0) > 0,
    (data.telemetry?.unlinkedLast24h ?? 0) > 0,
    data.consumptionConfigured && (data.consumption?.uncertainLast30d ?? 0) > 0,
  ].filter(Boolean).length;
}

export function dataQualityStatusLabel(data: DataQualityResponse) {
  if (data.status === 'unavailable') return 'Checks unavailable';
  const issueCount = dataQualityIssueCount(data);
  if (issueCount === 0) return 'No issues found';
  return `${issueCount} ${issueCount === 1 ? 'check needs' : 'checks need'} attention`;
}
