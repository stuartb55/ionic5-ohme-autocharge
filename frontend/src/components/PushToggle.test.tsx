import { render, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { server } from '../test/mocks/server';
import { urlBase64ToUint8Array } from '../utils/push';
import { PushToggle } from './PushToggle';

describe('urlBase64ToUint8Array', () => {
  it('decodes a URL-safe base64 key', () => {
    // "AQID" is base64 for bytes [1, 2, 3].
    expect(Array.from(urlBase64ToUint8Array('AQID'))).toEqual([1, 2, 3]);
  });

  it('handles URL-safe chars and missing padding', () => {
    // Should not throw on '-'/'_' and unpadded input.
    expect(() => urlBase64ToUint8Array('a-b_')).not.toThrow();
  });
});

describe('PushToggle', () => {
  it('renders nothing when push is disabled on the server', async () => {
    const { container } = render(<PushToggle />);
    // Default handler returns enabled:false.
    await waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders nothing without browser push support (jsdom)', async () => {
    server.use(
      http.get('*/api/push/config', () => HttpResponse.json({ enabled: true, publicKey: 'AQID' })),
    );
    const { container } = render(<PushToggle />);
    // jsdom has no PushManager, so the toggle stays hidden even when enabled.
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
