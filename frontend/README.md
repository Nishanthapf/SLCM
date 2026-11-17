# slcm frontend: frappe-ui apps inside desk pages

This folder holds the **Vue 3 + [frappe-ui](https://ui.frappe.io/docs/introduction)** apps of slcm. There are two:

| App | URL | Kind of page |
|---|---|---|
| **Admission Dashboard** | `/app/admission-dashboard` | Inside a Frappe **desk page**: the desk sidebar and navbar stay, the page body is frappe-ui |
| **Login** | `/login` | A **web page** (`slcm/www/login`) of its own: the sign-in page for staff, faculty, students and parents. See [section 10](#10-the-login-page-login) |

> **Why not a separate SPA like Helpdesk?** Helpdesk serves its frappe-ui app at its own route (`/helpdesk`), outside the desk. We wanted the dashboard inside the desk with the normal sidebar. ERPNext doesn't use frappe-ui at all. Its desk pages are plain JS.

---

## 1. Where everything lives

```
apps/slcm/
├── package.json                      ← "build" script: bench build runs the Vite build too
├── .gitignore                        ← ignores slcm/public/frontend (build output)
│
├── frontend/                         ← THIS FOLDER (Vite project)
│   ├── README.md                     ← you are here
│   ├── package.json                  ← frappe-ui, vue, vite, tailwind versions
│   ├── vite.config.js                ← the list of apps (entries), output folder, manifest
│   ├── tailwind.config.js            ← frappe-ui preset, scoped to .slcm-fui
│   ├── postcss.config.js             ← tailwind → scope plugin → autoprefixer
│   ├── postcss-scope.js              ← keeps frappe-ui's global CSS inside .slcm-fui
│   └── src/
│       ├── admission_dashboard/
│       │   ├── main.js               ← entry: exports mount(el, { api, boot })
│       │   ├── index.css             ← Tailwind layers + brand colours (maroon)
│       │   ├── App.vue               ← header, Academic Year, Settings button, view switch
│       │   ├── cards.js              ← icon + colour per Applicant Status
│       │   └── components/
│       │       ├── ProgrammeList.vue      ← Domestic/International toggle + programme cards
│       │       ├── ProgrammeOverview.vue  ← number cards, donut chart, trend chart
│       │       ├── StatCard.vue           ← one number card (icon + frappe-ui NumberCard)
│       │       ├── SettingsDialog.vue     ← show/hide + drag-to-reorder cards and charts
│       │       └── BuildingArt.vue        ← decorative campus SVG
│       └── login/
│           ├── main.js               ← entry: reads the page settings, mounts App.vue
│           ├── index.css             ← Tailwind layers + brand button colour
│           ├── api.js                ← server calls + turning errors into plain messages
│           ├── App.vue               ← brand, the three tabs, what each tab shows
│           └── components/
│               ├── PasswordSignIn.vue ← password → 2FA code; forgot password; email link
│               └── GoogleButton.vue   ← "Sign in with Google"
│
└── slcm/
    ├── admission/page/admission_dashboard/
    │   ├── admission_dashboard.json  ← the desk Page (name, title, roles)
    │   ├── admission_dashboard.js    ← desk loader: fetches assets, mounts the Vue app
    │   └── admission_dashboard.py    ← whitelisted API methods (data + settings)
    ├── admission/doctype/admission_dashboard_settings/
    │   └── ...                       ← Single DocType storing the global layout (JSON)
    ├── www/login.py + login.html     ← the /login web page (replaces Frappe's own)
    ├── utils/login_page.py           ← login rules: tabs, landing pages, hooks
    ├── utils/vite_assets.py          ← looks up an app's hashed files in manifest.json
    └── public/frontend/              ← BUILD OUTPUT for all apps (gitignored)
        ├── manifest.json             ← maps each entry (src/<app>/main.js) to hashed files
        └── assets/<app>-<hash>.js / .css, shared-<hash>.js (vue + frappe-ui)
```

---

## 2. How a page loads (step by step)

1. The user opens **`/app/admission-dashboard`**. Frappe runs
   `slcm/admission/page/admission_dashboard/admission_dashboard.js`.
2. The loader hides the normal page header and creates a root `<div class="slcm-fui">`.
3. It calls **`get_bootstrap`** in `admission_dashboard.py`, which returns:
   - `assets`: the current hashed JS/CSS URLs, read from `manifest.json`
   - `academic_years`: dropdown options and the default (the Active cycle's year)
   - `settings`: which cards and charts are shown, and in what order
   - `can_edit_settings`: whether to show the Settings button
4. The loader adds the CSS `<link>`, runs `import(js)`, and calls **`mount(rootEl, { api, boot })`** from `src/admission_dashboard/main.js`.
5. `main.js`:
   - copies `frappe.csrf_token` to `window.csrf_token` (frappe-ui reads it there)
   - calls `setConfig("resourceFetcher", frappeRequest)` so `createResource({ url: "dotted.method" })` becomes `POST /api/method/dotted.method`
   - creates a `.slcm-fui-portal` div on `<body>` so dialogs and dropdowns stay inside the CSS scope
   - mounts `App.vue`
6. Components load their data with frappe-ui's **`createResource`**.
7. When the user leaves the page, a `page-change` listener turns the stylesheet off and hides the portal. `on_page_show` turns them back on. Frappe has **no** `on_page_hide` event for desk pages (checked on v16.33 and v16.53), so don't rely on it.

Because the file names carry a hash, a new build is never served from a stale browser cache.

---

## 3. Admission Dashboard: what it shows and where the data comes from

| Screen / part | Component | Server method |
|---|---|---|
| Academic Year dropdown | `App.vue` (frappe-ui `Select`) | `get_academic_years` (also sent in `get_bootstrap`) |
| Domestic / International toggle + programme cards | `ProgrammeList.vue` | `get_programmes(academic_year, applicant_type)` |
| Programme overview: number cards and charts | `ProgrammeOverview.vue`, `StatCard.vue` | `get_programme_overview(academic_year, program, applicant_type)` |
| Settings dialog | `SettingsDialog.vue` | `get_settings`, `save_settings(layout)`, `reset_settings` |

**Programme cards** use the same rule as the admission site (`get_active_programs()` in `slcm/admission/utils/portal.py`):

- They come from the **Admission Cycle Program** rows with `is_active = 1`, across every **Admission Cycle** whose `academic_year` equals the selected Academic Year.
- **Domestic / International** uses `admission_open_for`. A blank value or "Domestic & International" shows the programme under both tabs.

**Applicant counts** are filtered by programme, by Admission Cycle (cycles of the selected year), and by applicant type:

- `foriegn_national = "Yes"` counts as International; anything else counts as Domestic.
- The counts use `frappe.get_list`, so the user's permissions apply.

**Number cards:**

- "Total Applications", plus **one card per Applicant Status** (every record in the Applicant Status DocType).
- Switched on by default: Total, Draft, Submitted, Submitted and Paid, Selected, Rejected.
- A new Applicant Status appears in Settings automatically, switched off.

**Charts:**

- **Application Status:** a frappe-ui `DonutChart`, with a count and percentage table beside it.
- **Application Trend:** a frappe-ui `AreaChart` of the running total by month (from `Applicant.creation`). The tooltip also shows the applications added that month.

**Settings:**

- Global for everyone, stored as JSON in **Admission Dashboard Settings** (field `layout`).
- Only **System Manager** and **Admission Admin** can change them.

**Page access:** the page's roles are System Manager, Admission Admin, Admission Officer and NLSIU Admin. Every API method also checks read permission on `Applicant`.

**Card colours and icons:** `src/admission_dashboard/cards.js` picks them by matching words in the status name (reject → red, paid → green, draft → gray, …).

---

## 4. Everyday commands

Run these **inside WSL** (Node and Yarn are there, not on Windows):

```bash
# First time / after pulling new dependencies
cd ~/frappe-bench/apps/slcm/frontend
yarn install

# Production build of every app (writes slcm/public/frontend/)
yarn build

# Rebuild automatically while editing (development mode, with source maps)
yarn dev
```

`bench build --app slcm` also runs `yarn install --frozen-lockfile && yarn build` here, through the root `apps/slcm/package.json`. Deployments don't need an extra step.

After **Python or DocType changes** (`admission_dashboard.py`, the Page JSON, the settings DocType):

```bash
cd ~/frappe-bench
bench --site slcm.com migrate      # new/changed DocTypes and Page roles
bench --site slcm.com clear-cache  # desk caches page scripts
```

After **Vue changes**, `yarn build` plus a browser refresh is enough. No migrate is needed.

---

## 5. Adding something new

### 5a. A new number card or chart on the Admission Dashboard

- **New status card:** create the record in **Applicant Status**. It shows up in Settings automatically.
- **New chart:**
  1. Add a key and label to `CHARTS` in `admission_dashboard.py`.
  2. Return its data from `get_programme_overview`.
  3. Add a `v-else-if="chart.key === '<key>'"` block in `ProgrammeOverview.vue`.
  4. Run `yarn build`.

### 5b. A whole new frappe-ui desk page

1. **Create the desk Page** (Page DocType, standard = Yes, module of your choice) and give it roles.
2. **Write the Vue app** in `frontend/src/<your_page>/`, with a `main.js` that exports `mount(el, options)`. Copy `admission_dashboard/main.js`: keep the csrf, `setConfig`, and portal lines.
3. **Add a build entry:** one line in `entries` in `vite.config.js` (`your_page: "src/your_page/main.js"`).
4. **Add the server side** in the page's `.py`: a `get_bootstrap` that returns `get_entry_assets("src/your_page/main.js")` (from `slcm/utils/vite_assets.py`) plus any data.
5. **Add the loader** to the page `.js`: copy `admission_dashboard.js`, change the API path, and keep the stylesheet enable/disable (`on_page_show` plus the `page-change` listener).
6. Run `yarn build`, then `bench migrate` and `clear-cache`.

---

## 6. CSS scoping: why it's needed and how it works

frappe-ui relies on Tailwind, which by default styles **everything** (`*`, `button`, `input`, `:root` variables). Inside desk that would break Bootstrap/desk styles. Four things prevent it:

| Mechanism | File | What it does |
|---|---|---|
| `important: ".slcm-fui"` | `tailwind.config.js` | Every utility becomes `.slcm-fui .flex`, so it only works inside our root or portal and beats desk rules |
| Scope plugin | `postcss-scope.js` | Rewrites base rules: `:root/html/body → .slcm-fui`; `button, *, [type=text] → :where(.slcm-fui) …`; `[data-theme="dark"] → [data-theme="dark"] .slcm-fui` |
| `corePlugins: { container: false }` | `tailwind.config.js` | Avoids clashing with Bootstrap's `.container` |
| Stylesheet on/off | page `.js` (`on_page_show` + `page-change` listener) | The CSS is only active while the page is open |

**Rule:** keep the frappe-ui markup **inside** the `.slcm-fui` root. Utility classes on the root element itself do not apply, so put them on the first child (as `App.vue` does).

---

## 7. Gotchas (learned the hard way)

- **"Unexpected token '<'" in a resource:** `setConfig("resourceFetcher", frappeRequest)` is missing. The default fetcher doesn't add `/api/method/`, so it gets an HTML page back.
- **`hidden lg:block` doesn't show the element:** desk defines `.hidden { display: none !important }`. Use `max-lg:!hidden` instead of `hidden`.
- **Don't import from `frappe-ui/src/...`:** the package's `exports` map blocks deep imports. Use `frappe-ui`, `frappe-ui/charts`, `frappe-ui/tailwind`, and so on. For the portal key, use `Symbol.for("frappe-ui:portal-target")`.
- **Icons** are class icons: `<span class="lucide-users size-5" />`, or `icon-left="lucide-settings"` on `Button`. Write the class name as a full literal string somewhere in the source; Tailwind only generates icons it can see.
- **Charts need a sized parent.** `DonutChart` and `AreaChart` fill their container, so wrap them in something with a height (`h-56`, `h-64`).
- **Colour tokens:** `text-ink-<color>-1…9` (higher is darker) and `bg-surface-<color>-1…10`. Brand maroon is `var(--adm-brand)` (set in `index.css`).
- **Assets missing error on the page:** the build hasn't run on that site. Run `bench build --app slcm`, or `yarn build` here.

---

## 8. Testing in a browser (WSL setup)

For `/login`, use a private window (or log out first). A signed-in user is sent straight on to their page.


WSL has no browser. To check the page:

- **Manually:** open `http://localhost:8000/app/admission-dashboard` in Windows Chrome while logged in.
- **Automated screenshots:** start Windows Chrome headless with `--remote-debugging-port`, log in with a session created through `bench execute` (pass `?sid=<sid>`), drive it over the DevTools protocol from PowerShell, then delete the session afterwards.

---

## 9. Versions

| Package | Version |
|---|---|
| frappe-ui | 1.2.0 (`frappe-ui/charts` uses ECharts) |
| vue | ^3.5 |
| vite | ^7.3 |
| tailwindcss | ^3.4 (frappe-ui does not support v4) |
| Frappe | v16. Checked on 16.33.0 (production) and 16.53.0 (local) |

Docs: https://ui.frappe.io/docs/introduction

---

## 10. The login page (`/login`)

One sign-in page for everyone except admission and PACE applicants (they keep `/nlsatadmissions/login`, `/paceadmissions/login`, ...). It is also the **desk login**: Frappe sends logged-out desk visitors to `/login?redirect-to=/desk/...`. There is **no sign-up**; accounts are created by the institution.

### 10a. Files

| What | Where |
|---|---|
| The web page (replaces Frappe's own `www/login`) | `slcm/www/login.py` + `login.html` |
| Rules: tabs, who-is-who, landing pages, hooks | `slcm/utils/login_page.py` |
| Logged-out redirects, logout cookie → first tab | `slcm/utils/auth_routing.py` (`intercept_login`) |
| Hooks | `slcm/hooks.py`: `on_login`, `on_session_creation`, `website_redirects` (`/portal-login` → `/login`) |
| Vue app | `frontend/src/login/` |

### 10b. The tabs and what configures them

| Tab | How people sign in | Configured in |
|---|---|---|
| **Staff** | Email/username + password (with forgot password and two-factor), "Email me a sign-in link", Google | **System Settings**: *Disable Username/Password Login*, *Login with email link*. Google shows when a **Social Login Key** for Google is enabled |
| **Faculty & Student** | Google only | **Faculty Portal Settings** / **Student Portal Settings**: *Enable Google Login*, *Allowed Google Account Domain* |
| **Parent & Guardian** | Email/username + password, and Google if switched on | **Parent Portal Settings**: *Enable Google Login*, *Allowed Google Account Domain*. Password follows System Settings, like Staff |

Branding (title, subtitle, logo = *Portal Favicon*, background image, primary colour, font) comes from **Student Portal Settings**.

### 10c. Rules enforced on the server

The page only shows what is allowed; the server decides:

- **Faculty and students can't use a password or email link** (`enforce_password_login_policy`, `on_login` hook). They see: *"Faculty and students sign in with their institutional Google account."* If their portal's Google sign-in is switched off, they see: *"Faculty sign-in is currently disabled."* Exception: accounts that also have **real desk access** (a System User with a desk role other than the legacy `Student` role) can sign in on the Staff tab.
- **Google sign-ins are checked** (`enforce_google_login`, `on_session_creation` hook). The account decides which settings apply: Faculty record → Student Master (`official_email_id`/`user`) → parent (Student Parent email) → staff. A switched-off portal, a wrong domain, or an unknown Google account is refused and sent back to `/login?tab=...&error=<code>`. The first Google sign-in links the record (`Faculty.user_id`, `Student Master.user`) and adds the portal role.
- **Error messages travel as codes** (`?error=faculty_disabled`), and the server turns them into text (`get_error_message`). Free text in the URL is never shown, so nobody can put their own message on the login page.

### 10d. Where people land after signing in

The page signs in, then reloads `/login?tab=<tab>&redirect-to=...`. A signed-in visit to `/login` is redirected (302) by `get_landing_page`:

| Tab used | Order tried |
|---|---|
| Staff | desk (`/desk`) → faculty → student → parent portal |
| Faculty & Student | `/faculty-portal` → `/student-portal` → desk → parent |
| Parent & Guardian | `/parent-portal` → desk → faculty → student |

`redirect-to` is honoured for staff (any path on the site) and for portal users only inside their own portal.

### 10e. Error messages

`src/login/api.js` (`explain`) turns Frappe's replies into messages a person can act on: wrong password, account locked after too many attempts, disabled account, too many requests, network down, server error, wrong or expired 2FA code. Add a case there if users report a confusing message.

### 10f. If the build is missing

`login.html` falls back to a plain email/password form, so staff can still sign in and run `bench build --app slcm`.
