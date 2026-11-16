// Builds the frappe-ui apps that are embedded in desk pages.
//
// Output goes to slcm/public/frontend/<app>/ with hashed file names and a
// manifest.json; the desk page asks the server for the current file names
// (see slcm/admission/page/admission_dashboard/admission_dashboard.py).
//
// Runs as part of `bench build --app slcm` through the root package.json.

import path from "node:path";
import { fileURLToPath } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

const root = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(root, "../slcm/public/frontend/admission_dashboard");

export default defineConfig(({ mode }) => ({
	plugins: [vue()],
	base: "/assets/slcm/frontend/admission_dashboard/",
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
			input: path.resolve(root, "src/admission_dashboard/main.js"),
			// Keep `mount` exported: the desk page imports the entry and calls it.
			preserveEntrySignatures: "exports-only",
		},
	},
}));
