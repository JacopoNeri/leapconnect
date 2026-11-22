<template>
  <div class="planner-tab">
    <div class="planner-header">
      <div class="header-title">
        <h2>Trip Planner</h2>
        <p>Plan the next days and get told when to charge</p>
      </div>
      <div class="header-actions">
        <span v-if="saveState" class="save-state">{{ saveState }}</span>
        <button class="toolbar-btn" title="Restart from the car's current state" @click="refreshStart">
          <RefreshCw :size="16" />
        </button>
      </div>
    </div>

    <div v-if="!ready" class="loading-center"><div class="spinner" /></div>

    <template v-else>
      <!-- Starting point -->
      <div class="card">
        <div class="card-title"><Battery :size="15" /> Starting point</div>
        <div class="form-grid">
          <div class="field span-2">
            <span class="field-label">Starting place</span>
            <div class="picker-row">
              <PlacePicker
                class="grow-1"
                :model-value="startPlace"
                :places="library.places"
                :zones="zones"
                placeholder="Where is the car now?"
                @select="(r) => (form.start_place = r)"
              />
              <button v-if="canSavePlace(form.start_place)" class="icon-btn" title="Save this place" @click="savePlaceRef(form.start_place)"><Star :size="14" /></button>
            </div>
          </div>
          <label class="field field-toggle">
            <span class="field-label">Charger there</span>
            <ToggleSwitch :model-value="!!startPlace?.charger" @update:model-value="(v) => setCharger(form.start_place, v)" />
          </label>
          <label class="field">
            <span class="field-label">From</span>
            <input v-model="form.start_time" type="datetime-local" />
            <span class="field-hint">
              <button class="link-btn" @click="form.start_time = nowLocal()">now</button>
            </span>
          </label>
          <label class="field">
            <span class="field-label">Battery now</span>
            <div class="input-unit">
              <input v-model.number="form.start_soc" type="number" min="0" max="100" step="1" />
              <span>%</span>
            </div>
            <span v-if="liveSoc != null" class="field-hint">
              Car: {{ liveSoc }}%
              <button v-if="liveSoc !== form.start_soc" class="link-btn" @click="form.start_soc = liveSoc">use</button>
            </span>
          </label>
          <label class="field">
            <span class="field-label">Never below</span>
            <div class="input-unit">
              <input v-model.number="form.min_soc" type="number" min="0" max="90" step="5" />
              <span>%</span>
            </div>
            <span class="field-hint">Minimum acceptable</span>
          </label>
          <label class="field">
            <span class="field-label">Never above</span>
            <div class="input-unit">
              <input v-model.number="form.max_soc" type="number" min="10" max="100" step="5" />
              <span>%</span>
            </div>
            <span class="field-hint">Charge up to this</span>
          </label>
        </div>

        <button class="advanced-toggle" @click="showAdvanced = !showAdvanced">
          <SlidersHorizontal :size="13" />
          <span>Car &amp; charging settings</span>
          <ChevronDown :size="14" :class="{ rotated: showAdvanced }" />
        </button>
        <div v-if="showAdvanced" class="form-grid advanced">
          <label class="field">
            <span class="field-label">Usable capacity</span>
            <div class="input-unit">
              <input v-model.number="form.capacity_kwh" type="number" min="5" max="250" step="0.1" />
              <span>kWh</span>
            </div>
            <span v-if="estimates.capacity" class="field-hint">
              {{ estimates.capacitySource }}: {{ estimates.capacity }} kWh
              <button v-if="estimates.capacity !== form.capacity_kwh" class="link-btn" @click="form.capacity_kwh = estimates.capacity">use</button>
            </span>
          </label>
          <label class="field">
            <span class="field-label">Consumption</span>
            <div class="input-unit">
              <input v-model.number="form.consumption_kwh_100km" type="number" min="5" max="60" step="0.1" />
              <span>kWh/100km</span>
            </div>
            <span v-if="estimates.consumption" class="field-hint">
              {{ estimates.consumptionSource }}: {{ estimates.consumption }}
              <button v-if="estimates.consumption !== form.consumption_kwh_100km" class="link-btn" @click="form.consumption_kwh_100km = estimates.consumption">use</button>
            </span>
          </label>
          <label class="field">
            <span class="field-label">Safety margin</span>
            <div class="input-unit">
              <input v-model.number="form.safety_margin_pct" type="number" min="0" max="100" step="1" />
              <span>%</span>
            </div>
            <span class="field-hint">Extra consumption (cold, motorway…)</span>
          </label>
          <label class="field">
            <span class="field-label">Charger power</span>
            <div class="input-unit">
              <input v-model.number="form.default_charger_power_kw" type="number" min="1" max="400" step="0.1" />
              <span>kW</span>
            </div>
            <span class="field-hint">Default for every charger</span>
          </label>
          <label class="field">
            <span class="field-label">Always top up below</span>
            <div class="input-unit">
              <input v-model.number="form.topup_below_soc" type="number" min="0" max="80" step="5" />
              <span>%</span>
            </div>
            <span class="field-hint">0 = only when needed</span>
          </label>
          <label class="field">
            <span class="field-label">Charging time</span>
            <select v-model="form.charge_timing">
              <option value="asap">Start on arrival</option>
              <option value="late">Finish at departure</option>
            </select>
          </label>
          <label class="field">
            <span class="field-label">Average speed</span>
            <div class="input-unit">
              <input v-model.number="form.avg_speed_kmh" type="number" min="10" max="150" step="5" />
              <span>km/h</span>
            </div>
            <span class="field-hint">When a trip has no duration</span>
          </label>
        </div>
      </div>

      <!-- Frequent trips -->
      <div class="card">
        <div class="card-title">
          <Bookmark :size="15" /> Frequent trips
          <span class="card-title-sub">{{ library.routes.length }} saved</span>
          <button class="link-btn right" @click="showPlaces = !showPlaces">
            {{ showPlaces ? 'Hide places' : `Places (${library.places.length})` }}
          </button>
        </div>

        <div v-if="!library.routes.length" class="empty-legs">
          Save a trip you make often with <Bookmark :size="12" class="inline-icon" /> in the list below
          (e.g. Home → Work), then add it here in one tap.
        </div>
        <template v-else>
          <div class="day-chips">
            <button
              v-for="d in nextDays"
              :key="d.key"
              class="chip"
              :class="{ active: d.key === routeDay }"
              @click="routeDay = d.key"
            >{{ d.label }}</button>
          </div>
          <div v-for="r in sortedRoutes" :key="r.id" class="route-row">
            <div class="route-name">
              <span>{{ placeName({ placeId: r.from_place_id }) }}</span>
              <ArrowRight :size="12" />
              <span>{{ placeName({ placeId: r.to_place_id }) }}</span>
              <Plug v-if="placeById(r.to_place_id)?.charger" :size="12" class="plug-icon" />
            </div>
            <input v-model="r.departure_time" class="time-input" type="time" title="Usual departure time" />
            <div class="input-unit route-km">
              <input v-model.number="r.distance_km" type="number" min="1" max="2000" step="1" />
              <span>km</span>
            </div>
            <button class="icon-btn accent" :title="`Add on ${dayName(routeDay)}`" @click="addRoute(r)"><Plus :size="14" /></button>
            <button class="icon-btn danger" title="Delete this frequent trip" @click="deleteRoute(r)"><Trash2 :size="14" /></button>
          </div>
          <button v-if="routesWithTime.length > 1" class="add-btn" @click="addAllRoutes">
            <CalendarPlus :size="14" /> Add all to {{ dayName(routeDay) }}
          </button>
        </template>

        <div v-if="showPlaces" class="places-box">
          <div class="places-title">Saved places</div>
          <div v-if="!library.places.length" class="empty-legs">No saved places yet: search one below or tap <Star :size="12" class="inline-icon" /> next to a place.</div>
          <div v-for="p in library.places" :key="p.id" class="place-row">
            <Star :size="14" class="star-icon" />
            <div class="place-info">
              <input v-model="p.name" type="text" maxlength="80" class="place-name" />
              <small>{{ p.address || `${p.latitude.toFixed(4)}, ${p.longitude.toFixed(4)}` }}</small>
            </div>
            <label class="place-charger" title="Charger at this place">
              <Plug :size="13" />
              <ToggleSwitch v-model="p.charger" />
            </label>
            <div v-if="p.charger" class="input-unit place-power">
              <input v-model.number="p.charger_power_kw" type="number" min="1" max="400" step="0.1" :placeholder="String(form.default_charger_power_kw)" />
              <span>kW</span>
            </div>
            <button class="icon-btn danger" title="Delete place" @click="deletePlace(p)"><Trash2 :size="14" /></button>
          </div>
          <div class="add-place">
            <PlacePicker :model-value="null" :places="[]" :zones="zones" placeholder="Add a place: search an address…" @select="addPlaceFromPicker" />
          </div>
        </div>
      </div>

      <!-- Trips -->
      <div class="card">
        <div class="card-title">
          <Route :size="15" /> Trips
          <span class="card-title-sub">{{ upcomingLegs.length }} planned</span>
          <button v-if="pastLegs.length" class="link-btn right" @click="removePast">
            Remove {{ pastLegs.length }} past
          </button>
        </div>

        <div v-if="!form.legs.length" class="empty-legs">
          Add the trips you need to make over the next days: each one starts where the previous one ends.
        </div>

        <div v-for="(leg, i) in sortedLegs" :key="leg.id" class="leg-row" :class="{ past: isPast(leg) }">
          <div class="leg-index">{{ i + 1 }}</div>
          <div class="leg-main">
            <div class="leg-from">
              From <b>{{ placeName(originRef(leg)) || 'starting place' }}</b>
            </div>
            <div class="leg-fields">
              <div class="field grow">
                <span class="field-label">To</span>
                <div class="picker-row">
                  <PlacePicker
                    class="grow-1"
                    :model-value="resolve(leg.to)"
                    :places="library.places"
                    :zones="zones"
                    @select="(r) => setDestination(leg, r)"
                  />
                  <button v-if="canSavePlace(leg.to)" class="icon-btn" title="Save this place" @click="savePlaceRef(leg.to)"><Star :size="14" /></button>
                </div>
              </div>
              <label class="field grow">
                <span class="field-label">Departure</span>
                <input v-model="leg.departure" type="datetime-local" />
              </label>
              <label class="field small">
                <span class="field-label">
                  Distance
                  <Loader2 v-if="routeState[leg.id]?.loading" :size="11" class="spin" />
                </span>
                <div class="input-unit">
                  <input :value="leg.distance_km" type="number" min="1" max="2000" step="0.1" placeholder="km" @input="setManual(leg, 'distance_km', $event)" />
                  <span>km</span>
                </div>
                <span v-if="routeState[leg.id]?.error" class="field-hint error">{{ routeState[leg.id].error }}</span>
                <span v-else-if="leg.manual && canAutoRoute(leg)" class="field-hint">
                  <button class="link-btn" @click="resetAuto(leg)">use route</button>
                </span>
                <span v-else-if="!leg.manual && leg.routeKey" class="field-hint">{{ leg.routeKey.startsWith('saved:') ? 'saved trip' : 'by road' }}</span>
              </label>
              <label class="field small">
                <span class="field-label">Duration</span>
                <div class="input-unit">
                  <input :value="leg.duration_min" type="number" min="1" max="2880" step="1" placeholder="auto" @input="setManual(leg, 'duration_min', $event)" />
                  <span>min</span>
                </div>
              </label>
              <label class="field field-toggle">
                <span class="field-label">Charger there</span>
                <ToggleSwitch :model-value="!!resolve(leg.to)?.charger" @update:model-value="(v) => setCharger(leg.to, v)" />
              </label>
              <label v-if="resolve(leg.to)?.charger" class="field small">
                <span class="field-label">Power</span>
                <div class="input-unit">
                  <input :value="resolve(leg.to).charger_power_kw" type="number" min="1" max="400" step="0.1" :placeholder="String(form.default_charger_power_kw)" @input="setPower(leg.to, $event)" />
                  <span>kW</span>
                </div>
              </label>
            </div>
          </div>
          <div class="leg-actions">
            <button class="icon-btn" :class="{ saved: isRouteSaved(leg) }" :disabled="!canSaveRoute(leg)" :title="saveRouteTitle(leg)" @click="saveRoute(leg)"><Bookmark :size="14" /></button>
            <button class="icon-btn" title="Add the return trip" @click="addReturn(leg)"><ArrowLeftRight :size="14" /></button>
            <button class="icon-btn" title="Duplicate on the next day" @click="duplicateNextDay(leg)"><Copy :size="14" /></button>
            <button class="icon-btn danger" title="Remove" @click="removeLeg(leg)"><Trash2 :size="14" /></button>
          </div>
        </div>

        <button class="add-btn" @click="addLeg"><Plus :size="14" /> Add trip</button>
      </div>

      <!-- Plan -->
      <div v-if="planError" class="alert error"><AlertTriangle :size="15" /> {{ planError }}</div>

      <template v-if="plan && plan.legs.length">
        <div class="summary-grid">
          <div class="summary-card">
            <div class="summary-value" style="color: var(--accent)">{{ Math.round(totalKm) }} km</div>
            <div class="summary-label">Total distance</div>
          </div>
          <div class="summary-card">
            <div class="summary-value" style="color: var(--green)">{{ plan.charges.length }}</div>
            <div class="summary-label">Charging sessions</div>
          </div>
          <div class="summary-card">
            <div class="summary-value" style="color: var(--purple)">{{ totalChargeKwh.toFixed(1) }} kWh</div>
            <div class="summary-label">Energy to charge</div>
          </div>
          <div class="summary-card">
            <div class="summary-value" :style="{ color: socColor(lastLeg.soc_end) }">{{ fmtSoc(lastLeg.soc_end) }}</div>
            <div class="summary-label">After the last trip</div>
          </div>
        </div>

        <div v-if="plan.warnings.length" class="alert" :class="plan.feasible ? 'warn' : 'error'">
          <AlertTriangle :size="15" />
          <ul><li v-for="w in plan.warnings" :key="w">{{ w }}</li></ul>
        </div>
        <div v-else class="alert ok">
          <CheckCircle2 :size="15" />
          <span>The battery always stays between {{ form.min_soc }}% and {{ form.max_soc }}%.</span>
        </div>

        <div class="timeline">
          <div v-for="day in timelineDays" :key="day.key" class="day-group">
            <div class="day-header">{{ day.label }}</div>

            <template v-for="item in day.items" :key="item.key">
              <!-- Charging suggestion -->
              <div v-if="item.type === 'charge'" class="tl-item charge" :class="{ topup: item.data.reason === 'topup' }">
                <div class="tl-icon charge-icon"><Zap :size="16" /></div>
                <div class="tl-body">
                  <div class="tl-title">
                    Charge at {{ item.data.location }}
                    <span v-if="item.data.reason === 'topup'" class="tag">top-up</span>
                    <span v-if="item.data.limited_by_time" class="tag warn">short stop</span>
                  </div>
                  <div class="tl-time">
                    {{ fmtTime(item.data.start) }} → {{ fmtTime(item.data.end) }}
                    <span v-if="!sameDay(item.data.start, item.data.end)"> ({{ fmtDayShort(item.data.end) }})</span>
                    · {{ fmtDuration(item.data.start, item.data.end) }}
                  </div>
                  <div class="tl-stats">
                    <span>{{ fmtSoc(item.data.from_soc) }} → <b>{{ fmtSoc(item.data.to_soc) }}</b></span>
                    <span>+{{ item.data.energy_kwh.toFixed(1) }} kWh</span>
                    <span>{{ item.data.power_kw }} kW</span>
                  </div>
                </div>
              </div>

              <!-- Trip -->
              <div v-else class="tl-item leg" :class="{ danger: item.data.below_min }">
                <div class="tl-icon leg-icon"><Car :size="16" /></div>
                <div class="tl-body">
                  <div class="tl-title">
                    <span>{{ item.from }} <ArrowRight :size="12" class="inline-icon" /> {{ item.data.label }}</span>
                    <span class="tl-distance">{{ item.data.distance_km }} km</span>
                  </div>
                  <div class="tl-time">
                    {{ fmtTime(item.data.departure) }} → {{ fmtTime(item.data.arrival) }}
                    · {{ item.data.energy_kwh.toFixed(1) }} kWh
                  </div>
                  <div class="soc-bar">
                    <div class="soc-bar-used" :style="usedStyle(item.data)" />
                    <div class="soc-bar-fill" :style="{ width: clampPct(item.data.soc_end) + '%', background: socColor(item.data.soc_end) }" />
                    <div class="soc-mark" :style="{ left: form.min_soc + '%' }" />
                    <div class="soc-mark target" :style="{ left: form.max_soc + '%' }" />
                  </div>
                  <div class="tl-stats">
                    <span>{{ fmtSoc(item.data.soc_start) }} → <b :style="{ color: socColor(item.data.soc_end) }">{{ fmtSoc(item.data.soc_end) }}</b></span>
                    <span>Range {{ item.data.range_km }} km</span>
                    <span>{{ item.data.range_to_min_km }} km before {{ form.min_soc }}%</span>
                    <span>{{ item.data.remaining_kwh.toFixed(1) }} kWh left</span>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../composables/useApi'
import ToggleSwitch from '../components/ToggleSwitch.vue'
import PlacePicker from '../components/PlacePicker.vue'
import {
  AlertTriangle, ArrowLeftRight, ArrowRight, Battery, Bookmark, CalendarPlus, Car, CheckCircle2,
  ChevronDown, Copy, Loader2, Plug, Plus, RefreshCw, Route, SlidersHorizontal, Star, Trash2, Zap,
} from 'lucide-vue-next'

const props = defineProps({
  vin: { type: String, required: true },
  status: { type: Object, default: () => ({}) },
})

const DEFAULTS = {
  capacity_kwh: 37.3,
  consumption_kwh_100km: 16,
  safety_margin_pct: 10,
  default_charger_power_kw: 6.6,
  max_soc: 80,
  min_soc: 20,
  topup_below_soc: 0,
  charge_timing: 'asap',
  avg_speed_kmh: 50,
}
// Fields saved in the draft (start SOC/time always restart from "now").
const SAVED_KEYS = [...Object.keys(DEFAULTS), 'start_place']

const ready = ref(false)
const showAdvanced = ref(false)
const showPlaces = ref(false)
const plan = ref(null)
const planError = ref('')
const saveState = ref('')
const estimates = reactive({ capacity: null, capacitySource: '', consumption: null, consumptionSource: '' })
const form = reactive({ ...DEFAULTS, start_place: null, start_soc: 50, start_time: nowLocal(), legs: [] })
// Saved places and frequent routes, shared by every vehicle.
const library = reactive({ places: [], routes: [] })
const zones = ref([])
// Per-leg routing status ({ loading, error, key }), kept out of the draft.
const routeState = reactive({})

// --- Date helpers (all naive local "YYYY-MM-DDTHH:MM" strings) ---
function pad(n) { return String(n).padStart(2, '0') }
function toLocalInput(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
function nowLocal() { return toLocalInput(new Date()) }
function parseLocal(s) { return new Date(s) }
function addMinutes(s, minutes) { return toLocalInput(new Date(parseLocal(s).getTime() + minutes * 60000)) }
function dayKeyOffset(offset) {
  const d = new Date()
  d.setDate(d.getDate() + offset)
  return toLocalInput(d).slice(0, 10)
}
function tomorrowAt(h) { return `${dayKeyOffset(1)}T${pad(h)}:00` }
function fmtTime(s) { return parseLocal(s).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) }
function fmtDayShort(s) { return parseLocal(s).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric' }) }
function sameDay(a, b) { return a.slice(0, 10) === b.slice(0, 10) }
function fmtDuration(a, b) {
  const min = Math.round((parseLocal(b) - parseLocal(a)) / 60000)
  const h = Math.floor(min / 60)
  return h ? `${h}h ${pad(min % 60)}m` : `${min}m`
}
function dayLabel(key) {
  const d = new Date(`${key}T00:00`)
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const diff = Math.round((d - today) / 86400000)
  const name = d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })
  if (diff === 0) return `Today · ${name}`
  if (diff === 1) return `Tomorrow · ${name}`
  return name
}
function dayName(key) {
  if (key === dayKeyOffset(0)) return 'today'
  if (key === dayKeyOffset(1)) return 'tomorrow'
  return new Date(`${key}T00:00`).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric' })
}

// --- SOC helpers ---
function clampPct(v) { return Math.max(0, Math.min(100, v)) }
function fmtSoc(v) { return `${Math.round(v)}%` }
function socColor(v) {
  if (v < form.min_soc) return 'var(--red)'
  if (v < form.min_soc + 15) return 'var(--amber)'
  return 'var(--green)'
}
function usedStyle(leg) {
  const from = clampPct(leg.soc_end)
  const to = clampPct(leg.soc_start)
  return { left: from + '%', width: Math.max(0, to - from) + '%' }
}

// --- Live data ---
const liveSoc = computed(() => {
  const soc = props.status?.battery?.soc
  return soc == null ? null : Math.round(Number(soc))
})

// --- Places ---
// A place reference is { placeId } for a saved place, or a full place object
// ({ name, address, latitude, longitude, charger, charger_power_kw }).
function uid() { return Math.random().toString(36).slice(2, 10) }
function placeById(id) { return library.places.find((p) => p.id === id) || null }
function resolve(ref) {
  if (!ref) return null
  return ref.placeId ? placeById(ref.placeId) : ref
}
function placeName(ref) { return resolve(ref)?.name || '' }
function hasCoords(p) { return !!p && p.latitude != null && p.longitude != null }
const startPlace = computed(() => resolve(form.start_place))

function setCharger(ref, value) {
  const place = resolve(ref)
  if (place) place.charger = value
}
function setPower(ref, event) {
  const place = resolve(ref)
  if (place) place.charger_power_kw = event.target.value === '' ? null : Number(event.target.value)
}
function canSavePlace(ref) { return !!ref && !ref.placeId && hasCoords(ref) }
function samePlace(a, b) {
  return a && b && !a.placeId && !b.placeId && a.name === b.name && a.latitude === b.latitude && a.longitude === b.longitude
}
// Save an ad-hoc place in the library and point every use of it there.
function savePlaceRef(ref) {
  if (!ref) return null
  if (ref.placeId) return ref.placeId
  if (!hasCoords(ref)) return null
  const id = uid()
  library.places.push({
    id, name: ref.name.slice(0, 80) || 'Place', address: (ref.address || '').slice(0, 300),
    latitude: ref.latitude, longitude: ref.longitude, charger: !!ref.charger, charger_power_kw: ref.charger_power_kw || null,
  })
  const target = { ...ref }
  if (samePlace(form.start_place, target)) form.start_place = { placeId: id }
  for (const leg of form.legs) if (samePlace(leg.to, target)) leg.to = { placeId: id }
  return id
}
function addPlaceFromPicker(ref) { if (ref && !ref.placeId) savePlaceRef(ref) }
function deletePlace(place) {
  // Keep the trips that use it, as plain places.
  const copy = () => { const { id, ...rest } = place; return { ...rest } }
  if (form.start_place?.placeId === place.id) form.start_place = copy()
  for (const leg of form.legs) if (leg.to?.placeId === place.id) leg.to = copy()
  library.places.splice(library.places.indexOf(place), 1)
  library.routes = library.routes.filter((r) => r.from_place_id !== place.id && r.to_place_id !== place.id)
}

// --- Legs ---
let nextId = 1
function newLeg(fields) {
  return {
    id: nextId++, departure: tomorrowAt(8), to: null, distance_km: null, duration_min: null,
    manual: false, routeKey: null, ...fields,
  }
}
const sortedLegs = computed(() => [...form.legs].sort((a, b) => a.departure.localeCompare(b.departure)))
function isPast(leg) { return leg.departure < form.start_time }
const pastLegs = computed(() => form.legs.filter(isPast))
const upcomingLegs = computed(() => sortedLegs.value.filter((l) => !isPast(l) && l.departure && l.distance_km > 0))

function originRef(leg) {
  const idx = sortedLegs.value.indexOf(leg)
  return idx > 0 ? sortedLegs.value[idx - 1].to : form.start_place
}
function legEnd(leg) {
  const km = leg.distance_km || 0
  const minutes = leg.duration_min > 0 ? leg.duration_min : Math.round(km / (form.avg_speed_kmh || 50) * 60)
  return addMinutes(leg.departure, minutes)
}
function copyRef(ref) { return ref ? { ...ref } : null }
function addLeg() {
  const last = sortedLegs.value[sortedLegs.value.length - 1]
  const departure = last ? addMinutes(legEnd(last), 60) : tomorrowAt(8)
  form.legs.push(newLeg({ departure }))
}
function setDestination(leg, ref) {
  leg.to = ref
  leg.manual = false
  leg.routeKey = null
}
function addReturn(leg) {
  form.legs.push(newLeg({ to: copyRef(originRef(leg)), departure: addMinutes(legEnd(leg), 60) }))
}
function duplicateNextDay(leg) {
  const { id, ...rest } = leg
  form.legs.push(newLeg({ ...rest, to: copyRef(leg.to), departure: addMinutes(leg.departure, 24 * 60) }))
}
function removeLeg(leg) { form.legs.splice(form.legs.indexOf(leg), 1) }
function removePast() { form.legs = form.legs.filter((l) => !isPast(l)) }

function setManual(leg, field, event) {
  const value = event.target.value === '' ? null : Number(event.target.value)
  leg[field] = value
  leg.manual = true
}
function resetAuto(leg) {
  leg.manual = false
  leg.routeKey = null
}

// --- Distances: from the previous point to the destination ---
function savedRouteBetween(fromRef, toRef) {
  if (!fromRef?.placeId || !toRef?.placeId) return null
  return library.routes.find((r) => r.from_place_id === fromRef.placeId && r.to_place_id === toRef.placeId) || null
}
function routeTarget(leg) {
  const fromRef = originRef(leg)
  const saved = savedRouteBetween(fromRef, leg.to)
  if (saved && saved.distance_km > 0) {
    return { key: `saved:${saved.id}:${saved.distance_km}:${saved.duration_min ?? ''}`, saved }
  }
  const from = resolve(fromRef)
  const to = resolve(leg.to)
  if (!hasCoords(from) || !hasCoords(to)) return null
  const coords = [from.latitude, from.longitude, to.latitude, to.longitude]
  return { key: coords.map((v) => v.toFixed(4)).join(','), coords }
}
function canAutoRoute(leg) { return !!routeTarget(leg) }

const routeCache = new Map()
async function updateRoute(leg, target) {
  const apply = (km, min) => {
    leg.distance_km = km
    leg.duration_min = min || null
    leg.routeKey = target.key
  }
  if (target.saved) { apply(target.saved.distance_km, target.saved.duration_min); return }
  if (routeCache.has(target.key)) { const r = routeCache.get(target.key); apply(r.distance_km, r.duration_min); return }
  if (routeState[leg.id]?.key === target.key) return // already in flight or failed
  routeState[leg.id] = { loading: true, key: target.key }
  const [fromLat, fromLon, toLat, toLon] = target.coords
  try {
    const r = await api('GET', `/api/trip-planner/route?from_lat=${fromLat}&from_lon=${fromLon}&to_lat=${toLat}&to_lon=${toLon}`)
    routeCache.set(target.key, r)
    delete routeState[leg.id]
    if (!leg.manual && routeTarget(leg)?.key === target.key) apply(r.distance_km, r.duration_min)
  } catch (err) {
    routeState[leg.id] = { error: 'No route: enter the km', key: target.key }
  }
}
const routeSignature = computed(() => sortedLegs.value.map((leg) => {
  if (leg.manual) return `${leg.id}:manual`
  return `${leg.id}:${routeTarget(leg)?.key ?? '-'}:${leg.routeKey ?? '-'}`
}).join('|'))
function syncRoutes() {
  if (!ready.value) return
  for (const leg of sortedLegs.value) {
    if (leg.manual) continue
    const target = routeTarget(leg)
    if (target && leg.routeKey !== target.key) updateRoute(leg, target)
  }
}
watch(routeSignature, syncRoutes)

// --- Frequent trips ---
const nextDays = computed(() => Array.from({ length: 7 }, (_, i) => {
  const key = dayKeyOffset(i)
  const label = i === 0 ? 'Today' : i === 1 ? 'Tomorrow' : new Date(`${key}T00:00`).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric' })
  return { key, label }
}))
const routeDay = ref(dayKeyOffset(1))
const sortedRoutes = computed(() => [...library.routes].sort((a, b) => (a.departure_time || '99').localeCompare(b.departure_time || '99')))
const routesWithTime = computed(() => sortedRoutes.value.filter((r) => r.departure_time))

function addRoute(route) {
  const day = routeDay.value
  let time = route.departure_time
  if (!time) {
    const sameDayLegs = sortedLegs.value.filter((l) => l.departure.startsWith(day))
    const last = sameDayLegs[sameDayLegs.length - 1]
    time = last ? legEnd(last).slice(11, 16) : '08:00'
  }
  const departure = `${day}T${time}`
  const duplicate = form.legs.some((l) => l.departure === departure && l.to?.placeId === route.to_place_id)
  if (duplicate) return
  form.legs.push(newLeg({
    departure, to: { placeId: route.to_place_id },
    distance_km: route.distance_km, duration_min: route.duration_min || null,
  }))
}
function addAllRoutes() { for (const r of routesWithTime.value) addRoute(r) }
function deleteRoute(route) { library.routes.splice(library.routes.indexOf(route), 1) }

function canSaveRoute(leg) {
  const from = originRef(leg)
  return !!from && !!leg.to && leg.distance_km > 0 && (from.placeId || hasCoords(from)) && (leg.to.placeId || hasCoords(leg.to))
}
function isRouteSaved(leg) { return !!savedRouteBetween(originRef(leg), leg.to) }
function saveRouteTitle(leg) {
  if (isRouteSaved(leg)) return 'Saved as a frequent trip (tap to update it)'
  if (!canSaveRoute(leg)) return 'Pick both places from the search to save this trip'
  return 'Save as a frequent trip'
}
function saveRoute(leg) {
  if (!canSaveRoute(leg)) return
  const fromId = savePlaceRef(originRef(leg))
  const toId = savePlaceRef(leg.to)
  if (!fromId || !toId) return
  const fields = {
    distance_km: Math.round(leg.distance_km * 10) / 10,
    duration_min: leg.duration_min > 0 ? Math.round(leg.duration_min) : null,
    departure_time: leg.departure.slice(11, 16),
  }
  const existing = library.routes.find((r) => r.from_place_id === fromId && r.to_place_id === toId)
  if (existing) Object.assign(existing, fields)
  else library.routes.push({ id: uid(), from_place_id: fromId, to_place_id: toId, ...fields })
  leg.manual = false
}

// --- Plan computation ---
function num(v, fallback) { return Number.isFinite(v) && v !== '' ? Number(v) : fallback }
function buildRequest() {
  const topup = num(form.topup_below_soc, 0)
  const start = startPlace.value
  return {
    settings: {
      start_time: form.start_time,
      start_soc: clampPct(num(form.start_soc, 50)),
      capacity_kwh: num(form.capacity_kwh, DEFAULTS.capacity_kwh),
      consumption_kwh_100km: num(form.consumption_kwh_100km, DEFAULTS.consumption_kwh_100km),
      start_label: start?.name || 'Start',
      charger_at_start: !!start?.charger,
      start_charger_power_kw: start?.charger && start.charger_power_kw > 0 ? Number(start.charger_power_kw) : null,
      default_charger_power_kw: num(form.default_charger_power_kw, DEFAULTS.default_charger_power_kw),
      max_soc: num(form.max_soc, 80),
      min_soc: num(form.min_soc, 20),
      safety_margin_pct: num(form.safety_margin_pct, 0),
      avg_speed_kmh: num(form.avg_speed_kmh, 50),
      charge_timing: form.charge_timing,
      topup_below_soc: topup > 0 ? topup : null,
    },
    legs: upcomingLegs.value.map((l, i) => {
      const to = resolve(l.to)
      return {
        label: (to?.name || `Trip ${i + 1}`).slice(0, 80),
        departure: l.departure,
        distance_km: Number(l.distance_km),
        duration_min: l.duration_min > 0 ? Number(l.duration_min) : null,
        charger_at_destination: !!to?.charger,
        charger_power_kw: to?.charger && to.charger_power_kw > 0 ? Number(to.charger_power_kw) : null,
      }
    }),
  }
}

let planTimer = null
let planSeq = 0
async function computePlan() {
  const seq = ++planSeq
  const body = buildRequest()
  if (!body.legs.length) { plan.value = null; planError.value = ''; return }
  if (!(body.settings.min_soc < body.settings.max_soc)) {
    plan.value = null
    planError.value = 'The minimum battery level must be lower than the maximum.'
    return
  }
  try {
    const result = await api('POST', `/api/vehicles/${props.vin}/trip-plan`, body)
    if (seq !== planSeq) return
    plan.value = result
    planError.value = ''
  } catch (err) {
    if (seq !== planSeq) return
    planError.value = err.message
  }
}

const lastLeg = computed(() => plan.value?.legs[plan.value.legs.length - 1])
const totalKm = computed(() => (plan.value?.legs || []).reduce((s, l) => s + l.distance_km, 0))
const totalChargeKwh = computed(() => (plan.value?.charges || []).reduce((s, c) => s + c.energy_kwh, 0))

const timelineDays = computed(() => {
  if (!plan.value) return []
  const legs = plan.value.legs
  const items = [
    ...plan.value.charges.map((c, i) => ({ type: 'charge', key: `c${i}`, time: c.start, order: 0, data: c })),
    ...legs.map((l, i) => ({
      type: 'leg', key: `l${i}`, time: l.departure, order: 1, data: l,
      from: i ? legs[i - 1].label : (startPlace.value?.name || 'Start'),
    })),
  ].sort((a, b) => a.time.localeCompare(b.time) || a.order - b.order)
  const days = []
  for (const item of items) {
    const key = item.time.slice(0, 10)
    let day = days[days.length - 1]
    if (!day || day.key !== key) { day = { key, label: dayLabel(key), items: [] }; days.push(day) }
    day.items.push(item)
  }
  return days
})

// --- Persistence: the draft per vehicle, the library for everyone ---
let saveTimer = null
let loadedVin = null
async function saveDraft() {
  const draft = { version: 2, legs: form.legs.map(({ id, ...rest }) => rest) }
  for (const k of SAVED_KEYS) draft[k] = form[k]
  try {
    await api('PUT', `/api/vehicles/${props.vin}/trip-plan/draft`, { draft })
    saveState.value = 'Saved'
  } catch {
    saveState.value = 'Not saved'
  }
}

let libraryLoaded = false
let libraryTimer = null
async function loadLibrary() {
  try {
    const lib = await api('GET', '/api/trip-planner/library')
    library.places = lib.places || []
    library.routes = lib.routes || []
  } catch { /* keep empty */ }
  await nextTick() // do not save back what was just loaded
  libraryLoaded = true
}
async function saveLibrary() {
  const body = {
    places: library.places.map((p) => ({ ...p, name: (p.name || '').trim() || 'Place', charger_power_kw: p.charger_power_kw > 0 ? p.charger_power_kw : null })),
    routes: library.routes.filter((r) => r.distance_km > 0).map((r) => ({ ...r, departure_time: r.departure_time || null })),
  }
  try {
    await api('PUT', '/api/trip-planner/library', body)
    saveState.value = 'Saved'
  } catch {
    saveState.value = 'Not saved'
  }
}
watch(library, () => {
  if (!libraryLoaded) return
  clearTimeout(libraryTimer)
  saveState.value = ''
  libraryTimer = setTimeout(saveLibrary, 800)
}, { deep: true })

async function loadZones(vin) {
  try { zones.value = await api('GET', `/api/zones?vin=${vin}`) } catch { zones.value = [] }
}

async function loadEstimates() {
  const b = props.status?.battery || {}
  // Capacity: battery-health estimate, else energy available / SOC.
  try {
    const health = await api('GET', `/api/vehicles/${props.vin}/battery/health`)
    if (health?.capacity_kwh) {
      estimates.capacity = Math.round(health.capacity_kwh * 10) / 10
      estimates.capacitySource = 'Battery health'
    }
  } catch { /* history disabled */ }
  if (!estimates.capacity && b.dump_energy_kwh && b.soc > 10) {
    estimates.capacity = Math.round((b.dump_energy_kwh / b.soc) * 1000) / 10
    estimates.capacitySource = 'From the car'
  }
  // Consumption: last 30 days of local trips, else the car's range estimate.
  try {
    const to = new Date()
    const from = new Date(Date.now() - 30 * 86400000)
    const iso = (d) => d.toISOString().slice(0, 10)
    const totals = await api('GET', `/api/vehicles/${props.vin}/trips/totals?begin_time=${iso(from)}&end_time=${iso(to)}`)
    if (totals?.total_mileage > 30 && totals.total_energy > 0) {
      estimates.consumption = Math.round((totals.total_energy / totals.total_mileage) * 1000) / 10
      estimates.consumptionSource = 'Last 30 days'
    }
  } catch { /* offline or no history */ }
  if (!estimates.consumption && b.dump_energy_kwh && b.expected_mileage > 0) {
    estimates.consumption = Math.round((b.dump_energy_kwh / b.expected_mileage) * 1000) / 10
    estimates.consumptionSource = 'Car estimate'
  }
}

function refreshStart() {
  form.start_time = nowLocal()
  if (liveSoc.value != null) form.start_soc = liveSoc.value
}

// Drafts saved before places existed: plain labels become places without
// coordinates (the km stay as typed), the old "charge up to" becomes the max.
function migrateDraft(draft) {
  if (draft.version >= 2) return draft
  const plain = (name, charger, power) => (name ? { name, address: '', latitude: null, longitude: null, charger: !!charger, charger_power_kw: power || null } : null)
  return {
    ...draft,
    version: 2,
    max_soc: draft.max_soc ?? draft.target_soc,
    topup_below_soc: 0,
    start_place: plain(draft.start_label, draft.charger_at_start),
    legs: (draft.legs || []).map(({ label, charger, charger_power_kw, ...rest }) => ({
      ...rest, to: plain(label, charger, charger_power_kw), manual: true,
    })),
  }
}

async function load(vin) {
  ready.value = false
  loadedVin = null
  plan.value = null
  Object.assign(estimates, { capacity: null, capacitySource: '', consumption: null, consumptionSource: '' })
  Object.assign(form, { ...DEFAULTS, start_place: null, start_soc: liveSoc.value ?? 50, start_time: nowLocal(), legs: [] })

  const [draftRes] = await Promise.allSettled([
    api('GET', `/api/vehicles/${vin}/trip-plan/draft`),
    loadEstimates(),
    libraryLoaded ? null : loadLibrary(),
    loadZones(vin),
  ])
  let draft = draftRes.status === 'fulfilled' ? draftRes.value?.draft : null
  if (draft) {
    draft = migrateDraft(draft)
    for (const k of SAVED_KEYS) if (draft[k] !== undefined && draft[k] !== null) form[k] = draft[k]
    form.legs = (draft.legs || []).map((l) => newLeg(l))
  } else {
    if (estimates.capacity) form.capacity_kwh = estimates.capacity
    if (estimates.consumption) form.consumption_kwh_100km = estimates.consumption
  }
  loadedVin = vin
  ready.value = true
  syncRoutes()
  computePlan()
}

watch(form, () => {
  if (!loadedVin) return
  clearTimeout(saveTimer)
  saveState.value = ''
  saveTimer = setTimeout(saveDraft, 1000)
}, { deep: true })
// The plan also depends on the library (chargers, names), not only the form.
watch([form, library], () => {
  if (!loadedVin) return
  clearTimeout(planTimer)
  planTimer = setTimeout(computePlan, 300)
}, { deep: true })

// Follow the live SOC while the user has not typed a different value.
watch(liveSoc, (soc, prev) => {
  if (soc != null && (form.start_soc === prev || form.start_soc == null)) form.start_soc = soc
})

watch(() => props.vin, (vin) => { if (vin) load(vin) })
onMounted(() => { if (props.vin) load(props.vin) })
onBeforeUnmount(() => {
  clearTimeout(planTimer)
  if (saveTimer) { clearTimeout(saveTimer); if (loadedVin) saveDraft() }
  if (libraryTimer) { clearTimeout(libraryTimer); saveLibrary() }
})
</script>

<style scoped>
.planner-tab { width: 100%; max-width: 980px; }
.planner-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; gap: 12px; }
.header-title h2 { font-size: 20px; font-weight: 700; color: var(--text); margin: 0; }
.header-title p { font-size: 12px; color: var(--muted); margin: 2px 0 0; }
.header-actions { display: flex; align-items: center; gap: 10px; }
.save-state { font-size: 11px; color: var(--muted); }
.toolbar-btn { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 6px; color: var(--text); cursor: pointer; display: flex; align-items: center; transition: all 0.15s; }
.toolbar-btn:hover { background: var(--btn-bg); color: var(--cyan); border-color: var(--cyan); }
.loading-center { display: flex; justify-content: center; padding: 48px; }

.card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; margin-bottom: 14px; box-shadow: var(--shadow-card); }
.card-title { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--heading); margin-bottom: 12px; }
.card-title-sub { font-size: 11px; font-weight: 400; color: var(--muted); }
.right { margin-left: auto; }

.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
@media (min-width: 768px) { .form-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
.form-grid.advanced { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--divider); }
.field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.field-label { font-size: 11px; color: var(--label); text-transform: uppercase; letter-spacing: 0.03em; }
.field-hint { font-size: 11px; color: var(--muted); }
.field-toggle { justify-content: flex-start; }
.field input, .field select {
  width: 100%; min-width: 0; background: var(--input); border: 1px solid var(--border); border-radius: 8px;
  padding: 7px 9px; color: var(--text); font-size: 13px; font-family: inherit; outline: none;
}
.field input:focus, .field select:focus { border-color: var(--accent); }
.input-unit { display: flex; align-items: center; background: var(--input); border: 1px solid var(--border); border-radius: 8px; }
.input-unit:focus-within { border-color: var(--accent); }
.input-unit input { border: none; background: transparent; }
.input-unit span { font-size: 11px; color: var(--muted); padding-right: 9px; white-space: nowrap; }
.link-btn { background: none; border: none; padding: 0 2px; color: var(--accent); font-size: 11px; cursor: pointer; text-decoration: underline; }

.advanced-toggle { display: inline-flex; align-items: center; gap: 6px; margin-top: 12px; background: none; border: none; color: var(--sub); font-size: 12px; cursor: pointer; padding: 0; }
.advanced-toggle:hover { color: var(--accent); }
.advanced-toggle .rotated { transform: rotate(180deg); }

.empty-legs { font-size: 13px; color: var(--muted); padding: 8px 0 12px; }
.leg-row { display: flex; gap: 10px; align-items: flex-start; padding: 12px 0; border-top: 1px solid var(--divider); }
.leg-row:first-of-type { border-top: none; }
.leg-row.past { opacity: 0.45; }
.leg-index { flex: 0 0 24px; height: 24px; border-radius: 50%; background: rgba(var(--accent-rgb), 0.12); color: var(--accent); font-size: 12px; font-weight: 700; display: flex; align-items: center; justify-content: center; margin-top: 18px; }
.leg-fields { flex: 1; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; min-width: 0; }
.leg-fields .grow { grid-column: 1 / -1; }
@media (min-width: 900px) {
  .leg-fields { grid-template-columns: 2.2fr 1.5fr 0.85fr 0.8fr 0.8fr 0.8fr; }
  .leg-fields .grow { grid-column: auto; }
}
.leg-actions { display: flex; flex-direction: column; gap: 4px; margin-top: 16px; }
.icon-btn { background: var(--bg2); border: 1px solid var(--border); border-radius: 7px; padding: 5px; color: var(--sub); cursor: pointer; display: flex; }
.icon-btn:hover { color: var(--accent); border-color: var(--accent); }
.icon-btn.danger:hover { color: var(--red); border-color: var(--red); }
.add-btn { display: inline-flex; align-items: center; gap: 6px; margin-top: 8px; background: rgba(var(--accent-rgb), 0.1); border: 1px solid rgba(var(--accent-rgb), 0.3); color: var(--accent); border-radius: 8px; padding: 7px 14px; font-size: 13px; font-weight: 600; cursor: pointer; }
.add-btn:hover { background: rgba(var(--accent-rgb), 0.18); }

.summary-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 14px; }
@media (min-width: 768px) { .summary-grid { grid-template-columns: repeat(4, 1fr); } }
.summary-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; text-align: center; }
.summary-value { font-size: 20px; font-weight: 700; }
.summary-label { font-size: 10px; color: var(--muted); margin-top: 4px; }

.alert { display: flex; gap: 8px; align-items: flex-start; border-radius: 10px; padding: 10px 12px; font-size: 12.5px; margin-bottom: 14px; border: 1px solid; }
.alert ul { margin: 0; padding-left: 16px; }
.alert svg { flex-shrink: 0; margin-top: 1px; }
.alert.ok { color: var(--green); border-color: color-mix(in srgb, var(--green) 35%, transparent); background: color-mix(in srgb, var(--green) 8%, transparent); }
.alert.warn { color: var(--amber); border-color: color-mix(in srgb, var(--amber) 35%, transparent); background: color-mix(in srgb, var(--amber) 8%, transparent); }
.alert.error { color: var(--red); border-color: color-mix(in srgb, var(--red) 35%, transparent); background: color-mix(in srgb, var(--red) 8%, transparent); }

.timeline { display: flex; flex-direction: column; gap: 12px; }
.day-group { background: var(--card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.day-header { padding: 9px 14px; font-weight: 600; font-size: 13px; color: var(--text); border-bottom: 1px solid var(--border); background: var(--bg2); }
.tl-item { display: flex; gap: 12px; padding: 12px 14px; border-bottom: 1px solid var(--divider); }
.tl-item:last-child { border-bottom: none; }
.tl-item.charge { background: color-mix(in srgb, var(--green) 6%, transparent); }
.tl-item.danger { background: color-mix(in srgb, var(--red) 7%, transparent); }
.tl-icon { flex: 0 0 32px; height: 32px; border-radius: 10px; display: flex; align-items: center; justify-content: center; }
.charge-icon { background: color-mix(in srgb, var(--green) 16%, transparent); color: var(--green); }
.leg-icon { background: rgba(var(--accent-rgb), 0.14); color: var(--accent); }
.tl-body { flex: 1; min-width: 0; }
.tl-title { font-size: 14px; font-weight: 600; color: var(--text); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.tl-distance { font-size: 12px; font-weight: 500; color: var(--accent); }
.tl-time { font-size: 12px; color: var(--sub); margin-top: 2px; }
.tl-stats { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; color: var(--muted3); margin-top: 6px; }
.tl-stats b { color: var(--text); }
.tag { font-size: 10px; font-weight: 600; text-transform: uppercase; padding: 2px 6px; border-radius: 6px; background: color-mix(in srgb, var(--green) 18%, transparent); color: var(--green); }
.tag.warn { background: color-mix(in srgb, var(--amber) 18%, transparent); color: var(--amber); }

.soc-bar { position: relative; height: 8px; border-radius: 4px; background: var(--btn-bg); margin-top: 8px; overflow: hidden; }
.soc-bar-fill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 4px; }
.soc-bar-used { position: absolute; top: 0; bottom: 0; background: repeating-linear-gradient(45deg, var(--muted2), var(--muted2) 3px, transparent 3px, transparent 6px); opacity: 0.6; }
.soc-mark { position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--red); opacity: 0.7; }
.soc-mark.target { background: var(--green); }
.span-2 { grid-column: span 2; }
.picker-row { display: flex; gap: 6px; align-items: center; min-width: 0; }
.grow-1 { flex: 1; min-width: 0; }
.field-hint.error { color: var(--red); }
.inline-icon { display: inline; vertical-align: -2px; }
.spin { animation: spin 1s linear infinite; vertical-align: -1px; }
@keyframes spin { to { transform: rotate(360deg); } }

.leg-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.leg-from { font-size: 11.5px; color: var(--muted); }
.leg-from b { color: var(--sub); font-weight: 600; }
.icon-btn:disabled { opacity: 0.35; cursor: default; }
.icon-btn.saved { color: var(--amber); border-color: color-mix(in srgb, var(--amber) 50%, transparent); }
.icon-btn.accent { color: var(--accent); border-color: rgba(var(--accent-rgb), 0.4); }

.day-chips { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 4px; scrollbar-width: none; }
.chip { flex-shrink: 0; background: var(--bg2); border: 1px solid var(--border); color: var(--sub); border-radius: 999px; padding: 4px 11px; font-size: 12px; cursor: pointer; font-family: inherit; }
.chip.active { background: rgba(var(--accent-rgb), 0.14); border-color: rgba(var(--accent-rgb), 0.45); color: var(--accent); font-weight: 600; }
.route-row { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-top: 1px solid var(--divider); }
.route-name { flex: 1; min-width: 0; display: flex; align-items: center; gap: 5px; font-size: 13px; font-weight: 600; color: var(--text); flex-wrap: wrap; }
.plug-icon { color: var(--green); }
.time-input { width: 84px; background: var(--input); border: 1px solid var(--border); border-radius: 8px; padding: 5px 6px; color: var(--text); font-size: 12.5px; font-family: inherit; }
.route-km { width: 82px; flex-shrink: 0; }
.route-km input, .place-power input { width: 100%; min-width: 0; padding: 5px 6px; color: var(--text); font-size: 12.5px; font-family: inherit; outline: none; }

.places-box { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--divider); }
.places-title { font-size: 11px; color: var(--label); text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 4px; }
.place-row { display: flex; align-items: center; gap: 8px; padding: 7px 0; }
.star-icon { color: var(--amber); flex-shrink: 0; }
.place-info { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.place-name { background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 2px 4px; margin-left: -4px; color: var(--text); font-size: 13px; font-weight: 600; font-family: inherit; outline: none; }
.place-name:focus { border-color: var(--accent); background: var(--input); }
.place-info small { font-size: 11px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.place-charger { display: flex; align-items: center; gap: 5px; color: var(--green); }
.place-power { width: 78px; flex-shrink: 0; }
.add-place { margin-top: 6px; }
@media (max-width: 520px) {
  .route-row { flex-wrap: wrap; }
  .route-name { flex-basis: 100%; }
  .place-row { flex-wrap: wrap; }
  .place-info { flex-basis: calc(100% - 30px); }
}
</style>
