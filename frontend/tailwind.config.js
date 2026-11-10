/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: { 'jbg': '#08070D', 'jcard': '#111019', 'jprimary': '#8B5CF6', 'jsecondary': '#B69CFF', 'jmuted': '#A1A1AA' },
      keyframes: { breathe: { '0%, 100%': { transform: 'scale(1)', boxShadow: '0 0 20px 5px rgba(139, 92, 246, 0.3)' }, '50%': { transform: 'scale(1.05)', boxShadow: '0 0 40px 15px rgba(139, 92, 246, 0.5)' } } },
      animation: { breathe: 'breathe 4s ease-in-out infinite' }
    },
  },
  plugins: [],
}
