<template>
	<div>
		<Button
			class="w-full"
			size="md"
			variant="outline"
			:loading="loading"
			loading-text="Opening Google…"
			@click="start"
		>
			<template #prefix>
				<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
					<path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84c-.21 1.13-.84 2.09-1.79 2.73v2.27h2.9c1.7-1.56 2.69-3.87 2.69-6.64z" />
					<path fill="#34A853" d="M9 18c2.43 0 4.47-.81 5.96-2.18l-2.9-2.27c-.8.54-1.84.86-3.06.86-2.35 0-4.34-1.59-5.05-3.72H.95v2.34C2.44 15.98 5.48 18 9 18z" />
					<path fill="#FBBC05" d="M3.95 10.69A5.4 5.4 0 0 1 3.68 9c0-.59.1-1.16.27-1.69V4.97H.95A9 9 0 0 0 0 9c0 1.45.35 2.83.95 4.03l3-2.34z" />
					<path fill="#EA4335" d="M9 3.58c1.32 0 2.51.46 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0 5.48 0 2.44 2.02.95 4.97l3 2.34C4.66 5.17 6.65 3.58 9 3.58z" />
				</svg>
			</template>
			Sign in with Google
		</Button>
		<ErrorMessage class="mt-2" :message="error" />
	</div>
</template>

<script setup>
import { ref } from "vue";
import { Button, ErrorMessage } from "frappe-ui";
import { googleSignInUrl } from "../api";

const props = defineProps({
	tab: { type: String, required: true },
	redirectTo: { type: String, default: "" },
});

const loading = ref(false);
const error = ref("");

async function start() {
	loading.value = true;
	error.value = "";
	try {
		window.location.href = await googleSignInUrl(props.tab, props.redirectTo);
	} catch (e) {
		error.value = e.message;
		loading.value = false;
	}
}
</script>
