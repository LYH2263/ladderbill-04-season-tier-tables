<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJSON, requestJSON } from '../api'

const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1)
const FALLBACK_REASONS = {
  matched: '命中季节方案',
  no_match: '该月份无启用方案覆盖，已回退全局默认档表',
  no_enabled_plan: '不存在任何启用方案，已回退全局默认档表',
}

const plans = ref([])
const error = ref('')
const conflict = ref(null)
const saving = ref(false)
const editingId = ref(null)
const form = ref(blankForm())

// 账期解析与只读试算
const resolveYear = ref(new Date().getFullYear())
const resolveMonth = ref(new Date().getMonth() + 1)
const resolved = ref(null)
const trialCode = ref('')
const trialKwh = ref(400)
const trialPeak = ref(false)
const trial = ref(null)
const trialError = ref('')

function blankForm() {
  return {
    code: '',
    name: '',
    months: [],
    enabled: true,
    tiers: [
      { up_to: 240, price: 0.55 },
      { up_to: null, price: 0.8 },
    ],
  }
}

const isEditing = computed(() => editingId.value !== null)

async function load() {
  plans.value = (await getJSON('/api/season-plans')).items
}

function toggleMonth(m) {
  const i = form.value.months.indexOf(m)
  if (i >= 0) form.value.months.splice(i, 1)
  else form.value.months.push(m)
  form.value.months.sort((a, b) => a - b)
}

// 末档固定为开放区间（up_to=null）；新增档位插入到末档之前
function addBand() {
  form.value.tiers.splice(form.value.tiers.length - 1, 0, { up_to: 400, price: 0.7 })
}
function removeBand(idx) {
  if (form.value.tiers.length <= 2 || idx === form.value.tiers.length - 1) return
  form.value.tiers.splice(idx, 1)
}

function startCreate() {
  editingId.value = null
  form.value = blankForm()
  error.value = ''
  conflict.value = null
}
function startEdit(p) {
  editingId.value = p.id
  form.value = {
    code: p.code,
    name: p.name,
    months: [...p.months],
    enabled: p.enabled,
    tiers: p.tiers.map((t) => ({ up_to: t.up_to, price: t.price })),
  }
  error.value = ''
  conflict.value = null
}

async function save() {
  error.value = ''
  conflict.value = null
  if (!form.value.months.length) {
    error.value = '请至少选择一个生效月份'
    return
  }
  const payload = {
    code: form.value.code.trim(),
    name: form.value.name.trim(),
    months: form.value.months,
    enabled: form.value.enabled,
    tiers: form.value.tiers.map((t, i) => ({
      up_to: i === form.value.tiers.length - 1 ? null : Number(t.up_to),
      price: Number(t.price),
    })),
  }
  saving.value = true
  try {
    if (isEditing.value) await requestJSON('PUT', `/api/season-plans/${editingId.value}`, payload)
    else await requestJSON('POST', '/api/season-plans', payload)
    await load()
    startCreate()
  } catch (e) {
    if (e.status === 409 && e.payload?.conflicts) {
      conflict.value = e.payload.conflicts
      error.value = e.payload.message || '生效月份与其它启用方案冲突'
    } else {
      error.value = e.message || '保存失败'
    }
  } finally {
    saving.value = false
  }
}

async function remove(p) {
  if (!confirm(`删除方案「${p.name}」(${p.code})？`)) return
  try {
    await requestJSON('DELETE', `/api/season-plans/${p.id}`)
    if (editingId.value === p.id) startCreate()
    await load()
  } catch (e) {
    error.value = e.message || '删除失败'
  }
}

async function doResolve() {
  resolved.value = null
  const q = `year=${resolveYear.value}&month=${resolveMonth.value}`
  resolved.value = await getJSON(`/api/season-plans/resolve?${q}`)
}

async function doTrial() {
  trial.value = null
  trialError.value = ''
  if (!trialCode.value) {
    trialError.value = '请选择方案标识'
    return
  }
  try {
    trial.value = await requestJSON(
      'POST',
      `/api/season-plans/${encodeURIComponent(trialCode.value)}/trial`,
      { kwh: Number(trialKwh.value), peak: trialPeak.value },
    )
  } catch (e) {
    trialError.value = e.message || '试算失败'
  }
}

const monthLabel = (ms) => ms.map((m) => `${m}月`).join('、')

onMounted(async () => {
  await load()
  if (plans.value.length) trialCode.value = plans.value[0].code
  await doResolve()
})
</script>
<template>
  <div class="page season-page">
    <h1>季节档位方案</h1>

    <div class="grid">
      <!-- 方案列表 -->
      <section class="panel">
        <div class="section-head">
          <h2>方案列表</h2>
          <button @click="startCreate">＋ 新建方案</button>
        </div>
        <table>
          <thead>
            <tr><th>标识</th><th>名称</th><th>生效月份</th><th>状态</th><th>阶梯</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="p in plans" :key="p.id" :class="{ off: !p.enabled }">
              <td><code>{{ p.code }}</code></td>
              <td>{{ p.name }}</td>
              <td>{{ monthLabel(p.months) }}</td>
              <td>
                <span :class="p.enabled ? 'tag-on' : 'tag-off'">
                  {{ p.enabled ? '启用' : '停用' }}
                </span>
              </td>
              <td class="muted">{{ p.tiers.length }} 档</td>
              <td class="row-actions">
                <button class="link" @click="startEdit(p)">编辑</button>
                <button class="link danger" @click="remove(p)">删除</button>
              </td>
            </tr>
            <tr v-if="!plans.length"><td colspan="6" class="muted">尚无方案</td></tr>
          </tbody>
        </table>
      </section>

      <!-- 编辑器 -->
      <section class="panel">
        <h2>{{ isEditing ? `编辑方案 #${editingId}` : '新建方案' }}</h2>
        <div v-if="error" class="alert">
          <div>{{ error }}</div>
          <ul v-if="conflict" class="conflict-list">
            <li v-for="(c, i) in conflict" :key="i">
              <strong>{{ c.month }}月</strong> 与启用方案
              <code>{{ c.with_code }}</code>（{{ c.with_name }}）相交
            </li>
          </ul>
        </div>
        <div class="form-grid">
          <label>方案标识
            <input v-model="form.code" :disabled="isEditing" placeholder="如 wet" />
          </label>
          <label>方案名称
            <input v-model="form.name" placeholder="如 丰水期" />
          </label>
        </div>
        <label class="inline"><input type="checkbox" v-model="form.enabled" /> 启用（停用方案不参与账期解析，也不做月份冲突校验）</label>

        <h3>生效月份</h3>
        <div class="months">
          <button
            v-for="m in MONTHS"
            :key="m"
            type="button"
            class="month-chip"
            :class="{ picked: form.months.includes(m) }"
            @click="toggleMonth(m)"
          >{{ m }}月</button>
        </div>

        <h3>阶梯序列</h3>
        <table>
          <thead><tr><th>档位</th><th>上限(kWh)</th><th>单价(元/kWh)</th><th></th></tr></thead>
          <tbody>
            <tr v-for="(t, i) in form.tiers" :key="i">
              <td>第 {{ i + 1 }} 档</td>
              <td>
                <span v-if="i === form.tiers.length - 1" class="muted">以上（末档开放）</span>
                <input v-else type="number" min="0" step="1" v-model.number="t.up_to" />
              </td>
              <td><input type="number" min="0" step="0.01" v-model.number="t.price" /></td>
              <td>
                <button
                  v-if="i !== form.tiers.length - 1"
                  class="link danger"
                  type="button"
                  @click="removeBand(i)"
                >移除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <button class="secondary" type="button" @click="addBand">＋ 在末档前插入档位</button>

        <div class="editor-actions">
          <button :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存方案' }}</button>
          <button v-if="isEditing" class="secondary" @click="startCreate">取消编辑</button>
        </div>
      </section>

      <!-- 账期解析 -->
      <section class="panel">
        <h2>账期解析</h2>
        <div class="form-row">
          <label>年 <input type="number" v-model.number="resolveYear" min="2000" max="2999" /></label>
          <label>月 <input type="number" v-model.number="resolveMonth" min="1" max="12" /></label>
          <button @click="doResolve">解析</button>
        </div>
        <div v-if="resolved" class="resolve-out">
          <p v-if="resolved.fallback" class="fallback-badge">
            ⚠ fallback：{{ FALLBACK_REASONS[resolved.fallback_reason] }}
            <code>{{ resolved.fallback_reason }}</code>
          </p>
          <p v-else class="match-badge">
            ✓ 命中方案 <strong>{{ resolved.plan.name }}</strong>
            <code>{{ resolved.plan.code }}</code>
          </p>
          <p class="muted">{{ resolved.year }} 年 {{ resolved.month }} 月账期，采用 {{ resolved.tiers.length }} 档</p>
          <table>
            <thead><tr><th>上限</th><th>单价</th></tr></thead>
            <tbody>
              <tr v-for="(t, i) in resolved.tiers" :key="i">
                <td>{{ t.up_to ?? '以上' }}</td><td>{{ t.price }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 只读试算 -->
      <section class="panel">
        <h2>按方案试算（只读，不写运行）</h2>
        <div class="form-row">
          <label>方案
            <select v-model="trialCode">
              <option v-for="p in plans" :key="p.id" :value="p.code">{{ p.name }} ({{ p.code }})</option>
            </select>
          </label>
          <label>电量(kWh) <input type="number" v-model.number="trialKwh" min="0" /></label>
          <label class="inline"><input type="checkbox" v-model="trialPeak" /> 尖峰</label>
          <button @click="doTrial">试算</button>
        </div>
        <p v-if="trialError" class="alert">{{ trialError }}</p>
        <div v-if="trial">
          <p>
            方案 <strong>{{ trial.plan.name }}</strong>
            <code>{{ trial.plan.code }}</code>
            <span class="tag-readonly">只读</span>
            合计 <strong>¥{{ trial.total }}</strong>
          </p>
          <table>
            <thead><tr><th>区间(kWh)</th><th>电量</th><th>单价</th><th>金额</th></tr></thead>
            <tbody>
              <tr v-for="(s, i) in trial.segment_summary" :key="i">
                <td>{{ s.from_kwh }} – {{ s.to_kwh }}</td>
                <td>{{ s.qty }}</td>
                <td>{{ s.price }}</td>
                <td>¥{{ s.amount }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>
<style scoped>
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
.section-head { display: flex; justify-content: space-between; align-items: center; }
.row-actions { white-space: nowrap; }
.off { opacity: 0.55; }
.tag-on { color: var(--accent); font-weight: 600; }
.tag-off { color: var(--muted); }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 0.5rem; }
.form-grid input { width: 100%; margin-top: 0.25rem; }
.inline { display: inline-flex; align-items: center; gap: 0.35rem; margin: 0.4rem 0; }
.months { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.5rem; }
.month-chip {
  background: #0d1612; color: var(--muted);
  border: 1px solid var(--muted); border-radius: 999px;
  padding: 0.25rem 0.7rem; font-weight: 400;
}
.month-chip.picked { background: var(--accent); color: #111; border-color: var(--accent); font-weight: 600; }
.editor-actions { margin-top: 0.9rem; display: flex; gap: 0.6rem; }
.secondary { background: transparent; color: var(--accent); border: 1px solid var(--accent); }
.link { background: none; color: var(--accent); padding: 0.15rem 0.4rem; font-weight: 400; }
.link.danger { color: #e57373; }
.alert {
  background: color-mix(in srgb, #e57373 18%, transparent);
  border: 1px solid #e57373; border-radius: 8px;
  padding: 0.5rem 0.7rem; color: #ffcdd2;
}
.conflict-list { margin: 0.35rem 0 0; padding-left: 1.1rem; }
.fallback-badge {
  background: color-mix(in srgb, #ffb74d 16%, transparent);
  border: 1px solid #ffb74d; border-radius: 8px; padding: 0.5rem 0.7rem;
}
.match-badge {
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  border: 1px solid var(--accent); border-radius: 8px; padding: 0.5rem 0.7rem;
}
.tag-readonly {
  font-size: 0.75rem; border: 1px solid var(--muted); color: var(--muted);
  border-radius: 999px; padding: 0 0.45rem; margin: 0 0.35rem;
}
.form-row { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: end; }
.form-row input, .form-row select { margin-top: 0.25rem; }
@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
</style>
