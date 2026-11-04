import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Logo } from "../components/ui";
import { fileUrl, get } from "../lib/api";

const STEPS = [
  ["01", "Record", "Mount a phone on the windscreen and drive the road. The capture page logs GPS every second while it films. Existing dashcam video and photos work too."],
  ["02", "Find and measure", "Every pothole, crack and open drain is outlined and tracked across frames, then measured on the road plane in square metres, with a stated range."],
  ["03", "Rank by risk", "Each site is scored by how bad the damage is and who uses the road: schools, clinics and bus stops nearby, the road's class, and the inspector's own voice notes."],
  ["04", "Issue the work", "Work orders, a bill of quantities and a request for quotation come out ready to send. Every line points back to a photo of the defect it pays for."],
];

const OUTPUTS = [
  ["Condition map", "The driven road coloured segment by segment, with repair sites ranked."],
  ["Defect register", "Type, size, position in the lane and evidence image for every defect."],
  ["Work orders", "One per site, with treatment, quantities and cost."],
  ["Tender pack", "Bill of quantities and RFQ for the whole survey, as PDF."],
];

export default function Landing() {
  const [demo, setDemo] = useState<{ id: string; video?: string } | null>(null);
  useEffect(() => {
    get<any[]>("/api/runs").then(async (runs) => {
      const r = runs.find((x) => x.status === "done");
      if (!r) return;
      const ann = await get<Record<string, string>>(`/api/runs/${r.id}/data/annotated`).catch(() => ({} as Record<string, string>));
      setDemo({ id: r.id, video: Object.values(ann)[0] });
    }).catch(() => {});
  }, []);

  return (
    <div className="min-h-full bg-mist">
      <header className="max-w-[1200px] mx-auto px-4 md:px-6 h-14 md:h-16 flex items-center border-b hair">
        <Logo to="/" />
        <nav className="ml-auto flex items-center gap-6 whitespace-nowrap">
          <a href="#how" className="hidden md:inline text-muted hover:text-black">How it works</a>
          <a href="#outputs" className="hidden md:inline text-muted hover:text-black">Outputs</a>
          <Link to="/capture" className="hidden md:inline text-muted hover:text-black">Record a drive</Link>
          <Link to="/app" className="btn btn-solid">Open platform</Link>
        </nav>
      </header>

      <section className="max-w-[1200px] mx-auto px-4 md:px-6 pt-10 md:pt-16 pb-10 md:pb-12 grid grid-cols-1 md:grid-cols-[1.1fr_1fr] gap-8 md:gap-12 items-end">
        <div>
          <h1 className="text-[34px] md:text-[48px] h-light leading-[1.08]">Road repair plans from a single drive.</h1>
          <p className="mt-5 md:mt-6 text-[15px] md:text-[17px] font-light text-muted max-w-[520px] leading-relaxed">
            MEND helps road maintenance teams turn phone or dashcam footage into a measured list of defects, a priority order based on who is at risk, and work orders a contractor can price.
          </p>
          <div className="mt-6 md:mt-8 flex flex-wrap gap-3">
            <Link to="/app" className="btn btn-solid px-5 py-2.5">Open platform</Link>
            {demo && <Link to={`/app/runs/${demo.id}/review`} className="btn px-5 py-2.5">See a survey</Link>}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-px bg-line border hair">
          {[["Same day", "from drive to tender pack"], ["m²", "measured, with a range, per defect"], ["1 image", "of evidence behind every cost line"], ["Ranked", "by risk to people, not by who complained"]].map(([a, b]) => (
            <div key={a} className="bg-mist p-4 md:p-5"><div className="text-[20px] md:text-[26px] h-light">{a}</div><div className="text-muted mt-1">{b}</div></div>
          ))}
        </div>
      </section>

      <section className="bg-carbon">
        <div className="max-w-[1200px] mx-auto px-4 md:px-6 py-6 md:py-12">
          {demo?.video ? (
            <video src={fileUrl(demo.id, demo.video)} autoPlay muted loop playsInline className="w-full aspect-video object-contain bg-carbon" />
          ) : (
            <div className="w-full aspect-video" />
          )}
          <div className="mt-4 text-[13px] text-graphite">Survey footage with each defect outlined, tracked and sized.</div>
        </div>
      </section>

      <section id="problem" className="max-w-[1200px] mx-auto px-4 md:px-6 py-10 md:py-16 grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-4 md:gap-12 border-b hair">
        <div className="text-[26px] h-light">The problem</div>
        <div className="text-[15px] font-light leading-relaxed space-y-4 max-w-[680px]">
          <p>Most road authorities find out about damage from complaints and drive-by inspections. An engineer writes notes, estimates sizes by eye, and turns them into a tender weeks later. By then the potholes are bigger and the list is out of date.</p>
          <p>The money that does exist rarely goes to the road outside the school first, because nobody has the evidence in one place to argue for it.</p>
        </div>
      </section>

      <section id="how" className="max-w-[1200px] mx-auto px-4 md:px-6 py-10 md:py-16">
        <div className="text-[26px] h-light mb-8">How it works</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-px bg-line border hair">
          {STEPS.map(([n, t, d]) => (
            <div key={n} className="bg-mist p-6">
              <div className="num text-muted">{n}</div>
              <div className="text-[19px] h-light mt-3 md:mt-6">{t}</div>
              <p className="mt-3 text-[13px] font-light leading-relaxed">{d}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="outputs" className="max-w-[1200px] mx-auto px-4 md:px-6 py-10 md:py-16 grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-4 md:gap-12 border-t hair">
        <div className="text-[26px] h-light">What you get</div>
        <div className="border-t hair">
          {OUTPUTS.map(([t, d]) => (
            <div key={t} className="py-4 border-b hair grid grid-cols-1 sm:grid-cols-[200px_1fr] gap-1 sm:gap-6"><div>{t}</div><div className="text-muted font-light">{d}</div></div>
          ))}
        </div>
      </section>

      <section className="max-w-[1200px] mx-auto px-4 md:px-6 py-10 md:py-16 grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-4 md:gap-12 border-t hair">
        <div className="text-[26px] h-light">Built on</div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-px bg-line border hair">
          {[["SAM 3.1", "Outlines and tracks each defect across video frames."], ["Muse Spark", "Checks each detection, plans the scan, explains rankings, drafts the tender, answers questions."], ["Muse Voice Transcribe", "Turns an inspector's spoken notes into ranking changes."]].map(([t, d]) => (
            <div key={t} className="bg-mist p-5"><div className="text-[15px]">{t}</div><div className="text-muted font-light mt-2 text-[13px]">{d}</div></div>
          ))}
        </div>
      </section>

      <footer className="bg-carbon text-mist">
        <div className="max-w-[1200px] mx-auto px-4 md:px-6 py-8 flex flex-wrap items-center gap-4 md:gap-6">
          <Logo dark to="/" />
          <span className="text-graphite text-[13px] order-3 md:order-none w-full md:w-auto">For road authorities, city works departments and maintenance contractors.</span>
          <Link to="/app" className="ml-auto text-mist">Open platform</Link>
        </div>
      </footer>
    </div>
  );
}
