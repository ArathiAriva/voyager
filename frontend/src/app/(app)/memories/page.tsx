"use client";

import { useEffect, useState } from "react";
import { Box, VStack, Text, Grid, Spinner, Flex } from "@chakra-ui/react";
import { fetchMemories, type Memories } from "@/lib/api";
import { BrainIcon } from "@/components/icons";

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
    <Box p={10}>
      <VStack align="start" gap={8} w="full">
        <Box>
          <Text fontSize="xs" fontWeight="600" letterSpacing="0.1em" textTransform="uppercase" color="text.secondary" mb={2}>What Voyager knows</Text>
          <Text fontSize="3xl" fontWeight="800" letterSpacing="-0.03em" lineHeight="1.1">Memories</Text>
        </Box>

        {loading && (
          <Flex align="center" gap={2} color="text.secondary">
            <Spinner size="sm" />
            <Text fontSize="sm">Loading memories...</Text>
          </Flex>
        )}

        {error && (
          <Box w="full" p={4} bg="red.950" borderRadius="lg" border="1px solid" borderColor="red.800">
            <Text fontSize="sm" color="red.600">{error}</Text>
          </Box>
        )}

        {isEmpty && (
          <Box py={16} w="full" textAlign="center" color="text.secondary">
            <Box color="text.muted" display="flex" justifyContent="center" mb={3}><BrainIcon size={26} /></Box>
            <Text fontSize="sm" fontWeight="medium">No memories yet.</Text>
            <Text fontSize="sm" mt={1}>
              Chat with Voyager or write journal entries and memories will build up here.
            </Text>
          </Box>
        )}

        {memories && memories.preferences.length > 0 && (
          <VStack align="stretch" gap={3} w="full">
            <Text fontSize="sm" fontWeight="semibold" color="text.muted" textTransform="uppercase" letterSpacing="wide">
              Preferences
            </Text>
            <Grid templateColumns="repeat(auto-fill, minmax(300px, 1fr))" gap={3} w="full">
              {memories.preferences.map((pref, i) => (
                <Box
                  key={i}
                  bg="bg.surface"
                  borderRadius="2xl"
                  p={5}
                  boxShadow="0 4px 20px rgba(0,0,0,0.2)"
                  border="none"
                >
                  <Text fontSize="sm" color="text.dim" lineHeight="tall">{pref}</Text>
                </Box>
              ))}
            </Grid>
          </VStack>
        )}

        {memories && memories.episodes.length > 0 && (
          <VStack align="stretch" gap={3} w="full">
            <Text fontSize="sm" fontWeight="semibold" color="text.muted" textTransform="uppercase" letterSpacing="wide">
              Past conversations
            </Text>
            <VStack align="stretch" gap={2} w="full">
              {memories.episodes.map((ep, i) => (
                <Box
                  key={i}
                  bg="bg.surface"
                  borderRadius="2xl"
                  p={5}
                  boxShadow="0 4px 20px rgba(0,0,0,0.2)"
                  border="none"
                >
                  <Text fontSize="sm" color="text.dim" lineHeight="tall">{ep}</Text>
                </Box>
              ))}
            </VStack>
          </VStack>
        )}
      </VStack>
    </Box>
  );
}
