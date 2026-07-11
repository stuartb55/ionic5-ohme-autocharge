import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { statusFixture } from '../test/fixtures';
import { NotificationSettings } from './NotificationSettings';

describe('NotificationSettings', () => {
  it('saves category choices and thresholds as one validated preference set', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<NotificationSettings value={statusFixture.config.notifications} onSave={onSave} />);

    await userEvent.click(screen.getByText(/^notifications$/i));
    await userEvent.click(screen.getByLabelText(/plug-in configured/i));
    const failurePolls = screen.getByLabelText(/problem alert after/i);
    await userEvent.clear(failurePolls);
    await userEvent.type(failurePolls, '3');
    const aux = screen.getByLabelText(/12v alert below/i);
    await userEvent.type(aux, '35');
    await userEvent.click(screen.getByRole('button', { name: /save notifications/i }));

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      plugIn: false,
      failurePolls: 3,
      auxBatteryBelowPercent: 35,
    }));
  });

  it('explains when delivery is not configured on the server', async () => {
    render(
      <NotificationSettings
        value={{ ...statusFixture.config.notifications, configured: false }}
        onSave={vi.fn()}
      />,
    );
    expect(screen.getByText(/ntfy not configured/i)).toBeInTheDocument();
    await userEvent.click(screen.getByText(/^notifications$/i));
    expect(screen.getByText(/set NTFY_TOPIC/i)).toBeInTheDocument();
  });

  it('keeps edits visible and reports a failed save', async () => {
    render(
      <NotificationSettings
        value={statusFixture.config.notifications}
        onSave={vi.fn().mockRejectedValue(new Error('offline'))}
      />,
    );
    await userEvent.click(screen.getByText(/^notifications$/i));
    await userEvent.click(screen.getByLabelText(/weekly charging summary/i));
    await userEvent.click(screen.getByRole('button', { name: /save notifications/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t update notifications/i);
    expect(screen.getByLabelText(/weekly charging summary/i)).not.toBeChecked();
  });
});
