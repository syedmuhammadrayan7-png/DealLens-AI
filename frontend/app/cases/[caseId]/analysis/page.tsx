"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { CheckCircle2, CircleDashed, AlertTriangle, ArrowRight } from "lucide-react";
import { CaseStatus, getStatus } from "../../../../lib/api";

const agents = ["Company Intelligence", "Market Analysis", "Technical Due Diligence", "Financial Analysis", "Risk Committee", "Investment Memo"];

export default function Analysis() {
  const params = useParams<{ caseId: string }>();
  const router = useRouter();
  const [data, setData] = useState<CaseStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const next = await getStatus(params.caseId);
        if (!active) return;
        setData(next);
        if (next.status === "completed") {
          router.replace(`/cases/${params.caseId}/report`);
          return;
        }
        if (next.status === "failed") {
          setError(next.errors[0] === "STRUCTURED_OUTPUT_SCHEMA_ERROR" ? "The report format needs attention. This case has stopped and will not make more requests." : "Analysis could not complete. This case has stopped and will not make more requests.");
          return;
        }
        timer = setTimeout(poll, 1800);
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Could not fetch case status.");
      }
    };
    void poll();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [params.caseId, router]);

  const pct = data?.completion_percentage ?? 0;
  return <main className="shell py-10"><Link className="eyebrow" href="/">← DealLens AI</Link><section className="mt-12 max-w-3xl"><p className="eyebrow">Live case analysis</p><h1 className="mt-3 text-4xl tracking-tight">{data?.company_name ?? "Preparing due diligence"}</h1><p className="mt-2 font-mono text-xs text-slate-500">CASE / {params.caseId}</p><div className="glass mt-9 p-6"><div className="flex justify-between text-sm"><span>{data?.current_stage?.replaceAll("_", " ") ?? "connecting"}</span><span className="text-cyan-200">{pct}%</span></div><div className="mt-3 h-2 overflow-hidden rounded bg-slate-700"><div className="h-full bg-cyan-300 transition-all duration-500" style={{ width: `${pct}%` }}/></div><p className="mt-4 text-sm text-slate-400">Showing task status, MCP access, and evidence counts only — never hidden reasoning.</p></div><div className="mt-5 grid gap-3">{agents.map(name => { const state = data?.agent_status[name] ?? "queued"; return <article className="glass flex items-center justify-between p-4" key={name}><div className="flex items-center gap-3">{state === "completed" ? <CheckCircle2 className="text-emerald-300" size={19}/> : state === "failed" ? <AlertTriangle className="text-red-300" size={19}/> : <CircleDashed className={state === "running" ? "animate-spin text-cyan-300" : "text-slate-500"} size={19}/>}<span>{name}</span></div><span className="text-xs uppercase tracking-widest text-slate-400">{state}</span></article>; })}</div>{data && <p className="mt-5 text-xs text-slate-500">Evidence objects collected: {data.evidence_count}</p>}{error && <div className="mt-6 rounded border border-red-400/30 bg-red-400/10 p-4 text-red-100"><p>{error}</p><Link className="button secondary mt-4" href="/new-case">Create a new case <ArrowRight size={16}/></Link></div>}</section></main>;
}
