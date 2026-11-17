<template>
	<Dialog v-model:open="isOpen" title="Dashboard Settings" size="xl">
		<div class="-mt-2">
			<TabButtons v-model="tab" :options="tabs" />
			<p class="mt-4 text-p-base text-ink-gray-6">
				{{
					tab === "cards"
						? "Show or hide number cards on the admission dashboard. Drag to reorder."
						: "Show or hide charts on the admission dashboard. Drag to reorder."
				}}
				These settings apply to everyone.
			</p>

			<ul class="mt-3 max-h-[50vh] overflow-y-auto rounded-lg border border-outline-gray-2">
				<li
					v-for="(item, index) in items"
					:key="item.key"
					draggable="true"
					class="flex items-center gap-3 border-b border-outline-gray-1 px-3 py-2 last:border-b-0"
					:class="{
						'bg-surface-gray-2': dragOver === index,
						'opacity-50': dragFrom === index,
					}"
					@dragstart="onDragStart(index, $event)"
					@dragover.prevent="dragOver = index"
					@dragleave="dragOver = null"
					@drop.prevent="onDrop(index)"
					@dragend="dragFrom = dragOver = null"
				>
					<span class="lucide-grip-vertical size-4 shrink-0 cursor-grab text-ink-gray-4" />
					<span class="flex-1 truncate text-base text-ink-gray-8">{{ item.label }}</span>
					<Switch v-model="item.enabled" :aria-label="`Show ${item.label}`" />
				</li>
			</ul>
		</div>

		<template #actions>
			<div class="flex items-center gap-2">
				<Button label="Reset to Default" variant="outline" :loading="reset.loading" @click="reset.submit()" />
				<div class="flex-1" />
				<Button label="Cancel" variant="outline" @click="isOpen = false" />
				<Button
					label="Save"
					variant="solid"
					class="!bg-[var(--adm-brand)] !text-white hover:!bg-[var(--adm-brand-hover)]"
					:loading="save.loading"
					@click="onSave"
				/>
			</div>
			<ErrorMessage class="mt-2" :message="save.error || reset.error" />
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { Button, Dialog, ErrorMessage, Switch, TabButtons, createResource } from "frappe-ui";

const props = defineProps({
	api: { type: String, required: true },
	settings: { type: Object, required: true },
	open: { type: Boolean, default: false },
});
const emit = defineEmits(["update:open", "saved"]);

const isOpen = computed({
	get: () => props.open,
	set: (v) => emit("update:open", v),
});

const tabs = [
	{ label: "Number Cards", value: "cards" },
	{ label: "Charts", value: "charts" },
];
const tab = ref("cards");

// Edit a copy; nothing changes on the dashboard until Save.
const draft = ref(clone(props.settings));
watch(isOpen, (open) => {
	if (open) {
		draft.value = clone(props.settings);
		tab.value = "cards";
	}
});

const items = computed(() => draft.value[tab.value]);

function clone(settings) {
	return {
		cards: settings.cards.map((c) => ({ ...c, enabled: !!c.enabled })),
		charts: settings.charts.map((c) => ({ ...c, enabled: !!c.enabled })),
	};
}

// Drag to reorder (native HTML5 drag and drop).
const dragFrom = ref(null);
const dragOver = ref(null);

function onDragStart(index, event) {
	dragFrom.value = index;
	event.dataTransfer.effectAllowed = "move";
}

function onDrop(index) {
	const from = dragFrom.value;
	dragFrom.value = dragOver.value = null;
	if (from === null || from === index) return;
	const list = draft.value[tab.value];
	const [moved] = list.splice(from, 1);
	list.splice(index, 0, moved);
}

const save = createResource({
	url: `${props.api}.save_settings`,
	onSuccess(data) {
		emit("saved", data);
		isOpen.value = false;
	},
});

function onSave() {
	const strip = (list) => list.map(({ key, enabled }) => ({ key, enabled: enabled ? 1 : 0 }));
	save.submit({
		layout: JSON.stringify({ cards: strip(draft.value.cards), charts: strip(draft.value.charts) }),
	});
}

const reset = createResource({
	url: `${props.api}.reset_settings`,
	onSuccess(data) {
		draft.value = clone(data);
		emit("saved", data);
	},
});
</script>
