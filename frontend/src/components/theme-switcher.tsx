"use client";

import { HStack, Box, Text } from "@chakra-ui/react";
import { useTheme } from "@/lib/theme-context";
import type { ThemePreference } from "@/lib/theme";
import { MonitorIcon, SunIcon, MoonIcon, type IconProps } from "@/components/icons";

const OPTIONS: { value: ThemePreference; label: string; Icon: (p: IconProps) => React.ReactElement }[] = [
  { value: "system", label: "System", Icon: MonitorIcon },
  { value: "light",  label: "Light",  Icon: SunIcon },
  { value: "dark",   label: "Dark",   Icon: MoonIcon },
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
            <Box display="flex" alignItems="center"><opt.Icon /></Box>
            <Text>{opt.label}</Text>
          </Box>
        );
      })}
    </HStack>
  );
}
