"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Loader2, Play, Square, Volume2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { apiFetch, apiUrl } from "@/lib/api";

interface TtsVoiceCardProps {
  summary: string;
  isExpanded: boolean;
  onToggleExpand: () => void;
  language?: string;
}

export const TtsVoiceCard = memo(function TtsVoiceCard({
  summary,
  isExpanded,
  onToggleExpand,
}: TtsVoiceCardProps) {
  const { t } = useTranslation();
  const [playbackState, setPlaybackState] = useState<"idle" | "loading" | "playing">("idle");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);

  const cleanup = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => cleanup();
  }, [cleanup]);

  const handlePlayToggle = useCallback(async () => {
    if (playbackState === "playing" || playbackState === "loading") {
      cleanup();
      setPlaybackState("idle");
      return;
    }

    setPlaybackState("loading");
    try {
      const resp = await apiFetch(apiUrl("/api/voice/tts"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: summary }),
      });

      if (!resp.ok) {
        cleanup();
        setPlaybackState("idle");
        return;
      }

      const blob = await resp.blob();
      cleanup();
      const url = URL.createObjectURL(blob);
      urlRef.current = url;
      const audio = new Audio(url);
      audioRef.current = audio;

      audio.onended = () => {
        setPlaybackState("idle");
        cleanup();
      };
      audio.onerror = () => {
        setPlaybackState("idle");
        cleanup();
      };

      await audio.play();
      setPlaybackState("playing");
    } catch {
      cleanup();
      setPlaybackState("idle");
    }
  }, [cleanup, playbackState, summary]);

  return (
    <div className="mb-4 rounded-xl border border-blue-500/20 bg-blue-500/5 p-4 backdrop-blur-sm dark:border-blue-400/20 dark:bg-blue-950/20">
      {/* Header */}
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-blue-600 dark:text-blue-400">
          <Volume2 className="h-4 w-4" />
          <span>{t("Voice Summary", "AI Voice Summary")}</span>
          {playbackState === "playing" && (
            <span className="flex items-center gap-0.5 ml-1">
              <span className="inline-block h-3 w-0.5 animate-pulse bg-blue-600 dark:bg-blue-400" />
              <span className="inline-block h-4 w-0.5 animate-pulse bg-blue-600 dark:bg-blue-400 [animation-delay:150ms]" />
              <span className="inline-block h-2 w-0.5 animate-pulse bg-blue-600 dark:bg-blue-400 [animation-delay:300ms]" />
            </span>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handlePlayToggle}
            className="flex items-center gap-1.5 rounded-lg border border-blue-500/30 bg-blue-500/10 px-2.5 py-1 text-xs font-medium text-blue-700 transition hover:bg-blue-500/20 dark:text-blue-300"
            title={playbackState === "playing" ? t("Stop", "Dừng") : t("Play", "Phát")}
          >
            {playbackState === "loading" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : playbackState === "playing" ? (
              <>
                <Square className="h-3 w-3 fill-current" />
                <span>{t("Stop", "Dừng")}</span>
              </>
            ) : (
              <>
                <Play className="h-3 w-3 fill-current" />
                <span>{t("Listen", "Nghe")}</span>
              </>
            )}
          </button>

          <button
            type="button"
            onClick={onToggleExpand}
            className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-[var(--muted-foreground)] transition hover:bg-[var(--accent)] hover:text-[var(--foreground)]"
          >
            {isExpanded ? (
              <>
                <span>{t("Show less", "Thu gọn")}</span>
                <ChevronUp className="h-3.5 w-3.5" />
              </>
            ) : (
              <>
                <span>{t("View full answer", "Xem đầy đủ")}</span>
                <ChevronDown className="h-3.5 w-3.5" />
              </>
            )}
          </button>
        </div>
      </div>

      {/* Summary Speech Text */}
      <div className="text-[15px] font-medium leading-relaxed text-[var(--foreground)]">
        &ldquo;{summary}&rdquo;
      </div>
    </div>
  );
});

TtsVoiceCard.displayName = "TtsVoiceCard";
export default TtsVoiceCard;
