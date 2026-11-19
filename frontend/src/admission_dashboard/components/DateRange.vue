<template>
	<!-- An empty range means "Entire cycle". Future dates can't be picked. -->
	<DateRangePicker
		:model-value="modelValue"
		class="w-64"
		dual-pane
		:max="today"
		:typeable="false"
		placeholder="Entire cycle"
		align="end"
		@update:model-value="emit('update:modelValue', $event || [])"
	>
		<template #prefix>
			<span class="lucide-calendar size-4 text-ink-gray-5" />
		</template>
		<template #actions="{ setRange, clear, close }">
			<div class="flex min-w-[132px] flex-col gap-0.5 border-r border-outline-gray-1 p-2">
				<button
					v-for="preset in presets"
					:key="preset.label"
					type="button"
					class="rounded-md px-2.5 py-1.5 text-left text-base text-ink-gray-8 hover:bg-surface-gray-2"
					:class="isActive(preset) && 'bg-surface-gray-2 font-medium'"
					@click="apply(preset, setRange, clear, close)"
				>
					{{ preset.label }}
				</button>
			</div>
		</template>
	</DateRangePicker>
</template>

<script setup>
import { DateRangePicker } from "frappe-ui";
import { addDays } from "../format";

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	today: { type: String, required: true },
});
const emit = defineEmits(["update:modelValue"]);

const presets = [
	{ label: "Entire cycle", days: null },
	{ label: "Today", days: 1 },
	{ label: "Last 7 days", days: 7 },
	{ label: "Last 30 days", days: 30 },
];

function rangeFor(preset) {
	return preset.days ? [addDays(props.today, 1 - preset.days), props.today] : [];
}

function isActive(preset) {
	const r = rangeFor(preset);
	const v = props.modelValue || [];
	return r.length === v.length && r.every((d, i) => d === v[i]);
}

function apply(preset, setRange, clear, close) {
	const r = rangeFor(preset);
	if (r.length) setRange(r);
	else clear();
	emit("update:modelValue", r);
	close();
}
</script>
