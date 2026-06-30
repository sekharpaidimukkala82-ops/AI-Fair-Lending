/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: { 900: '#1a237e', 800: '#283593', 700: '#303f9f', 600: '#3949ab', 500: '#3f51b5' },
        brand: { DEFAULT: '#1a237e', light: '#3949ab' },
      }
    }
  },
  plugins: []
}
