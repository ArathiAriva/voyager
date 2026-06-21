"use client";

import { HStack, Box, Text } from "@chakra-ui/react";
import { useTheme } from "@/lib/theme-context";
import type { ThemePreference } from "@/lib/theme";

const OPTIONS: { value: ThemePreference; label: string; icon: string }[] = [
  { value: "system", label: "System", icon: "💻" },
  { value: "light",  label: "Light",  icon: "☀️" },
  { value: "dark",   label: "Dark",   icon: "🌙" },
];

export function ThemeSwitcher() {
  const { preference, setPreference } = useTheme();

  return (
    <HStack gap={2}>
      {OPTIONS.map((opt) => {
        const active = preference === opt.value;
        return (
          <Box
            key={opt.value}
            as="button"
            onClick={() => setPreference(opt.value)}
            display="flex"
            alignItems="center"
            gap={1.5}
            px={3}
            py={2}
            borderRadius="lg"
            border="1.5px solid"
            borderColor={active ? "accent.active" : "border.default"}
            bg={active ? "accent.activeBg" : "transparent"}
            color={active ? "accent.active" : "text.secondary"}
            fontSize="sm"
            fontWeight={active ? "600" : "400"}
            transition="all 0.15s"
            _hover={{ borderColor: "accent.active", color: "text.primary" }}
          >
            <Text fontSize="sm" lineHeight="1">{opt.icon}</Text>
            <Text>{opt.label}</Text>
          </Box>
        );
      })}
    </HStack>
  );
}
