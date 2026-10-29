import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const backend = env.DEV_BACKEND_URL || 'http://127.0.0.1:18080';
  return {plugins:[react()],server:{proxy:{'/api':backend,'/admin':backend,'/static':backend}}};
});
