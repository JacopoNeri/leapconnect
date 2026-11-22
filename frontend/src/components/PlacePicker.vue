<template>
  <div ref="root" class="place-picker" :class="{ open }">
    <div class="pp-input">
      <MapPin :size="14" class="pp-pin" :class="{ set: !!modelValue }" />
      <input
        ref="input"
        v-model="query"
        type="text"
        maxlength="200"
        :placeholder="placeholder"
        @focus="onFocus"
        @keydown.enter.prevent="onEnter"
        @keydown.esc="close"
      />
      <Plug v-if="modelValue && modelValue.charger" :size="13" class="pp-plug" title="Charger here" />
      <button v-if="modelValue" class="pp-clear" title="Clear" @mousedown.prevent @click="clear"><X :size="13" /></button>
    </div>

    <div v-if="open" class="pp-menu" @mousedown.prevent>
      <template v-if="savedMatches.length">
        <div class="pp-section">Saved places</div>
        <button v-for="p in savedMatches" :key="'s' + p.id" class="pp-item" @click="pickSaved(p)">
          <Star :size="13" class="pp-icon star" />
          <span class="pp-text"><b>{{ p.name }}</b><small v-if="p.address">{{ p.address }}</small></span>
          <Plug v-if="p.charger" :size="12" class="pp-icon plug" />
        </button>
      </template>
      <template v-if="zoneMatches.length">
        <div class="pp-section">Zones</div>
        <button v-for="z in zoneMatches" :key="'z' + z.id" class="pp-item" @click="pickZone(z)">
          <MapPin :size="13" class="pp-icon" />
          <span class="pp-text"><b>{{ z.name }}</b></span>
          <Plug v-if="z.charging_tier_id" :size="12" class="pp-icon plug" />
        </button>
      </template>

      <template v-if="results.length">
        <div class="pp-section">Addresses</div>
        <button v-for="(r, i) in results" :key="'r' + i" class="pp-item" @click="pickResult(r)">
          <Navigation :size="13" class="pp-icon" />
          <span class="pp-text"><b>{{ r.name }}</b><small>{{ r.address }}</small></span>
        </button>
      </template>

      <div v-if="searchError" class="pp-note error">{{ searchError }}</div>
      <div v-else-if="searched && !results.length && !searching" class="pp-note">No address found</div>

      <button v-if="canSearch" class="pp-item pp-action" :disabled="searching" @click="search">
        <Loader2 v-if="searching" :size="13" class="pp-icon spin" />
        <Search v-else :size="13" class="pp-icon" />
        <span class="pp-text">Search “{{ query.trim() }}” on the map <small>Enter</small></span>
      </button>
      <button v-if="query.trim()" class="pp-item pp-action" @click="pickCustom">
        <Pencil :size="13" class="pp-icon" />
        <span class="pp-text">Use “{{ query.trim() }}” without address <small>enter the km by hand</small></span>
      </button>
      <div v-if="!query.trim() && !savedMatches.length && !zoneMatches.length" class="pp-note">
        Type a place or an address, then press Enter to search it.
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { api } from '../composables/useApi'
import { Loader2, MapPin, Navigation, Pencil, Plug, Search, Star, X } from 'lucide-vue-next'

const props = defineProps({
  // The resolved place shown in the field ({ name, address, latitude, longitude, charger }).
  modelValue: { type: Object, default: null },
  places: { type: Array, default: () => [] },
  zones: { type: Array, default: () => [] },
  placeholder: { type: String, default: 'Where to?' },
})
// "select" receives a place reference: { placeId } for a saved place, or a
// full place object for anything else.
const emit = defineEmits(['select'])

const root = ref(null)
const input = ref(null)
const open = ref(false)
const query = ref(props.modelValue?.name || '')
const results = ref([])
const searching = ref(false)
const searched = ref(false)
const searchError = ref('')

watch(() => props.modelValue?.name, (name) => { if (!open.value) query.value = name || '' })

const needle = computed(() => {
  const q = query.value.trim().toLowerCase()
  // Showing the current value: list everything, not only matches.
  return q === (props.modelValue?.name || '').toLowerCase() ? '' : q
})
function matches(text) { return !needle.value || (text || '').toLowerCase().includes(needle.value) }
const savedMatches = computed(() => props.places.filter((p) => matches(p.name) || matches(p.address)).slice(0, 8))
const zoneMatches = computed(() => {
  const saved = new Set(props.places.map((p) => p.name.toLowerCase()))
  return props.zones
    .filter((z) => z.latitude != null && !saved.has(z.name.toLowerCase()) && matches(z.name))
    .slice(0, 6)
})
const canSearch = computed(() => query.value.trim().length >= 3)

function onFocus() {
  open.value = true
  input.value?.select()
  document.addEventListener('mousedown', onOutside)
}
function close() {
  open.value = false
  results.value = []
  searched.value = false
  searchError.value = ''
  query.value = props.modelValue?.name || ''
  document.removeEventListener('mousedown', onOutside)
  input.value?.blur()
}
function onOutside(e) { if (root.value && !root.value.contains(e.target)) close() }
onBeforeUnmount(() => document.removeEventListener('mousedown', onOutside))

function onEnter() {
  if (savedMatches.value.length === 1 && needle.value) return pickSaved(savedMatches.value[0])
  if (canSearch.value) search()
}

// Nominatim's policy rules out search-as-you-type: search on demand only.
async function search() {
  if (searching.value) return
  searching.value = true
  searchError.value = ''
  try {
    results.value = await api('GET', `/api/trip-planner/search?q=${encodeURIComponent(query.value.trim())}`)
  } catch (err) {
    results.value = []
    searchError.value = err.message
  } finally {
    searching.value = false
    searched.value = true
  }
}

function done(ref) { emit('select', ref); close() }
function pickSaved(p) { done({ placeId: p.id }) }
function pickZone(z) {
  // A zone with a charging tariff is where you charge (e.g. home).
  done({ name: z.name, address: '', latitude: z.latitude, longitude: z.longitude, charger: !!z.charging_tier_id, charger_power_kw: null })
}
function pickResult(r) {
  done({ name: r.name || r.address.split(',')[0], address: r.address, latitude: r.latitude, longitude: r.longitude, charger: false, charger_power_kw: null })
}
function pickCustom() {
  done({ name: query.value.trim().slice(0, 80), address: '', latitude: null, longitude: null, charger: false, charger_power_kw: null })
}
function clear() { emit('select', null); query.value = '' }
</script>

<style scoped>
.place-picker { position: relative; min-width: 0; }
.pp-input { display: flex; align-items: center; gap: 6px; background: var(--input); border: 1px solid var(--border); border-radius: 8px; padding: 0 8px; }
.place-picker.open .pp-input { border-color: var(--accent); }
.pp-input input { flex: 1; min-width: 0; border: none; background: transparent; padding: 7px 0; color: var(--text); font-size: 13px; font-family: inherit; outline: none; }
.pp-pin { color: var(--muted); flex-shrink: 0; }
.pp-pin.set { color: var(--accent); }
.pp-plug { color: var(--green); flex-shrink: 0; }
.pp-clear { background: none; border: none; color: var(--muted); cursor: pointer; display: flex; padding: 2px; }
.pp-clear:hover { color: var(--red); }

.pp-menu {
  position: absolute; z-index: 40; top: calc(100% + 4px); left: 0; right: 0; min-width: 260px;
  max-height: 340px; overflow-y: auto; background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25); padding: 4px;
}
.pp-section { font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); padding: 8px 8px 4px; }
.pp-item { display: flex; align-items: center; gap: 8px; width: 100%; text-align: left; background: none; border: none; border-radius: 7px; padding: 7px 8px; color: var(--text); cursor: pointer; font-family: inherit; }
.pp-item:hover:not(:disabled) { background: var(--btn-bg); }
.pp-item:disabled { opacity: 0.6; cursor: default; }
.pp-action { color: var(--accent); }
.pp-icon { flex-shrink: 0; color: var(--muted); }
.pp-action .pp-icon { color: var(--accent); }
.pp-icon.star { color: var(--amber); }
.pp-icon.plug { color: var(--green); }
.pp-text { display: flex; flex-direction: column; min-width: 0; font-size: 13px; }
.pp-text b { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pp-text small { font-size: 11px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pp-note { font-size: 12px; color: var(--muted); padding: 8px; }
.pp-note.error { color: var(--red); }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
