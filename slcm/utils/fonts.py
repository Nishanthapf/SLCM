"""Install the receipt fonts as system fonts for the user running bench.

wkhtmltopdf turns any @font-face (web) font into vector outlines, so a PDF printed with one has no selectable or
copyable text. With the same TTFs installed for fontconfig, the print styles (templates/print/nls_receipt_style.html)
pick the system font first and the PDF embeds real text. Runs on install and every migrate; it only copies files that
are missing or changed and never fails the migrate.
"""

import filecmp
import os
import shutil
import subprocess

import frappe

FONTS = ("Merriweather-Regular.ttf", "Merriweather-Bold.ttf", "Merriweather-Italic.ttf")


def install_print_fonts():
	try:
		source_dir = frappe.get_app_path("slcm", "public", "fonts")
		target_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "fonts", "slcm")
		os.makedirs(target_dir, exist_ok=True)
		changed = False
		for name in FONTS:
			source = os.path.join(source_dir, name)
			target = os.path.join(target_dir, name)
			if not os.path.exists(source):
				continue
			if not os.path.exists(target) or not filecmp.cmp(source, target, shallow=False):
				shutil.copyfile(source, target)
				changed = True
		if changed and shutil.which("fc-cache"):
			subprocess.run(["fc-cache", "-f", target_dir], check=False, capture_output=True, timeout=120)
	except Exception:
		# fonts only affect how PDFs embed text; never block install / migrate over them
		frappe.log_error(frappe.get_traceback(), "SLCM: could not install print fonts")
