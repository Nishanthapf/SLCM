<template>
	<!-- The app's own empty state (frappe-ui "Replacing a state"): a still, grey outline of
	     the chart that would be here, with a short note. Shape follows the chart kind. -->
	<div class="relative flex h-full w-full flex-col items-center justify-end gap-2" role="status">
		<div v-if="kind === 'ring'" class="flex flex-1 items-center justify-center">
			<div class="size-36 rounded-full border-[18px] border-surface-gray-2" />
		</div>
		<div v-else-if="kind === 'strip'" class="flex w-full flex-1 items-center">
			<div class="h-7 w-full rounded-md bg-surface-gray-2" />
		</div>
		<div v-else-if="kind === 'rows'" class="flex w-full flex-1 flex-col justify-center gap-2.5">
			<div
				v-for="(w, i) in [92, 74, 60, 48, 36, 24]"
				:key="i"
				class="h-5 rounded-md bg-surface-gray-2"
				:style="{ width: `${w}%` }"
			/>
		</div>
		<div v-else class="flex h-full w-full flex-1 items-end gap-3">
			<div
				v-for="(h, i) in [46, 68, 52, 84, 38, 60, 30]"
				:key="i"
				class="flex-1 rounded-t-md bg-surface-gray-2"
				:style="{ height: `${h}%` }"
			/>
		</div>
		<span class="text-p-sm text-ink-gray-5">{{ message }}</span>
	</div>
</template>

<script setup>
defineProps({
	// bars (axis charts, funnel) | rows (horizontal bars) | ring (donut) | strip (percentage bar)
	kind: { type: String, default: "bars" },
	message: { type: String, default: "No data for this selection" },
});
</script>
