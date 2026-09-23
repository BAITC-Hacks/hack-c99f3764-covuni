export type Language = "ru" | "kz";
export type View = "login" | "employee" | "hr" | "rewards" | "history";
export type SessionUser = { username: string; role: "employee" | "hr"; employee_id: string | null };

export type EmployeeListItem = {
  employee_id: string;
  name?: string;
  role: string;
  grade: string;
};

export type SkillProgress = {
  skill_id: string;
  name: string;
  category: "hard" | "soft" | string;
  current_level: number;
  required_level: number;
  gap: number;
};

export type ParticipationSummary = {
  completed: number;
  missed: number;
  declined: number;
  completion_rate: number;
};

export type EmployeeProfile = {
  employee_id: string;
  name?: string;
  role: string;
  grade: string;
  next_grade?: string;
  tenure_months: number;
  skills: SkillProgress[];
  completed_activities?: Array<{ event_id: string; title: string; date: string }>;
  participation_summary?: ParticipationSummary;
};

export type Recommendation = {
  activity_id: string;
  title: string;
  type?: string;
  duration_minutes?: number;
  expected_gain: number;
  target_skills?: string[];
  explanation: string;
  factors: {
    current_skill: string;
    next_grade_requirement: string;
    skill_gap: string;
    participation_history: string;
  };
  score?: number;
  completed: boolean;
};

export type Analytics = {
  summary: {
    total_employees: number;
    average_participation: number;
    employees_needing_attention: number;
    largest_skill_gap: { name: string; average_gap: number };
  };
  skill_gaps: Array<{ name: string; employees_affected: number; average_gap: number }>;
  participation: { completed: number; missed: number; declined: number; no_activity: number };
  employees_needing_attention: Array<{
    employee_id: string;
    role: string;
    grade: string;
    main_gap: string;
    participation_status: string;
    recommendation_available: boolean;
  }>;
};

export type RewardCategory = "Halyk Brand" | "Professional Growth" | "Work-Life Balance";
export type Reward = {
  id: string;
  title: string;
  category: RewardCategory;
  description: string;
  cost: number;
  availability: string;
  icon: string;
  featured?: boolean;
};

export type RewardRequest = {
  id: string;
  employee_id?: string;
  rewardId: string;
  title: string;
  category: RewardCategory;
  cost: number;
  status: "Pending" | "Approved" | "Redeemed" | "Rejected";
  requestedAt: string;
};

export type RewardAnalytics = {
  totalQpAwarded: number;
  totalQpRedeemed: number;
  activeUsers: number;
  popularCategory: RewardCategory;
  pendingApprovals: number;
  categoryShare: Record<RewardCategory, number>;
  popularRewards: Array<{ title: string; category: RewardCategory; requests: number; approved: number; spent: number }>;
  journey: Array<{ label: string; count: number }>;
};

export type CompletionResponse = {
  message: string;
  skill_updates: Array<{ skill_id: string; before: number; gain: number; after: number; max_level: number }>;
};
