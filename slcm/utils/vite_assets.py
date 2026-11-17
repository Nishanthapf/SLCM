"""Hashed JS/CSS file names of the frappe-ui apps built from frontend/.

`yarn build` in frontend/ (run by `bench build --app slcm`) writes every app to
slcm/public/frontend/ with one manifest.json. Each app has an entry in that
manifest keyed by its source file, e.g. "src/login/main.js".
"""

import json
import os

import frappe

BUILD_DIR = ("public", "frontend")
BASE_URL = "/assets/slcm/frontend/"


def get_entry_assets(entry: str) -> dict | None:
	"""{"js": url, "css": [urls]} for a manifest entry, or None when not built.

	CSS is collected from the entry and every chunk it imports (shared chunks,
	like vue + frappe-ui, carry their own CSS when two apps use them).
	"""
	manifest = _read_manifest()
	chunk = manifest.get(entry) if manifest else None
	if not chunk:
		return None

	css, seen = [], set()

	def collect(key):
		if key in seen or key not in manifest:
			return
		seen.add(key)
		item = manifest[key]
		for href in item.get("css", []):
			if href not in css:
				css.append(href)
		for imported in item.get("imports", []):
			collect(imported)

	collect(entry)
	return {"js": BASE_URL + chunk["file"], "css": [BASE_URL + href for href in css]}


def _read_manifest() -> dict | None:
	path = os.path.join(frappe.get_app_path("slcm", *BUILD_DIR), "manifest.json")
	if not os.path.exists(path):
		return None
	with open(path) as f:
		return json.load(f)
