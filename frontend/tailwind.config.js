import frappeUIPreset from "frappe-ui/tailwind";

const frappeUI = "./node_modules/frappe-ui/src";

/** @type {import('tailwindcss').Config} */
export default {
	presets: [frappeUIPreset],
	content: [
		"./src/**/*.{vue,js,ts}",
		`${frappeUI}/components/**/*.{vue,js,ts}`,
		`${frappeUI}/charts/**/*.{vue,js,ts}`,
		`${frappeUI}/composables/**/*.{vue,js,ts}`,
		`${frappeUI}/utils/**/*.{vue,js,ts}`,
	],
	// The app is mounted inside desk. Utilities only apply under `.slcm-fui`
	// (the page root and the overlay portal), and win over desk's own rules.
	// Base/preflight rules are scoped by ./postcss-scope.js.
	important: ".slcm-fui",
	// Desk (Bootstrap) has its own `.container`.
	corePlugins: { container: false },
};
