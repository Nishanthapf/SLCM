<template>
	<div
		class="flex items-center gap-4 rounded-xl border border-outline-gray-2 bg-surface-white px-5 py-4 shadow-sm"
	>
		<span class="flex size-14 shrink-0 items-center justify-center rounded-xl" :class="tone.bg">
			<span class="size-7" :class="[tone.icon, tone.ink]" />
		</span>
		<NumberCard
			class="min-w-0 flex-1"
			:card="false"
			:title="title"
			:value="value"
			:color="tone.chart"
			:loading="loading"
		/>
	</div>
</template>

<script setup>
import { computed } from "vue";
import { NumberCard } from "frappe-ui/charts";
import { toneFor } from "../cards";

const props = defineProps({
	cardKey: { type: String, required: true },
	title: { type: String, required: true },
	value: { type: Number, default: 0 },
	loading: { type: Boolean, default: false },
});

const tone = computed(() => toneFor(props.cardKey));
</script>
