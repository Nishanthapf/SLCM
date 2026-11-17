// Builds the frappe-ui apps of slcm (see README.md).
//
// Every app is one entry below. Output goes to slcm/public/frontend/ with
// hashed file names and one manifest.json; the server looks the current file
// names up by entry (slcm/utils/vite_assets.py). Code both apps use (vue,
// frappe-ui) lands in shared chunks.
//
// Runs as part of `bench build --app slcm` through the root package.json.

import path from "node:path";
import { fileURLToPath } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

const root = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(root, "../slcm/public/frontend");

// name -> entry file. The manifest key is the path relative to frontend/.
const entries = {
	admission_dashboard: "src/admission_dashboard/main.js", // desk page /app/admission-dashboard
	login: "src/login/main.js", // web page /login (slcm/www/login.py)
};

export default defineConfig(({ mode }) => ({
	plugins: [vue()],
	base: "/assets/slcm/frontend/",
	resolve: {
		alias: { "@": path.resolve(root, "src") },
	},
	define: {
		"process.env.NODE_ENV": JSON.stringify(mode === "development" ? "development" : "production"),
	},
	build: {
		outDir,
		emptyOutDir: true,
		manifest: "manifest.json",
		sourcemap: mode === "development",
		chunkSizeWarningLimit: 1500,
		rollupOptions: {
			input: Object.fromEntries(
				Object.entries(entries).map(([name, file]) => [name, path.resolve(root, file)])
			),
			// Keep `mount` exported: the desk page imports the entry and calls it.
			preserveEntrySignatures: "exports-only",
			output: { chunkFileNames: "assets/shared-[hash].js" },
		},
	},
}));
