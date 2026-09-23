import type { Analytics, CompletionResponse, EmployeeListItem, EmployeeProfile, Recommendation, Reward, RewardAnalytics, RewardRequest, SessionUser } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...init?.headers },
  });
  if (!response.ok) {
    const text = await response.text();
    let detail = text;
    try { const body = JSON.parse(text); detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body); } catch { /* use plain response */ }
    if (response.status === 401 && path !== "/api/auth/login") window.dispatchEvent(new Event("session-expired"));
    throw new Error(detail || String(response.status));
  }
  return response.json() as Promise<T>;
}

type BackendRecommendation = { event_id: string; title: string; target_skill: string; gain: number; max_level: number; score: number; rationale: string };
type BackendRecommendationResponse = { recommendations: BackendRecommendation[] };
type BackendReward = Reward;

export const api = {
  me: () => request<{ auth_enabled: boolean; authenticated: boolean; user: SessionUser | null }>("/api/auth/me"),
  login: (username: string, password: string) => request<{ user: SessionUser }>("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  async health(): Promise<boolean> {
    try { await request("/api/health"); return true; } catch { return false; }
  },
  employees: () => request<EmployeeListItem[]>("/api/employees"),
  profile: (id: string) => request<EmployeeProfile>(`/api/employees/${encodeURIComponent(id)}/profile`),
  async recommendations(employeeId: string): Promise<{ recommendations: Recommendation[] }> {
    const [result, profile] = await Promise.all([
      request<BackendRecommendationResponse>("/api/recommendations", { method: "POST", body: JSON.stringify({ employee_id: employeeId }) }),
      api.profile(employeeId),
    ]);
    const topScore = Math.max(1, ...result.recommendations.map((item) => item.score));
    const recommendations = result.recommendations.map((item) => {
      const skill = profile.skills.find((entry) => entry.name === item.target_skill || entry.skill_id === item.target_skill);
      const projected = Math.min((skill?.current_level ?? 0) + item.gain, item.max_level);
      return {
        activity_id: item.event_id, title: item.title, type: "Рекомендованная активность",
        expected_gain: item.gain, target_skills: [item.target_skill], explanation: item.rationale,
        factors: {
          current_skill: `${item.target_skill}: ${skill?.current_level ?? "—"}`,
          next_grade_requirement: `${profile.next_grade ?? profile.grade}: ${skill?.required_level ?? "—"}`,
          skill_gap: `Разрыв: ${skill?.gap ?? "—"}; после активности уровень будет ${projected}`,
          participation_history: profile.participation_summary
            ? `Завершено ${profile.participation_summary.completed}, пропусков ${profile.participation_summary.missed}, отказов ${profile.participation_summary.declined}`
            : "История учтена в обосновании",
        },
        score: item.score / topScore, completed: false,
      } satisfies Recommendation;
    });
    return { recommendations };
  },
  complete: (activityId: string, employeeId: string, requestKey: string) => request<CompletionResponse & { points_awarded: number; points_balance: number }>(`/api/activities/${encodeURIComponent(activityId)}/complete`, {
    method: "POST", headers: { "Idempotency-Key": requestKey }, body: JSON.stringify({ employee_id: employeeId }),
  }),
  analytics: () => request<Analytics>("/api/hr/dashboard"),
  upload: async (file: File) => {
    const form = new FormData(); form.append("file", file);
    const result = await request<{ profile_ids: string[] }>("/api/profiles/upload-file", { method: "POST", body: form });
    return { employee_ids: result.profile_ids };
  },
  chat: (message: string, employeeId: string) => request<{ answer: string; source?: string }>("/api/chat", { method: "POST", body: JSON.stringify({ message, employee_id: employeeId }) }),
  rewardAnalytics: () => request<RewardAnalytics>("/api/hr/rewards/analytics"),
  rewards: () => request<BackendReward[]>("/api/rewards"),
  wallet: (employeeId: string) => request<{ balance: number; total_earned: number; total_spent: number }>(`/api/employees/${encodeURIComponent(employeeId)}/points`),
  requests: (employeeId: string) => request<RewardRequest[]>(`/api/employees/${encodeURIComponent(employeeId)}/rewards/requests`),
  hrRequests: () => request<RewardRequest[]>("/api/hr/rewards/requests"),
  redeem: (rewardId: string, employeeId: string, requestKey: string) => request<{ id: string; balance: number }>(`/api/rewards/${encodeURIComponent(rewardId)}/redeem`, { method: "POST", headers: { "Idempotency-Key": requestKey }, body: JSON.stringify({ employee_id: employeeId }) }),
  decideReward: (requestId: string, decision: "Approved" | "Rejected") => request<RewardRequest>(`/api/hr/rewards/requests/${encodeURIComponent(requestId)}/decision`, { method: "POST", body: JSON.stringify({ decision }) }),
  fulfillReward: (requestId: string) => request<RewardRequest>(`/api/hr/rewards/requests/${encodeURIComponent(requestId)}/fulfill`, { method: "POST" }),
};

export const demoEmployees: EmployeeListItem[] = [{ employee_id: "E0028", name: "Demo profile", role: "Backend Engineer", grade: "Middle" }];
export const demoProfile: EmployeeProfile = { employee_id: "E0028", name: "Demo profile", role: "Backend Engineer", grade: "Middle", next_grade: "Senior", tenure_months: 0, skills: [], participation_summary: { completed: 0, missed: 0, declined: 0, completion_rate: 0 } };
export const demoRecommendations = (): Recommendation[] => [];
export const demoAnalytics: Analytics = { summary: { total_employees: 0, average_participation: 0, employees_needing_attention: 0, largest_skill_gap: { name: "—", average_gap: 0 } }, skill_gaps: [], participation: { completed: 0, missed: 0, declined: 0, no_activity: 0 }, employees_needing_attention: [] };
export const demoRewardAnalytics: RewardAnalytics = { totalQpAwarded: 0, totalQpRedeemed: 0, activeUsers: 0, popularCategory: "Professional Growth", pendingApprovals: 0, categoryShare: { "Halyk Brand": 0, "Professional Growth": 0, "Work-Life Balance": 0 }, popularRewards: [], journey: [] };
