import { useEffect, useState } from "react";
import { api, type UploadedFile } from "../services/api";
import { Spinner, StatusBadge } from "./ui";

/** A small observed-image thumbnail (raster bytes or a rendered default slice). */
export function ImageTile({ upload, caption }: { upload: UploadedFile; caption?: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    let created: string | null = null;
    const raster = /\.(png|jpe?g|bmp)$/i.test(upload.filename);
    const request = raster ? api.getUploadObjectUrl(upload.id) : api.renderImagingSlice(upload.id, {}).then((result) => result.url);
    request.then(
      (objectUrl) => {
        created = objectUrl;
        if (cancelled) URL.revokeObjectURL(objectUrl);
        else setUrl(objectUrl);
      },
      (error: unknown) => !cancelled && setFailed(error instanceof Error ? error.message : String(error)),
    );
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [upload.id, upload.filename]);
  return (
    <figure className="min-w-0 overflow-hidden rounded-lg border border-line bg-surface">
      <div className="grid aspect-square place-items-center bg-black">
        {url ? <img src={url} alt={upload.filename} className="max-h-full max-w-full object-contain" /> : failed ? <span className="p-2 text-center text-[11px] text-white/70">{failed}</span> : <Spinner label="" />}
      </div>
      <figcaption className="flex items-center justify-between gap-1 p-1.5">
        <span className="truncate text-[11px] text-ink-2" title={upload.filename}>{caption ?? upload.filename}</span>
        <StatusBadge status="OBSERVED" />
      </figcaption>
    </figure>
  );
}
