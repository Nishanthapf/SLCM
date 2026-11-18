<template>
	<div class="relative mx-auto max-w-[1400px] px-5 pb-10 pt-5 sm:px-8">
		<BuildingArt v-if="!programmes" class="pointer-events-none absolute right-8 top-16 h-28 w-60 max-lg:!hidden" />

		<!-- Sidebar toggle and breadcrumbs -->
		<nav class="relative flex h-8 items-center gap-1.5">
			<Button
				v-if="hasDeskSidebar"
				variant="ghost"
				:icon="sidebarOpen ? 'lucide-panel-left-close' : 'lucide-panel-left-open'"
				:aria-label="sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'"
				:title="sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'"
				@click="toggleSidebar"
			/>
			<span v-if="hasDeskSidebar" class="mx-1 h-4 w-px bg-outline-gray-2" />
			<a
				href="/desk"
				class="flex size-7 items-center justify-center rounded-md text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8"
				aria-label="Home"
				title="Home"
				@click="goHome"
			>
				<span class="lucide-house size-4" />
			</a>
			<span class="text-ink-gray-4" aria-hidden="true">/</span>
			<Breadcrumbs :items="breadcrumbs" />
		</nav>

		<!-- Header: title, Admission Cycle, Settings -->
		<header class="relative mt-3 flex flex-wrap items-center justify-between gap-4">
			<h1 class="min-w-0 truncate text-2xl-semibold text-ink-gray-9">
				{{ programmes ? `${overviewTitle} · Admission Overview` : "Admission Dashboard" }}
			</h1>

			<div class="flex flex-wrap items-center gap-3">
				<span class="text-base-medium text-ink-gray-7">Admission Cycle</span>
				<Select v-model="cycle" class="w-72" :options="cycleOptions" placeholder="Select cycle" />
				<Button
					v-if="programmes && boot.can_edit_settings"
					label="Settings"
					icon-left="lucide-settings"
					variant="outline"
					@click="settingsOpen = true"
				/>
			</div>
		</header>

		<div
			v-if="!cycle"
			class="mt-8 rounded-xl border border-dashed border-outline-gray-2 p-10 text-center text-base text-ink-gray-5"
		>
			No Admission Cycle has been created yet.
		</div>

		<ProgrammeList
			v-else-if="!programmes"
			v-model:applicant-type="applicantType"
			v-model:range="range"
			v-model:selected="selected"
			:api="api"
			:cycle="cycle"
			:cycle-label="cycleLabel"
			:today="boot.today"
			@open="openProgrammes"
		/>
		<ProgrammeOverview
			v-else
			v-model:programmes="programmes"
			:api="api"
			:cycle="cycle"
			:cycle-info="cycleInfo"
			:applicant-type="applicantType"
			:all-programmes="openProgrammeList"
			:settings="settings"
			:today="boot.today"
		/>

		<SettingsDialog
			v-if="boot.can_edit_settings"
			v-model:open="settingsOpen"
			:api="api"
			:settings="settings"
			@saved="settings = $event"
		/>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { Breadcrumbs, Button, Select } from "frappe-ui";
import BuildingArt from "./components/BuildingArt.vue";
import ProgrammeList from "./components/ProgrammeList.vue";
import ProgrammeOverview from "./components/ProgrammeOverview.vue";
import SettingsDialog from "./components/SettingsDialog.vue";

const props = defineProps({
	api: { type: String, required: true },
	boot: { type: Object, required: true },
});

const cycle = ref(props.boot.cycles.default);
const applicantType = ref("Domestic");
const range = ref([]); // [] = entire cycle
const selected = ref([]); // programme names ticked on the list
const programmes = ref(null); // programmes open in the overview (null = list view)
const openProgrammeList = ref([]); // every programme of the current tab, for the overview chips
const settings = ref(props.boot.settings);
const settingsOpen = ref(false);

const cycleInfo = computed(() => props.boot.cycles.options.find((c) => c.value === cycle.value) || {});
const cycleLabel = computed(() => cycleInfo.value.label || cycle.value);
const cycleOptions = computed(() =>
	props.boot.cycles.options.map((c) => ({
		value: c.value,
		label: [c.label, c.academic_year, c.status === "Active" ? "Active" : null].filter(Boolean).join(" · "),
	}))
);

const overviewTitle = computed(() => {
	const list = programmes.value || [];
	if (list.length === 1) return list[0].label;
	if (list.length === 2) return `${list[0].label} + ${list[1].label}`;
	return `${list.length} programmes`;
});

// ---- breadcrumbs: (home icon) / Admission Dashboard / <programme(s)>
// A plain click routes inside desk; a ctrl/cmd/middle click opens /desk the usual way.
function goHome(e) {
	if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0 || !window.frappe?.router) return;
	e.preventDefault();
	window.frappe.router.push_state("/desk");
}
const breadcrumbs = computed(() => {
	const items = [{ label: "Admission Dashboard", onClick: programmes.value ? backToList : undefined }];
	if (programmes.value) items.push({ label: overviewTitle.value });
	return items;
});

// ---- desk sidebar: the page folds it on open (see admission_dashboard.js); this button brings it back.
const deskSidebar = () => window.frappe?.app?.sidebar;
const hasDeskSidebar = Boolean(deskSidebar());
const sidebarOpen = ref(Boolean(deskSidebar()?.sidebar_expanded));
// Opens/closes the sidebar on screen only. Desk's own toggle_width() would also save it as
// the setting for every page, and the sidebar is meant to be folded on this page alone.
function toggleSidebar() {
	const sidebar = deskSidebar();
	if (!sidebar?.apply_expanded_state) return;
	sidebar.sidebar_expanded = !sidebar.sidebar_expanded;
	sidebar.apply_expanded_state();
	if (sidebar.sidebar_expanded) sidebar.highlight_active_item?.();
	sidebarOpen.value = Boolean(sidebar.sidebar_expanded);
}
// The rail's own edge/arrow can open it too; keep the icon honest.
const sync = () => (sidebarOpen.value = Boolean(deskSidebar()?.sidebar_expanded));
document.addEventListener("click", () => setTimeout(sync, 0), true);

function openProgrammes({ open, all }) {
	openProgrammeList.value = all;
	programmes.value = open;
}

function backToList() {
	// Coming back from a combined view keeps those programmes ticked.
	if (programmes.value?.length > 1) selected.value = programmes.value.map((p) => p.name);
	programmes.value = null;
}

// Another cycle has its own programmes and dates: start over on the list.
watch(cycle, () => {
	programmes.value = null;
	selected.value = [];
	range.value = [];
});
</script>
