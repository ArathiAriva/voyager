import { Box, VStack, Text, HStack, Switch } from "@chakra-ui/react";

export default function SettingsPage() {
  return (
    <Box p={8} maxW="560px">
      <VStack align="start" gap={8} w="full">
        <Box>
          <Text fontSize="2xl" fontWeight="bold">
            Settings
          </Text>
          <Text color="gray.500" fontSize="sm">
            Configure your Voyager experience.
          </Text>
        </Box>

        <VStack align="stretch" gap={4} w="full">
          <Text fontSize="sm" fontWeight="semibold" color="gray.500" textTransform="uppercase" letterSpacing="wide">
            Memory
          </Text>
          <Box bg="white" borderRadius="xl" p={5} boxShadow="sm" border="1px solid" borderColor="gray.100">
            <VStack align="stretch" gap={4}>
              {[
                { label: "Save journal entries to memory", description: "Voyager learns from what you write" },
                { label: "Build preference profile", description: "Infer your travel style over time" },
                { label: "Generate reflections", description: "Periodic summaries of your travel patterns" },
              ].map((item) => (
                <HStack key={item.label} justify="space-between">
                  <Box>
                    <Text fontSize="sm" fontWeight="medium">{item.label}</Text>
                    <Text fontSize="xs" color="gray.400">{item.description}</Text>
                  </Box>
                  <Switch.Root defaultChecked colorPalette="blue">
                    <Switch.HiddenInput />
                    <Switch.Control>
                      <Switch.Thumb />
                    </Switch.Control>
                  </Switch.Root>
                </HStack>
              ))}
            </VStack>
          </Box>

          <Text fontSize="sm" fontWeight="semibold" color="gray.500" textTransform="uppercase" letterSpacing="wide" mt={2}>
            AI Model
          </Text>
          <Box bg="white" borderRadius="xl" p={5} boxShadow="sm" border="1px solid" borderColor="gray.100">
            <Text fontSize="sm" color="gray.500">Model configuration coming in a future phase.</Text>
          </Box>
        </VStack>
      </VStack>
    </Box>
  );
}
