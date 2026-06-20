import { Box, VStack, HStack, Text, Badge } from "@chakra-ui/react";

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
    <Box p={8} maxW="560px">
      <VStack align="start" gap={8} w="full">
        <Box>
          <Text fontSize="2xl" fontWeight="bold">Settings</Text>
          <Text color="gray.500" fontSize="sm">Configure your Voyager experience.</Text>
        </Box>

        <VStack align="stretch" gap={3} w="full">
          <Text fontSize="sm" fontWeight="semibold" color="gray.500" textTransform="uppercase" letterSpacing="wide">
            Memory — active
          </Text>
          <Box bg="white" borderRadius="xl" p={5} boxShadow="sm" border="1px solid" borderColor="gray.100">
            <VStack align="stretch" gap={4}>
              {MEMORY_BEHAVIOURS.map((item) => (
                <HStack key={item.label} justify="space-between" align="start" gap={4}>
                  <Box flex={1}>
                    <Text fontSize="sm" fontWeight="medium">{item.label}</Text>
                    <Text fontSize="xs" color="gray.400" mt={0.5}>{item.description}</Text>
                  </Box>
                  <Badge colorPalette="green" borderRadius="full" px={2} size="sm" flexShrink={0}>on</Badge>
                </HStack>
              ))}
            </VStack>
          </Box>
        </VStack>

        <VStack align="stretch" gap={3} w="full">
          <Text fontSize="sm" fontWeight="semibold" color="gray.500" textTransform="uppercase" letterSpacing="wide">
            Coming in future phases
          </Text>
          <Box bg="gray.50" borderRadius="xl" p={5} border="1px dashed" borderColor="gray.200">
            <VStack align="stretch" gap={4}>
              {COMING_SOON.map((item) => (
                <HStack key={item.label} justify="space-between" align="start" gap={4}>
                  <Box flex={1}>
                    <Text fontSize="sm" fontWeight="medium" color="gray.500">{item.label}</Text>
                    <Text fontSize="xs" color="gray.400" mt={0.5}>{item.description}</Text>
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
