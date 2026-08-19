/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#FAF9F6',
        ink: '#18181B',
        stone: '#71717A',
        cobalt: '#2563EB',
        'cobalt-dark': '#1D4ED8',
        'cobalt-light': '#EFF6FF',
        'cobalt-mid': '#DBEAFE',
        // keep legacy aliases used by modals/toasts
        primary: '#2563EB',
        'primary-dark': '#1D4ED8',
        'primary-container': '#1E40AF',
        'primary-fixed': '#DBEAFE',
        'on-primary': '#ffffff',
        surface: '#FAF9F6',
        'surface-container': '#F4F3EF',
        'surface-container-low': '#F9F8F5',
        'surface-container-high': '#EEECEA',
        'surface-container-lowest': '#ffffff',
        'surface-variant': '#E5E3DF',
        'on-surface': '#18181B',
        'on-surface-variant': '#71717A',
        background: '#FAF9F6',
        'outline-variant': '#E4E4E7',
        outline: '#A1A1AA',
      },
      fontFamily: {
        sans: ['Nunito', 'sans-serif'],
        serif: ['"Instrument Serif"', 'Georgia', 'serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
      },
      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        pulse2: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
        glow: {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(37,99,235,0.3)' },
          '50%': { boxShadow: '0 0 0 6px rgba(37,99,235,0)' },
        },
      },
      animation: {
        'fade-up': 'fadeUp 0.5s ease both',
        'fade-in': 'fadeIn 0.3s ease both',
        pulse2: 'pulse2 2s ease-in-out infinite',
        glow: 'glow 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
