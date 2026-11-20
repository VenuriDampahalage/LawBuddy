import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The backend's address is not set here: it comes from VITE_API_URL in frontend/.env
// (see src/lib/api.ts), the same way locally and when deployed.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
  },
})
