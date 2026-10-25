import { create } from "zustand";

export type TwinViewMode = "single" | "split" | "forecast";

type TwinState = {
  viewMode: TwinViewMode;
  horizon: number;
  selectedOrgan: string | null;
  hoveredOrgan: string | null;
  running: boolean;
  setViewMode: (viewMode: TwinViewMode) => void;
  setHorizon: (horizon: number) => void;
  selectOrgan: (selectedOrgan: string | null) => void;
  hoverOrgan: (hoveredOrgan: string | null) => void;
  setRunning: (running: boolean) => void;
};

export const useTwinStore = create<TwinState>((set) => ({
  viewMode: "single",
  horizon: 0,
  selectedOrgan: null,
  hoveredOrgan: null,
  running: false,
  setViewMode: (viewMode) => set((state) => ({ viewMode, horizon: viewMode === "split" ? 0 : state.horizon })),
  setHorizon: (horizon) => set({ horizon }),
  selectOrgan: (selectedOrgan) => set({ selectedOrgan }),
  hoverOrgan: (hoveredOrgan) => set({ hoveredOrgan }),
  setRunning: (running) => set({ running }),
}));
