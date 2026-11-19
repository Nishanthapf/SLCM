// Programme card icons.
//
// A Programme can pick one in its "Dashboard Icon" field; the options of that
// Select field are the keys below (keep both lists in sync). Icons are
// frappe-ui class icons (`lucide-*`) and must stay literal strings here, or
// Tailwind's content scan won't emit them.

export const PROGRAMME_ICONS = {
	"graduation-cap": "lucide-graduation-cap",
	"book-open": "lucide-book-open",
	microscope: "lucide-microscope",
	landmark: "lucide-landmark",
	scale: "lucide-scale",
	gavel: "lucide-gavel",
	briefcase: "lucide-briefcase",
	"building-2": "lucide-building-2",
	library: "lucide-library",
	"scroll-text": "lucide-scroll-text",
	globe: "lucide-globe",
	users: "lucide-users",
	shield: "lucide-shield",
	leaf: "lucide-leaf",
	handshake: "lucide-handshake",
	newspaper: "lucide-newspaper",
};

// Used when the Programme has no Dashboard Icon.
const LEVEL_ICONS = {
	undergraduate: "lucide-graduation-cap",
	postgraduate: "lucide-book-open",
	research: "lucide-microscope",
};

export function programmeIcon(programme) {
	return PROGRAMME_ICONS[programme.icon] || LEVEL_ICONS[programme.level_key] || "lucide-school";
}
