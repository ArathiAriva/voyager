import { Box, VStack, Text, HStack } from "@chakra-ui/react";

const PLACEHOLDER_ENTRIES = [
  {
    id: "1",
    date: "March 18, 2025",
    location: "Kyoto, Japan",
    emoji: "🏯",
    content:
      "Walked through Fushimi Inari at dawn before the crowds arrived. The thousands of torii gates disappearing into the mist felt like stepping into another world. Realized I travel best when I slow down.",
  },
  {
    id: "2",
    date: "March 21, 2025",
    location: "Arashiyama, Japan",
    emoji: "🎋",
    content:
      "The bamboo grove is somehow more alive in person than any photo suggests. Had lunch at a tiny place with no English menu — pointed at something and got the best meal of the trip.",
  },
  {
    id: "3",
    date: "August 12, 2025",
    location: "Sintra, Portugal",
    emoji: "🏰",
    content:
      "Day trip from Lisbon. The Pena Palace looks like it was designed by a child who was given unlimited colored paint. Loved it unironically.",
  },
];

export default function JournalPage() {
  return (
    <Box p={8} maxW="720px">
      <VStack align="start" gap={6} w="full">
        <Box>
          <Text fontSize="2xl" fontWeight="bold">
            Travel Journal
          </Text>
          <Text color="gray.500" fontSize="sm">
            Moments worth keeping.
          </Text>
        </Box>

        <VStack align="stretch" gap={0} w="full">
          {PLACEHOLDER_ENTRIES.map((entry, i) => (
            <Box key={entry.id}>
              <Box
                py={6}
                _hover={{ bg: "gray.50" }}
                borderRadius="lg"
                px={3}
                cursor="pointer"
                transition="background 0.15s"
              >
                <HStack gap={3} mb={2} align="center">
                  <Text fontSize="xl">{entry.emoji}</Text>
                  <Box>
                    <Text fontSize="sm" fontWeight="semibold" color="gray.700">
                      {entry.location}
                    </Text>
                    <Text fontSize="xs" color="gray.400">
                      {entry.date}
                    </Text>
                  </Box>
                </HStack>
                <Text fontSize="sm" color="gray.700" lineHeight="tall" pl={9}>
                  {entry.content}
                </Text>
              </Box>
              {i < PLACEHOLDER_ENTRIES.length - 1 && (
                <Box h="1px" bg="gray.100" mx={3} />
              )}
            </Box>
          ))}
        </VStack>

        <Box
          w="full"
          py={4}
          textAlign="center"
          color="gray.400"
          fontSize="sm"
          cursor="pointer"
          _hover={{ color: "blue.500" }}
          borderRadius="lg"
          border="1px dashed"
          borderColor="gray.200"
        >
          + Write a new entry
        </Box>
      </VStack>
    </Box>
  );
}
