import '@testing-library/jest-dom/vitest';
import { afterAll, afterEach, beforeAll } from 'vitest';
import { server } from './mocks/server';

// Node 26 exposes an experimental global localStorage that is undefined unless
// a file flag is supplied, which can shadow the DOM environment's storage. Use
// a deterministic per-worker implementation so tests behave like supported
// Node 24 and do not share persistence across Vitest workers.
class MemoryStorage implements Storage {
  private values = new Map<string, string>();
  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, String(value)); }
}
const testStorage = new MemoryStorage();
Object.defineProperty(window, 'localStorage', { configurable: true, value: testStorage });
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: testStorage });

// jsdom doesn't implement matchMedia; provide a minimal (light-preference) stub.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});
afterAll(() => server.close());
