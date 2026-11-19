<template>
	<!-- frappe-ui charts draw their title, legend and states and fill the box they are given;
	     the page supplies that box (Charts > Dashboard). This is the box: a ChartCard of a fixed
	     height, plus the dashboard's own empty placeholder for every chart. -->
	<ChartCard class="min-w-0" :class="cardClass" :style="{ height }">
		<component :is="chart" v-bind="$attrs">
			<template #empty>
				<ChartEmpty :kind="emptyKind" :message="emptyMessage" />
			</template>
			<template v-if="$slots.actions" #actions>
				<slot name="actions" />
			</template>
		</component>
	</ChartCard>
</template>

<script setup>
import { ChartCard } from "frappe-ui/charts";
import ChartEmpty from "./ChartEmpty.vue";

// Everything else (data, x, y, title, @select …) goes to the chart itself.
defineOptions({ inheritAttrs: false });

defineProps({
	chart: { type: Object, required: true },
	height: { type: String, default: "340px" },
	cardClass: { type: [String, Array, Object], default: "" },
	emptyKind: { type: String, default: "bars" },
	emptyMessage: { type: String, default: "No data for this selection" },
});
</script>
