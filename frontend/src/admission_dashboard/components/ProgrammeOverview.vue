<template>
	<section class="relative mt-4">
		<h1 class="text-[30px] font-bold leading-tight text-[var(--adm-brand)]" style="font-family: var(--adm-serif)">
			{{ programme.label }}
			<span class="text-2xl font-semibold">– Admission Overview</span>
		</h1>
		<div class="mt-2 flex flex-wrap gap-2">
			<Badge
				size="lg"
				:label="applicantType"
				class="!bg-[var(--adm-brand-soft)] !text-[var(--adm-brand)]"
			>
				<template #prefix>
					<span :class="applicantType === 'International' ? 'lucide-globe' : 'lucide-users'" class="size-3.5" />
				</template>
			</Badge>
			<Badge size="lg" theme="gray" :label="`Academic Year: ${academicYear}`" />
		</div>

		<ErrorMessage v-if="overview.error" class="mt-6" :message="overview.error" />

		<template v-else>
			<!-- Number cards (order and visibility from Dashboard Settings) -->
			<div v-if="cards.length" class="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
				<StatCard
					v-for="card in cards"
					:key="card.key"
					:card-key="card.key"
					:title="cardTitle(card)"
					:value="cardValue(card)"
					:loading="overview.loading && !overview.data"
				/>
			</div>

			<!-- Charts -->
			<div v-if="charts.length" class="mt-5 grid gap-4 lg:grid-cols-2">
				<template v-for="chart in charts" :key="chart.key">
					<div
						v-if="chart.key === 'status_donut'"
						class="rounded-xl border border-outline-gray-2 bg-surface-white p-5 shadow-sm"
					>
						<h3 class="mb-3 text-xl font-semibold text-[var(--adm-brand)]" style="font-family: var(--adm-serif)">
							{{ chart.label }}
						</h3>
						<div class="adm-donut flex flex-col items-center gap-6 sm:flex-row">
							<div class="h-56 w-56 shrink-0">
								<DonutChart
									:data="statusRows"
									category="status"
									value="count"
									center-label="Total"
									:colors="statusColors"
									:loading="overview.loading && !overview.data"
								/>
							</div>
							<table v-if="statusRows.length" class="w-full text-base">
								<tbody>
									<tr v-for="row in statusRows" :key="row.status">
										<td class="py-1.5 pr-3">
											<span class="inline-flex items-center gap-2 text-ink-gray-8">
												<span class="size-2.5 rounded-full" :style="{ background: statusColors[row.status] }" />
												{{ row.status }}
											</span>
										</td>
										<td class="py-1.5 pr-3 text-right font-medium tabular-nums text-ink-gray-8">
											{{ formatNumber(row.count) }}
										</td>
										<td class="py-1.5 text-right tabular-nums text-ink-gray-5">
											({{ percent(row.count) }})
										</td>
									</tr>
								</tbody>
							</table>
						</div>
					</div>

					<div
						v-else-if="chart.key === 'trend'"
						class="flex flex-col rounded-xl border border-outline-gray-2 bg-surface-white p-5 shadow-sm"
					>
						<h3 class="mb-3 text-xl font-semibold text-[var(--adm-brand)]" style="font-family: var(--adm-serif)">
							{{ chart.label }}
						</h3>
						<div class="h-64 min-h-0 flex-1">
							<AreaChart
								:data="trend"
								x="month"
								y="applications"
								:x-axis="{ type: 'category' }"
								:series-config="{ applications: { label: 'Applications', color: brandColor } }"
								:tooltip-columns="[{ name: 'new', label: 'New this month' }]"
								show-data-points
								:loading="overview.loading && !overview.data"
							/>
						</div>
					</div>
				</template>
			</div>
		</template>
	</section>
</template>

<script setup>
import { computed, watch } from "vue";
import { Badge, ErrorMessage, createResource } from "frappe-ui";
import { AreaChart, DonutChart } from "frappe-ui/charts";
import StatCard from "./StatCard.vue";
import { toneFor } from "../cards";

const props = defineProps({
	api: { type: String, required: true },
	programme: { type: Object, required: true },
	academicYear: { type: String, default: null },
	applicantType: { type: String, required: true },
	settings: { type: Object, required: true },
});

const brandColor = "#8a1c2b";

const overview = createResource({
	url: `${props.api}.get_programme_overview`,
	makeParams: () => ({
		academic_year: props.academicYear,
		program: props.programme.name,
		applicant_type: props.applicantType,
	}),
	auto: true,
});

watch(
	() => [props.academicYear, props.programme.name, props.applicantType],
	() => overview.reload()
);

const cards = computed(() => props.settings.cards.filter((c) => c.enabled));
const charts = computed(() => props.settings.charts.filter((c) => c.enabled));

const total = computed(() => overview.data?.total || 0);

function cardTitle(card) {
	if (card.key === "total") return card.label;
	// "Draft" -> "Draft Applications" reads like the mock-up; longer names stay as-is.
	return card.label.split(" ").length === 1 ? `${card.label} Applications` : card.label;
}

function cardValue(card) {
	if (card.key === "total") return total.value;
	return overview.data?.by_status?.[card.key.replace(/^status:/, "")] || 0;
}

const statusRows = computed(() =>
	Object.entries(overview.data?.by_status || {})
		.filter(([, count]) => count > 0)
		.sort((a, b) => b[1] - a[1])
		.map(([status, count]) => ({ status, count }))
);

const statusColors = computed(() =>
	Object.fromEntries(statusRows.value.map((r) => [r.status, toneFor(`status:${r.status}`).chart]))
);

const trend = computed(() =>
	(overview.data?.trend || []).map((row) => ({
		...row,
		month: new Date(row.month + "T00:00:00").toLocaleString(undefined, { month: "short", year: "2-digit" }),
	}))
);

const numberFormat = new Intl.NumberFormat("en-IN");
function formatNumber(n) {
	return numberFormat.format(n || 0);
}

function percent(count) {
	if (!total.value) return "0%";
	return `${((count / total.value) * 100).toFixed(1)}%`;
}
</script>

<style>
/* The table beside the ring already names every status with its count and share. */
.adm-donut [data-slot="chart-legend"] {
	display: none;
}
</style>
