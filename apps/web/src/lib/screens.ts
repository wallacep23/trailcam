/** The eleven screens of DESIGN §14, with the milestone that delivers each one. */
export interface Screen {
  id: string;
  label: string;
  milestone: string;
  summary: string;
}

export const SCREENS: readonly Screen[] = [
  { id: "setup", label: "Setup", milestone: "M1", summary: "Property, satellite map, sites with aliases and heading cones." },
  { id: "ingest", label: "Ingest", milestone: "M1", summary: "Add SD-card folders as deployments; preview, confirm, watch progress." },
  { id: "clips", label: "Clips", milestone: "M1", summary: "Browse every clip with filters and a detail drawer." },
  { id: "review", label: "Review", milestone: "M3", summary: "Rapid keyboard review of uncertain clips with TrailcamParser hotkeys." },
  { id: "map", label: "Map", milestone: "M4", summary: "Sites, heading cones, bearing roses and cross-camera links." },
  { id: "analytics", label: "Analytics", milestone: "M4", summary: "Activity clock, wind rose, heatmap and effort-normalized rates." },
  { id: "individuals", label: "Individuals", milestone: "M5", summary: "Named bucks, timelines, merge and split." },
  { id: "highlights", label: "Highlights", milestone: "M5", summary: "Big, returning and daylight bucks worth a look." },
  { id: "replay", label: "Replay", milestone: "M6", summary: "Conditions-matched history animated on the map." },
  { id: "forecast", label: "Forecast", milestone: "M6", summary: "Where to sit in the next three days, and why." },
  { id: "jobs", label: "Jobs", milestone: "M0", summary: "Pipeline jobs, progress and errors." },
] as const;

export const DEFAULT_SCREEN = "jobs";

export function getScreen(id: string): Screen {
  const screen = SCREENS.find((s) => s.id === id);
  if (!screen) throw new Error(`unknown screen ${id}`);
  return screen;
}
