import { Box, VStack, Text, HStack, Grid, Badge } from "@chakra-ui/react";

const PLACEHOLDER_MEMORIES = [
  {
    id: "1",
    type: "preference",
    content: "Prefers slow travel — fewer places, deeper immersion.",
    confidence: 0.94,
    source: "Kyoto journal entries",
  },
  {
    id: "2",
    type: "preference",
    content: "Dislikes tourist crowds; travels early morning or off-season when possible.",
    confidence: 0.89,
    source: "Fushimi Inari entry",
  },
  {
    id: "3",
    type: "insight",
    content: "Finds meaning in food as cultural access — willing to take risks on menus.",
    confidence: 0.82,
    source: "Arashiyama entry",
  },
  {
    id: "4",
    type: "fact",
    content: "Visited Kyoto in March 2025 during cherry blossom season.",
    confidence: 1.0,
    source: "Trip log",
  },
  {
    id: "5",
    type: "fact",
    content: "Visited Lisbon and Sintra in August 2025.",
    confidence: 1.0,
    source: "Trip log",
  },
  {
    id: "6",
    type: "insight",
    content: "Appreciates aesthetic absurdity — responds positively to places that are unabashedly themselves.",
    confidence: 0.76,
    source: "Sintra journal entry",
  },
];

const typeColor: Record<string, string> = {
  preference: "blue",
  insight: "purple",
  fact: "green",
};

export default function MemoriesPage() {
  return (
    <Box p={8}>
      <VStack align="start" gap={6} w="full">
        <Box>
          <Text fontSize="2xl" fontWeight="bold">
            Memories
          </Text>
          <Text color="gray.500" fontSize="sm">
            What Voyager has learned about how you travel.
          </Text>
        </Box>

        <Grid templateColumns="repeat(auto-fill, minmax(320px, 1fr))" gap={4} w="full">
          {PLACEHOLDER_MEMORIES.map((memory) => (
            <Box
              key={memory.id}
              bg="white"
              borderRadius="xl"
              p={5}
              boxShadow="sm"
              border="1px solid"
              borderColor="gray.100"
            >
              <HStack justify="space-between" mb={3}>
                <Badge colorPalette={typeColor[memory.type]} borderRadius="full" px={2}>
                  {memory.type}
                </Badge>
                <Text fontSize="xs" color="gray.400">
                  {Math.round(memory.confidence * 100)}% confidence
                </Text>
              </HStack>
              <Text fontSize="sm" color="gray.800" lineHeight="tall" mb={3}>
                {memory.content}
              </Text>
              <Text fontSize="xs" color="gray.400">
                Source: {memory.source}
              </Text>
            </Box>
          ))}
        </Grid>
      </VStack>
    </Box>
  );
}
