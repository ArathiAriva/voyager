"use client";

import { useState, useEffect } from "react";
import { Box, Flex, Text, VStack, HStack, Spinner } from "@chakra-ui/react";
import { useRouter } from "next/navigation";
import {
  fetchConversations,
  createConversation,
  deleteConversation,
  type ConversationSummary,
} from "@/lib/api";
import { CompassIcon } from "@/components/icons";
import { useConfirm } from "@/components/confirm-dialog";

function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return d.toLocaleDateString(undefined, { weekday: "long" });
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function ChatsPage() {
  const router = useRouter();
  const { confirm, dialog } = useConfirm();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetchConversations()
      .then(setConversations)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  async function handleNewChat() {
    setCreating(true);
    try {
      const conv = await createConversation();
      router.push(`/chats/${conv.id}`);
    } catch {
      setCreating(false);
    }
  }

  async function handleDelete(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    const ok = await confirm({
      title: "Delete this conversation?",
      body: "The conversation and its messages will be removed. Memories already extracted from it are kept. This cannot be undone.",
      confirmLabel: "Delete chat",
    });
    if (!ok) return;
    await deleteConversation(id);
    setConversations((prev) => prev.filter((c) => c.id !== id));
  }

  return (
    <Flex direction="column" flex={1} minH="100vh" bg="bg.page">
      {dialog}
      {/* Header */}
      <Box px={10} pt={10} pb={6}>
        <Flex align="end" justify="space-between">
          <Box>
            <Text fontSize="xs" fontWeight="600" letterSpacing="0.1em" textTransform="uppercase" color="text.secondary" mb={2}>
              Your conversations
            </Text>
            <Text fontSize="3xl" fontWeight="800" letterSpacing="-0.03em" lineHeight="1.1">
              Chats
            </Text>
          </Box>
          <Box
            as="button"
            onClick={handleNewChat}
            px={5}
            py={2.5}
            bg="accent.active"
            color="bg.page"
            borderRadius="full"
            fontSize="sm"
            fontWeight="700"
            _hover={{ opacity: 0.88 }}
            transition="opacity 0.15s"
            display="flex"
            alignItems="center"
            gap={2}
            cursor={creating ? "not-allowed" : "pointer"}
          >
            {creating ? <Spinner size="xs" /> : null}
            <Text>New chat</Text>
          </Box>
        </Flex>
      </Box>

      {/* Content */}
      <Box flex={1} px={10} pb={10}>
        {loading ? (
          <Flex justify="center" pt={16}>
            <Spinner color="accent.active" />
          </Flex>
        ) : conversations.length === 0 ? (
          <Flex direction="column" align="center" justify="center" pt={24} gap={3}>
            <Box color="text.muted" display="flex" justifyContent="center"><CompassIcon size={30} /></Box>
            <Text fontSize="lg" fontWeight="700" letterSpacing="-0.02em" color="text.bright">
              No chats yet
            </Text>
            <Text fontSize="sm" color="text.secondary" mb={4}>
              Start a conversation with your AI travel companion
            </Text>
            <Box
              as="button"
              onClick={handleNewChat}
              px={6}
              py={3}
              bg="accent.active"
              color="bg.page"
              borderRadius="full"
              fontSize="sm"
              fontWeight="700"
              _hover={{ opacity: 0.88 }}
              transition="opacity 0.15s"
            >
              Start a new chat
            </Box>
          </Flex>
        ) : (
          <VStack align="stretch" gap={0} maxW="3xl">
            {conversations.map((conv, i) => (
              <Box key={conv.id}>
                {i > 0 && (
                  <Box h="1px" bg="border.default" mx={0} />
                )}
                <Box
                  px={4}
                  py={4}
                  borderRadius="lg"
                  cursor="pointer"
                  role="group"
                  position="relative"
                  _hover={{ bg: "bg.subtle" }}
                  onClick={() => router.push(`/chats/${conv.id}`)}
                  transition="background 0.1s"
                >
                  <HStack justify="space-between" align="center">
                    <Box flex={1} minW={0}>
                      <Text
                        fontSize="sm"
                        fontWeight="500"
                        color="text.primary"
                        overflow="hidden"
                        textOverflow="ellipsis"
                        whiteSpace="nowrap"
                        pr={8}
                      >
                        {conv.title}
                      </Text>
                    </Box>
                    <Text fontSize="xs" color="text.secondary" flexShrink={0}>
                      {formatDate(conv.updated_at)}
                    </Text>
                  </HStack>
                  <Box
                    as="button"
                    position="absolute"
                    right={3}
                    top="50%"
                    transform="translateY(-50%)"
                    opacity={0}
                    _groupHover={{ opacity: 1 }}
                    onClick={(e: React.MouseEvent) => handleDelete(conv.id, e)}
                    color="text.secondary"
                    _hover={{ color: "red.400" }}
                    fontSize="lg"
                    lineHeight={1}
                    transition="opacity 0.1s"
                    w={6}
                    h={6}
                    display="flex"
                    alignItems="center"
                    justifyContent="center"
                    borderRadius="md"
                  >
                    ×
                  </Box>
                </Box>
              </Box>
            ))}
          </VStack>
        )}
      </Box>
    </Flex>
  );
}
