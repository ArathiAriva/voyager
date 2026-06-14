"use client";

import { useState, useRef, useEffect } from "react";
import { Box, Flex, Text, Input, VStack, HStack, Spinner } from "@chakra-ui/react";
import { sendChat, type Message } from "@/lib/api";

const INITIAL_MESSAGES: Message[] = [
  {
    role: "assistant",
    content:
      "Hi! I'm Voyager, your AI travel companion. Tell me about a trip you're planning, or ask me anything about a destination.",
  },
];

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: Message = { role: "user", content: text };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput("");
    setLoading(true);

    try {
      const reply = await sendChat(nextMessages);
      setMessages((prev) => [...prev, reply]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Something went wrong. Is the backend running?" },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Flex direction="column" h="100vh">
      <Box px={6} py={4} borderBottom="1px solid" borderColor="gray.200" bg="white">
        <Text fontSize="lg" fontWeight="semibold">
          Chat with Voyager
        </Text>
        <Text fontSize="sm" color="gray.500">
          Your AI travel companion
        </Text>
      </Box>

      <VStack flex={1} overflowY="auto" px={6} py={4} align="stretch" gap={4}>
        {messages.map((msg, i) => (
          <Flex
            key={i}
            justify={msg.role === "user" ? "flex-end" : "flex-start"}
            align="flex-end"
            gap={2}
          >
            {msg.role === "assistant" && (
              <Box
                w={8}
                h={8}
                borderRadius="full"
                bg="blue.500"
                display="flex"
                alignItems="center"
                justifyContent="center"
                flexShrink={0}
              >
                <Text fontSize="sm">✈️</Text>
              </Box>
            )}
            <Box
              maxW="70%"
              px={4}
              py={3}
              borderRadius="xl"
              bg={msg.role === "user" ? "blue.500" : "white"}
              color={msg.role === "user" ? "white" : "gray.800"}
              boxShadow="sm"
              borderBottomRightRadius={msg.role === "user" ? "sm" : "xl"}
              borderBottomLeftRadius={msg.role === "assistant" ? "sm" : "xl"}
            >
              <Text fontSize="sm" lineHeight="tall">
                {msg.content}
              </Text>
            </Box>
          </Flex>
        ))}

        {loading && (
          <Flex align="flex-end" gap={2}>
            <Box
              w={8}
              h={8}
              borderRadius="full"
              bg="blue.500"
              display="flex"
              alignItems="center"
              justifyContent="center"
              flexShrink={0}
            >
              <Text fontSize="sm">✈️</Text>
            </Box>
            <Box bg="white" px={4} py={3} borderRadius="xl" boxShadow="sm">
              <Spinner size="sm" color="blue.400" />
            </Box>
          </Flex>
        )}

        <div ref={bottomRef} />
      </VStack>

      <Box px={6} py={4} borderTop="1px solid" borderColor="gray.200" bg="white">
        <HStack gap={2}>
          <Input
            placeholder="Ask about a destination, plan a trip..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            borderRadius="full"
            bg="gray.50"
            disabled={loading}
            _focus={{ bg: "white", borderColor: "blue.400" }}
          />
          <Box
            as="button"
            onClick={handleSend}
            bg={loading ? "gray.300" : "blue.500"}
            color="white"
            borderRadius="full"
            w={10}
            h={10}
            display="flex"
            alignItems="center"
            justifyContent="center"
            _hover={{ bg: loading ? "gray.300" : "blue.600" }}
            flexShrink={0}
            cursor={loading ? "not-allowed" : "pointer"}
          >
            ↑
          </Box>
        </HStack>
      </Box>
    </Flex>
  );
}
