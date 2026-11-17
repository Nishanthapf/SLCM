// Look of each number card and donut slice, decided from the Applicant Status name.
// Icons are frappe-ui class icons (`lucide-*`); keep them as literal strings so
// Tailwind's content scan emits them.

const TONES = {
	brand: { icon: "lucide-users", ink: "text-[var(--adm-brand)]", bg: "bg-[var(--adm-brand-soft)]", chart: "#8a1c2b" },
	gray: { icon: "lucide-file-text", ink: "text-ink-gray-7", bg: "bg-surface-gray-2", chart: "#7c7c7c" },
	blue: { icon: "lucide-file-check", ink: "text-ink-blue-6", bg: "bg-surface-blue-1", chart: "#2283c3" },
	green: { icon: "lucide-credit-card", ink: "text-ink-green-6", bg: "bg-surface-green-1", chart: "#289e60" },
	violet: { icon: "lucide-user-check", ink: "text-ink-violet-6", bg: "bg-surface-violet-1", chart: "#753cbb" },
	amber: { icon: "lucide-clock", ink: "text-ink-amber-6", bg: "bg-surface-amber-1", chart: "#e0a526" },
	red: { icon: "lucide-circle-x", ink: "text-ink-red-6", bg: "bg-surface-red-1", chart: "#c54b58" },
	teal: { icon: "lucide-circle-check", ink: "text-ink-teal-6", bg: "bg-surface-teal-1", chart: "#1f9aa5" },
};

// First match wins, so the more specific words come first.
const RULES = [
	[/reject|declin|expire|withdraw|cancel/i, "red"],
	[/paid|fee/i, "green"],
	[/draft/i, "gray"],
	[/waitlist|scheduled|sheduled|allocated|pending/i, "amber"],
	[/select|accept|offer|enrol|merit published/i, "violet"],
	[/complet|exempt|excempt/i, "teal"],
	[/submit/i, "blue"],
];

export function toneFor(key) {
	if (key === "total") return TONES.brand;
	const status = key.replace(/^status:/, "");
	const rule = RULES.find(([re]) => re.test(status));
	return TONES[rule ? rule[1] : "blue"];
}
