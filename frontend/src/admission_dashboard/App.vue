<template>
	<div class="relative mx-auto max-w-[1400px] px-5 pb-10 pt-5 sm:px-8">
		<BuildingArt class="pointer-events-none absolute right-6 top-14 h-28 w-60 max-lg:!hidden" />

		<!-- Header: title (list view only), Academic Year, Settings -->
		<header class="relative flex flex-wrap items-start justify-between gap-4">
			<h1
				v-if="!programme"
				class="text-[32px] font-bold leading-tight text-[var(--adm-brand)]"
				style="font-family: var(--adm-serif)"
			>
				Admission Dashboard
			</h1>
			<button
				v-else
				type="button"
				class="inline-flex items-center gap-1.5 text-base font-semibold text-[var(--adm-brand)] hover:underline"
				style="font-family: var(--adm-serif)"
				@click="programme = null"
			>
				<span class="lucide-arrow-left size-4" />
				All Programmes
			</button>

			<div class="flex items-center gap-3">
				<span class="text-base font-semibold text-ink-gray-8">Academic Year</span>
				<Select
					v-model="academicYear"
					class="w-48"
					:options="yearOptions"
					placeholder="Select year"
				/>
				<Button
					v-if="boot.can_edit_settings"
					label="Settings"
					icon-left="lucide-settings"
					variant="outline"
					@click="settingsOpen = true"
				/>
			</div>
		</header>

		<ProgrammeList
			v-if="!programme"
			v-model:applicant-type="applicantType"
			:api="api"
			:academic-year="academicYear"
			@select="programme = $event"
		/>
		<ProgrammeOverview
			v-else
			:api="api"
			:programme="programme"
			:academic-year="academicYear"
			:applicant-type="applicantType"
			:settings="settings"
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
import { Button, Select } from "frappe-ui";
import BuildingArt from "./components/BuildingArt.vue";
import ProgrammeList from "./components/ProgrammeList.vue";
import ProgrammeOverview from "./components/ProgrammeOverview.vue";
import SettingsDialog from "./components/SettingsDialog.vue";

const props = defineProps({
	api: { type: String, required: true },
	boot: { type: Object, required: true },
});

const academicYear = ref(props.boot.academic_years.default);
const applicantType = ref("Domestic");
const programme = ref(null);
const settings = ref(props.boot.settings);
const settingsOpen = ref(false);

const yearOptions = computed(() =>
	props.boot.academic_years.options.map((y) => ({ label: y, value: y }))
);

// A different year can have a different set of programmes: go back to the list.
watch(academicYear, () => (programme.value = null));
</script>
