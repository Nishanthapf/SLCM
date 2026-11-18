const numberFormat = new Intl.NumberFormat("en-IN");

export function formatNumber(value) {
	return numberFormat.format(value || 0);
}

/** ₹ with lakh / crore shortening: ₹4,000 · ₹1.12 L · ₹2.4 Cr */
export function formatINR(value) {
	const v = Number(value) || 0;
	const trim = (s) => s.replace(/\.?0+$/, "");
	if (Math.abs(v) >= 1e7) return `₹${trim((v / 1e7).toFixed(2))} Cr`;
	if (Math.abs(v) >= 1e5) return `₹${trim((v / 1e5).toFixed(2))} L`;
	return `₹${numberFormat.format(Math.round(v))}`;
}

export function percent(part, whole) {
	if (!whole) return 0;
	return Math.round((part / whole) * 1000) / 10;
}

export function formatDate(iso) {
	if (!iso) return "";
	return new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export function addDays(iso, days) {
	const d = new Date(`${iso}T00:00:00Z`);
	d.setUTCDate(d.getUTCDate() + days);
	return d.toISOString().slice(0, 10);
}
