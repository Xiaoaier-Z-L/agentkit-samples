const REPOSITORY_ROOT = 'https://github.com/Xiaoaier-Z-L/agentkit-samples';
const BRANCH = 'codex/hybrid-cloud-loop-harness-demos';
const DEMO_PATH = 'python/02-use-cases/hybrid_cloud_loop_engineering';
const fileUrl = path => `${REPOSITORY_ROOT}/blob/${BRANCH}/${DEMO_PATH}/${path}`;

const STEPS = [
  {
    id: 'objective', badge: 'SCOPE', title: '先固定目标与验收证据',
    summary: 'Loop 不围绕“再想一想”运行，而是围绕一个可验证目标运行。Planner 为不同目标声明 required_events、引用要求和副作用属性。',
    value: '<p><b>退款闭环：</b>规则步骤必须产生 Knowledge 引用；交易步骤必须产生分析工具事件；工单步骤必须同时看到记忆读取与幂等创建事件。</p>',
    proof: ['loop.start.objective', 'loop.plan.steps[].required_events', '每个步骤显式标记 side_effect'],
    files: 'loop_engine.py · demo_core.py',
    code: `ground_policy → knowledge.search + citation\nanalyze_transactions → tool.transaction_analysis\ncreate_work_order → memory.read + tool.work_order.create`,
    failure: '如果验收条件只是“回答看起来不错”，Critic 无法区分真实执行、自然语言模拟和缺失证据。',
  },
  {
    id: 'budget', badge: 'BUDGET', title: '预算必须由控制器执行',
    summary: 'max_iterations 与 max_tool_calls 是执行前后的硬门禁。控制器在动作前预留预算，并按实际受控能力事件累计用量。',
    value: '<p><b>混合云：</b>预算值进入 Runtime Trace；工具预算不足时不会进入下一步，更不会先执行写操作再补救。</p>',
    proof: ['执行前 remaining_* 可见', 'loop.observe.tool_calls_used', 'tool_budget_reached / tool_budget_exceeded'],
    files: 'loop_engine.py · tests/test_loop_engine.py',
    code: `if used + step.expected_tool_calls > max_tool_calls:\n    stop("tool_budget_reached")\n\nused += observed_controlled_events`,
    failure: '只把预算写进 Prompt 或事件 detail，不参与分支判断，不能阻止失控调用。',
  },
  {
    id: 'act', badge: 'ACT', title: '每轮只推进一个可验收步骤',
    summary: '一次 iteration 包含 Act、Observe 和 Critic。业务动作继续复用已验证的 HybridCustomerService，不在 Loop 层复制 Knowledge、MEM0 或 CRM 实现。',
    value: '<p><b>混合云：</b>Runtime 承载控制器；业务核心继续通过平台关联使用 Knowledge、MEM0、PostgreSQL、Sandbox、MCP、Skills 与 A2A。</p>',
    proof: ['loop.iteration.start.step', '原业务 capability events', '一个步骤对应一个清晰责任'],
    files: 'loop_engine.py · agent.py · platform_*.py',
    code: `result = business.chat(step.instruction, ...)\nevents.extend(result.events)\n# orchestration does not reimplement tools`,
    failure: '把业务决策复制进 Loop 层会产生两套规则，基础 Demo 的验证结论也无法复用。',
  },
  {
    id: 'checkpoint', badge: 'WRITE', title: '副作用必须经过 checkpoint',
    summary: '只读步骤可以安全失败；写操作在执行前记录 idempotency scope。Critic 只读已产生的结果，绝不通过重跑来“确认”工单。',
    value: '<p><b>退款工单：</b>使用 session_id + step_id 形成循环 checkpoint；底层 CRM 继续用 session_id + operation 作为业务幂等键。</p>',
    proof: ['loop.checkpoint 只在写步骤前出现', 'tool.work_order.create 只出现一次', '评审阶段没有工具副作用'],
    files: 'loop_engine.py · tools/crm.py',
    code: `loop.checkpoint(\n  step="create_work_order",\n  idempotency_scope=f"{session_id}:create_work_order"\n)`,
    failure: '把写操作放进自动重试会造成重复工单、重复扣款或难以恢复的外部状态。',
  },
  {
    id: 'critic', badge: 'PROOF', title: 'Critic 只接受结构化证据',
    summary: 'Observe 汇总本轮事件、引用和工具数；Critic 对照当前步骤的 required_events 判断 accepted 或 needs_revision。',
    value: '<p><b>混合云：</b>应用级 loop.* 事件解释“为什么继续或停止”；平台 Trace 证明实际模型、工具、Token、耗时和状态，两者互补。</p>',
    proof: ['missing_evidence 是机器可读列表', 'citation 是独立验收项', '安全 blocked 优先结束循环'],
    files: 'loop_engine.py · docs/evaluation_and_observability.md',
    code: `missing = required_events - observed_events\nif require_citation and not citations:\n    missing += ["citation"]`,
    failure: 'Critic 若再次调用工具或依赖自己的主观判断，就既不独立，也可能制造新的副作用。',
  },
  {
    id: 'stop', badge: 'STOP', title: '每种停止都可解释、可回归',
    summary: '成功、安全拦截、工具预算、迭代预算、无进展和副作用未验证都有独立 reason。遇到确定性无进展时立即停止，不做昂贵的原地重试。',
    value: '<p><b>发布门禁：</b>本地测试断言事件顺序和停止原因；离线评测覆盖结果；AgentKit Trace 验证真实执行轨迹和凭据脱敏。</p>',
    proof: ['loop.stop.reason', 'iterations_used / tool_calls_used', 'accepted_steps 与 planned_steps'],
    files: 'tests/test_loop_engine.py · evaluation/',
    code: `acceptance_criteria_met | policy_blocked\ntool_budget_reached | iteration_budget_reached\nno_progress | side_effect_unverified`,
    failure: '模型自行宣布完成、沉默超时或统一返回 failed，都无法支持生产排障和评测回归。',
  },
];

const list = document.querySelector('#step-list');
let active = 0;

function renderList() {
  list.innerHTML = STEPS.map((step, index) => `
    <button class="step ${index === active ? 'active' : ''}" data-index="${index}">
      <span>${String(index + 1).padStart(2, '0')}</span>
      <span><small>${step.badge}</small><strong>${step.title}</strong></span>
      <b>→</b>
    </button>`).join('');
  list.querySelectorAll('.step').forEach(button => {
    button.addEventListener('click', () => { active = Number(button.dataset.index); render(); });
  });
}

function render() {
  const step = STEPS[active];
  renderList();
  document.querySelector('#detail-step').textContent = `STAGE ${String(active + 1).padStart(2, '0')}`;
  document.querySelector('#detail-title').textContent = step.title;
  document.querySelector('#detail-badge').textContent = step.badge;
  document.querySelector('#detail-summary').textContent = step.summary;
  document.querySelector('#detail-value').innerHTML = step.value;
  document.querySelector('#detail-proof').innerHTML = step.proof.map(item => `<li>${item}</li>`).join('');
  document.querySelector('#detail-files').textContent = step.files;
  document.querySelector('#detail-code').textContent = step.code;
  document.querySelector('#detail-failure').textContent = step.failure;
  document.querySelector('#previous').disabled = active === 0;
  document.querySelector('#next').textContent = active === STEPS.length - 1 ? '进入工作台 ↗' : '下一步 →';
  history.replaceState(null, '', `#${step.id}`);
}

document.querySelector('#development-guide-link').href = fileUrl('docs/loop_engineering.md');
document.querySelector('#previous').addEventListener('click', () => { if (active > 0) { active -= 1; render(); } });
document.querySelector('#next').addEventListener('click', () => {
  if (active === STEPS.length - 1) window.location.href = '/chat';
  else { active += 1; render(); }
});
const initial = STEPS.findIndex(step => `#${step.id}` === window.location.hash);
active = initial >= 0 ? initial : 0;
render();
