import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';

export default [
  { ignores: ['dist', 'coverage', 'node_modules'] },
  js.configs.recommended,
  {
    // Build/test config files run in Node.
    files: ['*.config.{ts,js}'],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    // The service worker runs in the ServiceWorkerGlobalScope.
    files: ['public/sw.js'],
    languageOptions: { globals: { ...globals.browser, ...globals.serviceworker } },
    rules: { 'no-useless-assignment': 'off' },
  },
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: { ...globals.browser },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      // Babel's scope analyser treats type-only names as runtime references.
      // TypeScript enforces both checks via noUnused* and ordinary type checking.
      'no-undef': 'off',
      'no-unused-vars': 'off',
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
];
