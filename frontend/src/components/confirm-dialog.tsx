"use client";

import { useState, useCallback } from "react";
import { Button, Dialog, Portal, Text } from "@chakra-ui/react";

type ConfirmOptions = {
  title: string;
  /** What is about to happen, in the user's terms. Name what else gets removed. */
  body: string;
  /** Label for the destructive action, e.g. "Delete trip". */
  confirmLabel: string;
};

type PendingConfirm = ConfirmOptions & { resolve: (ok: boolean) => void };

/**
 * Confirmation for destructive actions (B-9). Deletes are unrecoverable here --
 * there is no undo, and deleting a trip takes its journal entries and saved
 * places with it -- so a single stray click must not be the whole safety story.
 *
 * Usage:
 *   const { confirm, dialog } = useConfirm();
 *   if (!(await confirm({ ... }))) return;
 *   ...then render {dialog} once in the component.
 */
export function useConfirm() {
  const [pending, setPending] = useState<PendingConfirm | null>(null);

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => setPending({ ...options, resolve }));
  }, []);

  const settle = useCallback((ok: boolean) => {
    setPending((current) => {
      current?.resolve(ok);
      return null;
    });
  }, []);

  const dialog = (
    <Dialog.Root
      open={pending !== null}
      onOpenChange={(e) => { if (!e.open) settle(false); }}
      role="alertdialog"
      placement="center"
    >
      <Portal>
        <Dialog.Backdrop />
        <Dialog.Positioner>
          <Dialog.Content borderRadius="xl" maxW="420px">
            <Dialog.Header pb={2}>
              <Dialog.Title fontSize="md" fontWeight="700">{pending?.title}</Dialog.Title>
            </Dialog.Header>
            <Dialog.Body py={2}>
              <Text fontSize="sm" color="text.secondary">{pending?.body}</Text>
            </Dialog.Body>
            <Dialog.Footer gap={2} pt={4}>
              <Button size="sm" variant="ghost" onClick={() => settle(false)}>
                Cancel
              </Button>
              <Button size="sm" colorPalette="red" onClick={() => settle(true)}>
                {pending?.confirmLabel}
              </Button>
            </Dialog.Footer>
          </Dialog.Content>
        </Dialog.Positioner>
      </Portal>
    </Dialog.Root>
  );

  return { confirm, dialog };
}
