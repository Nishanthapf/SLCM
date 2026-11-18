<template>
	<!-- frappe-ui's NumberCard draws the card, the states and the type; this only makes it clickable.
	     `value: null` is the empty state ("—" and "No data"). -->
	<component
		:is="clickable ? 'button' : 'div'"
		:type="clickable ? 'button' : undefined"
		class="group block h-full min-h-[118px] w-full min-w-0 rounded-[10px] text-left transition"
		:class="[
			clickable && 'cursor-pointer hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-outline-gray-4',
			wide && 'sm:col-span-2',
		]"
		:title="clickable ? hint : undefined"
		@click="clickable && emit('open')"
	>
		<NumberCard
			class="h-full"
			:title="title"
			:value="value"
			:format="format"
			:color="valueColor"
			:delta-caption="value == null ? undefined : caption || undefined"
			:progress="value == null || progress == null ? undefined : { value: progress, color: progressColor }"
			:sparkline="value == null || !sparkline ? undefined : { data: sparkline }"
			:loading="loading"
		>
			<template v-if="clickable" #actions>
				<span class="lucide-arrow-up-right size-4 text-ink-gray-4 opacity-0 transition group-hover:opacity-100" />
			</template>
		</NumberCard>
	</component>
</template>

<script setup>
import { computed } from "vue";
import { NumberCard } from "frappe-ui/charts";

const props = defineProps({
	title: { type: String, required: true },
	value: { type: [Number, String], default: null },
	caption: { type: String, default: "" },
	format: { type: Function, default: undefined },
	progress: { type: Number, default: null },
	// "success" | "warning" | "danger": colours the progress bar, and the number for warning/danger.
	tone: { type: String, default: "" },
	sparkline: { type: Array, default: null },
	loading: { type: Boolean, default: false },
	clickable: { type: Boolean, default: true },
	hint: { type: String, default: "Open the matching list" },
	wide: { type: Boolean, default: false },
});
const emit = defineEmits(["open"]);

const TONES = { success: "var(--adm-success)", warning: "var(--adm-warning)", danger: "var(--adm-danger)" };
const progressColor = computed(() => TONES[props.tone]);
const valueColor = computed(() => (props.tone === "warning" || props.tone === "danger" ? TONES[props.tone] : undefined));
</script>
