<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, postJSON } from '../api'
import TierLadder from '../components/TierLadder.vue'
import SegmentTable from '../components/SegmentTable.vue'

const now = new Date()
const kwh = ref(220)
const peak = ref(false)
const year = ref(now.getFullYear())
const month = ref(now.getMonth() + 1)
const planCode = ref('') // 空串 = 不显式指定，走账期解析
const plans = ref([])
const result = ref(null)
const loadError = ref('')

const FALLBACK_REASON_TEXT = {
  no_match: '该账期月份无启用季节方案，已回退全局默认档表',
  no_enabled_plan: '不存在任何启用季节方案，已回退全局默认档表',
}

const run = async () => {
  loadError.value = ''
  result.value = null
  try {
    result.value = await postJSON('/api/bill', {
      kwh: kwh.value,
      peak: peak.value,
      persist: true,
      year: year.value,
      month: month.value,
      plan_code: planCode.value || null,
    })
  } catch (e) {
    loadError.value = '计算失败：' + e.message
  }
}

onMounted(async () => {
  try {
    plans.value = (await getJSON('/api/season-plans')).items.filter((p) => p.enabled)
  } catch {
    /* 方案列表加载失败不阻断测算 */
  }
})
</script>
<template>
  <div class="page work">
    <h1>测算工作台</h1>
    <div class="panel form-row">
      <label>电量(kWh) <input type="number" v-model.number="kwh" min="0" step="1" /></label>
      <label>账期年
        <input type="number" v-model.number="year" min="2000" max="2999" />
      </label>
      <label>账期月
        <input type="number" v-model.number="month" min="1" max="12" />
      </label>
      <label>档表
        <select v-model="planCode">
          <option value="">自动按账期解析</option>
          <option v-for="p in plans" :key="p.id" :value="p.code">{{ p.name }} ({{ p.code }})</option>
        </select>
      </label>
      <label><input type="checkbox" v-model="peak" /> 尖峰系数</label>
      <button @click="run">计算并入库</button>
    </div>

    <p v-if="loadError" class="alert">{{ loadError }}</p>

    <div v-if="result" class="panel">
      <div class="applied">
        <template v-if="result.applied.fallback">
          <span class="badge fallback">⚠ FALLBACK</span>
          <span>{{ FALLBACK_REASON_TEXT[result.applied.fallback_reason] || result.applied.fallback_reason }}</span>
          <code class="muted">{{ result.applied.fallback_reason }}</code>
        </template>
        <template v-else>
          <span class="badge matched">✓ 季节方案</span>
          <span>本次采用：<strong>{{ result.applied.plan.name }}</strong></span>
          <code class="muted">{{ result.applied.plan.code }}</code>
        </template>
      </div>
      <p>
        合计 ¥{{ result.total }}
        <span class="muted">记录#{{ result.run_id }}
          · {{ result.applied.year }} 年 {{ result.applied.month }} 月账期</span>
      </p>
      <TierLadder :segments="result.segments" />
      <SegmentTable :rows="result.segments" />
    </div>
  </div>
</template>
<style scoped>
.form-row { display: flex; flex-wrap: wrap; gap: 1rem; align-items: end; }
input[type=number] { width: 6rem; margin-left: 0.35rem; }
select { margin-left: 0.35rem; }
.applied { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; margin-bottom: 0.6rem; }
.badge { border-radius: 999px; padding: 0.15rem 0.6rem; font-size: 0.8rem; font-weight: 600; }
.badge.matched { background: color-mix(in srgb, var(--accent) 20%, transparent); color: var(--accent); }
.badge.fallback { background: color-mix(in srgb, #ffb74d 20%, transparent); color: #ffb74d; }
.alert {
  background: color-mix(in srgb, #e57373 18%, transparent);
  border: 1px solid #e57373; border-radius: 8px; padding: 0.5rem 0.7rem;
}
</style>
