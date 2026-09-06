"use client";

import { useEffect, useState } from "react";
import { Box, Button, Flex, Input, Text, VStack } from "@chakra-ui/react";
import { getToken, setToken, setUnauthorizedHandler } from "@/lib/api";
import { CompassIcon } from "@/components/icons";

/**
 * Prompts for the access token when the backend rejects a request.
 *
 * Not a login screen -- Voyager has no user model, and this is a shared token in
 * front of a single-tenant app (see backend/app/auth.py). It renders only after a
 * 401, so a local backend running without VOYAGER_AUTH_TOKEN never shows it.
 *
 * A real input rather than window.prompt(): this gets typed on a phone, where
 * paste needs to work properly and a native prompt is easy to dismiss by accident.
 */
export function UnlockGate({ children }: { children: React.ReactNode }) {
  const [locked, setLocked] = useState(false);
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setUnauthorizedHandler(() => setLocked(true));
    return () => setUnauthorizedHandler(null);
  }, []);

  function submit() {
    const token = value.trim();
    if (!token) return;
    setSaving(true);
    setToken(token);
    // Reload rather than retrying in place: every page has already-failed
    // requests in flight or in state, and re-fetching each one individually is
    // more code than it is worth for a screen shown once.
    window.location.reload();
  }

  if (!locked) return <>{children}</>;

  return (
    <Flex minH="100vh" align="center" justify="center" bg="bg.page" px={6}>
      <VStack gap={5} maxW="380px" w="full">
        <Box color="text.muted"><CompassIcon size={28} /></Box>
        <VStack gap={1}>
          <Text fontSize="xl" fontWeight="800" letterSpacing="-0.02em">Voyager</Text>
          <Text fontSize="sm" color="text.secondary" textAlign="center">
            {getToken()
              ? "That access token was rejected. Try again?"
              : "Enter your access token to continue."}
          </Text>
        </VStack>
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
          placeholder="Access token"
          type="password"
          autoComplete="current-password"
          autoFocus
          size="lg"
          bg="bg.surface"
        />
        <Button
          w="full"
          colorPalette="blue"
          loading={saving}
          disabled={!value.trim()}
          onClick={submit}
        >
          Unlock
        </Button>
        <Text fontSize="xs" color="text.muted" textAlign="center">
          Stored on this device only. Clearing site data means entering it again.
        </Text>
      </VStack>
    </Flex>
  );
}
