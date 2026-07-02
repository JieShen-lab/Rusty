import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Microsoft YaHei UI', 'Segoe UI', 'PingFang SC', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        glass: '0 20px 60px rgba(0, 0, 0, 0.35)',
      },
    },
  },
  plugins: [],
} satisfies Config;
