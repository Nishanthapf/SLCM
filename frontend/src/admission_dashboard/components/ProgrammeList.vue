<template>
	<section class="relative mt-6">
		<!-- Domestic / International -->
		<div class="inline-flex gap-1 rounded-lg bg-surface-gray-2 p-1">
			<Button
				v-for="t in types"
				:key="t.value"
				size="lg"
				:icon-left="t.icon"
				:label="t.label"
				:variant="applicantType === t.value ? 'solid' : 'ghost'"
				class="min-w-[180px] !text-base"
				:class="
					applicantType === t.value
						? '!bg-[var(--adm-brand)] !text-white hover:!bg-[var(--adm-brand-hover)]'
						: '!text-ink-gray-8'
				"
				@click="emit('update:applicantType', t.value)"
			/>
		</div>

		<h2
			class="mb-4 mt-7 text-2xl font-semibold text-[var(--adm-brand)]"
			style="font-family: var(--adm-serif)"
		>
			Select a Programme
		</h2>

		<div v-if="programmes.loading && !programmes.data" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
			<div v-for="i in 6" :key="i" class="h-[88px] animate-pulse rounded-xl bg-surface-gray-2" />
		</div>

		<ErrorMessage v-else-if="programmes.error" :message="programmes.error" />

		<div
			v-else-if="!programmes.data?.length"
			class="rounded-xl border border-dashed border-outline-gray-2 p-10 text-center text-base text-ink-gray-5"
		>
			No {{ applicantType.toLowerCase() }} programmes are open in the admission cycle for
			{{ academicYear || "this year" }}.
		</div>

		<div v-else class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
			<button
				v-for="p in programmes.data"
				:key="p.name"
				type="button"
				class="group flex items-center gap-4 rounded-xl border border-outline-gray-2 bg-surface-white px-5 py-4 text-left shadow-sm transition hover:border-[var(--adm-brand)] hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--adm-brand)]"
				@click="emit('select', p)"
			>
				<span
					class="flex size-14 shrink-0 items-center justify-center rounded-xl bg-[var(--adm-brand-soft)] text-[var(--adm-brand)]"
				>
					<span :class="levelIcon(p.level_key)" class="size-7" />
				</span>
				<span class="min-w-0 flex-1">
					<span
						class="block truncate text-xl font-semibold text-[var(--adm-brand)]"
						style="font-family: var(--adm-serif)"
					>
						{{ p.label }}
					</span>
					<span class="mt-1 block text-base text-ink-gray-6">{{ p.level_label }}</span>
				</span>
				<span
					class="lucide-chevron-right size-5 shrink-0 text-[var(--adm-brand)] transition group-hover:translate-x-0.5"
				/>
			</button>
		</div>
	</section>
</template>

<script setup>
import { watch } from "vue";
import { Button, ErrorMessage, createResource } from "frappe-ui";

const props = defineProps({
	api: { type: String, required: true },
	academicYear: { type: String, default: null },
	applicantType: { type: String, required: true },
});
const emit = defineEmits(["select", "update:applicantType"]);

const types = [
	{ value: "Domestic", label: "Domestic", icon: "lucide-users" },
	{ value: "International", label: "International", icon: "lucide-globe" },
];

const programmes = createResource({
	url: `${props.api}.get_programmes`,
	makeParams: () => ({
		academic_year: props.academicYear,
		applicant_type: props.applicantType,
	}),
	auto: true,
});

watch(
	() => [props.academicYear, props.applicantType],
	() => programmes.reload()
);

function levelIcon(levelKey) {
	return {
		undergraduate: "lucide-graduation-cap",
		postgraduate: "lucide-book-open",
		research: "lucide-microscope",
	}[levelKey] || "lucide-school";
}
</script>
