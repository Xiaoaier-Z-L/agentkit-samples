const REPOSITORY_ROOT = 'https://github.com/bytedance/agentkit-samples';
const DEMO_PATH = 'python/02-use-cases/hybrid_cloud_agent_harness';
const fileUrl = path => `${REPOSITORY_ROOT}/blob/main/${DEMO_PATH}/${path}`;
const directoryUrl = path => `${REPOSITORY_ROOT}/tree/main/${DEMO_PATH}/${path}`;
const REFERENCE_ROOT = 'https://github.com/deusyu/harness-engineering';

const STEPS = [
  {
    id: 'record', badge: 'RECORD', title: '把意图与状态变成工件', subtitle: 'Repo / state store is the record',
    summary: 'Harness 的起点不是 system prompt，而是智能体可重新读取的版本化记录：任务规格、验收标准、任务状态、scratchpad 与候选工件。计划可以重建，事实和完成状态不能只存在于聊天历史。',
    value: '<p><b>客服场景：</b>把“退款窗口改为 10 天、保留人工确认和引用”写成 SPEC 与 acceptance，而不是口头告诉 Agent。<br><b>混合云：</b>规范和 Skill 进仓库；运行中状态落 PostgreSQL Session；候选大工件落 Sandbox 工作区或对象存储。</p>',
    proof: ['spec.json / SPEC.md 可版本化', 'tasks.json 明确记录 passes 与反馈', 'scratchpad 只保存跨轮必要发现'],
    files: 'examples/customer_policy_change/ · engineering_harness.py',
    links: [
      {label:'示例 SPEC 与验收工件', href:directoryUrl('examples/customer_policy_change'), kind:'source'},
      {label:'混合云映射说明', href:fileUrl('docs/ralph_customer_service_mapping.md'), kind:'doc'},
      {label:'参考：仓库即记录系统', href:`${REFERENCE_ROOT}/blob/main/concepts/01-repo-as-source-of-truth.md`, kind:'reference'},
    ],
    code: `spec.json       # human intent + acceptance\ntasks.json      # pass/fail + feedback\nscratchpad.md   # cross-iteration discoveries\ncandidate_policy.json`,
    failure: '如果关键决策只存在于 Prompt、会议或某次模型上下文里，下一轮 Agent 无法可靠恢复。',
  },
  {
    id: 'context', badge: 'CONTEXT', title: '每轮从新鲜上下文恢复', subtitle: 'Fresh context is reliability',
    summary: '长任务不应无限累积聊天历史。每次迭代重新读取小型入口、当前任务状态和必要工件，让上下文可预测；AGENTS.md 是地图，按需指向更深文档。',
    value: '<p><b>客服场景：</b>Builder 修复时只读取 spec、失败不变量和当前候选包，不继承上一轮的推理噪声。<br><b>混合云：</b>Runtime 每轮按 checkpoint 重建上下文；Knowledge/Skills 按需加载，MEM0 仅提供已验证的稳定经验。</p>',
    proof: ['每轮重新从磁盘/状态库读取', '模型上下文不充当权威状态', '入口文档保持短小并可导航'],
    files: 'engineering_harness.py · examples/.../AGENTS.md',
    links: [
      {label:'Fresh-context 实现源码', href:fileUrl('engineering_harness.py'), kind:'source'},
      {label:'示例 AGENTS.md 地图', href:fileUrl('examples/customer_policy_change/AGENTS.md'), kind:'doc'},
      {label:'参考：Harness 核心概念', href:REFERENCE_ROOT, kind:'reference'},
    ],
    code: `state = read_json("tasks.json")\ncandidate = read_json("candidate_policy.json")\n# do not replay unbounded model chat\nrepair(state["feedback"], candidate)`,
    failure: '上下文越长不等于信息越可靠；历史推理、过期计划和失败尝试会挤占真正的任务状态。',
  },
  {
    id: 'roles', badge: 'LOOP', title: '让角色在有界循环中协作', subtitle: 'Planner → Builder → Critic → Finalizer',
    summary: 'Harness 负责循环、角色切换、预算与交接协议；模型负责在角色允许的自主空间内完成工作。计划不是结果，Builder 也不能自证完成。',
    value: '<p><b>客服场景：</b>Planner 拆验收项；Builder 在隔离工作区生成候选规则；Critic 独立复验；Finalizer 决定是否发布。<br><b>混合云：</b>VeADK Agent/Workflow 承载角色，Sandbox 执行修改，Trace 串联 iteration 与 role。</p>',
    proof: ['role 与 iteration 可观测', 'Critic 不共享 Builder 临时状态', 'max_iterations 限制成本和死循环'],
    files: 'engineering_harness.py · agent.py',
    links: [
      {label:'角色循环源码', href:fileUrl('engineering_harness.py'), kind:'source'},
      {label:'Runtime 工具接线', href:fileUrl('agent.py'), kind:'source'},
      {label:'参考：Ralph Demo', href:`${REFERENCE_ROOT}/tree/main/practice/01-ralph-demo`, kind:'reference'},
    ],
    code: `1 Planner   → persist spec and tasks\n2 Builder   → candidate + test\n3 Builder   → fresh-context repair\n4 Critic    → independent verification\n5 Finalizer → completion decision`,
    failure: '让单个 Agent 一次性规划、实现、评审并宣布完成，会把生成偏差和确认偏差叠加在一起。',
  },
  {
    id: 'backpressure', badge: 'GATES', title: '用机械反馈形成背压', subtitle: 'Backpressure over prescription',
    summary: '不要用更长 Prompt 规定每一步怎么修。把不可违反的边界编码成测试、schema、lint 和评估器；Harness 把失败信号交给下一轮，让 Agent 自主选择修复路径。',
    value: '<p><b>客服场景：</b>首次候选故意漏掉 citation_required；机械门禁只返回这个失败项，下一轮据此修复。<br><b>混合云：</b>Sandbox 跑单测/规则检查，Code Evaluator 做确定性门禁，失败证据写回 Session 并进入 Trace。</p>',
    proof: ['首次 Builder = needs_revision', '失败项是机器可读的不变量', '修复后 Critic 重跑完整检查'],
    files: 'engineering_harness.py · tests/test_engineering_harness.py',
    links: [
      {label:'背压与修复源码', href:fileUrl('engineering_harness.py'), kind:'source'},
      {label:'机械门禁测试', href:fileUrl('tests/test_engineering_harness.py'), kind:'source'},
      {label:'参考：机械化执行', href:`${REFERENCE_ROOT}/blob/main/concepts/02-mechanical-enforcement.md`, kind:'reference'},
    ],
    code: `refund_window_is_bounded\nmanual_confirmation_required\ncitation_required       # first run fails here\npolicy_source_recorded\n\nfeedback → next fresh iteration`,
    failure: '只写“必须高质量、请认真检查”不是门禁；无法机械判断的约束会随上下文和模型波动。',
  },
  {
    id: 'state', badge: 'RECOVER', title: '让失败可以恢复而非重来', subtitle: 'Disk is state, durable artifacts are memory',
    summary: '每轮完成后持久化任务状态、候选工件、反馈和检查证据。Runtime 重启或上下文刷新后从 checkpoint 恢复，而不是要求同一个模型会话永远存活。',
    value: '<p><b>客服场景：</b>规则候选包、失败项和 passes 状态是交接协议；稳定经验才进入长期记忆。<br><b>混合云：</b>PostgreSQL Session 存 run/iteration/task；Sandbox/对象存储存工件；MEM0 不保存未验证计划和凭据。</p>',
    proof: ['运行状态与模型上下文解耦', '候选工件可被 Critic 独立重载', '重启后不会重复已通过的 story'],
    files: 'engineering_harness.py · docs/ralph_customer_service_mapping.md',
    links: [
      {label:'状态持久化源码', href:fileUrl('engineering_harness.py'), kind:'source'},
      {label:'平台组件职责说明', href:fileUrl('docs/ralph_customer_service_mapping.md'), kind:'doc'},
      {label:'参考：Ralph README', href:`${REFERENCE_ROOT}/blob/main/practice/01-ralph-demo/README.md`, kind:'reference'},
    ],
    code: `PostgreSQL Session: run / iteration / task\nSandbox storage: candidate artifacts\nRepository: spec / skill / tests / docs\nMEM0: verified reusable learnings only`,
    failure: '把所有状态放在内存或单次会话中，遇到 Runtime 重启、超时或上下文耗尽就只能从头开始。',
  },
  {
    id: 'complete', badge: 'STOP', title: '验证完成承诺并治理熵', subtitle: 'Completion is proved, not claimed',
    summary: 'Finalizer 必须同时看到所有 story 通过、独立 Critic 证据有效且仍在预算内，才允许发出 HARNESS_COMPLETE。发布后继续用评测、Trace 和定期扫描管理漂移。',
    value: '<p><b>客服场景：</b>候选规则只有在引用、确认、窗口与来源全部通过后才能进入 Knowledge 发布流程。<br><b>混合云：</b>Code Evaluator 是硬门禁；LLM Judge 补充语义质量；Trace 验证真实轨迹；定时评测发现规则和 Skill 漂移。</p>',
    proof: ['completion promise 有严格前置条件', '达到 max_iterations 时必须 blocked', '评测同时覆盖结果与执行轨迹'],
    files: 'engineering_harness.py · evaluation/ · docs/evaluation_and_observability.md',
    links: [
      {label:'完成判定源码', href:fileUrl('engineering_harness.py'), kind:'source'},
      {label:'评测与 Trace 文档', href:fileUrl('docs/evaluation_and_observability.md'), kind:'doc'},
      {label:'参考：Ralph 配置', href:`${REFERENCE_ROOT}/blob/main/practice/01-ralph-demo/ralph.yml`, kind:'reference'},
    ],
    code: `complete = (\n  all_stories_pass\n  and independent_critic_passed\n  and iterations <= max_iterations\n)\n\nreturn "HARNESS_COMPLETE" if complete else "blocked"`,
    failure: '模型说“完成了”不是停止条件；没有独立证据的 completion promise 会让未完成工作进入生产。',
  },
];

const list = document.querySelector('#step-list');
let active = 0;

function renderList() {
  list.innerHTML = STEPS.map((step, index) => `
    <button class="step ${index === active ? 'active' : ''}" data-index="${index}">
      <span>${String(index + 1).padStart(2, '0')}</span>
      <span><small>${step.badge}</small><strong>${step.title}</strong><em>${step.subtitle}</em></span>
      <b>→</b>
    </button>`).join('');
  list.querySelectorAll('.step').forEach(button => {
    button.addEventListener('click', () => { active = Number(button.dataset.index); render(); });
  });
}

function render() {
  const step = STEPS[active];
  renderList();
  document.querySelector('#detail-step').textContent = `GATE ${String(active + 1).padStart(2, '0')}`;
  document.querySelector('#detail-title').textContent = step.title;
  document.querySelector('#detail-badge').textContent = step.badge;
  document.querySelector('#detail-summary').textContent = step.summary;
  document.querySelector('#detail-value').innerHTML = step.value;
  document.querySelector('#detail-proof').innerHTML = step.proof.map(item => `<li>${item}</li>`).join('');
  document.querySelector('#detail-files').textContent = step.files;
  document.querySelector('#detail-code').textContent = step.code;
  document.querySelector('#detail-failure').textContent = step.failure;
  document.querySelector('#detail-links').replaceChildren(...step.links.map(link => {
    const anchor = document.createElement('a');
    anchor.href = link.href;
    anchor.target = '_blank';
    anchor.rel = 'noreferrer';
    anchor.className = `resource-link ${link.kind}`;
    anchor.textContent = `${link.label} ↗`;
    return anchor;
  }));
  document.querySelector('#previous').disabled = active === 0;
  document.querySelector('#next').textContent = active === STEPS.length - 1 ? '进入工作台 ↗' : '下一层 →';
  history.replaceState(null, '', `#${step.id}`);
}

document.querySelector('#previous').addEventListener('click', () => { if (active > 0) { active -= 1; render(); } });
document.querySelector('#next').addEventListener('click', () => {
  if (active === STEPS.length - 1) window.location.href = '/chat';
  else { active += 1; render(); }
});
const initial = STEPS.findIndex(step => `#${step.id}` === window.location.hash);
active = initial >= 0 ? initial : 0;
render();
