import { createSystem, defaultConfig, defineConfig } from "@chakra-ui/react";

// Semantic tokens with _light / _dark conditions.
// Chakra v3 resolves these via data-theme="dark"|"light" on <html>.
const config = defineConfig({
  theme: {
    semanticTokens: {
      colors: {
        "bg.page": {
          value: { _light: "#ffffff", _dark: "#0f1117" },
        },
        "bg.surface": {
          value: { _light: "#f8f9fa", _dark: "#1a1d27" },
        },
        "bg.subtle": {
          value: { _light: "#f1f3f5", _dark: "#14161f" },
        },
        "bg.muted": {
          value: { _light: "#e9ecef", _dark: "#2a2d3a" },
        },

        "text.primary": {
          value: { _light: "#111827", _dark: "#e2e8f0" },
        },
        "text.secondary": {
          value: { _light: "#6b7280", _dark: "#94a3b8" },
        },
        "text.muted": {
          value: { _light: "#9ca3af", _dark: "#64748b" },
        },
        "text.dim": {
          value: { _light: "#374151", _dark: "#cbd5e1" },
        },
        "text.bright": {
          value: { _light: "#030712", _dark: "#f1f5f9" },
        },

        "border.default": {
          value: { _light: "#e5e7eb", _dark: "#2a2d3a" },
        },
        "border.muted": {
          value: { _light: "#d1d5db", _dark: "#374151" },
        },

        "accent.active": {
          value: { _light: "#2563eb", _dark: "#3b82f6" },
        },
        "accent.activeHover": {
          value: { _light: "#1d4ed8", _dark: "#2563eb" },
        },
        "accent.activeBg": {
          value: { _light: "#dbeafe", _dark: "#1e3a5f" },
        },

        "bubble.user": {
          value: { _light: "#2563eb", _dark: "#2563eb" },
        },
        "bubble.assistant": {
          value: { _light: "#f1f3f5", _dark: "#1a1d27" },
        },
      },
    },
  },
  globalCss: {
    "html, body": { bg: "bg.page", color: "text.primary" },
  },
});

export const system = createSystem(defaultConfig, config);

export type ThemePreference = "system" | "dark" | "light";
