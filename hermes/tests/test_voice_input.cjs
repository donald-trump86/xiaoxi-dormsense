// Exercise the actual patched recording callbacks and polling with synthetic audio only.
const assert = require('node:assert/strict')
const ts = require('typescript')
const result = ts.transpileModule(globalThis.__sidebarSource, {
  fileName: 'ChatSidebar.tsx',
  compilerOptions: { target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.Preserve },
  reportDiagnostics: true,
})
const errors = (result.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error)
assert.equal(errors.length, 0, errors.map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')).join('\n'))
const js = result.outputText
const start = js.indexOf('const stopVoiceInput = useCallback(')
assert(start >= 0, 'Physical release needs an explicit stop operation that cannot start recording')
const recording = js.slice(start, js.indexOf('const refreshEffectiveModel = useCallback(', start))
const polling = js.slice(js.indexOf('// Poll UNO physical button events'), js.indexOf('// Seed the badge on mount'))
assert(polling.startsWith('// Poll UNO physical button events'))
const inputs = [
  'useCallback', 'useEffect', 'useRef', 'voiceInputRef', 'recognitionRef', 'lastBtnEventRef',
  'setMicListening', 'setVoiceStatus', 'setAutoTts', 'stopSpeaking', 'onSendVoiceText',
  'profile', 'channel', 'navigator', 'MediaRecorder', 'FileReader', 'fetchJSON', 'window', 'localStorage',
]
const initialize = new Function(...inputs, `${recording}\n${polling}\nreturn { startVoiceInput, stopVoiceInput, toggleVoiceInput }`)
const tick = () => new Promise(resolve => setImmediate(resolve))
const deferred = () => {
  let resolve, reject
  const promise = new Promise((a, b) => { resolve = a; reject = b })
  return { promise, resolve, reject }
}
function fixture(options = {}) {
  const state = {}, recorders = [], sent = [], requests = [], cleanups = []
  const timers = new Map(), streams = []
  const voiceInputRef = { current: null }, recognitionRef = { current: null }, lastBtnEventRef = { current: null }
  let timerId = 0, latest = { ok: true, boot_id: 'node90-test', sequence: 1, state: 'button_single_press' }
  let stopSpeakingCalls = 0, mediaCalls = 0
  function stream() {
    const track = { stopped: false, stop() { this.stopped = true } }
    const value = { getTracks: () => [track], track }
    streams.push(value)
    return value
  }
  class Recorder {
    static isTypeSupported() { return true }
    constructor(source, opts) {
      this.stream = source; this.mimeType = opts?.mimeType || 'audio/webm'; this.state = 'inactive'; this.stops = 0
      recorders.push(this)
    }
    start() { this.state = 'recording' }
    stop() {
      assert.equal(this.state, 'recording', 'recorder must only stop once')
      this.state = 'inactive'; this.stops++
      queueMicrotask(() => {
        this.ondataavailable?.({ data: new Blob(['x'.repeat(1024)]) })
        this.onstop?.()
      })
    }
  }
  class Reader {
    readAsDataURL() {
      this.result = 'data:audio/webm;base64,c3ludGhldGlj'
      queueMicrotask(() => this.onloadend?.())
    }
  }
  const browser = {
    setTimeout(fn) { const id = ++timerId; timers.set(id, fn); return id },
    clearTimeout(id) { timers.delete(id) },
    ...(options.speechRecognition ? { SpeechRecognition: options.speechRecognition } : {}),
  }
  const navigatorStub = options.speechRecognition ? {} : { mediaDevices: {
    getUserMedia() { mediaCalls++; return options.media ? options.media.promise : Promise.resolve(stream()) },
  } }
  const runtime = initialize(
    fn => fn, fn => { const cleanup = fn(); if (cleanup) cleanups.push(cleanup) }, value => ({ current: value }),
    voiceInputRef, recognitionRef, lastBtnEventRef,
    value => { state.listening = value }, value => { state.status = value }, value => { state.autoTts = value },
    () => { stopSpeakingCalls++ }, text => sent.push(text), 'test-profile', 'chat-test', navigatorStub,
    options.speechRecognition ? undefined : Recorder, Reader,
    (url, init) => {
      requests.push({ url, init })
      if (url.startsWith('/api/audio/button-event')) return options.poll ? options.poll.promise : Promise.resolve({ ...latest })
      assert(url.startsWith('/api/audio/transcribe?profile=test-profile'))
      return options.transcription ? options.transcription.promise : Promise.resolve({ ok: true, transcript: '  室内温度是多少？  ' })
    }, browser, { setItem() {} },
  )
  return {
    runtime, state, recorders, streams, sent, requests, cleanups, timers, stream, voiceInputRef,
    get mediaCalls() { return mediaCalls }, get stopSpeakingCalls() { return stopSpeakingCalls },
    event(sequence, event, boot = 'node90-test') { latest = { ok: true, boot_id: boot, sequence, state: event } },
    async poll() {
      await tick()
      assert.equal(timers.size, 1, 'exactly one follow-up poll should be scheduled')
      const [id, fn] = timers.entries().next().value
      timers.delete(id)
      await fn()
      await tick()
    },
    cleanup() { cleanups.forEach(fn => fn()) },
  }
}
const cases = []
const test = (name, fn) => cases.push({ name, fn })
test('physical hold then release stops tracks, transcribes and sends exactly once', async () => {
  const f = fixture()
  await tick()
  f.event(2, 'button_long_press_voice'); await f.poll()
  assert.equal(f.recorders.length, 1)
  assert.equal(f.state.listening, true)
  f.event(3, 'button_long_release_voice'); await f.poll()
  assert.equal(f.recorders[0].stops, 1)
  assert.equal(f.streams[0].track.stopped, true)
  assert.equal(f.state.listening, false)
  assert.deepEqual(f.sent, ['室内温度是多少？'])
  const request = f.requests.find(r => r.url.startsWith('/api/audio/transcribe'))
  assert.equal(request.init.headers['Content-Type'], 'application/json')
  assert.equal(JSON.parse(request.init.body).data_url, 'data:audio/webm;base64,c3ludGhldGlj')
  await f.poll()
  assert.equal(f.recorders[0].stops, 1)
  assert.equal(f.sent.length, 1)
})
test('release during microphone initialization closes the late stream without recording', async () => {
  const media = deferred(), f = fixture({ media })
  await tick()
  f.event(2, 'button_long_press_voice'); await f.poll()
  f.event(3, 'button_long_release_voice'); await f.poll()
  const stream = f.stream(); media.resolve(stream); await tick()
  assert.equal(stream.track.stopped, true)
  assert.equal(f.recorders.length, 0)
  assert.equal(f.state.listening, false)
  assert.equal(f.sent.length, 0)
  assert.equal(f.voiceInputRef.current, null)
})
test('a release without a matching physical start never opens or stops the microphone', async () => {
  const f = fixture(); await tick()
  f.event(2, 'button_long_release_voice'); await f.poll()
  assert.equal(f.mediaCalls, 0)
  f.runtime.toggleVoiceInput(); await tick()
  f.event(3, 'button_long_release_voice'); await f.poll()
  assert.equal(f.recorders[0].stops, 0)
  f.runtime.toggleVoiceInput(); await tick()
  assert.deepEqual(f.sent, ['室内温度是多少？'])
})
test('repeated starts and releases cannot duplicate capture or pending transcription', async () => {
  const transcription = deferred(), f = fixture({ transcription }); await tick()
  f.event(2, 'button_long_press_voice'); await f.poll()
  f.event(3, 'button_long_press_voice'); await f.poll()
  assert.equal(f.mediaCalls, 1)
  f.event(4, 'button_long_release_voice'); await f.poll()
  f.event(5, 'button_long_release_voice'); await f.poll()
  assert.equal(f.requests.filter(r => r.url.startsWith('/api/audio/transcribe')).length, 1)
  transcription.resolve({ ok: true, transcript: '一次' }); await tick()
  assert.deepEqual(f.sent, ['一次'])
})
test('manual toggling also stops a pending microphone request', async () => {
  const media = deferred(), f = fixture({ media }); await tick()
  f.runtime.toggleVoiceInput(); f.runtime.toggleVoiceInput()
  const stream = f.stream(); media.resolve(stream); await tick()
  assert.equal(f.mediaCalls, 1)
  assert.equal(stream.track.stopped, true)
  assert.equal(f.recorders.length, 0)
})
test('permission failure is visible and the next hold can retry', async () => {
  const media = deferred(), f = fixture({ media }); await tick()
  f.runtime.startVoiceInput('button'); media.reject(new Error('stub permission denied')); await tick()
  assert.equal(f.state.listening, false)
  assert.match(f.state.status, /stub permission denied/)
  assert.equal(f.voiceInputRef.current, null)
  f.runtime.startVoiceInput('button'); await tick()
  assert.equal(f.mediaCalls, 2)
})
test('initial event is seeded without replay; polling never overlaps and stops on cleanup', async () => {
  const poll = deferred(), f = fixture({ poll })
  assert.equal(f.requests.length, 1)
  assert.equal(f.timers.size, 0)
  poll.resolve({ ok: true, boot_id: 'node90-test', sequence: 4, state: 'button_long_press_voice' })
  await tick()
  assert.equal(f.mediaCalls, 0)
  assert.equal(f.timers.size, 1)
  f.cleanup()
  assert.equal(f.timers.size, 0)
})
test('cleanup during initialization closes the late stream and suppresses send', async () => {
  const media = deferred(), f = fixture({ media }); await tick()
  f.runtime.startVoiceInput('button'); f.cleanup()
  const stream = f.stream(); media.resolve(stream); await tick()
  assert.equal(stream.track.stopped, true)
  assert.equal(f.recorders.length + f.sent.length, 0)
})
test('cleanup stops an active recorder and ignores an old transcription', async () => {
  const transcription = deferred(), f = fixture({ transcription }); await tick()
  f.runtime.startVoiceInput('button'); await tick()
  f.runtime.stopVoiceInput(); await tick()
  f.cleanup(); transcription.resolve({ ok: true, transcript: '不要发送旧会话' }); await tick()
  assert.equal(f.streams[0].track.stopped, true)
  assert.equal(f.sent.length, 0)
  const g = fixture(); await tick()
  g.runtime.startVoiceInput('button'); await tick(); g.cleanup(); await tick()
  assert.equal(g.recorders[0].stops, 1)
  assert.equal(g.streams[0].track.stopped, true)
  assert.equal(g.sent.length, 0)
})
test('speech recognition fallback stops on release and sends only once', async () => {
  const recognizers = []
  class Recognition {
    constructor() { recognizers.push(this); this.stops = 0 }
    start() { this.onstart?.() }
    stop() {
      this.stops++
      this.onresult?.({ resultIndex: 0, results: [Object.assign([{ transcript: '后备识别' }], { isFinal: true })] })
      this.onend?.()
    }
    abort() { this.onend?.() }
  }
  const f = fixture({ speechRecognition: Recognition }); await tick()
  f.event(2, 'button_long_press_voice'); await f.poll()
  f.event(3, 'button_long_release_voice'); await f.poll()
  assert.equal(recognizers[0].stops, 1)
  assert.deepEqual(f.sent, ['后备识别'])
  recognizers[0].onend()
  assert.equal(f.sent.length, 1)
})
;(async () => {
  for (const { name, fn } of cases) { await fn(); console.log(`PASS ${name}`) }
  console.log(`${cases.length} offline voice input callback tests passed; no microphone or network used`)
})().catch(error => { console.error(error); process.exitCode = 1 })
