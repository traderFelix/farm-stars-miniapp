export const INFO_HINTS = {
  releaseSubscriptionSlot:
    "Для освобождения слота необходимо завершить или удалить минимум одно из активных заданий",
} as const;

export type InfoHintKey = keyof typeof INFO_HINTS;
