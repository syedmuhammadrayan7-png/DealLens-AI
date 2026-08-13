export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Evidence = { statement: string; status: string; source?: string | null; source_type?: string | null; source_name?: string | null; source_url?: string | null; confidence: number; observed_at?: string | null; notes?: string | null };
export type CaseStatus = { case_id: string; company_name: string; status: string; current_stage: string; completed_stages: string[]; agent_status: Record<string, string>; evidence_count: number; errors: string[]; completion_percentage: number };
export type ScoreFactor = { label: string; points: number; max_points?: number; note: string; evidence_refs: string[] }; export type ScoreBreakdown = { category: string; score: number; confidence: string; contributing_factors: ScoreFactor[]; deductions: ScoreFactor[]; evidence_summary: string[] }; export type Report = { case_id: string; company_name: string; sector: string; funding_stage: string; overall_score: number; market_score: number; technical_score: number; traction_score: number; financial_score: number; team_score: number; risk_level: string; confidence_level: string; investment_thesis: string; strengths: string[]; red_flags: string[]; verified_evidence: Evidence[]; founder_provided_claims: Evidence[]; unverified_claims: Evidence[]; conflicting_evidence: Evidence[]; unavailable_evidence: Evidence[]; investor_questions: string[]; additional_verification_required: string[]; recommendation: string; recommendation_reason: string; score_breakdowns: ScoreBreakdown[]; generated_at: string };

async function readError(response: Response) {
  const data = await response.json().catch(() => ({}));
  const detail = data.detail;
  return typeof detail === "object" && detail?.message ? detail.message : typeof detail === "string" ? detail : "The request could not be completed.";
}

export async function createCase(payload: unknown, deck?: File | null): Promise<{ case_id: string }> {
  const endpoint = deck ? "/api/cases/with-pitch-deck" : "/api/cases";
  const response = deck
    ? await fetch(`${API_URL}${endpoint}`, { method: "POST", body: (() => { const form = new FormData(); form.append("payload", JSON.stringify(payload)); form.append("pitch_deck", deck); return form; })() })
    : await fetch(`${API_URL}${endpoint}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function getStatus(caseId: string): Promise<CaseStatus> {
  const response = await fetch(`${API_URL}/api/cases/${caseId}/status`, { cache: "no-store" });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function getReport(caseId: string): Promise<Report> {
  const response = await fetch(`${API_URL}/api/cases/${caseId}/report`, { cache: "no-store" });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}
export type CaseSummary = { case_id:string; company_name:string; industry:string; funding_stage:string; status:string; current_stage:string; overall_score?:number|null; risk_level?:string|null; confidence_level?:string|null; recommendation?:string|null; created_at:string; completed_at?:string|null };
export async function getCases(): Promise<CaseSummary[]> { const response = await fetch(`${API_URL}/api/cases`, { cache:"no-store" }); if (!response.ok) throw new Error(await readError(response)); return response.json(); }
export async function retryCase(caseId:string): Promise<{case_id:string}> { const response=await fetch(`${API_URL}/api/cases/${caseId}/retry`, {method:"POST"}); if(!response.ok) throw new Error(await readError(response)); return response.json(); }
