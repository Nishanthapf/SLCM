"""NLSIU logo for receipt / invoice print formats, embedded as a data URI.

wkhtmltopdf fetches a plain "/files/..." image over HTTP from the site's own URL; behind a proxy or with a
host_name the server cannot reach (UAT), the logo comes out blank. A data URI needs no request at all.

Use in a print format:  {% set logo = get_nls_logo() %} ... <img src="{{ logo }}">
"""

import base64
import mimetypes
import os

import frappe

_SITE_FILE = "nlsiu-logo.jpg"  # sites/<site>/public/files/nlsiu-logo.jpg (uploaded; preferred when present)
_APP_FILE = ("public", "images", "nlsiu-logo.jpg")  # bundled copy, so every site has a logo


def get_nls_logo() -> str:
	for path in (frappe.get_site_path("public", "files", _SITE_FILE), frappe.get_app_path("slcm", *_APP_FILE)):
		try:
			if os.path.isfile(path):
				with open(path, "rb") as f:
					data = base64.b64encode(f.read()).decode()
				mime = mimetypes.guess_type(path)[0] or "image/jpeg"
				return f"data:{mime};base64,{data}"
		except OSError:
			continue
	return "/assets/slcm/images/nlsiu-logo.jpg"
