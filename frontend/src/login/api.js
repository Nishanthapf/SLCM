// Server calls of the login page, and turning their errors into messages a
// person can act on. Every function resolves to { ok, data } or throws a
// LoginError whose `message` is ready to show.

export class LoginError extends Error {
	/** `tab`: the tab the server says this account signs in on (wrong-tab refusals). */
	constructor(message, tab = "") {
		super(message);
		this.tab = tab;
	}
}

/** A refused sign-in, carrying the tab to switch to when the server named one. */
function refusal(result) {
	return new LoginError(explain(result), result.body.login_tab || "");
}

const NETWORK = "We couldn't reach the server. Check your internet connection and try again.";
const SERVER = "Something went wrong on our side. Please try again in a few minutes.";

async function post(method, data) {
	let response;
	try {
		response = await fetch(`/api/method/${method}`, {
			method: "POST",
			headers: {
				Accept: "application/json",
				"Content-Type": "application/json",
				"X-Frappe-CSRF-Token": window.csrf_token || "",
			},
			body: JSON.stringify(data),
		});
	} catch {
		throw new LoginError(NETWORK);
	}
	let body = {};
	try {
		body = await response.json();
	} catch {
		// HTML error page (proxy timeout, 502, ...)
	}
	return { ok: response.ok, status: response.status, body };
}

/** The text Frappe sent with an error: `message`, or the first `_server_messages` entry. */
function serverText(body) {
	if (typeof body.message === "string") return body.message;
	if (body.message?.message) return String(body.message.message);
	try {
		for (const raw of JSON.parse(body._server_messages || "[]")) {
			const msg = typeof raw === "string" ? JSON.parse(raw) : raw;
			if (msg?.message) return stripHtml(msg.message);
		}
	} catch {
		// not JSON
	}
	return "";
}

function stripHtml(text) {
	const div = document.createElement("div");
	div.innerHTML = text;
	return div.textContent || "";
}

/** A message for a failed sign-in, password-reset or link request. */
export function explain({ status, body }) {
	const text = serverText(body);
	const exc = body.exc_type || "";

	// Our own refusals (slcm/utils/login_page.py) are already written for people.
	if (exc === "LoginNotAllowed") return text;

	if (status === 429 || /RateLimit|TooManyRequests/.test(exc))
		return "Too many attempts. Please wait a few minutes and try again.";
	if (/locked/i.test(text))
		return 'Too many wrong passwords, so the account is locked for a few minutes. Wait, then try again, or use "Forgot password?".';
	if (/verification code/i.test(text)) return "That verification code is wrong or has expired. Please try again.";
	if (/session expired/i.test(text)) return "The verification step timed out. Go back and sign in again.";
	if (/disabled or missing/i.test(text))
		return "This account is disabled. Please contact the administration office.";
	if (/IP Address/i.test(text))
		return "This account can only sign in from the university network. Connect to it, or contact the IT office.";
	if (/not allowed at this time/i.test(text))
		return "Your account can't sign in at this time of day. Please try again during your permitted hours.";
	if (/username and password is not allowed/i.test(text))
		return 'Password sign-in is switched off. Use "Sign in with Google" instead.';
	if (status === 401 || exc === "AuthenticationError" || /Invalid login|Incorrect password/i.test(text))
		return "The email/username or password is incorrect. Please check them and try again.";
	if (status >= 500 || !status) return SERVER;
	return text || "Sign-in didn't complete. Please try again.";
}

/**
 * Password sign-in. Resolves to { done } or { verify: { tmpId, prompt } } for two-factor.
 * `tab` (slcm_tab) lets the server check the account belongs on that tab.
 */
export async function signIn(usr, pwd, tab) {
	const result = await post("login", { usr, pwd, slcm_tab: tab });
	const { body } = result;
	if (result.ok && body.verification && body.tmp_id) {
		return { verify: { tmpId: body.tmp_id, prompt: twoFactorPrompt(body.verification) } };
	}
	if (result.ok && body.message === "Password Reset" && body.redirect_to) {
		// The password has expired: Frappe sends the user to set a new one.
		window.location.href = body.redirect_to;
		return { done: false };
	}
	if (result.ok) return { done: true };
	throw refusal(result);
}

export async function verifyCode(tmpId, otp, tab) {
	const result = await post("login", { tmp_id: tmpId, otp, slcm_tab: tab });
	if (result.ok && !result.body.verification) return { done: true };
	throw result.ok ? new LoginError(explain({ status: 401, body: { message: "verification code" } })) : refusal(result);
}

function twoFactorPrompt(verification) {
	if (verification.method === "OTP App") return "Open your authenticator app and enter the 6-digit code.";
	if (verification.method === "SMS") return verification.prompt || "Enter the code we sent to your phone.";
	return (
		verification.prompt ||
		"Enter the code we sent to your email. It can take a minute to arrive; check your spam folder too."
	);
}

export async function requestPasswordReset(email) {
	const result = await post("slcm.api.user.reset_password", { user: email });
	const reply = result.body.message || {};
	if (result.ok && (!reply.status || reply.status === "ok")) {
		return reply.message || "A password reset link has been sent. Check your inbox and spam folder.";
	}
	if (reply.status === "not_found") throw new LoginError("We couldn't find an account with that email address.");
	// Worded here, not in slcm.api.user, whose texts the admission login pages also show.
	if (reply.status === "not_allowed")
		throw new LoginError("This account's password can't be reset here. Please contact the IT office.");
	if (reply.status === "disabled")
		throw new LoginError("This account is disabled. Please contact the administration office.");
	if (reply.message) throw new LoginError(reply.message);
	throw new LoginError(explain(result));
}

export async function googleSignInUrl(tab, redirectTo) {
	const result = await post("slcm.utils.login_page.get_google_login_url", { tab, redirect_to: redirectTo });
	if (result.ok && typeof result.body.message === "string") return result.body.message;
	throw new LoginError(explain(result));
}

/** After signing in, /login sends each user to their own portal (or the desk). */
export function finishSignIn(tab, redirectTo) {
	const params = new URLSearchParams({ tab });
	if (redirectTo) params.set("redirect-to", redirectTo);
	window.location.href = `/login?${params}`;
}
