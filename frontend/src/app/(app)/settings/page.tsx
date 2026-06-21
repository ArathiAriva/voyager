import { Box, VStack, HStack, Text, Badge } from "@chakra-ui/react";
import { ThemeSwitcher } from "@/components/theme-switcher";

const MEMORY_BEHAVIOURS = [
  { label: "Save journal entries to memory", description: "Voyager extracts episodes and preferences from entries you write.", active: true },
  { label: "Learn from conversations", description: "Each chat is summarised and stored in memory after you reply.", active: true },
  { label: "Build preference profile", description: "Infers your travel style from journals and conversations over time.", active: true },
];

const COMING_SOON = [
  { label: "Telegram journal bot", description: "Send voice notes and photos from the field, auto-ingested into your trips." },
  { label: "Email booking ingestion", description: "Forward confirmation emails to auto-create trip records." },
  { label: "AI Model selection", description: "Switch between models per conversation." },
  { label: "Auth & multi-user", description: "Sign in and keep your data private." },
];

export default function SettingsPage() {
  return (
    <Box p={10} maxW="600px">
      <VStack align="start" gap={8} w="full">
        <Box>
          <Text fontSize="xs" fontWeight="600" letterSpacing="0.1em" textTransform="uppercase" color="text.secondary" mb={2}>Preferences</Text>
          <Text fontSize="3xl" fontWeight="800" letterSpacing="-0.03em" lineHeight="1.1">Settings</Text>
        </Box>

        <VStack align="stretch" gap={3} w="full">
          <Text fontSize="sm" fontWeight="semibold" color="text.muted" textTransform="uppercase" letterSpacing="wide">
            Appearance
          </Text>
          <Box bg="bg.surface" borderRadius="2xl" p={6} boxShadow="0 4px 20px rgba(0,0,0,0.2)" border="none">
            <Text fontSize="sm" fontWeight="medium" mb={3}>Theme</Text>
            <ThemeSwitcher />
          </Box>
        </VStack>

        <VStack align="stretch" gap={3} w="full">
          <Text fontSize="sm" fontWeight="semibold" color="text.muted" textTransform="uppercase" letterSpacing="wide">
            Memory — active
          </Text>
          <Box bg="bg.surface" borderRadius="2xl" p={6} boxShadow="0 4px 20px rgba(0,0,0,0.2)" border="none">
            <VStack align="stretch" gap={4}>
              {MEMORY_BEHAVIOURS.map((item) => (
                <HStack key={item.label} justify="space-between" align="start" gap={4}>
                  <Box flex={1}>
                    <Text fontSize="sm" fontWeight="medium">{item.label}</Text>
                    <Text fontSize="xs" color="text.secondary" mt={0.5}>{item.description}</Text>
                  </Box>
                  <Badge colorPalette="green" borderRadius="full" px={2} size="sm" flexShrink={0}>on</Badge>
                </HStack>
              ))}
            </VStack>
          </Box>
        </VStack>

        <VStack align="stretch" gap={3} w="full">
          <Text fontSize="sm" fontWeight="semibold" color="text.muted" textTransform="uppercase" letterSpacing="wide">
            Coming in future phases
          </Text>
          <Box bg="bg.subtle" borderRadius="2xl" p={6} border="1px dashed" borderColor="border.muted">
            <VStack align="stretch" gap={4}>
              {COMING_SOON.map((item) => (
                <HStack key={item.label} justify="space-between" align="start" gap={4}>
                  <Box flex={1}>
                    <Text fontSize="sm" fontWeight="medium" color="text.muted">{item.label}</Text>
                    <Text fontSize="xs" color="text.secondary" mt={0.5}>{item.description}</Text>
                  </Box>
                  <Badge borderRadius="full" px={2} size="sm" flexShrink={0} variant="outline" colorPalette="gray">soon</Badge>
                </HStack>
              ))}
            </VStack>
          </Box>
        </VStack>
      </VStack>
    </Box>
  );
}
