<template>
	<!-- Step 1: email/username + password -->
	<form v-if="step === 'credentials'" class="space-y-4" novalidate @submit.prevent="submitCredentials">
		<TextInput
			v-model="usr"
			size="md"
			label="Email or username"
			placeholder="you@example.com"
			autocomplete="username"
			:error="errors.usr"
		/>
		<Password
			v-model="pwd"
			size="md"
			label="Password"
			placeholder="Your password"
			autocomplete="current-password"
			:error="errors.pwd"
		/>
		<div class="text-sm">
			<button type="button" class="text-[var(--login-brand)] hover:underline" @click="go('forgot')">
				Forgot password?
			</button>
		</div>
		<Alert v-if="message" :theme="message.theme" :title="message.title" :description="message.text" />
		<Button
			type="submit"
			class="login-brand-button w-full"
			size="md"
			variant="solid"
			label="Sign in"
			loading-text="Signing in…"
			:loading="busy"
		/>
	</form>

	<!-- Step 2: two-factor code -->
	<form v-else-if="step === 'otp'" class="space-y-4" novalidate @submit.prevent="submitCode">
		<p class="text-p-sm text-ink-gray-6">{{ otpPrompt }}</p>
		<TextInput
			v-model="otp"
			size="md"
			label="Verification code"
			placeholder="6-digit code"
			autocomplete="one-time-code"
			inputmode="numeric"
			maxlength="10"
			:error="errors.otp"
			@update:model-value="otp = String($event).replace(/\D/g, '')"
		/>
		<Alert v-if="message" :theme="message.theme" :title="message.title" :description="message.text" />
		<Button
			type="submit"
			class="login-brand-button w-full"
			size="md"
			variant="solid"
			label="Verify"
			loading-text="Verifying…"
			:loading="busy"
		/>
		<BackLink label="Back to sign in" @click="go('credentials')" />
	</form>

	<!-- Forgot password -->
	<form v-else class="space-y-4" novalidate @submit.prevent="submitEmail">
		<p class="text-p-sm text-ink-gray-6">
			Enter the email address of your account. We'll send a link to set a new password.
		</p>
		<TextInput
			v-model="email"
			size="md"
			type="email"
			label="Email address"
			placeholder="you@example.com"
			autocomplete="email"
			:error="errors.email"
		/>
		<Alert v-if="message" :theme="message.theme" :title="message.title" :description="message.text" />
		<Button
			type="submit"
			class="login-brand-button w-full"
			size="md"
			variant="solid"
			label="Send reset link"
			loading-text="Sending…"
			:loading="busy"
		/>
		<BackLink label="Back to sign in" @click="go('credentials')" />
	</form>
</template>

<script setup>
import { h, reactive, ref } from "vue";
import { Alert, Button, Password, TextInput } from "frappe-ui";
import { finishSignIn, requestPasswordReset, signIn, verifyCode } from "../api";

const props = defineProps({
	tab: { type: String, required: true },
	redirectTo: { type: String, default: "" },
});

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const step = ref("credentials"); // credentials | otp | forgot
const usr = ref("");
const pwd = ref("");
const otp = ref("");
const email = ref("");
const tmpId = ref(null);
const otpPrompt = ref("");
const busy = ref(false);
const errors = reactive({ usr: "", pwd: "", otp: "", email: "" });
const message = ref(null); // { theme, text }

const BackLink = (p, { emit }) =>
	h(
		"button",
		{ type: "button", class: "block w-full text-center text-sm text-[var(--login-brand)] hover:underline", onClick: () => emit("click") },
		p.label
	);
BackLink.props = ["label"];
BackLink.emits = ["click"];

function go(next) {
	step.value = next;
	message.value = null;
	Object.keys(errors).forEach((k) => (errors[k] = ""));
	if (next === "credentials") {
		otp.value = "";
		tmpId.value = null;
	} else if (next !== "otp" && !email.value && EMAIL.test(usr.value.trim())) {
		email.value = usr.value.trim();
	}
}

async function run(task) {
	busy.value = true;
	message.value = null;
	try {
		await task();
	} catch (e) {
		const title = step.value === "credentials" || step.value === "otp" ? "Couldn't sign you in" : "Couldn't send the email";
		message.value = { theme: "red", title, text: e.message };
		busy.value = false;
	}
}

function submitCredentials() {
	errors.usr = usr.value.trim() ? "" : "Please enter your email or username.";
	errors.pwd = pwd.value ? "" : "Please enter your password.";
	if (errors.usr || errors.pwd) return;

	run(async () => {
		const result = await signIn(usr.value.trim(), pwd.value);
		if (result.verify) {
			tmpId.value = result.verify.tmpId;
			otpPrompt.value = result.verify.prompt;
			step.value = "otp";
			busy.value = false;
		} else if (result.done) {
			signedIn();
		}
	});
}

function submitCode() {
	errors.otp = otp.value ? "" : "Please enter the verification code.";
	if (errors.otp) return;
	run(async () => {
		await verifyCode(tmpId.value, otp.value);
		signedIn();
	});
}

function submitEmail() {
	const value = email.value.trim();
	errors.email = !value
		? "Please enter your email address."
		: EMAIL.test(value)
			? ""
			: "That doesn't look like an email address. Please check it.";
	if (errors.email) return;

	run(async () => {
		const text = await requestPasswordReset(value);
		message.value = { theme: "green", title: "Check your email", text };
		busy.value = false;
	});
}

function signedIn() {
	message.value = { theme: "green", title: "Signed in", text: "Taking you to your page…" };
	finishSignIn(props.tab, props.redirectTo);
}
</script>
