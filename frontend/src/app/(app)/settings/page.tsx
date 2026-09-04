import { Box, VStack, Text } from "@chakra-ui/react";
import { ThemeSwitcher } from "@/components/theme-switcher";

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
      </VStack>
    </Box>
  );
}
