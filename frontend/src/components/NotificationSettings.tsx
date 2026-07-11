import { useState } from 'react';
import type { NotificationPreferences } from '../api/types';
import { useSaveAction } from '../hooks/useSaveAction';

type EditablePreferences = Omit<NotificationPreferences, 'configured'>;

const TOGGLES: Array<[keyof EditablePreferences, string]> = [
  ['plugIn', 'Plug-in configured'],
  ['chargeComplete', 'Charging complete'],
  ['problems', 'Connection problems and recovery'],
  ['vehicleHealth', 'Vehicle health warnings'],
  ['weeklyDigest', 'Weekly charging summary'],
];

export function NotificationSettings({
  value,
  onSave,
}: {
  value: NotificationPreferences;
  onSave: (preferences: EditablePreferences) => Promise<void>;
}) {
  const editable = (preferences: NotificationPreferences): EditablePreferences => ({
    plugIn: preferences.plugIn,
    chargeComplete: preferences.chargeComplete,
    problems: preferences.problems,
    vehicleHealth: preferences.vehicleHealth,
    weeklyDigest: preferences.weeklyDigest,
    failurePolls: preferences.failurePolls,
    minimumChargeKwh: preferences.minimumChargeKwh,
    auxBatteryBelowPercent: preferences.auxBatteryBelowPercent,
  });
  const [draft, setDraft] = useState<EditablePreferences>(() => editable(value));
  const [previous, setPrevious] = useState(value);
  const [edited, setEdited] = useState(false);
  const { saving, error, saved, run, reset } = useSaveAction();

  if (value !== previous) {
    setPrevious(value);
    if (!edited) setDraft(editable(value));
  }

  const change = <K extends keyof EditablePreferences>(key: K, next: EditablePreferences[K]) => {
    reset();
    setEdited(true);
    setDraft((current) => ({ ...current, [key]: next }));
  };
  const save = async () => {
    if (await run(() => onSave(draft))) setEdited(false);
  };
  const thresholdsValid =
    draft.failurePolls >= 1
    && draft.failurePolls <= 20
    && draft.minimumChargeKwh >= 0
    && draft.minimumChargeKwh <= 100
    && (draft.auxBatteryBelowPercent == null
      || (draft.auxBatteryBelowPercent >= 1 && draft.auxBatteryBelowPercent <= 100));

  return (
    <details className="notification-settings">
      <summary>
        Notifications
        {!value.configured && <span className="badge">ntfy not configured</span>}
      </summary>
      <div className="notification-options">
        {TOGGLES.map(([key, text]) => (
          <label key={key}>
            <input
              type="checkbox"
              checked={Boolean(draft[key])}
              disabled={saving}
              onChange={(event) => change(key, event.target.checked)}
            />
            <span>{text}</span>
          </label>
        ))}
      </div>
      <div className="notification-thresholds">
        <label>
          <span>Problem alert after</span>
          <input
            type="number"
            min={1}
            max={20}
            value={draft.failurePolls}
            disabled={saving || !draft.problems}
            onChange={(event) => change('failurePolls', Number(event.target.value))}
          />
          <span>failed polls</span>
        </label>
        <label>
          <span>Completion minimum</span>
          <input
            type="number"
            min={0}
            max={100}
            step={0.1}
            value={draft.minimumChargeKwh}
            disabled={saving || !draft.chargeComplete}
            onChange={(event) => change('minimumChargeKwh', Number(event.target.value))}
          />
          <span>kWh</span>
        </label>
        <label>
          <span>12V alert below</span>
          <input
            type="number"
            min={1}
            max={100}
            placeholder="Off"
            value={draft.auxBatteryBelowPercent ?? ''}
            disabled={saving || !draft.vehicleHealth}
            onChange={(event) => change(
              'auxBatteryBelowPercent',
              event.target.value === '' ? null : Number(event.target.value),
            )}
          />
          <span>% · optional</span>
        </label>
      </div>
      {!value.configured && (
        <p className="field-hint">Set NTFY_TOPIC on the server before alerts can be delivered.</p>
      )}
      {edited && (
        <button
          type="button"
          className="save"
          disabled={saving || !thresholdsValid}
          onClick={() => void save()}
        >
          {saving ? 'Saving…' : 'Save notifications'}
        </button>
      )}
      {saved && !edited && <span className="save-confirm" role="status">Saved ✓</span>}
      {error && <div className="target-error" role="alert">Couldn’t update notifications. Try again.</div>}
    </details>
  );
}
