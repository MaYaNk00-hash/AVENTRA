import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
      },
      fontSize: {
        '2xs': ['13px', '18px'],
        'xs': ['14px', '20px'],      // Scaled up by 2px (standard was 12px)
        'sm': ['16px', '24px'],      // Scaled up by 2px (standard was 14px)
        'base': ['18px', '28px'],    // Scaled up by 2px (standard was 16px)
        'lg': ['20px', '28px'],      // Scaled up by 2px (standard was 18px)
        'xl': ['22px', '30px'],      // Scaled up by 2px (standard was 20px)
        '2xl': ['26px', '34px'],     // Scaled up by 2px (standard was 24px)
        '3xl': ['32px', '38px'],     // Scaled up by 2px (standard was 30px)
        '4xl': ['38px', '44px'],     // Scaled up by 2px (standard was 36px)
      },
    },
  },
  plugins: [],
};
export default config;
