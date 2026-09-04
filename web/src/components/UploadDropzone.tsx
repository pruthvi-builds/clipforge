"use client";

import { useCallback, useRef, useState } from "react";
import { fmtBytes } from "@/lib/format";

const ACCEPT = [".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"];

export function UploadDropzone({
  onFile,
  disabled,
  progress,
  fileName,
}: {
  onFile: (f: File) => void;
  disabled?: boolean;
  progress?: number | null;
  fileName?: string | null;
}) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = useCallback(
    (f?: File | null) => {
      if (!f) return;
      const ext = "." + (f.name.split(".").pop() || "").toLowerCase();
      if (!ACCEPT.includes(ext)) {
        alert(`Unsupported file type ${ext}. Supported: ${ACCEPT.join(", ")}`);
        return;
      }
      onFile(f);
    },
    [onFile],
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        if (!disabled) pick(e.dataTransfer.files?.[0]);
      }}
      onClick={() => !disabled && inputRef.current?.click()}
      className={`card grid cursor-pointer place-items-center px-6 py-16 text-center transition-colors ${
        drag ? "border-brand-500 bg-brand-500/5" : "hover:border-white/20"
      } ${disabled ? "pointer-events-none opacity-70" : ""}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT.join(",")}
        className="hidden"
        onChange={(e) => pick(e.target.files?.[0])}
      />
      <div className="mb-3 text-4xl opacity-40">⬆</div>
      <div className="text-lg font-medium">
        {fileName ? fileName : "Drop a video here"}
      </div>
      <div className="mt-1 text-sm text-ink-100/40">
        {fileName ? "" : "MP4, MOV, MKV and more"}
      </div>

      {typeof progress === "number" && (
        <div className="mt-5 w-full max-w-xs">
          <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full bg-brand-500 transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="mt-1.5 text-[11px] text-ink-100/40">
            Uploading… {progress}%
          </div>
        </div>
      )}
    </div>
  );
}

export { fmtBytes };
