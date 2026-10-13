import type { Screen } from "../lib/screens";

/** Stand-in for screens delivered by later milestones (DESIGN §17). */
export function Placeholder({ screen }: { screen: Screen }) {
  return (
    <section className="mx-auto mt-16 max-w-lg text-center">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-lamp-500">
        Arrives in {screen.milestone}
      </p>
      <h1 className="mt-3 text-2xl font-semibold text-bark-100">{screen.label}</h1>
      <p className="mt-3 text-sm leading-relaxed text-bark-300">{screen.summary}</p>
    </section>
  );
}
