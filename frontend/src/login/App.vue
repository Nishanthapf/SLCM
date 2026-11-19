<template>
	<div class="flex min-h-screen items-center justify-center px-4 py-4" style="font-family: var(--login-font)">
		<main
			class="w-full max-w-[500px] login-card px-6 py-6 sm:px-8"
		>
			<!-- Brand: logo + institution name (Student Portal Settings), left-aligned with the form, two lines -->
			<div class="mb-4 flex items-center gap-4">
				<img v-if="brand.logo" :src="brand.logo" :alt="brand.title" class="h-16 w-auto shrink-0 object-contain" />
				<span v-else class="lucide-graduation-cap size-12 shrink-0 text-[var(--login-brand)]" aria-hidden="true" />
				<!-- One line per span: the name breaks evenly at its middle -->
				<div class="min-w-0 text-[1.6rem] leading-tight text-[var(--login-brand)] max-sm:text-[1.3rem]">
					<span v-for="(line, i) in titleLines" :key="i" class="block whitespace-nowrap max-sm:whitespace-normal">{{
						line
					}}</span>
				</div>
			</div>

			<h1 class="text-center text-xl text-ink-gray-9">Sign in</h1>
			<p class="mb-4 mt-1 text-center text-sm text-ink-gray-6">{{ subtitles[tab] }}</p>

			<!-- Full width, lined up with the fields below; stacked on phones -->
			<TabButtons v-model="tab" :options="tabOptions" :vertical="narrow" fluid class="login-tabs mb-5 w-full" />

			<Alert
				v-if="pageError"
				class="mb-5"
				theme="red"
				title="Couldn't sign you in"
				:description="pageError"
				dismissible
				@dismiss="pageError = ''"
			/>

			<!-- Staff: password and/or Google -->
			<section v-if="tab === 'staff'">
				<PasswordSignIn
					v-if="tabs.staff.password"
					tab="staff"
					:redirect-to="redirectTo"
					@wrong-tab="moveToTab"
				/>
				<Divider v-if="tabs.staff.password && tabs.staff.google" />
				<GoogleButton v-if="tabs.staff.google" tab="staff" :redirect-to="redirectTo" />
				<Alert
					v-if="!tabs.staff.password && !tabs.staff.google"
					theme="amber"
					title="Not available"
					description="Staff sign-in is not available right now. Please contact the IT office."
				/>
			</section>

			<!-- Faculty & Student: Google only -->
			<section v-else-if="tab === 'faculty-student'" class="space-y-4">
				<template v-if="tabs['faculty-student'].google">
					<p class="text-center text-sm text-ink-gray-7">
						Please sign in with your institutional Google account<span v-if="domains">
							(<b class="font-semibold">{{ domains }}</b>)</span
						>.
					</p>
					<GoogleButton tab="faculty-student" :redirect-to="redirectTo" />
					<Alert v-if="partlyDisabled" theme="amber" title="Please note" :description="partlyDisabled" />
				</template>
				<Alert
					v-else
					theme="amber"
					title="Sign-in disabled"
					description="Faculty and student sign-in is currently disabled. Please contact the administration office if you need access."
				/>
			</section>

			<!-- Parent & Guardian: password and/or Google -->
			<section v-else>
				<PasswordSignIn
					v-if="tabs.parent.password"
					tab="parent"
					:redirect-to="redirectTo"
					@wrong-tab="moveToTab"
				/>
				<Divider v-if="tabs.parent.password && tabs.parent.google" />
				<GoogleButton v-if="tabs.parent.google" tab="parent" :redirect-to="redirectTo" />
				<Alert
					v-if="!tabs.parent.password && !tabs.parent.google"
					theme="amber"
					title="Not available"
					description="Parent sign-in is not available right now. Please contact the administration office."
				/>
			</section>

			<p class="mt-5 flex items-center justify-center gap-1 text-center text-xs text-[var(--login-brand)]">
				<span class="lucide-info size-3.5" aria-hidden="true" />
				Cookies must be enabled in your browser to sign in.
			</p>
		</main>
	</div>
</template>

<script setup>
import { computed, h, nextTick, ref, watch } from "vue";
import { Alert, TabButtons } from "frappe-ui";
import GoogleButton from "./components/GoogleButton.vue";
import PasswordSignIn from "./components/PasswordSignIn.vue";

const props = defineProps({
	config: { type: Object, required: true },
});

const brand = props.config.brand;
const tabs = props.config.tabs;
const redirectTo = props.config.redirect_to || "";

// Split a long institution name at the space nearest its middle: two even lines.
const titleLines = (() => {
	const title = (brand.title || "").trim();
	if (title.length <= 24) return [title];
	const mid = title.length / 2;
	let best = -1;
	for (let i = 0; i < title.length; i++) {
		if (title[i] === " " && (best < 0 || Math.abs(i - mid) < Math.abs(best - mid))) best = i;
	}
	if (best < 0) return [title];
	let first = title.slice(0, best);
	let second = title.slice(best + 1);
	// A small connecting word ends the first line ("…School of / India University"), not starts the second.
	const [lead, ...rest] = second.split(" ");
	if (rest.length && /^(of|and|&|for|the|in|at)$/i.test(lead)) {
		first += " " + lead;
		second = rest.join(" ");
	}
	return [first, second];
})();

const tab = ref(props.config.tab);
const pageError = ref(props.config.error || "");

const tabOptions = [
	{ value: "staff", label: "Staff", iconLeft: "lucide-briefcase" },
	{ value: "faculty-student", label: "Faculty & Student", iconLeft: "lucide-graduation-cap" },
	{ value: "parent", label: "Parent & Guardian", iconLeft: "lucide-users" },
];

// Three labels don't fit side by side on a phone.
const phoneQuery = window.matchMedia("(max-width: 520px)");
const narrow = ref(phoneQuery.matches);
phoneQuery.addEventListener("change", (e) => (narrow.value = e.matches));

const subtitles = {
	staff: "Sign in to the staff workspace.",
	"faculty-student": "Faculty and students sign in with Google.",
	parent: "Sign in to follow your ward's attendance, results and fees.",
};

const domains = computed(() => tabs["faculty-student"].domains.map((d) => "@" + d).join(", "));

// One of the two groups switched off in its portal settings: say so up front.
const partlyDisabled = computed(() => {
	const fs = tabs["faculty-student"];
	if (!fs.faculty) return "Faculty sign-in is currently disabled. Students can still sign in.";
	if (!fs.student) return "Student sign-in is currently disabled. Faculty can still sign in.";
	return "";
});

const Divider = () =>
	h("div", { class: "my-4 flex items-center gap-3 text-xs text-ink-gray-5" }, [
		h("span", { class: "h-px flex-1 bg-outline-gray-2" }),
		"or",
		h("span", { class: "h-px flex-1 bg-outline-gray-2" }),
	]);

// Keep ?tab= in the address bar, so a refresh or a shared link opens the same tab.
// On arrival too: plain /login shows as /login?tab=staff (the server's default tab).
const startUrl = new URL(window.location.href);
if (startUrl.searchParams.get("tab") !== tab.value) {
	startUrl.searchParams.set("tab", tab.value);
	window.history.replaceState(null, "", startUrl.pathname + "?" + startUrl.searchParams);
}

// The server refused a sign-in made on the wrong tab: open the account's own
// tab and show why there (after the tab watcher below has cleared old errors).
async function moveToTab({ tab: target, message }) {
	tab.value = target;
	await nextTick();
	pageError.value = message;
}

watch(tab, (value) => {
	pageError.value = "";
	const url = new URL(window.location.href);
	url.searchParams.set("tab", value);
	url.searchParams.delete("error");
	window.history.replaceState(null, "", url.pathname + "?" + url.searchParams);
});
</script>
