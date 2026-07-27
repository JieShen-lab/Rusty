import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Microsoft YaHei UI', 'Segoe UI', 'PingFang SC', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config;
