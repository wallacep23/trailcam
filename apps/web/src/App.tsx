import type { ComponentType } from "react";

import { HealthBadge } from "./components/HealthBadge";
import { AnalyticsPage } from "./features/analytics/AnalyticsPage";
import { ClipsPage } from "./features/clips/ClipsPage";
import { ForecastPage } from "./features/forecast/ForecastPage";
import { HighlightsPage } from "./features/highlights/HighlightsPage";
import { IndividualsPage } from "./features/individuals/IndividualsPage";
import { IngestPage } from "./features/ingest/IngestPage";
import { JobsPage } from "./features/jobs/JobsPage";
import { MapPage } from "./features/map/MapPage";
import { ReplayPage } from "./features/map/ReplayPage";
import { ReviewPage } from "./features/review/ReviewPage";
import { SetupPage } from "./features/setup/SetupPage";
import { SCREENS } from "./lib/screens";
import { useHashRoute } from "./lib/useHashRoute";

const PAGES: Record<string, ComponentType> = {
  setup: SetupPage,
  ingest: IngestPage,
  clips: ClipsPage,
  review: ReviewPage,
  map: MapPage,
  analytics: AnalyticsPage,
  individuals: IndividualsPage,
  highlights: HighlightsPage,
  replay: ReplayPage,
  forecast: ForecastPage,
  jobs: JobsPage,
};

export function App() {
  const [route, navigate] = useHashRoute();
  const Page = PAGES[route] ?? JobsPage;
  return (
    <div className="flex h-full">
      <aside className="flex w-52 shrink-0 flex-col border-r border-bark-800 bg-bark-900">
        <div className="flex items-center gap-2 px-4 py-4">
          <img src="/favicon.svg" alt="" className="size-6" />
          <span className="text-sm font-semibold tracking-tight">Trail Camera Analyzer</span>
        </div>
        <nav className="flex-1 space-y-0.5 px-2" aria-label="Screens">
          {SCREENS.map((s) => {
            const active = s.id === route;
            return (
              <a
                key={s.id}
                href={`#/${s.id}`}
                aria-current={active ? "page" : undefined}
                onClick={(e) => {
                  e.preventDefault();
                  navigate(s.id);
                }}
                className={`flex items-center justify-between rounded-md px-3 py-1.5 text-sm ${
                  active ? "bg-bark-800 text-bark-100" : "text-bark-300 hover:bg-bark-850 hover:text-bark-100"
                }`}
              >
                {s.label}
                {s.milestone !== "M0" && (
                  <span className="text-[10px] font-medium text-bark-500">{s.milestone}</span>
                )}
              </a>
            );
          })}
        </nav>
        <div className="border-t border-bark-800 px-4 py-3">
          <HealthBadge />
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto px-8 py-8">
        <Page />
      </main>
    </div>
  );
}
