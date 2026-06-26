import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { registerServiceWorker } from './pwa';
import { applyTheme, getStoredTheme } from './theme';
import './styles/theme.css';
import './styles/app.css';

// Resolve the saved theme onto <html> before first paint to limit any flash.
applyTheme(getStoredTheme());

// Register the offline/push service worker (production only).
registerServiceWorker();

const root = document.getElementById('root');
if (!root) throw new Error('Root element #root not found');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
