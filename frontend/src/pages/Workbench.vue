<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJSON, postJSON } from '../api'
import TierLadder from '../components/TierLadder.vue'
import SegmentTable from '../components/SegmentTable.vue'

const kwh = ref(220)
const peak = ref(false)
const period = ref('') // 账期年月 YYYY-MM
const schemeKey = ref('') // 空 = 自动解析
const schemes = ref([])
const result = ref(null)
const error = ref('')

const REASON_TEXT = {
  no_period: '未提供账期',
  no_matching_scheme: '无启用方案覆盖该账期月份',
}

onMounted(async () => {
  schemes.value = (await getJSON('/api/season-schemes')).items
})

const sourceLabel = computed(() => {
  const ts = result.value?.tier_source
  if (!ts) return ''
  if (ts.fallback) return `回退默认档表（${REASON_TEXT[ts.reason] ?? ts.reason}）`
  const via = ts.source === 'explicit' ? '显式指定' : '按账期命中'
  return `方案「${ts.scheme_name}」(${ts.scheme_key}，${via})`
})

const run = async () => {
  error.value = ''
  try {
    result.value = await postJSON('/api/bill', {
      kwh: kwh.value,
      peak: peak.value,
      persist: true,
      period: period.value || null,
      scheme_key: schemeKey.value || null,
    })
  } catch (e) {
    try {
      error.value = JSON.parse(e.message).detail ?? e.message
    } catch {
      error.value = e.message
    }
  }
}
</script>

<template>
  <div class="page work">
    <h1>测算工作台</h1>
    <div class="panel form-row">
      <label>电量(kWh) <input type="number" v-model.number="kwh" min="0" step="1" /></label>
      <label>账期年月 <input type="month" v-model="period" /></label>
      <label>档表
        <select v-model="schemeKey">
          <option value="">自动解析（按账期）</option>
          <option v-for="s in schemes" :key="s.key" :value="s.key">{{ s.name }}（{{ s.key }}）</option>
        </select>
      </label>
      <label><input type="checkbox" v-model="peak" /> 尖峰系数</label>
      <button @click="run">计算并入库</button>
    </div>
    <p v-if="error" class="error-text">{{ error }}</p>
    <div v-if="result" class="panel">
      <p>
        合计 ¥{{ result.total }} <span class="muted">记录#{{ result.run_id }}</span>
      </p>
      <p>
        档表来源：
        <span :class="result.tier_source.fallback ? 'badge fallback' : 'badge'">{{ sourceLabel }}</span>
      </p>
      <TierLadder :segments="result.segments" />
      <SegmentTable :rows="result.segments" />
    </div>
  </div>
</template>

<style scoped>
.form-row { display: flex; flex-wrap: wrap; gap: 1rem; align-items: end; }
input[type=number] { width: 6rem; margin-left: 0.35rem; }
select { background: #0d1612; border: 1px solid var(--muted); color: var(--text); padding: 0.35rem 0.5rem; border-radius: 6px; }
.badge { background: color-mix(in srgb, var(--accent) 20%, transparent); color: var(--accent); padding: 0.15rem 0.6rem; border-radius: 999px; }
.badge.fallback { background: color-mix(in srgb, #e0a75e 20%, transparent); color: #e0a75e; }
.error-text { color: #e06c75; }
</style>
