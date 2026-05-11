/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#1a1a2e',
        foreground: '#f5f5f5',
        card: '#16213e',
        'card-foreground': '#f5f5f5',
        primary: '#0f3460',
        'primary-foreground': '#f5f5f5',
        secondary: '#1f4068',
        'secondary-foreground': '#f5f5f5',
        muted: '#1f4068',
        'muted-foreground': '#a0a0a0',
        border: '#2a2a4a',
        input: '#1f4068',
        ring: '#0f3460',
        positive: '#00d26a',
        negative: '#f73636',
        warning: '#feca57',
      },
    },
  },
  plugins: [],
}