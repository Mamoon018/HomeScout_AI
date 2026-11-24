# React + TypeScript + Vite

## Mock mode (UI work without the backend)

In a dev build, mock mode answers every backend call (`/api/*`, `/auth/refresh`) in the browser
from `src/mocks/`. You don't need to sign in or run a backend. Production builds never contain
it: `npm run build` fails with `mock_leaked_to_prod` if mock code reaches `dist/`.

1. Put `VITE_USE_MOCK_API=true` in `frontend/.env.local`, then run `npm run dev`. A
   "MOCK DATA" badge shows on every page.
2. Pick a UI state when the page loads with `?mock=<scenario>`, for example
   `https://localhost:5173/home?mock=error`:

   | Scenario | What the pages do |
   |---|---|
   | `happy` (default) | R1 is running, then asks a question, then shows the plan. R2 and R3 run for a few polls, then finish. |
   | `running` | Every run stays running. |
   | `paused` | R1 waits on its clarification question. R2 and R3 stay running. |
   | `error` | Runs fail with Retry offered, and finish after the retry. |
   | `not-found` | Status reads answer 404. |
   | `empty` | R2 and R3 finish with no places or results. |
   | `slow` | R1 calls take 100 s. R2 passes its 120 s "still going" notice, and R3 its 4 min notice. |
   | `unauthenticated` | Calls answer 401, so the app redirects to `/auth/login`. |

3. Every run has a fixed ID, one per scenario and stage: `mock_<scenario>_r1`, `_r2` and
   `_r3`. Pages that take a run in the URL can be opened directly, for example
   `/proximity_info?run=mock_happy_r2` or `/places_metrics?run=mock_error_r3`.
4. The scenario is chosen once per page load. A run ID keeps its scenario after the app rewrites
   the URL. A reload shows each run's end state.

The responses come from `src/mocks/fixtures/`. The tests use the same fixtures, and a contract
test (`src/test/mock-backend/`) checks that they still parse. Switching the flag clears this
tab's saved runs, so mock IDs never reach the real backend.

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])

```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])

```
