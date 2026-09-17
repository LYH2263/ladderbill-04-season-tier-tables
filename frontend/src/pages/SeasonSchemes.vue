<script setup>
import { onMounted, ref } from 'vue'
import { delJSON, getJSON, postJSON, putJSON } from '../api'
import SegmentTable from '../components/SegmentTable.vue'

const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1)
const schemes = ref([])
const error = ref('')
const conflicts = ref([])

const emptyForm = () => ({
  key: '',
  name: '',
  months: [],
  enabled: true,
  tiers: [
    { up_to: 180, price: 0.52 },
    { up_to: null, price: 0.82 },
  ],
})
const form = ref(null) // null = 未打开；{...} = 编辑中
const editing = ref(false)

const trialKey = ref('')
const trialKwh = ref(300)
const trialPeak = ref(false)
const trialResult = ref(null)

const load = async () => {
  schemes.value = (await getJSON('/api/season-schemes')).items
}
onMounted(load)

const monthsText = (ms) => ms.map((m) => `${m}月`).join(' ')

const parseError = (e) => {
  conflicts.value = []
  try {
    const det = JSON.parse(e.message).detail
    if (det && Array.isArray(det.conflicts)) {
      conflicts.value = det.conflicts
      return det.message
    }
    return typeof det === 'string' ? det : JSON.stringify(det)
  } catch {
    return e.message
  }
}

const openCreate = () => {
  form.value = emptyForm()
  editing.value = false
  error.value = ''
  conflicts.value = []
}
const openEdit = (s) => {
  form.value = {
    key: s.key,
    name: s.name,
    months: [...s.months],
    enabled: s.enabled,
    tiers: s.tiers.map((t) => ({ up_to: t.up_to, price: t.price })),
  }
  editing.value = true
  error.value = ''
  conflicts.value = []
}
const cancel = () => { form.value = null }

const addTier = () => form.value.tiers.push({ up_to: null, price: 0 })
const removeTier = (i) => form.value.tiers.splice(i, 1)

const save = async () => {
  error.value = ''
  conflicts.value = []
  const payload = {
    ...form.value,
    tiers: form.value.tiers.map((t) => ({
      up_to: t.up_to === '' || t.up_to === null ? null : Number(t.up_to),
      price: Number(t.price),
    })),
  }
  try {
    if (editing.value) {
      await putJSON(`/api/season-schemes/${form.value.key}`, payload)
    } else {
      await postJSON('/api/season-schemes', payload)
    }
    form.value = null
    await load()
  } catch (e) {
    error.value = parseError(e)
  }
}

const remove = async (s) => {
  if (!confirm(`删除方案「${s.name}」(${s.key})？`)) return
  error.value = ''
  try {
    await delJSON(`/api/season-schemes/${s.key}`)
    await load()
  } catch (e) {
    error.value = parseError(e)
  }
}

const openTrial = (s) => {
  trialKey.value = trialKey.value === s.key ? '' : s.key
  trialResult.value = null
}
const runTrial = async () => {
  error.value = ''
  try {
    trialResult.value = await postJSON(`/api/season-schemes/${trialKey.value}/trial`, {
      kwh: trialKwh.value,
      peak: trialPeak.value,
    })
  } catch (e) {
    error.value = parseError(e)
  }
}
</script>

<template>
  <div class="page">
    <h1>季节档位方案</h1>
    <p class="muted">启用方案的生效月份两两不得重叠；测算按账期月份命中方案，未命中回退全局默认档表。</p>

    <div v-if="error" class="panel error">
      <strong>保存失败：</strong>{{ error }}
      <ul v-if="conflicts.length">
        <li v-for="(c, i) in conflicts" :key="i">
          {{ c.month }}月 已被「{{ c.scheme_name }}」({{ c.scheme_key }}) 占用
        </li>
      </ul>
    </div>

    <div class="panel">
      <button @click="openCreate">新建方案</button>
    </div>

    <div v-if="form" class="panel form">
      <h3>{{ editing ? `编辑方案 ${form.key}` : '新建方案' }}</h3>
      <div class="grid">
        <label>方案标识
          <input v-model.trim="form.key" :disabled="editing" placeholder="如 summer-ac" />
        </label>
        <label>方案名称 <input v-model.trim="form.name" placeholder="如 夏季空调方案" /></label>
        <label class="inline"><input type="checkbox" v-model="form.enabled" /> 启用</label>
      </div>
      <fieldset>
        <legend>生效月份</legend>
        <label v-for="m in MONTHS" :key="m" class="month">
          <input type="checkbox" :value="m" v-model="form.months" /> {{ m }}月
        </label>
      </fieldset>
      <fieldset>
        <legend>阶梯序列（上限留空表示“以上不限”，仅末档可不限）</legend>
        <div v-for="(t, i) in form.tiers" :key="i" class="tier-row">
          <span>第{{ i + 1 }}档</span>
          <input type="number" v-model="form.tiers[i].up_to" min="0" placeholder="上限kWh/留空不限" />
          <input type="number" v-model="form.tiers[i].price" min="0" step="0.01" placeholder="单价" />
          <button type="button" @click="removeTier(i)" :disabled="form.tiers.length <= 1">删除</button>
        </div>
        <button type="button" @click="addTier">加一档</button>
      </fieldset>
      <div class="actions">
        <button @click="save">保存</button>
        <button type="button" class="ghost" @click="cancel">取消</button>
      </div>
    </div>

    <table>
      <thead>
        <tr><th>标识</th><th>名称</th><th>生效月份</th><th>阶梯</th><th>状态</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="s in schemes" :key="s.key">
          <td><code>{{ s.key }}</code></td>
          <td>{{ s.name }}</td>
          <td>{{ monthsText(s.months) }}</td>
          <td>{{ s.tiers.map((t) => `${t.up_to ?? '以上'}:${t.price}`).join(' / ') }}</td>
          <td><span :class="s.enabled ? 'tag on' : 'tag off'">{{ s.enabled ? '启用' : '停用' }}</span></td>
          <td class="ops">
            <a href="#" @click.prevent="openEdit(s)">编辑</a>
            <a href="#" @click.prevent="openTrial(s)">试算</a>
            <a href="#" class="danger" @click.prevent="remove(s)">删除</a>
          </td>
        </tr>
        <tr v-if="!schemes.length"><td colspan="6" class="muted">暂无方案</td></tr>
      </tbody>
    </table>

    <div v-if="trialKey" class="panel">
      <h3>只读试算：{{ trialKey }}（不写运行记录）</h3>
      <div class="trial-form">
        <label>电量(kWh) <input type="number" v-model.number="trialKwh" min="0" /></label>
        <label><input type="checkbox" v-model="trialPeak" /> 尖峰系数</label>
        <button @click="runTrial">试算</button>
      </div>
      <div v-if="trialResult">
        <p>方案「{{ trialResult.scheme_name }}」 合计 <strong>¥{{ trialResult.total }}</strong></p>
        <SegmentTable :rows="trialResult.segments" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.error { border: 1px solid #e06c75; }
.error ul { margin: 0.4rem 0 0; }
.form .grid { display: flex; gap: 1rem; flex-wrap: wrap; align-items: end; }
.form fieldset { border: 1px solid color-mix(in srgb, var(--muted) 35%, transparent); border-radius: 8px; margin: 0.75rem 0; }
.month { display: inline-flex; align-items: center; gap: 0.2rem; margin-right: 0.6rem; }
.tier-row { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.4rem; }
.tier-row input { width: 9rem; }
.actions { display: flex; gap: 0.6rem; }
.ghost { background: transparent; color: var(--text); border: 1px solid var(--muted); }
.tag { padding: 0.1rem 0.5rem; border-radius: 999px; font-size: 0.8rem; }
.tag.on { background: color-mix(in srgb, var(--accent) 25%, transparent); color: var(--accent); }
.tag.off { background: color-mix(in srgb, var(--muted) 25%, transparent); color: var(--muted); }
.ops a { margin-right: 0.6rem; }
.danger { color: #e06c75; }
.trial-form { display: flex; gap: 1rem; align-items: end; flex-wrap: wrap; }
code { color: var(--accent); }
</style>
