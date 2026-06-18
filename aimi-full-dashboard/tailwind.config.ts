import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}", "./lib/**/*.{js,ts,jsx,tsx}"],
  theme: { extend: { boxShadow: { glow: "0 0 35px rgba(168, 85, 247, .35)" } } },
  plugins: []
};
export default config;
