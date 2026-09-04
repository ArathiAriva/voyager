"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Box, Flex, Text, Input, VStack, HStack, Spinner, Button } from "@chakra-ui/react";
import { ChevronLeftIcon } from "@/components/icons";
import { useRouter, useParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import {
  fetchConversation,
  streamMessage,
  deleteConversation,
  type Message,
  type Trip,
} from "@/lib/api";
import { useConfirm } from "@/components/confirm-dialog";

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
        View
      </Box>
    </Box>
  );
}

export default function ChatConversationPage() {
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;

  const { confirm, dialog } = useConfirm();
  const [messages, setMessages] = useState<Message[]>([]);
  const [title, setTitle] = useState("Chat");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [steps, setSteps] = useState<string[]>([]);
  const [loadingConversation, setLoadingConversation] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadConversation = useCallback(async () => {
    setLoadingConversation(true);
    try {
      const conv = await fetchConversation(id);
      setMessages(conv.messages);
      setTitle(conv.title);
    } catch {
      setMessages([]);
    } finally {
      setLoadingConversation(false);
    }
  }, [id]);

  useEffect(() => {
    loadConversation();
  }, [loadConversation]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleDelete() {
    const ok = await confirm({
      title: "Delete this conversation?",
      body: "The conversation and its messages will be removed. Memories already extracted from it are kept. This cannot be undone.",
      confirmLabel: "Delete chat",
    });
    if (!ok) return;
    setDeleting(true);
    try {
      await deleteConversation(id);
      router.push("/chats");
    } catch {
      setDeleting(false);
    }
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

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

    if (messages.length === 0) {
      setTitle(text.slice(0, 60) + (text.length > 60 ? "…" : ""));
    }

    try {
      for await (const event of streamMessage(id, text)) {
        if (event.event === "step") {
          setSteps((prev) => [...prev, event.data.label]);
        } else if (event.event === "done") {
          setMessages((prev) => [...prev, event.data]);
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
    <Flex direction="column" h="100vh">
      {dialog}
      {/* Header */}
      <Box px={8} py={5} borderBottom="1px solid" borderColor="border.default">
        <Flex align="center" gap={3}>
          <Button
            size="sm"
            variant="ghost"
            color="text.secondary"
            onClick={() => router.push("/chats")}
            _hover={{ bg: "bg.muted", color: "text.primary" }}
            flexShrink={0}
          >
            <ChevronLeftIcon />
            Chats
          </Button>
          <Box w="1px" h={4} bg="border.default" flexShrink={0} />
          <Box flex={1} minW={0}>
            <Text
              fontSize="sm"
              fontWeight="600"
              color="text.primary"
              overflow="hidden"
              textOverflow="ellipsis"
              whiteSpace="nowrap"
            >
              {title}
            </Text>
          </Box>
          <Box
            as="button"
            onClick={handleDelete}
            px={3}
            py={1.5}
            borderRadius="full"
            fontSize="xs"
            fontWeight="600"
            color="text.secondary"
            border="1px solid"
            borderColor="border.default"
            _hover={{ color: "red.400", borderColor: "red.400" }}
            transition="color 0.1s, border-color 0.1s"
            opacity={deleting ? 0.4 : 1}
            cursor={deleting ? "not-allowed" : "pointer"}
          >
            Delete chat
          </Box>
        </Flex>
      </Box>

      {/* Messages */}
      <VStack flex={1} overflowY="auto" px={8} py={6} align="stretch" gap={5}>
        {loadingConversation ? (
          <Flex justify="center" pt={8}>
            <Spinner color="accent.active" />
          </Flex>
        ) : messages.length === 0 ? (
          <Flex h="full" align="center" justify="center">
            <Box textAlign="center">
              <Text fontSize="3xl" mb={3}>🧭</Text>
              <Text color="text.primary" fontSize="lg" fontWeight="700" letterSpacing="-0.02em" mb={1}>Where are we going?</Text>
              <Text color="text.secondary" fontSize="sm">Ask me anything about a destination.</Text>
            </Box>
          </Flex>
        ) : null}

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

      {/* Input */}
      <Box px={8} py={5} borderTop="1px solid" borderColor="border.default">
        <HStack gap={3}>
          <Input
            placeholder="Ask about a destination, plan a trip…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            borderRadius="full"
            bg="bg.surface"
            color="text.primary"
            fontSize="sm"
            px={5}
            disabled={loading}
            _focus={{ bg: "bg.surface", borderColor: "accent.active" }}
          />
          <Box
            as="button"
            onClick={handleSend}
            bg={loading ? "bg.muted" : "accent.active"}
            color="bg.page"
            borderRadius="full"
            w={10}
            h={10}
            display="flex"
            alignItems="center"
            justifyContent="center"
            fontWeight="700"
            fontSize="lg"
            _hover={{ opacity: loading ? 1 : 0.88 }}
            flexShrink={0}
            cursor={loading ? "not-allowed" : "pointer"}
            transition="opacity 0.15s"
          >
            ↑
          </Box>
        </HStack>
      </Box>
    </Flex>
  );
}
