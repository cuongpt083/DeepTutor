/**
 * Helper to extract and format TTS-optimized response summaries.
 *
 * When TTS summary mode is active, the assistant wraps its conversational
 * speech-ready summary in `<tts_summary>...</tts_summary>`. This utility
 * parses the summary and the remaining full response content.
 */

const TTS_SUMMARY_REGEX = /<tts_summary>([\s\S]*?)(?:<\/tts_summary>|$)/i;

export interface TtsSummaryResult {
  hasSummary: boolean;
  summary: string;
  fullContent: string;
  isStreamingSummary: boolean;
}

export function extractTtsSummary(rawContent: string): TtsSummaryResult {
  if (!rawContent) {
    return {
      hasSummary: false,
      summary: "",
      fullContent: "",
      isStreamingSummary: false,
    };
  }

  const match = TTS_SUMMARY_REGEX.exec(rawContent);
  if (!match) {
    return {
      hasSummary: false,
      summary: "",
      fullContent: rawContent,
      isStreamingSummary: false,
    };
  }

  const summary = match[1].trim();
  const hasCloseTag = rawContent.toLowerCase().includes("</tts_summary>");
  
  // Remove the <tts_summary> block from the main content
  const fullContent = rawContent.replace(TTS_SUMMARY_REGEX, "").trim();

  return {
    hasSummary: summary.length > 0,
    summary,
    fullContent,
    isStreamingSummary: !hasCloseTag,
  };
}
