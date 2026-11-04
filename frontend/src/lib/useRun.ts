import { useCallback, useEffect, useState } from "react";
import { Boq, Defect, Doc, Media, RunMeta, Site, data, get } from "./api";

export type RunData = { meta?: RunMeta; media: Media[]; defects: Defect[]; sites: Site[]; boq?: Boq; docs: Doc[]; route: any; calibration: any };

export function useRun(runId: string) {
  const [d, setD] = useState<RunData>({ media: [], defects: [], sites: [], docs: [], route: {}, calibration: {} });
  const load = useCallback(async () => {
    const meta = await get<RunMeta>(`/api/runs/${runId}`).catch(() => undefined);
    const safe = <T,>(p: Promise<T>, dflt: T) => p.catch(() => dflt);
    const [media, defects, sites, boq, docs, route, calibration] = await Promise.all([
      safe(data<Media[]>(runId, "media"), []), safe(data<Defect[]>(runId, "defects"), []), safe(data<Site[]>(runId, "sites"), []),
      safe(data<Boq | undefined>(runId, "boq"), undefined), safe(data<Doc[]>(runId, "documents"), []), safe(data(runId, "route"), {}), safe(data(runId, "calibration"), {}),
    ]);
    setD({ meta, media, defects, sites, boq, docs, route, calibration });
  }, [runId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (d.meta?.status !== "running") return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [d.meta?.status, load]);
  return { ...d, reload: load };
}
