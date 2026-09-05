"use client";

import { useEffect, useState } from "react";
import { Box, VStack, Text, Grid, Spinner, Flex, IconButton } from "@chakra-ui/react";
import { fetchMemories, deleteMemory, type Memories, type MemoryRow } from "@/lib/api";
import { BrainIcon, CloseIcon } from "@/components/icons";
import { useConfirm } from "@/components/confirm-dialog";

/**
 * Both sections are Chroma collections, so they are named for what they are.
 * "Past conversations" was actively wrong: the episodic collection also holds one
 * summary per journal entry (keyed `journal-{entry_id}`), and on some profiles
 * those are the majority of rows. The source tag on each card resolves the
 * ambiguity the old heading hid.
 */
function SourceTag({ source }: { source: MemoryRow["source"] }) {
  const isJournal = source === "journal";
  return (
    <Box
      as="span"
      flexShrink={0}
      fontSize="10px"
      fontWeight="700"
      letterSpacing="0.08em"
      textTransform="uppercase"
      px={2}
      py="2px"
      borderRadius="full"
      color={isJournal ? "purple.300" : "blue.300"}
      bg={isJournal ? "purple.950" : "blue.950"}
    >
      {isJournal ? "Journal" : "Chat"}
    </Box>
  );
}

function MemoryCard({
  row,
  onDelete,
  busy,
}: {
  row: MemoryRow;
  onDelete: (row: MemoryRow) => void;
  busy: boolean;
}) {
  return (
    <Box
      position="relative"
      bg="bg.surface"
      borderRadius="2xl"
      p={5}
      boxShadow="0 4px 20px rgba(0,0,0,0.2)"
      border="none"
      opacity={busy ? 0.5 : 1}
      _hover={{ "& .memory-delete": { opacity: 1 } }}
    >
      <Flex align="start" gap={3}>
        <Text fontSize="sm" color="text.dim" lineHeight="tall" flex="1">
          {row.text}
        </Text>
        <SourceTag source={row.source} />
      </Flex>
      <IconButton
        className="memory-delete"
        aria-label="Forget this memory"
        size="2xs"
        variant="ghost"
        position="absolute"
        top={2}
        right={2}
        opacity={0}
        transition="opacity 0.15s"
        disabled={busy}
        onClick={() => onDelete(row)}
        _focusVisible={{ opacity: 1 }}
      >
        <CloseIcon size={12} />
      </IconButton>
    </Box>
  );
}

export default function MemoriesPage() {
  const { confirm, dialog } = useConfirm();
  const [memories, setMemories] = useState<Memories | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    fetchMemories()
      .then(setMemories)
      .catch(() => setError("Couldn't load memories. Is the backend running?"))
      .finally(() => setLoading(false));
  }, []);

  async function handleDelete(kind: "episodic" | "semantic", row: MemoryRow) {
    // Say what deleting does and does not do. Forgetting a memory leaves the
    // conversation or journal entry it came from intact, and a preference the
    // user keeps demonstrating can be re-derived by a later extraction.
    const isEpisode = kind === "episodic";
    const ok = await confirm({
      title: isEpisode ? "Forget this memory?" : "Forget this preference?",
      body: isEpisode
        ? `Voyager will forget this summary. The ${row.source === "journal" ? "journal entry" : "conversation"} it came from is not deleted. This cannot be undone.`
        : "Voyager will forget this preference. It may be learned again from future conversations or journal entries. This cannot be undone.",
      confirmLabel: "Forget",
    });
    if (!ok) return;

    setDeletingId(row.id);
    try {
      await deleteMemory(kind, row.id);
      setMemories((current) => {
        if (!current) return current;
        const key = isEpisode ? "episode_rows" : "preference_rows";
        const remaining = current[key].filter((r) => r.id !== row.id);
        return {
          ...current,
          [key]: remaining,
          [isEpisode ? "episodes" : "preferences"]: remaining.map((r) => r.text),
        };
      });
    } catch {
      setError("Couldn't forget that memory. Is the backend running?");
    } finally {
      setDeletingId(null);
    }
  }

  const preferenceRows = memories?.preference_rows ?? [];
  const episodeRows = memories?.episode_rows ?? [];
  const isEmpty = memories && preferenceRows.length === 0 && episodeRows.length === 0;

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

        {preferenceRows.length > 0 && (
          <VStack align="stretch" gap={3} w="full">
            <Box>
              <Text fontSize="sm" fontWeight="semibold" color="text.muted" textTransform="uppercase" letterSpacing="wide">
                Semantic
              </Text>
              <Text fontSize="xs" color="text.secondary" mt={1}>
                Durable preferences distilled from what you say and write.
              </Text>
            </Box>
            <Grid templateColumns="repeat(auto-fill, minmax(300px, 1fr))" gap={3} w="full">
              {preferenceRows.map((row) => (
                <MemoryCard
                  key={row.id}
                  row={row}
                  busy={deletingId === row.id}
                  onDelete={(r) => handleDelete("semantic", r)}
                />
              ))}
            </Grid>
          </VStack>
        )}

        {episodeRows.length > 0 && (
          <VStack align="stretch" gap={3} w="full">
            <Box>
              <Text fontSize="sm" fontWeight="semibold" color="text.muted" textTransform="uppercase" letterSpacing="wide">
                Episodic
              </Text>
              <Text fontSize="xs" color="text.secondary" mt={1}>
                One summary per conversation and per journal entry.
              </Text>
            </Box>
            <VStack align="stretch" gap={2} w="full">
              {episodeRows.map((row) => (
                <MemoryCard
                  key={row.id}
                  row={row}
                  busy={deletingId === row.id}
                  onDelete={(r) => handleDelete("episodic", r)}
                />
              ))}
            </VStack>
          </VStack>
        )}
      </VStack>
      {dialog}
    </Box>
  );
}
