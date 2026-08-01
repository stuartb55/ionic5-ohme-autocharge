import type { IntegrationsResponse, IntegrationStatus } from '../api/types';

const STATUS_LABEL: Record<IntegrationStatus, string> = {
  healthy: 'Healthy',
  configured: 'Configured',
  attention: 'Action needed',
  disabled: 'Optional',
};

export function IntegrationHealth({ data }: { data: IntegrationsResponse }) {
  const attention = data.integrations.filter((item) => item.status === 'attention').length;
  const enabled = data.integrations.filter((item) => item.configured).length;

  return (
    <details className="card integration-health">
      <summary>
        <span>
          <span className="eyebrow">Setup &amp; connections</span>
          <strong>Integration health</strong>
        </span>
        <span className={`integration-summary ${attention ? 'attention' : ''}`}>
          {attention ? `${attention} action needed` : `${enabled} configured`}
        </span>
      </summary>
      <div className="integration-list">
        {data.integrations.map((item) => (
          <div className="integration-row" key={item.id}>
            <span className={`integration-dot ${item.status}`} aria-hidden="true" />
            <span>
              <strong>{item.name}</strong>
              <small>{item.detail}</small>
            </span>
            <span className={`integration-state ${item.status}`}>
              {STATUS_LABEL[item.status]}
            </span>
          </div>
        ))}
      </div>
    </details>
  );
}
