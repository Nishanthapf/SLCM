import autoprefixer from "autoprefixer";
import tailwindcss from "tailwindcss";
import scope from "./postcss-scope.js";

export default {
	plugins: [tailwindcss(), scope(), autoprefixer()],
};
