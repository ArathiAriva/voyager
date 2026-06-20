"use client";

import { useEffect, useState } from "react";
import { Box, VStack, HStack, Text, Badge, Grid, Spinner, Flex } from "@chakra-ui/react";
import { fetchMemories, type Memories } from "@/lib/api";

export default function MemoriesPage() {
  const [memories, setMemories] = useState<Memories | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMemories()
      .then(setMemories)
      .catch(() => setError("Couldn't load memories. Is the backend running?"))
      .finally(() => setLoading(false));
  }, []);

  const isEmpty = memories && memories.episodes.length === 0 && memories.preferences.length === 0;

  return (
    <Box p={8}>
      <VStack align="start" gap={6} w="full">
        <Box>
          <Text fontSize="2xl" fontWeight="bold">Memories</Text>
          <Text color="gray.500" fontSize="sm">What Voyager has learned about how you travel.</Text>
        </Box>

        {loading && (
          <Flex align="center" gap={2} color="gray.400">
            <Spinner size="sm" />
            <Text fontSize="sm">Loading memories...</Text>
          </Flex>
        )}

        {error && (
          <Box w="full" p={4} bg="red.50" borderRadius="lg" border="1px solid" borderColor="red.200">
            <Text fontSize="sm" color="red.600">{error}</Text>
          </Box>
        )}

        {isEmpty && (
          <Box py={16} w="full" textAlign="center" color="gray.400">
            <Text fontSize="3xl" mb={3}>🧠</Text>
            <Text fontSize="sm" fontWeight="medium">No memories yet.</Text>
            <Text fontSize="sm" mt={1}>
              Chat with Voyager or write journal entries and memories will build up here.
            </Text>
          </Box>
        )}

        {memories && memories.preferences.length > 0 && (
          <VStack align="stretch" gap={3} w="full">
            <Text fontSize="sm" fontWeight="semibold" color="gray.500" textTransform="uppercase" letterSpacing="wide">
              Preferences
            </Text>
            <Grid templateColumns="repeat(auto-fill, minmax(300px, 1fr))" gap={3} w="full">
              {memories.preferences.map((pref, i) => (
                <Box
                  key={i}
                  bg="white"
                  borderRadius="xl"
                  p={4}
                  boxShadow="sm"
                  border="1px solid"
                  borderColor="gray.100"
                >
                  <HStack mb={2}>
                    <Badge colorPalette="blue" borderRadius="full" px={2} size="sm">preference</Badge>
                  </HStack>
                  <Text fontSize="sm" color="gray.700" lineHeight="tall">{pref}</Text>
                </Box>
              ))}
            </Grid>
          </VStack>
        )}

        {memories && memories.episodes.length > 0 && (
          <VStack align="stretch" gap={3} w="full">
            <Text fontSize="sm" fontWeight="semibold" color="gray.500" textTransform="uppercase" letterSpacing="wide">
              Past conversations
            </Text>
            <VStack align="stretch" gap={2} w="full">
              {memories.episodes.map((ep, i) => (
                <Box
                  key={i}
                  bg="white"
                  borderRadius="xl"
                  p={4}
                  boxShadow="sm"
                  border="1px solid"
                  borderColor="gray.100"
                >
                  <HStack mb={2}>
                    <Badge colorPalette="purple" borderRadius="full" px={2} size="sm">episode</Badge>
                  </HStack>
                  <Text fontSize="sm" color="gray.700" lineHeight="tall">{ep}</Text>
                </Box>
              ))}
            </VStack>
          </VStack>
        )}
      </VStack>
    </Box>
  );
}
