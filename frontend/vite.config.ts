// vite.config.ts
import path from "path"; // 1. Import the 'path' module from Node.js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { // 2. Add the 'resolve' section
    alias: {
      // 3. Define the '@' alias to point to the 'src' directory
      "@": path.resolve(__dirname, "./src"),
    },
  },
});