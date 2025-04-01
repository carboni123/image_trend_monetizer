/** @type {import('tailwindcss').Config} */
export default {
  darkMode: false, // Disable dark mode to force light mode styles
  content: [
    "./index.html",
    "./src/**/*.{js,jsx,ts,tsx}", // Ensure all component files are included
  ],
  theme: {
    extend: {
      // Add custom colors here
      colors: {
        'beige-main': '#fffc00', // Your primary beige background
        'beige-light': '#fffef5', // A slightly lighter variant (optional)
        'brand-brown': '#a1887f', // A complementary darker tone (optional, e.g., for footer)
      }
      // Extend other theme properties here if needed
    },
  },
  plugins: [],
};