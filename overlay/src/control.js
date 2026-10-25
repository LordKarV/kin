import { speakerChoices } from './lib.mjs'
const $ = (id) => document.getElementById(id)
const NEW_FAMILY = '__new'
const DEFAULT_LANG = 'ta'
const DEFAULT_RELATION = 'mother.mother'
const RETRY_MS = 3000
let running = false
let family = '' // selected family id, as a string like every <select> value
let langLabel = ''
let langNames = {} // code -> English name, from kin.languages()

// ipcRenderer.invoke wraps backend errors as "Error invoking remote method 'kin:x': Error: ..."
const errText = (e) => String(e?.message ?? e).replace(/^Error invoking remote method '[^']+': (Error: )?/, '')
const setStatus = (text, level = 'info') => { $('status').textContent = text; $('status').className = `status ${level === 'info' ? '' : level}` }
const setMsg = (text) => { $('s-msg').textContent = text }
function displayLang(code) {
  try { return new Intl.DisplayNames(['en'], { type: 'language' }).of(code) || code } catch { return code } // bad tag -> RangeError
}
function setLang(text) { $('lang').textContent = text }

// the window is click-through; take the mouse only while the pointer is over the panel
$('panel').addEventListener('mouseenter', () => window.kin.mouse(true))
$('panel').addEventListener('mouseleave', () => window.kin.mouse(false))

function showView(name) {
  $('setup').hidden = name !== 'setup'
  $('live').hidden = name !== 'live'
  $('hotkey').hidden = name !== 'live'
}

// ---- live view ---------------------------------------------------------------
function fillFamilies(fams, selected) {
  const sel = $('family')
  sel.innerHTML = ''
  for (const f of fams) sel.add(new Option(`${f.name} (${f.language})`, f.id))
  sel.add(new Option('+ New family…', NEW_FAMILY))
  sel.value = selected
  if (!sel.value || sel.value === NEW_FAMILY) sel.selectedIndex = 0
}

async function loadGraph() {
  const g = await window.kin.graph(family)
  const keep = $('speaker').value
  $('speaker').innerHTML = ''
  for (const p of speakerChoices(g)) $('speaker').add(new Option(p.label, p.id))
  if (keep && [...$('speaker').options].some((o) => o.value === keep)) $('speaker').value = keep
  langLabel = `${displayLang(g.heritage_lang)} to English`
  setLang(langLabel)
}

async function chooseFamily(id) {
  family = String(id)
  $('family').value = family
  $('call').value = '' // a call belongs to one family
  window.kin.selectFamily(family)
  await loadGraph()
  if (!running) setStatus('Ready')
}

async function init() {
  try {
    const fams = await window.kin.families()
    if (!fams.length) return showSetup(false)
    fillFamilies(fams, family || String(fams[0].id))
    showView('live')
    await chooseFamily($('family').value)
  } catch (e) {
    setStatus(`Cannot reach KIN: ${errText(e)}. Is the backend running?`, 'error')
    setTimeout(init, RETRY_MS)
  }
}

$('family').onchange = () => {
  const v = $('family').value
  if (v === NEW_FAMILY) { $('family').value = family; return showSetup(true) }
  chooseFamily(v).catch((e) => setStatus(`Cannot load that family: ${errText(e)}`, 'error'))
}

function setRunning(on) {
  running = on
  $('go').textContent = on ? 'Stop' : 'Start listening'
  $('dot').classList.toggle('on', on)
}

$('go').onclick = async () => {
  if (running) { await window.kin.stop(); return setRunning(false) }
  if (!$('speaker').value) return setStatus('Pick who is on the other end first', 'warn')
  try {
    const { callId } = await window.kin.start({ speaker: $('speaker').value, source: $('source').value, callId: $('call').value, familyId: family })
    $('call').value = callId
    setRunning(true)
  } catch (e) { setStatus(`Start failed: ${errText(e)}`, 'error') }
}
$('typed').onkeydown = (e) => {
  if (e.key !== 'Enter' || !$('typed').value.trim()) return
  window.kin.text($('typed').value)
  $('typed').value = ''
}
$('quit').onclick = () => window.kin.quit()

// ---- setup view --------------------------------------------------------------
let setupLoaded = false
async function loadSetupOptions() {
  if (setupLoaded) return
  const [langs, rels] = await Promise.all([window.kin.languages(), window.kin.relations()])
  const avail = langs.filter((l) => l.available)
  langNames = Object.fromEntries(avail.map((l) => [l.code, l.name]))
  $('s-lang').innerHTML = ''
  for (const l of avail) $('s-lang').add(new Option(l.native_name && l.native_name !== l.name ? `${l.name} (${l.native_name})` : l.name, l.code))
  if (langNames[DEFAULT_LANG]) $('s-lang').value = DEFAULT_LANG
  $('s-rel').innerHTML = ''
  for (const r of rels) $('s-rel').add(new Option(r.label, r.path))
  if (rels.some((r) => r.path === DEFAULT_RELATION)) $('s-rel').value = DEFAULT_RELATION
  setupLoaded = true
}
const setupLang = () => { const n = langNames[$('s-lang').value]; setLang(n ? `${n} to English` : '') }
$('s-lang').onchange = setupLang

async function showSetup(cancelable) {
  showView('setup')
  $('s-cancel').hidden = !cancelable
  setMsg('')
  setStatus('')
  for (let attempt = 1; ; attempt++) {
    try { await loadSetupOptions(); setupLang(); setMsg(''); break } catch (e) {
      setMsg(`Cannot load languages: ${errText(e)}. Retrying…`)
      if (attempt >= 10) break
      await new Promise((r) => setTimeout(r, 1500))
    }
  }
  $('s-you').focus()
}

$('s-cancel').onclick = () => { showView('live'); setLang(langLabel); setStatus(running ? '' : 'Ready') }

const REQUIRED = [
  ['s-lang', 'the language they speak'],
  ['s-you', 'your name'],
  ['s-them', 'who you are calling'],
  ['s-call', 'what you call them'],
  ['s-rel', 'how they are related to you'],
]

$('setup').onsubmit = async (e) => {
  e.preventDefault()
  try { await loadSetupOptions() } catch (err) { return setMsg(`Cannot load languages: ${errText(err)}`) }
  const missing = REQUIRED.find(([id]) => !$(id).value.trim())
  if (missing) { setMsg(`Please add ${missing[1]}.`); return $(missing[0]).focus() }
  const body = {
    language: $('s-lang').value,
    your_name: $('s-you').value.trim(),
    their_name: $('s-them').value.trim(),
    you_call_them: $('s-call').value.trim(),
    relation: $('s-rel').value,
  }
  setMsg('')
  $('s-create').disabled = true
  $('s-create').textContent = 'Creating…'
  try {
    const r = await window.kin.setup(body)
    fillFamilies(await window.kin.families(), String(r.family_id))
    showView('live')
    await chooseFamily(r.family_id)
    setStatus(`Family created. Pick ${body.their_name} and start listening.`, 'ok')
    for (const id of ['s-you', 's-them', 's-call']) $(id).value = ''
  } catch (err) {
    setMsg(`Could not create the family: ${errText(err)}`)
  } finally {
    $('s-create').disabled = false
    $('s-create').textContent = 'Create family'
  }
}

window.kin.on((m) => {
  if (m.type === 'overlay-status') { setStatus(m.text, m.level); if (m.text === 'Stopped') setRunning(false) }
  if (m.type === 'family-changed' && String(m.familyId) === family) {
    loadGraph().catch((e) => setStatus(`Cannot reload the family: ${errText(e)}`, 'error'))
  }
})
init()
