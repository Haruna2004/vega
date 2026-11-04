import { Link } from "react-router-dom";
import { Logo } from "../components/ui";

const DEMO = "https://youtu.be/hTMNhOyJMkg";
const REPO = "https://github.com/Haruna2004/vega";
const SURVEY = "/app/runs/20261104-160433-bolonge/review";

type Step = { n: string; title: string; body: string; model: string; img: string; alt: string; tall?: boolean };

const STEPS: Step[] = [
  {
    n: "01", title: "Drive the road once",
    body: "Mount a phone on the windscreen and open the capture page. It films the road and logs GPS every second. Dashcam video and photos you already have work too.",
    model: "Phone capture", img: "/shots/capture.webp", alt: "Phone capture screen filming a damaged road",
  },
  {
    n: "02", title: "Every defect outlined and measured",
    body: "SAM 3.1 outlines each pothole and follows it through the video, so one hole is counted once. A camera model projects the mask onto the road and gives its area in square metres, with a range.",
    model: "SAM 3.1", img: "/shots/stage.webp", alt: "Survey video with each pothole outlined, the processing steps and live counters",
  },
  {
    n: "03", title: "Checked like an engineer would",
    body: "Muse Spark looks at the close-up of every detection, confirms it is real damage and not a shadow or a puddle, and scores how bad it is. You see the reasons behind every number.",
    model: "Muse Spark", img: "/shots/defect.webp", alt: "Defect inspector with size, range, severity reasons and Muse Spark's crop review", tall: true,
  },
  {
    n: "04", title: "Ranked by risk to people",
    body: "Nearby defects become repair sites on a map coloured by condition. Each site is scored on severity and exposure, and Muse Spark writes down why it sits where it does.",
    model: "Muse Spark · OpenStreetMap", img: "/shots/map.webp", alt: "Map of the driven road coloured by condition with repair sites ranked",
  },
  {
    n: "05", title: "What the camera cannot see",
    body: "Hold to record a note on site. Muse Voice Transcribe turns it into text, Muse Spark reads it, and a school crossing or a bus stop raises the site's priority on the spot.",
    model: "Muse Voice Transcribe", img: "/shots/site.webp", alt: "Repair site with an inspector's field note and its raised priority score", tall: true,
  },
  {
    n: "06", title: "Paperwork a contractor can price",
    body: "Work orders, a bill of quantities and a request for quotation are built from the measurements. Change a unit rate and every total follows. Each line points to the defect it pays for.",
    model: "PDF · Markdown", img: "/shots/orders.webp", alt: "Request for quotation with sites in priority order and editable unit rates",
  },
  {
    n: "07", title: "Ask the roads",
    body: "Ask in plain words which site to fix first or what the budget covers. Muse Spark answers from the survey itself and cites the sites and defects, so every figure can be checked.",
    model: "Muse Spark", img: "/shots/ask.webp", alt: "Muse Spark answering which site to fix first, citing site and defect ids",
  },
];

function Shot({ s, eager }: { s: Step; eager?: boolean }) {
  return (
    <div className="bg-carbon p-2 md:p-3">
      <img src={s.img} alt={s.alt} loading={eager ? "eager" : "lazy"} className="w-full block" />
    </div>
  );
}

export default function Landing() {
  return (
    <div className="min-h-full bg-mist">
      <header className="sticky top-0 z-40 bg-mist/95 backdrop-blur w-full px-4 md:px-[max(24px,calc((100%-1200px)/2+24px))] h-14 md:h-16 flex items-center border-b hair">
        <Logo to="/" />
        <nav className="ml-auto flex items-center gap-6 whitespace-nowrap">
          <a href="#how" className="hidden md:inline text-muted hover:text-black">How it works</a>
          <a href={DEMO} target="_blank" rel="noreferrer" className="hidden md:inline text-muted hover:text-black">Demo video</a>
          <Link to="/capture" className="hidden md:inline text-muted hover:text-black">Record a drive</Link>
          <Link to="/app" className="btn btn-solid">Open platform</Link>
        </nav>
      </header>

      {/* hero */}
      <section className="max-w-[1200px] mx-auto px-4 md:px-6 pt-10 md:pt-20 pb-8 md:pb-14">
        <h1 className="text-[34px] md:text-[56px] h-light leading-[1.05] max-w-[880px]">Road repair plans from a single drive.</h1>
        <div className="mt-6 md:mt-8 grid grid-cols-1 md:grid-cols-[1fr_auto] gap-6 md:gap-12 items-end">
          <p className="text-[15px] md:text-[18px] font-light text-muted max-w-[620px] leading-relaxed">
            Film a road with a phone. MEND finds and measures every pothole, ranks the repairs by who is at risk, and writes the work orders a contractor can price.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link to={SURVEY} className="btn btn-solid px-5 py-2.5">See a real survey</Link>
            <a href={DEMO} target="_blank" rel="noreferrer" className="btn px-5 py-2.5">Watch the demo</a>
          </div>
        </div>
      </section>

      <section className="bg-carbon">
        <div className="max-w-[1200px] mx-auto px-4 md:px-6 py-6 md:py-12">
          <img src="/shots/review.webp" alt="MEND review screen: survey video with every pothole outlined by SAM 3.1, pipeline steps and totals" className="w-full block" />
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-px bg-carbon-2 border border-carbon-2">
            {[["37", "defects found in a 28 second drive"], ["22.7 m²", "of damage, measured with a range"], ["5", "repair sites ranked by risk"], ["$3,001", "estimated repair cost, itemised"]].map(([a, b]) => (
              <div key={a} className="bg-carbon p-4 md:p-5"><div className="text-[22px] md:text-[28px] h-light text-mist">{a}</div><div className="text-graphite mt-1">{b}</div></div>
            ))}
          </div>
        </div>
      </section>

      {/* problem */}
      <section id="problem" className="max-w-[1200px] mx-auto px-4 md:px-6 py-12 md:py-20 grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-4 md:gap-12 border-b hair">
        <div className="text-[26px] h-light">The problem</div>
        <div className="text-[15px] md:text-[17px] font-light leading-relaxed space-y-4 max-w-[680px]">
          <p>Most road authorities find out about damage from complaints and drive-by inspections. Someone walks the road with a tape measure, sizes are guessed, and the tender goes out weeks later. By then the holes are bigger and the list is out of date.</p>
          <p>The money that does exist rarely goes to the road outside the school first, because nobody has the evidence in one place to argue for it.</p>
        </div>
      </section>

      {/* how it works: one row per step, screenshot beside the words */}
      <section id="how" className="max-w-[1200px] mx-auto px-4 md:px-6 pt-12 md:pt-20">
        <div className="text-[26px] md:text-[40px] h-light leading-[1.1]">From a drive to a work order</div>
      </section>
      <div className="max-w-[1200px] mx-auto px-4 md:px-6 pb-8">
        {STEPS.map((s, i) => (
          <section key={s.n} className="py-10 md:py-16 border-b hair grid grid-cols-1 md:grid-cols-12 gap-6 md:gap-12 items-center">
            <div className={`md:col-span-4 ${i % 2 ? "md:order-2" : ""}`}>
              <div className="flex items-center gap-3">
                <span className="num text-muted">{s.n}</span>
                <span className="h-px w-8 bg-amber" />
                <span className="label">{s.model}</span>
              </div>
              <h2 className="text-[24px] md:text-[30px] h-light mt-4 leading-[1.15]">{s.title}</h2>
              <p className="mt-4 text-[15px] font-light leading-relaxed text-ink/80">{s.body}</p>
            </div>
            <div className={`md:col-span-8 ${i % 2 ? "md:order-1" : ""} ${s.tall ? "max-w-[460px] w-full mx-auto" : ""}`}>
              <Shot s={s} />
            </div>
          </section>
        ))}
      </div>

      {/* models */}
      <section className="max-w-[1200px] mx-auto px-4 md:px-6 py-12 md:py-16 grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-4 md:gap-12">
        <div className="text-[26px] h-light">Built on Meta models</div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-px bg-line border hair">
          {[["SAM 3.1", "Outlines and tracks every defect across the video, and finds the road for camera calibration."], ["Muse Spark 1.3", "Plans the scan, reviews each detection, explains the ranking, drafts the tender, answers questions."], ["Muse Voice Transcribe", "Turns an inspector's spoken notes into text that changes the repair order."]].map(([t, d]) => (
            <div key={t} className="bg-mist p-5"><div className="text-[15px]">{t}</div><div className="text-muted font-light mt-2 text-[13px] leading-relaxed">{d}</div></div>
          ))}
        </div>
      </section>

      {/* closing call to action */}
      <section className="bg-carbon text-mist">
        <div className="max-w-[1200px] mx-auto px-4 md:px-6 py-14 md:py-20 grid grid-cols-1 md:grid-cols-[1fr_auto] gap-8 items-end">
          <div>
            <div className="text-[30px] md:text-[44px] h-light leading-[1.1]">Drive it. Measure it. Fix the right road first.</div>
            <div className="mt-4 text-graphite text-[15px] font-light max-w-[560px]">For road authorities, city works departments and maintenance contractors.</div>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link to="/app" className="btn px-5 py-2.5" style={{ color: "#f6f8f7", borderColor: "#f6f8f7" }}>Open platform</Link>
            <Link to="/capture" className="btn px-5 py-2.5" style={{ background: "#f6f8f7", color: "#0f0e12", borderColor: "#f6f8f7" }}>Record a drive</Link>
          </div>
        </div>
      </section>

      <footer className="bg-carbon text-mist border-t border-carbon-2">
        <div className="max-w-[1200px] mx-auto px-4 md:px-6 py-8 flex flex-wrap items-center gap-4 md:gap-6">
          <Logo dark to="/" />
          <a href={REPO} target="_blank" rel="noreferrer" className="ml-auto text-graphite hover:text-mist">GitHub</a>
          <a href={DEMO} target="_blank" rel="noreferrer" className="text-graphite hover:text-mist">Demo video</a>
          <Link to="/app" className="text-mist">Open platform</Link>
        </div>
      </footer>
    </div>
  );
}
