"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Box, Flex, Text, Input, VStack, HStack, Spinner } from "@chakra-ui/react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import {
  fetchConversations,
  fetchConversation,
  createConversation,
  streamMessage,
  deleteConversation,
  type ConversationSummary,
  type Message,
  type Trip,
} from "@/lib/api";

function TripActionCard({ trip, action }: { trip: Trip; action: "trip_created" | "trip_updated" }) {
  const router = useRouter();
  return (
    <Box
      mt={2}
      px={4}
      py={3}
      bg="accent.activeBg"
      borderRadius="xl"
      border="1px solid"
      borderColor="accent.active"
      display="flex"
      alignItems="center"
      justifyContent="space-between"
      gap={4}
    >
      <HStack gap={3}>
        <Text fontSize="xl" lineHeight="1">{trip.emoji}</Text>
        <Box>
          <Text fontSize="xs" fontWeight="700" letterSpacing="0.08em" textTransform="uppercase" color="accent.active" mb={0.5}>
            {action === "trip_created" ? "Trip saved" : "Trip updated"}
          </Text>
          <Text fontSize="sm" fontWeight="600" color="text.bright">{trip.destination}</Text>
          <Text fontSize="xs" color="text.dim">{trip.dates}</Text>
        </Box>
      </HStack>
      <Box
        as="button"
        onClick={() => router.push(`/trips/${trip.id}`)}
        px={3}
        py={1.5}
        bg="accent.active"
        color="bg.page"
        borderRadius="full"
        fontSize="xs"
        fontWeight="700"
        _hover={{ opacity: 0.88 }}
        transition="opacity 0.15s"
        flexShrink={0}
      >
        View →
      </Box>
    </Box>
  );
}

export default function ChatPage() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [steps, setSteps] = useState<string[]>([]);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchConversations().then(setConversations).catch(console.error);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, steps]);

  const openConversation = useCallback(async (id: string) => {
    setActiveId(id);
    setLoadingConversation(true);
    try {
      const conv = await fetchConversation(id);
      setMessages(conv.messages);
    } catch {
      setMessages([]);
    } finally {
      setLoadingConversation(false);
    }
  }, []);

  async function handleNewChat() {
    const conv = await createConversation();
    setConversations((prev) => [conv, ...prev]);
    setActiveId(conv.id);
    setMessages([]);
  }

  async function handleDelete(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    await deleteConversation(id);
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (activeId === id) {
      setActiveId(null);
      setMessages([]);
    }
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || loading || !activeId) return;

    const optimisticUser: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUser]);
    setInput("");
    setLoading(true);
    setSteps([]);

    const conversationId = activeId;
    try {
      for await (const event of streamMessage(conversationId, text)) {
        if (event.event === "step") {
          setSteps((prev) => [...prev, event.data.label]);
        } else if (event.event === "done") {
          setMessages((prev) => [...prev, event.data]);
          setConversations((prev) =>
            prev.map((c) =>
              c.id === conversationId
                ? { ...c, title: text.slice(0, 60) + (text.length > 60 ? "…" : ""), updated_at: new Date().toISOString() }
                : c
            )
          );
        } else if (event.event === "error") {
          throw new Error(event.data.detail);
        }
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "Something went wrong. Is the backend running?",
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setLoading(false);
      setSteps([]);
    }
  }

  return (
    <Flex h="100vh">
      {/* Conversation list panel */}
      <Flex
        direction="column"
        w="280px"
        flexShrink={0}
        borderRight="1px solid"
        borderColor="border.default"
        bg="bg.subtle"
      >
        <Box px={5} pt={6} pb={4} borderBottom="1px solid" borderColor="border.default">
          <Text fontSize="xs" fontWeight="600" letterSpacing="0.1em" textTransform="uppercase" color="text.secondary" mb={3}>
            Conversations
          </Text>
          <Box
            as="button"
            onClick={handleNewChat}
            w="full"
            py={2.5}
            px={4}
            bg="accent.active"
            color="bg.page"
            borderRadius="full"
            fontSize="sm"
            fontWeight="700"
            textAlign="center"
            _hover={{ opacity: 0.88 }}
            display="flex"
            alignItems="center"
            justifyContent="center"
            gap={2}
            transition="opacity 0.15s"
          >
            <Text>+ New chat</Text>
          </Box>
        </Box>

        <VStack flex={1} overflowY="auto" gap={0} align="stretch" py={3} px={3}>
          {conversations.length === 0 && (
            <Text fontSize="xs" color="text.secondary" px={2} py={3}>
              No conversations yet
            </Text>
          )}
          {conversations.map((conv) => (
            <Box
              key={conv.id}
              px={3}
              py={3}
              borderRadius="xl"
              cursor="pointer"
              bg={activeId === conv.id ? "bg.surface" : "transparent"}
              _hover={{ bg: "bg.surface" }}
              onClick={() => openConversation(conv.id)}
              role="group"
              position="relative"
              transition="background 0.1s"
            >
              <Text fontSize="sm" fontWeight={activeId === conv.id ? "600" : "400"} color="text.primary" pr={6} overflow="hidden" textOverflow="ellipsis" whiteSpace="nowrap" letterSpacing="-0.01em">
                {conv.title}
              </Text>
              <Text fontSize="xs" color="text.secondary" mt={0.5} letterSpacing="0.01em">
                {new Date(conv.updated_at).toLocaleDateString()}
              </Text>
              <Box
                as="button"
                position="absolute"
                right={2}
                top="50%"
                transform="translateY(-50%)"
                opacity={0}
                _groupHover={{ opacity: 1 }}
                onClick={(e: React.MouseEvent) => handleDelete(conv.id, e)}
                color="text.secondary"
                _hover={{ color: "red.400" }}
                fontSize="sm"
                lineHeight={1}
                transition="opacity 0.1s"
              >
                ×
              </Box>
            </Box>
          ))}
        </VStack>
      </Flex>

      {/* Chat area */}
      <Flex direction="column" flex={1} minW={0}>
        <Box px={8} py={5} borderBottom="1px solid" borderColor="border.default">
          <Text fontSize="xl" fontWeight="800" letterSpacing="-0.03em">
            Chat with Voyager
          </Text>
          <Text fontSize="xs" color="text.secondary" mt={0.5} letterSpacing="0.06em" textTransform="uppercase" fontWeight="500">
            Your AI travel companion
          </Text>
        </Box>

        <VStack flex={1} overflowY="auto" px={8} py={6} align="stretch" gap={5}>
          {!activeId && (
            <Flex h="full" align="center" justify="center">
              <Box textAlign="center">
                <Text fontSize="3xl" mb={3}>🧭</Text>
                <Text color="text.primary" fontSize="lg" fontWeight="700" letterSpacing="-0.02em" mb={1}>Where to next?</Text>
                <Text color="text.secondary" fontSize="sm">Start a new chat or pick one from the left</Text>
              </Box>
            </Flex>
          )}

          {activeId && loadingConversation && (
            <Flex justify="center" pt={8}>
              <Spinner color="accent.active" />
            </Flex>
          )}

          {activeId && !loadingConversation && messages.length === 0 && (
            <Flex h="full" align="center" justify="center">
              <Box textAlign="center">
                <Text fontSize="3xl" mb={3}>🧭</Text>
                <Text color="text.primary" fontSize="lg" fontWeight="700" letterSpacing="-0.02em" mb={1}>Where are we going?</Text>
                <Text color="text.secondary" fontSize="sm">Ask me anything about a destination.</Text>
              </Box>
            </Flex>
          )}

          {messages.map((msg) => (
            <Box key={msg.id}>
              <Flex
                justify={msg.role === "user" ? "flex-end" : "flex-start"}
                align="flex-end"
                gap={3}
              >
                {msg.role === "assistant" && (
                  <Box
                    w={8}
                    h={8}
                    borderRadius="full"
                    bg="accent.active"
                    display="flex"
                    alignItems="center"
                    justifyContent="center"
                    flexShrink={0}
                  >
                    <Text fontSize="xs">🧭</Text>
                  </Box>
                )}
                <Box
                  maxW="68%"
                  px={5}
                  py={3.5}
                  borderRadius="2xl"
                  bg={msg.role === "user" ? "bubble.user" : "bubble.assistant"}
                  color="text.primary"
                  boxShadow="0 2px 12px rgba(0,0,0,0.18)"
                  borderBottomRightRadius={msg.role === "user" ? "sm" : "2xl"}
                  borderBottomLeftRadius={msg.role === "assistant" ? "sm" : "2xl"}
                >
                  {msg.role === "user" ? (
                    <Text fontSize="sm" lineHeight="1.65">
                      {msg.content}
                    </Text>
                  ) : (
                    <Box fontSize="sm" lineHeight="1.65" className="markdown">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </Box>
                  )}
                </Box>
              </Flex>
              {msg.trip_action && (
                <Flex justify="flex-start" pl={11} mt={1}>
                  <Box maxW="68%">
                    <TripActionCard trip={msg.trip_action.trip} action={msg.trip_action.action} />
                  </Box>
                </Flex>
              )}
            </Box>
          ))}

          {loading && (
            <Flex align="flex-end" gap={3}>
              <Box
                w={8}
                h={8}
                borderRadius="full"
                bg="accent.active"
                display="flex"
                alignItems="center"
                justifyContent="center"
                flexShrink={0}
              >
                <Text fontSize="xs">🧭</Text>
              </Box>
              <Box bg="bubble.assistant" px={5} py={3.5} borderRadius="2xl" borderBottomLeftRadius="sm" boxShadow="0 2px 12px rgba(0,0,0,0.18)" minW="200px">
                <VStack align="stretch" gap={1.5}>
                  {steps.slice(0, -1).map((label, i) => (
                    <HStack key={i} gap={2}>
                      <Text fontSize="xs" color="accent.active" flexShrink={0}>✓</Text>
                      <Text fontSize="sm" color="text.secondary" opacity={0.6}>{label}</Text>
                    </HStack>
                  ))}
                  <HStack gap={2}>
                    <Spinner size="xs" color="accent.active" flexShrink={0} />
                    <Text fontSize="sm" color="text.secondary">
                      {steps.length > 0 ? steps[steps.length - 1] : "Thinking…"}
                    </Text>
                  </HStack>
                </VStack>
              </Box>
            </Flex>
          )}

          <div ref={bottomRef} />
        </VStack>

        <Box px={8} py={5} borderTop="1px solid" borderColor="border.default">
          <HStack gap={3}>
            <Input
              placeholder={activeId ? "Ask about a destination, plan a trip…" : "Start a new chat to begin"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              borderRadius="full"
              bg="bg.surface"
              color="text.primary"
              fontSize="sm"
              px={5}
              disabled={loading || !activeId}
              _focus={{ bg: "bg.surface", borderColor: "accent.active" }}
            />
            <Box
              as="button"
              onClick={handleSend}
              bg={loading || !activeId ? "bg.muted" : "accent.active"}
              color="bg.page"
              borderRadius="full"
              w={10}
              h={10}
              display="flex"
              alignItems="center"
              justifyContent="center"
              fontWeight="700"
              fontSize="lg"
              _hover={{ opacity: loading || !activeId ? 1 : 0.88 }}
              flexShrink={0}
              cursor={loading || !activeId ? "not-allowed" : "pointer"}
              transition="opacity 0.15s"
            >
              ↑
            </Box>
          </HStack>
        </Box>
      </Flex>
    </Flex>
  );
}
