"use client";

import { useEffect, useState } from "react";
import { Box, Flex, Grid, Text, VStack, HStack, Badge, Spinner } from "@chakra-ui/react";
import { fetchTrips, type Trip } from "@/lib/api";

export default function TripsPage() {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTrips()
      .then(setTrips)
      .catch(() => setError("Couldn't load trips. Is the backend running?"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Box p={8}>
      <VStack align="start" gap={6} w="full">
        <Box>
          <Text fontSize="2xl" fontWeight="bold">
            Your Trips
          </Text>
          <Text color="gray.500" fontSize="sm">
            Every journey, remembered.
          </Text>
        </Box>

        {loading && (
          <Flex align="center" gap={2} color="gray.400">
            <Spinner size="sm" />
            <Text fontSize="sm">Loading trips...</Text>
          </Flex>
        )}

        {error && (
          <Box w="full" p={4} bg="red.50" borderRadius="lg" border="1px solid" borderColor="red.200">
            <Text fontSize="sm" color="red.600">{error}</Text>
          </Box>
        )}

        {!loading && !error && (
          <Grid templateColumns="repeat(auto-fill, minmax(300px, 1fr))" gap={4} w="full">
            {trips.map((trip) => (
              <Box
                key={trip.id}
                bg="white"
                borderRadius="xl"
                p={5}
                boxShadow="sm"
                border="1px solid"
                borderColor="gray.100"
                _hover={{ boxShadow: "md", borderColor: "blue.100" }}
                transition="all 0.15s"
                cursor="pointer"
              >
                <HStack justify="space-between" mb={3}>
                  <Text fontSize="2xl">{trip.emoji}</Text>
                  <Badge
                    colorPalette={trip.status === "upcoming" ? "blue" : "gray"}
                    borderRadius="full"
                    px={2}
                  >
                    {trip.status}
                  </Badge>
                </HStack>
                <Text fontWeight="semibold" fontSize="lg">
                  {trip.destination}
                </Text>
                <Text fontSize="sm" color="gray.400" mb={2}>
                  {trip.dates}
                </Text>
                <Text fontSize="sm" color="gray.600" lineHeight="tall">
                  {trip.summary}
                </Text>
              </Box>
            ))}

            <Box
              bg="gray.50"
              borderRadius="xl"
              p={5}
              border="2px dashed"
              borderColor="gray.200"
              display="flex"
              alignItems="center"
              justifyContent="center"
              cursor="pointer"
              _hover={{ borderColor: "blue.300", bg: "blue.50" }}
              transition="all 0.15s"
              minH="160px"
            >
              <VStack gap={1} color="gray.400">
                <Text fontSize="2xl">+</Text>
                <Text fontSize="sm">Add a trip</Text>
              </VStack>
            </Box>
          </Grid>
        )}
      </VStack>
    </Box>
  );
}
