import type { Config } from 'tailwindcss'
const config: Config = { content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'], theme: { extend: { colors: { aimi: { bg:'#080711', panel:'#111023', card:'#17142d', line:'#2c2654', purple:'#9b5cff', mint:'#62f0bd', pink:'#ff5fc8', amber:'#ffb74d' } } } }, plugins: [] }
export default config
