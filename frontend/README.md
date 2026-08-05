# RepoPilot frontend

Vue 3, TypeScript, Pinia, Axios, and Vite provide the RepoPilot control-plane UI.

```powershell
npm install
npm run dev
```

Set `VITE_API_BASE_URL` to the FastAPI origin when it differs from the frontend origin. `npm run build` runs Vue TypeScript checking before producing the Vite bundle.

Realtime Preview Lab Phase 1 is a configuration workflow only. It analyzes and approves runtime manifests but does not execute repositories. Future mobile/tablet choices will be labelled as Playwright **emulated profiles**, not physical devices.
