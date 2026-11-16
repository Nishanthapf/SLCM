frappe.listview_settings["User Activity Log"] = {
	hide_name_column: true,
	get_indicator(doc) {
		const colors = {
			Login: "green", Logout: "gray", "Login Failed": "red",
			Create: "blue", Update: "orange", Submit: "purple", Cancel: "red",
			"Update After Submit": "orange", Delete: "red", Rename: "yellow",
			View: "gray", Export: "cyan", Print: "cyan", Download: "cyan", Action: "pink",
		};
		return [__(doc.action), colors[doc.action] || "gray", `action,=,${doc.action}`];
	},
};
