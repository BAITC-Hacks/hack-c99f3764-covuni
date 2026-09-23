import "./styles.css";
import { api, demoAnalytics, demoEmployees, demoProfile, demoRecommendations, demoRewardAnalytics } from "./api";
import type { Analytics, EmployeeListItem, EmployeeProfile, Language, Recommendation, Reward, RewardAnalytics, RewardCategory, RewardRequest, View, SessionUser } from "./types";

type Toast = { message: string; tone: "success" | "error" | "info" };
type ChatMessage = { role: "assistant" | "user"; text: string };
type AppState = { authEnabled: boolean; authChecked: boolean; user: SessionUser | null; view: View; language: Language; connected: boolean; employees: EmployeeListItem[]; profile: EmployeeProfile; recommendations: Recommendation[]; analytics: Analytics; rewardAnalytics: RewardAnalytics; rewards: Reward[]; requests: RewardRequest[]; hrRequests: RewardRequest[]; points: number; totalSpent: number; totalEarned: number; loading: boolean; chatOpen: boolean; chatLoading: boolean; chatMessages: ChatMessage[]; busyActivity?: string; selectedReward?: Reward; toast?: Toast; error?: string };

const state: AppState = { authEnabled: false, authChecked: false, user: null, view: "login", language: "ru", connected: false, employees: demoEmployees, profile: demoProfile, recommendations: demoRecommendations(), analytics: demoAnalytics, rewardAnalytics: demoRewardAnalytics, rewards: [], requests: [], hrRequests: [], points: 0, totalSpent: 0, totalEarned: 0, loading: false, chatOpen: false, chatLoading: false, chatMessages: [{ role: "assistant", text: "Здравствуйте! Я помогу разобраться с навыками, рекомендациями и Quest Points." }] };
const root = document.querySelector<HTMLDivElement>("#app")!;
const copy = { ru: { employee: "Кабинет сотрудника", hr: "HR-Аналитика", rewards: "Магазин наград", history: "Мои награды", login: "Войти", upload: "Загрузить JSON-профиль жюри", complete: "Выполнить активность", completed: "Выполнено", loading: "Загрузка…", offline: "Demo-режим: API недоступен" }, kz: { employee: "Қызметкер кабинеті", hr: "HR-талдау", rewards: "Сыйлықтар дүкені", history: "Менің сыйлықтарым", login: "Кіру", upload: "Қазылар JSON профилін жүктеу", complete: "Белсенділікті орындау", completed: "Орындалды", loading: "Жүктелуде…", offline: "Demo режимі: API қолжетімсіз" } } as const;
const t = () => copy[state.language];
const esc = (value: unknown) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[c]!));
const money = (value: number) => new Intl.NumberFormat("ru-RU").format(value);
const percent = (value: number) => `${Math.round(value * 100)}%`;
const categoryClass = (category: RewardCategory) => category.toLowerCase().replaceAll(" ", "-");

function renderJuryPanel(): string {
  return `<div class="jury-demo-panel" id="jury-demo-panel"><div class="jury-badge"><span class="jury-title">🔑 Демо-вход (Жюри):</span><button type="button" class="jury-btn jury-emp-btn" id="jury-btn-employee" title="Переключить на демо-сотрудника E0028">👤 Демо-Сотрудник (E0028)</button><button type="button" class="jury-btn jury-hr-btn" id="jury-btn-hr" title="Переключить на HR-аналитику">📊 HR-Руководитель</button><div class="jury-tooltip"><div class="tooltip-title">🔑 Тестовые логины для жюри:</div><div class="tooltip-row">👤 Сотрудник: <code>demo.employee@halykbank.kz</code> / <code>demo123</code></div><div class="tooltip-row">📊 HR-Руководитель: <code>hr.manager@halykbank.kz</code> / <code>admin123</code></div></div></div></div>`;
}

function header(): string {
  return `<header class="topbar"><button class="brand brand-button" data-view="employee"><span class="brand-mark">H</span><span><strong>Halyk Bank</strong><small>Career Quest AI</small></span></button><span class="team-badge">Team 202453</span><span class="api-status ${state.connected ? "online" : "offline"}"><i></i>${state.connected ? "API connected" : t().offline}</span>${state.view !== "login" ? `<nav><button class="tab ${state.view === "employee" ? "active" : ""}" data-view="employee">${t().employee}</button><button class="tab ${state.view === "hr" ? "active" : ""}" data-view="hr">${t().hr}</button><button class="tab ${state.view === "rewards" || state.view === "history" ? "active" : ""}" data-view="rewards">${t().rewards}</button></nav><button class="profile-menu" data-view="history"><span class="avatar">AS</span><span class="desktop-only">Aigerim S.</span><span class="chevron">⌄</span></button>` : `<div style="flex:1"></div>`}${renderJuryPanel()}<select id="language"><option value="ru" ${state.language === "ru" ? "selected" : ""}>RU</option><option value="kz" ${state.language === "kz" ? "selected" : ""}>KZ</option></select></header>`;
}

function renderLogin(): string {
  return `<main class="auth-page"><div class="auth-visual"><div class="auth-mark">H</div><p class="eyebrow">HALYK BANK · CAREER QUEST</p><h1>Grow with purpose.</h1><p>Ваш следующий шаг в развитии — и награда за прогресс.</p></div><section class="auth-card"><div class="auth-logo"><span class="brand-mark">H</span><strong>Halyk Bank</strong></div><h2>${state.authEnabled ? "Вход в Career Quest" : "Демонстрация Career Quest"}</h2><p class="muted">${state.authEnabled ? "Введите данные учётной записи, созданной администратором." : "Выберите сотрудника и пройдите путь от развития до награды. Демо работает без пароля."}</p><form id="login-form">${state.authEnabled ? `<label>Логин<input name="username" autocomplete="username" value="demo.employee@halykbank.kz" required></label><label>Пароль<input name="password" type="password" autocomplete="current-password" value="demo123" required></label>` : ""}<button class="button primary wide" type="submit" ${!state.authChecked || !state.connected || state.loading ? "disabled" : ""}>${state.loading ? "Загрузка…" : state.authEnabled ? "Войти" : "Открыть демо"}</button></form><div class="quick-demo-box"><div class="quick-demo-title">🔑 Быстрый демо-вход для жюри:</div><div class="quick-demo-buttons"><button type="button" class="jury-btn jury-emp-btn" id="login-quick-emp">👤 Демо-Сотрудник (E0028)</button><button type="button" class="jury-btn jury-hr-btn" id="login-quick-hr">📊 HR-Руководитель</button></div><div class="quick-demo-creds"><div>👤 Сотрудник: <code>demo.employee@halykbank.kz</code> / <code>demo123</code></div><div>📊 HR: <code>hr.manager@halykbank.kz</code> / <code>admin123</code></div></div></div>${state.error ? `<p class="error-message">${esc(state.error)}</p>` : ""}</section></main>`;
}
function renderEmployee(): string { const profile = state.profile; return `<main><section class="page-head"><div><p class="eyebrow">PRIVATE EMPLOYEE SPACE</p><h1>Доброе утро, ${esc(profile.name ?? profile.employee_id)}</h1><p class="muted">Ваша текущая карьерная траектория и следующий шаг развития.</p></div><div class="toolbar"><select id="employee-select">${state.employees.map((e) => `<option value="${esc(e.employee_id)}" ${e.employee_id === profile.employee_id ? "selected" : ""}>${esc(e.employee_id)} · ${esc(e.role)} · ${esc(e.grade)}</option>`).join("")}</select><button class="button secondary" id="upload-button">${t().upload}</button><input id="profile-file" type="file" accept="application/json,.json" hidden></div></section><div class="profile-grid"><article class="card profile-card"><div><span class="role-label">${esc(profile.role)}</span><span class="grade-badge">${esc(profile.grade)}</span><p class="muted">${profile.tenure_months} месяцев в Halyk</p></div><div class="target"><small>Целевой грейд</small><strong>${esc(profile.next_grade ?? "Senior")}</strong><span class="status-chip">Progressing steadily</span></div></article><article class="card journey"><h2>Ваша карьерная траектория</h2><p class="muted">Текущий грейд и следующий целевой уровень.</p><div class="journey-line"><span></span><b></b><i></i></div><div class="journey-labels"><span>Junior</span><strong>${esc(profile.grade)}</strong><span>${esc(profile.next_grade ?? "Senior")}</span></div></article></div><div class="dashboard-grid"><article class="card skills"><h2>Навыки для следующего грейда</h2><p class="muted">Навыки с наибольшим влиянием на следующий грейд.</p>${profile.skills.map((skill) => `<div class="skill-row"><div class="skill-meta"><strong>${esc(skill.name)}</strong><span class="gap ${skill.gap > 1 ? "attention" : ""}">Gap ${skill.gap}</span><small>${skill.current_level} / ${skill.required_level}</small></div><div class="progress"><span style="width:${Math.min(100, (skill.current_level / Math.max(skill.required_level, 1)) * 100)}%"></span></div></div>`).join("")}<p class="hint">Skill gap — это фокус развития, а не оценка сотрудника.</p></article><article class="recommendations"><div class="section-title"><div><h2>Рекомендованные активности</h2><p class="muted">AI учитывает четыре фактора, а не только самый низкий навык.</p></div><span class="ai-pill">AI powered</span></div>${state.loading ? loadingRecommendations() : state.recommendations.map(renderRecommendation).join("")}${state.error ? `<p class="error-message">${esc(state.error)}</p>` : ""}</article></div>${renderPointsCard()}<button class="assistant-launcher" title="Halyk AI Assistant" data-chat-open><span>AI</span> Спросить Halyk AI</button></main>`; }
function renderPointsCard(): string { return `<article class="card points-card"><div class="points-icon">✦</div><div><p class="eyebrow">YOUR PRIVATE BALANCE</p><h2>${money(state.points)} <span>QP</span></h2><p class="muted">Quest Points за добровольное развитие и инициативу</p></div><div class="points-breakdown"><span>Всего заработано <b>+${money(state.totalEarned)}</b></span><span>Уже потрачено <b>${money(state.totalSpent)}</b></span><span>Заявок на награды <b>${state.requests.length}</b></span></div><button class="button primary" data-view="rewards">Open Rewards Store <span>→</span></button></article>`; }
function loadingRecommendations(): string { return `<div class="skeleton-card"><div></div><div></div><div></div><div></div></div><div class="skeleton-card"><div></div><div></div><div></div></div>`; }
function renderRecommendation(rec: Recommendation): string { return `<article class="recommendation card"><div class="recommendation-head"><span class="recommendation-label">RECOMMENDED NEXT STEP</span>${rec.score ? `<strong class="score">${Math.round(rec.score * 100)}%</strong>` : ""}</div><h3>${esc(rec.title)}</h3><p class="muted">${esc(rec.type ?? "Development activity")} · ${rec.duration_minutes ?? 60} мин · +${rec.expected_gain} уровень</p><div class="why"><strong>Обоснование AI — 4 фактора</strong><p>${esc(rec.explanation)}</p><div class="factor-grid"><span>Current skill<em>${esc(rec.factors.current_skill)}</em></span><span>Next-grade target<em>${esc(rec.factors.next_grade_requirement)}</em></span><span>Skill gap<em>${esc(rec.factors.skill_gap)}</em></span><span>Participation history<em>${esc(rec.factors.participation_history)}</em></span></div></div><button class="button primary complete-button" data-activity="${esc(rec.activity_id)}" ${rec.completed || state.busyActivity === rec.activity_id ? "disabled" : ""}>${rec.completed ? t().completed : state.busyActivity === rec.activity_id ? t().loading : t().complete}</button></article>`; }
function renderHr(): string { const a = state.analytics; const ra = state.rewardAnalytics; return `<main><section class="page-head"><div><p class="eyebrow">PRIVATE HR VIEW</p><h1>HR-Аналитика</h1><p class="muted">Сводка развития сотрудников и компетенций компании.</p></div><div class="filters"><select><option>Последние 6 месяцев</option></select><select><option>Все департаменты</option></select><button class="button secondary" data-view="rewards">Rewards Insights →</button></div></section><div class="metric-grid"><article class="metric card"><small>Всего сотрудников</small><strong>${a.summary.total_employees}</strong></article><article class="metric card"><small>Средняя активность</small><strong>${percent(a.summary.average_participation)}</strong></article><article class="metric card"><small>Главный дефицит</small><strong>${esc(a.summary.largest_skill_gap.name)}</strong></article><article class="metric card"><small>Нуждаются во внимании</small><strong>${a.summary.employees_needing_attention}</strong></article></div><div class="analytics-grid"><article class="card chart-card"><h2>Топ-проседающие навыки</h2>${a.skill_gaps.map((gap, index) => `<div class="bar-row"><span>${esc(gap.name)}</span><div class="bar"><i class="${index === 0 ? "highlight" : ""}" style="width:${Math.max(18, (gap.employees_affected / Math.max(a.skill_gaps[0]?.employees_affected ?? 1, 1)) * 100)}%"></i></div><b>${gap.employees_affected}</b></div>`).join("")}</article><article class="card chart-card"><h2>Участие в активностях</h2>${Object.entries(a.participation).map(([key, value]) => `<div class="bar-row"><span>${key}</span><div class="bar"><i style="width:${value}%"></i></div><b>${value}%</b></div>`).join("")}</article></div><article class="card risk-table"><h2>Сотрудники, которым может потребоваться поддержка</h2><table><thead><tr><th>Сотрудник</th><th>Роль</th><th>Грейд</th><th>Главный gap</th><th>Статус</th><th>Рекомендация</th></tr></thead><tbody>${a.employees_needing_attention.map((e) => `<tr><td>${esc(e.employee_id)}</td><td>${esc(e.role)}</td><td>${esc(e.grade)}</td><td><strong>${esc(e.main_gap)}</strong></td><td><span class="risk-chip">${esc(e.participation_status)}</span></td><td>${e.recommendation_available ? "Доступна" : "Нет"}</td></tr>`).join("")}</tbody></table></article><section class="hr-rewards-preview card"><div><p class="eyebrow">NEW HR VIEW</p><h2>Как сотрудники используют Quest Points</h2><p class="muted">${ra.activeUsers} активных пользователей · ${ra.pendingApprovals} заявок ожидают решения</p></div><div class="mini-metrics"><span><b>${money(ra.totalQpAwarded)}</b><small>QP awarded</small></span><span><b>${money(ra.totalQpRedeemed)}</b><small>QP redeemed</small></span><span><b>${ra.popularCategory}</b><small>most popular category</small></span></div><button class="button primary" data-view="rewards">Open Rewards Insights →</button></section></main>`; }
function rewardCard(reward: Reward): string { return `<article class="reward-card card ${reward.featured ? "featured" : ""}"><div class="reward-art ${categoryClass(reward.category)}"><span>${reward.icon}</span>${reward.featured ? `<em>Popular</em>` : ""}</div><div class="reward-body"><span class="category-tag ${categoryClass(reward.category)}">${reward.category}</span><h3>${esc(reward.title)}</h3><p class="muted">${esc(reward.description)}</p><div class="reward-meta"><strong>${money(reward.cost)} QP</strong><span>${esc(reward.availability)}</span></div><button class="button ${reward.featured ? "primary" : "secondary"} wide" data-reward="${reward.id}">View reward</button></div></article>`; }
function renderRewards(): string { const categories: Array<RewardCategory | "All rewards"> = ["All rewards", "Halyk Brand", "Professional Growth", "Work-Life Balance"]; const active = state.selectedReward ? `<aside class="drawer-backdrop" data-close-drawer><section class="reward-drawer" data-stop-propagation><button class="drawer-close" data-close-drawer>×</button><div class="drawer-art ${categoryClass(state.selectedReward.category)}">${state.selectedReward.icon}</div><span class="category-tag ${categoryClass(state.selectedReward.category)}">${state.selectedReward.category}</span><h2>${esc(state.selectedReward.title)}</h2><p class="muted">${esc(state.selectedReward.description)}</p><div class="drawer-cost"><span>Cost</span><strong>${money(state.selectedReward.cost)} QP</strong></div><div class="balance-check"><span>Your balance</span><b>${money(state.points)} QP</b></div><button class="button primary wide" data-redeem="${state.selectedReward.id}" ${state.points < state.selectedReward.cost ? "disabled" : ""}>${state.points < state.selectedReward.cost ? "Not enough QP" : "Redeem reward"}</button><small class="private-note">Private request · HR approval may be required</small></section></aside>` : ""; return `<main><section class="page-head store-head"><div><p class="eyebrow">PRIVATE REWARDS STORE</p><h1>Choose your next reward.</h1><p class="muted">Spend Quest Points on things that support your growth, wellbeing and Halyk community.</p></div><div class="wallet"><small>Available balance</small><strong>${money(state.points)} <span>QP</span></strong><button class="link-button" data-view="history">View history →</button></div></section><div class="category-tabs">${categories.map((c, i) => `<button class="category-tab ${i === 0 ? "active" : ""}" data-category="${c}">${c}</button>`).join("")}</div><section class="reward-grid">${state.rewards.map(rewardCard).join("")}</section><section class="store-principles card"><div><span class="principle-icon">✦</span><h2>Rewards for meaningful progress</h2><p class="muted">Quest Points are earned for voluntary learning, knowledge sharing, mentoring and initiative — never for routine work or overtime.</p></div><div class="principles-list"><span>◈ No public leaderboards</span><span>◈ Private balance and history</span><span>◈ HR approval for selected benefits</span></div></section>${active}</main>`; }
function renderHistory(): string { return `<main><section class="page-head"><div><p class="eyebrow">PRIVATE EMPLOYEE SPACE</p><h1>Мои награды</h1><p class="muted">История ваших заявок и использованных Quest Points.</p></div><button class="button secondary" data-view="rewards">← Back to store</button></section><div class="history-summary"><article class="card"><small>Available balance</small><strong>${money(state.points)} QP</strong></article><article class="card"><small>Total redeemed</small><strong>${money(state.totalSpent)} QP</strong></article><article class="card"><small>Requests this year</small><strong>${state.requests.length}</strong></article></div><section class="card history-table"><div class="section-title"><div><h2>Reward history</h2><p class="muted">Only visible to you.</p></div><span class="private-badge">Private</span></div>${state.requests.map((request) => `<div class="history-row"><div class="history-icon">✦</div><div><strong>${esc(request.title)}</strong><small>${esc(request.category)} · ${esc(request.requestedAt)}</small></div><b>${money(request.cost)} QP</b><span class="history-status ${request.status.toLowerCase()}">${request.status}</span></div>`).join("") || `<p class="muted">Заявок пока нет.</p>`}</section></main>`; }
function renderPendingRewards(): string {
  return `<main><section class="card risk-table"><h2>Заявки на награды</h2><p class="muted">Одобрите заявку, отклоните с возвратом баллов или отметьте выдачу награды.</p>${state.hrRequests.map((request) => `<div class="history-row"><div class="history-icon">✦</div><div><strong>${esc(request.title)}</strong><small>${esc(request.employee_id)} · ${esc(request.requestedAt)}</small></div><b>${money(request.cost)} QP</b><span class="history-status ${request.status.toLowerCase()}">${esc(request.status)}</span>${request.status === "Pending" ? `<button class="button secondary" data-reward-decision="Rejected" data-request="${esc(request.id)}">Отклонить</button><button class="button primary" data-reward-decision="Approved" data-request="${esc(request.id)}">Одобрить</button>` : request.status === "Approved" ? `<button class="button primary" data-fulfill="${esc(request.id)}">Выдано сотруднику</button>` : ""}</div>`).join("") || `<p class="muted">Заявок пока нет.</p>`}</section></main>`;
}
function renderAssistant(): string { if (!state.chatOpen) return ""; return `<aside class="assistant-panel"><div class="assistant-header"><div><span class="ai-avatar">AI</span><span><strong>Halyk AI Assistant</strong><small>Career Quest support</small></span></div><button data-chat-close>×</button></div><div class="chat-messages">${state.chatMessages.map((message) => `<div class="chat-bubble ${message.role}">${esc(message.text)}</div>`).join("")}${state.chatLoading ? `<div class="chat-bubble assistant typing">Thinking…</div>` : ""}</div><div class="suggestions"><button data-suggestion="What should I do next?">What should I do next?</button><button data-suggestion="Explain my skill gap">Explain my skill gap</button><button data-suggestion="How can I earn QP?">How can I earn QP?</button></div><form class="chat-form" id="chat-form"><input name="message" placeholder="Ask about your development…" autocomplete="off"><button aria-label="Send">↑</button></form><small class="chat-private">Your conversation is private to your profile.</small></aside>`; }
function renderToast(): string { return state.toast ? `<div class="toast ${state.toast.tone}">${state.toast.tone === "success" ? "✓" : "!"} ${esc(state.toast.message)}</div>` : ""; }
function render(): void {
  if (state.authEnabled && !state.user) state.view = "login";
  if (state.view === "hr" && !canViewHr()) state.view = "employee";
  root.innerHTML = `${renderHeader()}${state.view === "login" ? renderLogin() : state.view === "employee" ? renderEmployee() : state.view === "hr" ? renderHr() + renderPendingRewards() : state.view === "rewards" ? renderRewards() : renderHistory()}${renderAssistant()}${renderToast()}`;
  bind(); bindRewardDecisions(); bindSessionControls();
}

async function loadEmployee(id: string): Promise<void> {
  const generation = ++profileLoadGeneration;
  state.loading = true; state.error = undefined; render();
  try {
    const [profile, recommendations, wallet, requests] = await Promise.all([api.profile(id), api.recommendations(id), api.wallet(id), api.requests(id)]);
    if (generation !== profileLoadGeneration) return;
    if (state.profile.employee_id !== id) state.chatMessages = [{ role: "assistant", text: "Здравствуйте! Чем помочь с вашим развитием?" }];
    state.profile = profile; state.recommendations = recommendations.recommendations; state.points = wallet.balance;
    state.totalEarned = wallet.total_earned; state.totalSpent = wallet.total_spent; state.requests = requests;
  } catch (error) { state.error = `Не удалось загрузить профиль: ${String(error)}`; state.recommendations = []; }
  finally { if (generation === profileLoadGeneration) { state.loading = false; render(); } }
}
async function completeActivity(activityId: string): Promise<void> {
  if (state.busyActivity) return;
  const employeeId = state.profile.employee_id;
  const operation = `${employeeId}:activity:${activityId}`;
  const key = attemptKeys.get(operation) ?? crypto.randomUUID(); attemptKeys.set(operation, key);
  state.busyActivity = activityId; state.error = undefined; render();
  try {
    const result = await api.complete(activityId, employeeId, key);
    attemptKeys.delete(operation); state.points = result.points_balance;
    state.toast = { message: result.points_awarded ? `Активность выполнена. +${result.points_awarded} QP.` : "Выполнение учтено. Новые баллы за эту активность не начислены.", tone: "success" };
    await Promise.allSettled([loadEmployee(employeeId), refreshHr()]);
  } catch (error) { state.error = `Не удалось подтвердить выполнение: ${String(error)}. Можно повторить запрос.`; }
  finally { state.busyActivity = undefined; render(); }
}
async function uploadProfile(file: File): Promise<void> {
  state.loading = true; state.error = undefined; render();
  try { const result = await api.upload(file); const id = result.employee_ids[0]; state.employees = await api.employees(); if (id) await loadEmployee(id); await refreshHr(); }
  catch (error) { state.error = `Не удалось загрузить JSON: ${String(error)}`; }
  finally { state.loading = false; render(); }
}
async function sendChat(message: string): Promise<void> { if (!message.trim()) return; state.chatMessages.push({ role: "user", text: message }); state.chatLoading = true; render(); try { const result = await api.chat(message, state.profile.employee_id); state.chatMessages.push({ role: "assistant", text: result.answer }); } catch { state.chatMessages.push({ role: "assistant", text: "Не удалось получить ответ сервера. Попробуйте отправить вопрос ещё раз." }); } finally { state.chatLoading = false; render(); } }
async function redeemReward(id: string): Promise<void> {
  if (rewardBusy) return;
  rewardBusy = true;
  const employeeId = state.profile.employee_id;
  const operation = `${employeeId}:reward:${id}`;
  const key = attemptKeys.get(operation) ?? crypto.randomUUID(); attemptKeys.set(operation, key); render();
  try {
    const result = await api.redeem(id, employeeId, key);
    attemptKeys.delete(operation); state.points = result.balance; state.selectedReward = undefined;
    state.toast = { message: "Заявка отправлена в HR. Баллы списаны.", tone: "success" };
    await Promise.allSettled([refreshWallet(), refreshHr(), api.rewards().then((items) => { state.rewards = items; })]);
  } catch (error) { state.toast = { message: `Не удалось оформить награду: ${String(error)}`, tone: "error" }; }
  finally { rewardBusy = false; render(); }
}
async function decideRewardRequest(requestId: string, decision: "Approved" | "Rejected"): Promise<void> {
  try { await api.decideReward(requestId, decision); await Promise.allSettled([refreshHr(), refreshWallet(), api.rewards().then((items) => { state.rewards = items; })]); state.toast = { message: decision === "Approved" ? "Заявка одобрена. После передачи награды отметьте выдачу." : "Заявка отклонена; баллы возвращены.", tone: "success" }; }
  catch (error) { state.toast = { message: `Не удалось обработать заявку: ${String(error)}`, tone: "error" }; }
  render();
}
function bindRewardDecisions(): void { document.querySelectorAll<HTMLButtonElement>("[data-reward-decision]").forEach((button) => button.addEventListener("click", () => void decideRewardRequest(button.dataset.request!, button.dataset.rewardDecision as "Approved" | "Rejected"))); }
async function switchToDemoEmployee(): Promise<void> {
  state.loading = true; state.error = undefined; render();
  try {
    if (state.authEnabled) {
      try {
        const res = await api.login("demo.employee@halykbank.kz", "demo123");
        state.user = res.user;
      } catch (err) {
        console.warn("Demo employee login API:", err);
      }
    }
    await loadApplication();
    await loadEmployee("E0028");
    state.view = "employee";
    state.toast = { message: "Демо-вход: выбран сотрудник E0028", tone: "success" };
  } catch (err) {
    state.toast = { message: `Ошибка переключения: ${String(err)}`, tone: "error" };
  } finally {
    state.loading = false;
    render();
  }
}

async function switchToDemoHr(): Promise<void> {
  state.loading = true; state.error = undefined; render();
  try {
    if (state.authEnabled) {
      try {
        const res = await api.login("hr.manager@halykbank.kz", "admin123");
        state.user = res.user;
      } catch (err) {
        console.warn("Demo HR login API:", err);
      }
    }
    await loadApplication();
    await refreshHr();
    state.view = "hr";
    state.toast = { message: "Демо-вход: переключено на HR-аналитику", tone: "success" };
  } catch (err) {
    state.toast = { message: `Ошибка переключения: ${String(err)}`, tone: "error" };
  } finally {
    state.loading = false;
    render();
  }
}

function bind(): void {
  document.querySelectorAll<HTMLElement>("[data-view]").forEach((el) => el.addEventListener("click", () => { state.view = el.dataset.view as View; render(); if (state.view === "hr") void refreshHr().then(render).catch(showError); if (state.view === "history") void refreshWallet().then(render).catch(showError); }));
  document.querySelectorAll("#jury-btn-employee, #login-quick-emp").forEach((btn) => btn.addEventListener("click", () => void switchToDemoEmployee()));
  document.querySelectorAll("#jury-btn-hr, #login-quick-hr").forEach((btn) => btn.addEventListener("click", () => void switchToDemoHr()));
  document.querySelector<HTMLSelectElement>("#language")?.addEventListener("change", (event) => { state.language = (event.target as HTMLSelectElement).value as Language; render(); });
  document.querySelector<HTMLButtonElement>("[data-language-switch]")?.addEventListener("click", () => { state.language = state.language === "ru" ? "kz" : "ru"; render(); });
  document.querySelector<HTMLFormElement>("#login-form")?.addEventListener("submit", (event) => { event.preventDefault(); void signIn(event.currentTarget as HTMLFormElement); });
  document.querySelector<HTMLButtonElement>("[data-password-toggle]")?.addEventListener("click", (event) => { const button = event.currentTarget as HTMLButtonElement; const input = button.parentElement?.querySelector<HTMLInputElement>("input"); if (input) { input.type = input.type === "password" ? "text" : "password"; button.textContent = input.type === "password" ? "Show" : "Hide"; } });
  document.querySelector<HTMLSelectElement>("#employee-select")?.addEventListener("change", (event) => void loadEmployee((event.target as HTMLSelectElement).value));
  document.querySelector("#upload-button")?.addEventListener("click", () => document.querySelector<HTMLInputElement>("#profile-file")?.click());
  document.querySelector<HTMLInputElement>("#profile-file")?.addEventListener("change", (event) => { const file = (event.target as HTMLInputElement).files?.[0]; if (file) void uploadProfile(file); });
  document.querySelectorAll<HTMLButtonElement>(".complete-button").forEach((button) => button.addEventListener("click", () => void completeActivity(button.dataset.activity!)));
  document.querySelector("[data-chat-open]")?.addEventListener("click", () => { state.chatOpen = true; render(); });
  document.querySelector("[data-chat-close]")?.addEventListener("click", () => { state.chatOpen = false; render(); });
  document.querySelectorAll<HTMLButtonElement>("[data-suggestion]").forEach((button) => button.addEventListener("click", () => void sendChat(button.dataset.suggestion!)));
  document.querySelector<HTMLFormElement>("#chat-form")?.addEventListener("submit", (event) => { event.preventDefault(); const input = (event.currentTarget as HTMLFormElement).elements.namedItem("message") as HTMLInputElement; void sendChat(input.value); input.value = ""; });
  document.querySelectorAll<HTMLButtonElement>("[data-reward]").forEach((button) => button.addEventListener("click", () => { state.selectedReward = state.rewards.find((reward) => reward.id === button.dataset.reward); render(); }));
  document.querySelectorAll<HTMLElement>("[data-close-drawer]").forEach((element) => element.addEventListener("click", () => { if (element.classList.contains("drawer-backdrop") || element.classList.contains("drawer-close")) { state.selectedReward = undefined; render(); } }));
  document.querySelector("[data-redeem]")?.addEventListener("click", (event) => redeemReward((event.currentTarget as HTMLElement).dataset.redeem!));
  document.querySelectorAll<HTMLButtonElement>("[data-category]").forEach((button) => button.addEventListener("click", () => { const value = button.dataset.category as RewardCategory | "All rewards"; document.querySelectorAll("[data-category]").forEach((item) => item.classList.toggle("active", item === button)); document.querySelectorAll<HTMLElement>(".reward-card").forEach((card) => { const category = card.querySelector<HTMLElement>(".category-tag")?.textContent; card.style.display = value === "All rewards" || category === value ? "" : "none"; }); }));
}
async function bootstrap(): Promise<void> {
  render();
  try {
    const [connected, session] = await Promise.all([api.health(), api.me()]);
    state.connected = connected; state.authEnabled = session.auth_enabled; state.user = session.user; state.authChecked = true;
    if (state.user && state.authEnabled) {
      state.view = state.user.role === "hr" ? "hr" : "employee";
      await loadApplication();
    } else if (!state.authEnabled) {
      state.view = "employee";
      await loadApplication();
    }
  } catch (error) { state.connected = false; state.error = `Не удалось подключиться к серверу: ${String(error)}`; }
  render();
}

let profileLoadGeneration = 0;
let rewardBusy = false;
const attemptKeys = new Map<string, string>();
const canViewHr = () => !state.authEnabled || state.user?.role === "hr";
const showError = (error: unknown) => { state.toast = { message: String(error), tone: "error" }; render(); };
function renderHeader(): string {
  const name = esc(state.profile.name ?? state.user?.username ?? "Career Quest");
  return header().replace("Aigerim S.</span>", `${name}</span>`).replace('<span class="avatar">AS</span>', '<span class="avatar">H</span>').replace('</nav>', '</nav><button class="button secondary" id="logout-button">Выход</button>');
}
async function refreshWallet(): Promise<void> {
  const id = state.profile.employee_id;
  const [wallet, requests] = await Promise.all([api.wallet(id), api.requests(id)]);
  if (id !== state.profile.employee_id) return;
  state.points = wallet.balance; state.totalEarned = wallet.total_earned; state.totalSpent = wallet.total_spent; state.requests = requests;
}
async function refreshHr(): Promise<void> {
  if (!canViewHr()) return;
  const [analytics, rewardAnalytics, requests] = await Promise.all([api.analytics(), api.rewardAnalytics(), api.hrRequests()]);
  state.analytics = analytics; state.rewardAnalytics = rewardAnalytics; state.hrRequests = requests;
}
async function loadApplication(): Promise<void> {
  const [employees, rewards] = await Promise.all([api.employees(), api.rewards()]);
  state.employees = employees; state.rewards = rewards;
  const first = state.user?.employee_id ?? (employees.some((employee) => employee.employee_id === "E0028") ? "E0028" : employees[0]?.employee_id);
  await Promise.all([first ? loadEmployee(first) : Promise.resolve(), refreshHr()]);
}
async function signIn(form: HTMLFormElement): Promise<void> {
  if (!state.authChecked || !state.connected) return;
  const data = new FormData(form); state.loading = true; state.error = undefined; render();
  try {
    if (state.authEnabled) state.user = (await api.login(String(data.get("username")), String(data.get("password")))).user;
    await loadApplication(); state.view = state.user?.role === "hr" ? "hr" : "employee";
  } catch (error) { state.error = String(error); }
  finally { state.loading = false; render(); }
}
function bindSessionControls(): void {
  if (!canViewHr()) document.querySelectorAll('[data-view="hr"],#employee-select,#upload-button,#profile-file').forEach((node) => node.remove());
  if (state.loading || state.busyActivity) document.querySelectorAll<HTMLButtonElement | HTMLSelectElement>(".complete-button,#employee-select").forEach((node) => { node.disabled = true; });
  if (rewardBusy) document.querySelectorAll<HTMLButtonElement>("[data-redeem]").forEach((button) => { button.disabled = true; });
  document.querySelector("#logout-button")?.addEventListener("click", () => { void api.logout().then(() => { state.user = null; state.view = "login"; state.chatOpen = false; state.points = 0; attemptKeys.clear(); render(); }).catch(showError); });
  document.querySelectorAll<HTMLButtonElement>("[data-fulfill]").forEach((button) => button.addEventListener("click", () => {
    button.disabled = true;
    void api.fulfillReward(button.dataset.fulfill!).then(async () => { await Promise.allSettled([refreshHr(), refreshWallet()]); state.toast = { message: "Выдача награды отмечена.", tone: "success" }; render(); }).catch(showError);
  }));
}
window.addEventListener("session-expired", () => { state.user = null; state.view = "login"; state.chatOpen = false; state.error = "Сессия завершена. Войдите снова."; render(); });

void bootstrap();
