"use client";

import { ClerkProvider } from "@clerk/nextjs";
import { useTheme } from "./theme";

/* Clerk's appearance prop takes literal colors (it derives shades from
   them), so it can't read our CSS tokens — mirror them per theme here. */
const light = {
  variables: {
    colorPrimary: "#c96442",
    colorText: "#1f1e1d",
    colorTextSecondary: "#63605b",
    colorBackground: "#ffffff",
    colorInputBackground: "#ffffff",
    borderRadius: "8px",
    fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
  },
};

const dark = {
  variables: {
    colorPrimary: "#d97757",
    colorText: "#f0eee6",
    colorTextSecondary: "#b8b3aa",
    colorBackground: "#30302e",
    colorInputBackground: "#262624",
    borderRadius: "8px",
    fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
  },
};

export function AppClerkProvider({ children }: { children: React.ReactNode }) {
  const { theme } = useTheme();
  return (
    <ClerkProvider appearance={theme === "dark" ? dark : light}>
      {children}
    </ClerkProvider>
  );
}
