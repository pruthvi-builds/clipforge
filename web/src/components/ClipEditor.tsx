"use client";

import { useState } from "react";
import type { Clip } from "@/lib/types";

const CAPTIONS = ["bold", "clean", "karaoke", "minimal", "highlight"];
const REFRAMES = [
  ["smart_auto", "Smart Auto"],
  ["center", "Center"],
  ["face", "Face Tracking"],
  ["speaker", "Speaker Tracking"],
];

export function ClipEditor({
  clip,
  onClose,
  onApply,
}: {
  clip: Clip;
  onClose: () => void;
  onApply: (body: Record<string, unknown>) => void;
}) {
  const [start, setStart] = useState(clip.start);
  const [end, setEnd] = useState(clip.end);
  const [hook, setHook] = useState(clip.hook);
  const [opening, setOpening] = useState(clip.opening_text);
  const [captionStyle, setCaptionStyle] = useState("bold");
  const [reframe, setReframe] = useState("smart_auto");
  const [useCaptions, setUseCaptions] = useState(true);
  const [highlights, setHighlights] = useState((clip.emphasis_words || []).join(", "));

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4">
      <div className="card w-full max-w-lg p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold">Edit clip #{clip.idx}</h3>
          <button onClick={onClose} className="text-ink-100/40 hover:text-ink-100">
            ✕
          </button>
        </div>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="label">Trim start (s)</span>
              <input
                type="number"
                step="0.1"
                className="input"
                value={start}
                onChange={(e) => setStart(Number(e.target.value))}
              />
            </label>
            <label className="block">
              <span className="label">Trim end (s)</span>
              <input
                type="number"
                step="0.1"
                className="input"
                value={end}
                onChange={(e) => setEnd(Number(e.target.value))}
              />
            </label>
          </div>

          <label className="block">
            <span className="label">Hook text</span>
            <input
              className="input"
              value={hook}
              onChange={(e) => setHook(e.target.value)}
              maxLength={120}
            />
          </label>

          <label className="block">
            <span className="label">On-screen opening text</span>
            <input
              className="input"
              value={opening}
              onChange={(e) => setOpening(e.target.value)}
              maxLength={80}
            />
          </label>

          <label className="block">
            <span className="label">Highlight words (comma separated)</span>
            <input
              className="input"
              value={highlights}
              onChange={(e) => setHighlights(e.target.value)}
              placeholder="mistake, three years, wrong"
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="label">Caption style</span>
              <select
                className="input"
                value={captionStyle}
                onChange={(e) => setCaptionStyle(e.target.value)}
              >
                {CAPTIONS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="label">Reframe</span>
              <select
                className="input"
                value={reframe}
                onChange={(e) => setReframe(e.target.value)}
              >
                {REFRAMES.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={useCaptions}
              onChange={(e) => setUseCaptions(e.target.checked)}
            />
            Burn captions
          </label>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn-primary"
            onClick={() =>
              onApply({
                start,
                end,
                hook,
                opening_text: opening,
                caption_style: captionStyle,
                reframe_mode: reframe,
                use_captions: useCaptions,
                highlight_words: highlights
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
          >
            Save & re-render
          </button>
        </div>
      </div>
    </div>
  );
}
