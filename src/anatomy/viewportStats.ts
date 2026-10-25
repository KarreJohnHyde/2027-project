import { create } from "zustand";

export type ViewportStats = { fps: number | null; calls: number; triangles: number; points: number; geometries: number; textures: number; programs: number; heapMb: number | null; sampledAt: number };

/**
 * Written by the render loop, read only by the performance overlay. Keeping it
 * outside the viewport's props stops stats updates from re-rendering (and so
 * re-invalidating) the scene.
 */
export const useViewportStats = create<{ stats: ViewportStats | null; publish: (stats: ViewportStats) => void }>((set) => ({
  stats: null,
  publish: (stats) => set({ stats }),
}));
