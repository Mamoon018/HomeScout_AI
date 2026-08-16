* **Where each piece of code belongs based on its responsibility**
  
  ***Definition:*** Every piece of code should be placed according to what it is responsible for doing, rather than simply placing related code together.
  
  **Goal:** Keep responsibilities separated so the purpose and location of every piece of code is predictable.

* **UI/components → `components/`**
  
  ***Definition:*** Contains reusable React components responsible for displaying UI and handling direct user interaction.
  
    **Goal:** Keep presentation and UI interaction separate from business logic, API communication, and infrastructure.

* *Feature behavior/business logic → `features/<feature>/`*
  
  ***Definition:*** Contains logic that represents what a specific application feature does, such as authentication, dashboard operations, payments, etc.
    
    **Goal:** Keep feature-specific behavior together while preventing it from being mixed with generic UI or infrastructure code.

* **API calls → `features/<feature>/api/`**
  
  ***Definition:*** Contains functions responsible for communicating with backend endpoints and handling the API request/response boundary.
  
    **Goal:** Keep network communication separate from UI and feature behavior so API implementation can change without affecting components.

* **React hooks/event-driven state/behavior → `features/<feature>/hooks/`**
  
  ***Definition:*** Contains React hooks that manage feature-specific state, lifecycle behavior, and actions triggered by user interaction or application events.
  
    **Goal:** Keep React-specific state and behavior outside UI components so components remain focused on rendering.

* **Feature-specific helpers → `features/<feature>/utils/`**
  
  ***Definition:*** Contains small, reusable functions that process, validate, transform, or calculate data specifically for that feature.
  
    **Goal:** Prevent repeated helper logic and keep small operations separate from larger feature functions.

* **Shared infrastructure → `lib/`**
  
  ***Definition:*** Contains technical infrastructure that is not specific to one feature and can be used by multiple parts of the application, such as Supabase clients, API clients, configuration, or session management.
  
    **Goal:** Centralize shared technical functionality instead of duplicating it across features.

* **Pages/final composition → `pages/`**
  
  ***Definition:*** Contains the actual pages/screens that bring together components, hooks, and feature functionality to produce a complete webpage.
  
    **Goal:** Make the page responsible primarily for **composition**, rather than containing the implementation of every piece of functionality.

* **Routing → `routes/`**
  
  ***Definition:*** Contains the application's route definitions and 
  determines which page/component is associated with each URL.
  
    **Goal:** Keep navigation and URL mapping separate from the implementation of the pages themselves.

* **Assets → `assets/`**
  
  ***Definition:*** Contains static resources used by the application, such as images, icons, fonts, and other files required by the UI.
  
    **Goal:** Keep application code separate from the resources it consumes.

### Key rules to apply while writing the code
1. **Responsibility rule** — Every file must have one primary responsibility.
2. **Placement rule** — Before creating code, determine which folder owns that responsibility.
3. **No duplication rule** — Do not duplicate logic across components, hooks, utils, or API files.
4. **UI rule** — Components should primarily handle rendering and user interaction, not API calls or business logic.
5. **API rule** — API files contain request/response communication only; they should not contain UI logic.
6. **Hook rule** — Hooks coordinate React state and feature behavior; they should not contain reusable UI.
7. **Utility rule** — Utils should contain small, reusable, feature-specific functions and should not manage React state.
8. **Composition rule** — Pages should compose components, hooks, and feature functions rather than implementing their internal logic.
9. **Shared-code rule** — If code is genuinely shared across multiple features, place it in `lib/`; otherwise keep it inside the relevant feature.
10. **Comments rule** -- Make sure your provide the comments in code that helps understand what is happening in the code. It should not be very detailed, just describe the purpose and desired outcome from the unit function.
11. **Naming rule** — File and function names should clearly describe their responsibility.
12. **Creation rule** — Do not create folders/files merely to follow the structure. Create `api`, `hooks`, `utils`, etc. only when that feature actually needs them.
13. **Reuse rule** — Before creating a new component/helper/function, check whether an existing one can be reused.
14. **Data-flow rule** — Explicitly define where data originates, where it is transformed, and which component ultimately consumes it. Data path — Document the flow explicitly: For example, User input → LoginForm.jsx → useAuth.js → authApi.js → Backend → authApi.js → useAuth.js → LoginForm.jsx
15. **Final-composition rule** — The page should make the overall feature flow easy to understand by reading it, without needing to inspect every implementation detail.
16. **Validation rule** — After implementation, verify that no API calls, business logic, helper functions, or state-management logic have been placed in the wrong layer.


### Key Instructions to Manage Code effectively in Vite Folder
1. Keep imports explicit and file-level, one component per file, since the browser's native ESM loader resolves each import as a separate request. of per-file, on-demand transform.

2. Avoid importing large libraries in full when only part is used (e.g. import a single function instead of the whole package).

3. Let the Dependency Pre-Bundler run without interference, don't manually alter node_modules output or bypass its cache, since it only reruns when dependencies change. Frequent unnecessary changes to package.json trigger unneeded re-bundling.

4. Keep components structured so state doesn't depend on file-level side effects that break on partial reload, since HMR swaps only the changed module and expects the rest of the app state to remain valid.

5. Avoid deeply circular imports between components, since the browser's loader resolves the import graph itself, and circular references add resolution overhead there instead of during a pre-computed bundler step.

**A particularly useful instruction:**
> **Before writing each piece of code, identify its responsibility and place it in the corresponding layer. Do not decide the file location based on convenience; decide it based on responsibility.**
