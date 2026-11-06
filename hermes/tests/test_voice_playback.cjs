// Offline callback tests for the actual reconstructed ChatSidebar. No DOM or playback.
// Run through run_offline.py or run_frontend_tests.py; the existing TypeScript compiler
// transpiles in memory. All fetch, audio, speech synthesis and React hooks stubbed.
const assert = require('node:assert/strict')
const ts = require('typescript')
const source = globalThis.__sidebarSource
const transpiled = ts.transpileModule(source, {
  fileName: 'ChatSidebar.tsx',
  compilerOptions: { target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.Preserve },
  reportDiagnostics: true,
})
const errors = (transpiled.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error)
assert.equal(errors.length, 0, errors.map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')).join('\n'))
const page = ts.transpileModule(globalThis.__chatPageSource, {
  fileName: 'ChatPage.tsx',
  compilerOptions: { target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.Preserve },
  reportDiagnostics: true,
})
const pageErrors = (page.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error)
assert.equal(pageErrors.length, 0, pageErrors.map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')).join('\n'))
const js = transpiled.outputText
const normalizeStart = js.indexOf('function prepareXiaoxiSpokenText(')
assert(normalizeStart >= 0, 'Playback uses the actual staged speech text helper')
const normalizeBlock = js.slice(normalizeStart, js.indexOf('\n}', normalizeStart) + 2)
const callbackBlock = js.slice(js.indexOf('const stopSpeaking = useCallback('), js.indexOf('const stopVoiceInput = useCallback('))
const eventBlock = js.slice(js.indexOf("const offMsgComplete = feed.on('message.complete'"), js.indexOf('void connect()', js.indexOf('const offMsgComplete')))
assert(callbackBlock.startsWith('const stopSpeaking'))
assert(eventBlock.startsWith('const offMsgComplete'))
const inputs = ['useCallback', 'useRef', 'useEffect', 'audioRef', 'ttsRequestRef', 'setTtsSpeaking', 'setVoiceStatus', 'setPlaybackSource', 'ttsVoice', 'autoTts', 'profile', 'channel', 'fetchJSON', 'Audio', 'window', 'SpeechSynthesisUtterance', 'feed', 'setLastReplyText']
const initialize = new Function(...inputs, `${normalizeBlock}\n${callbackBlock}\n${eventBlock}\nreturn { stopSpeaking, speakWithXiaoxi, voicePlaybackRef, offMsgComplete }`)
const tick = () => new Promise(resolve => setImmediate(resolve))
const deferred = () => {
  let resolve, reject
  const promise = new Promise((a, b) => { resolve = a; reject = b })
  return { promise, resolve, reject }
}
const edgeResult = voice => ({ ok: true, provider: 'edge', voice, data_url: `data:stub,${voice}` })
function fixture(fetchImpl = async () => edgeResult('zh-CN-XiaoxiaoNeural')) {
  const state = {}, audio = [], native = [], requests = [], cleanups = [], subscriptions = []
  const audioRef = { current: null }, ttsRequestRef = { current: null }
  let stableRef
  let playImpl = async () => {}
  class AudioStub {
    constructor(url) { this.url = url; this.paused = false; audio.push(this) }
    play() { return playImpl(this) }
    pause() { this.paused = true }
  }
  class UtteranceStub { constructor(text) { this.text = text } }
  const browser = { speechSynthesis: {
    cancel() {},
    getVoices() { return [{ name: 'Stub 中文声线', lang: 'zh-CN' }] },
    speak(utterance) { native.push(utterance); utterance.onstart?.() },
  } }
  function render(voice = 'zh-CN-XiaoxiaoNeural', auto = true) {
    const feed = { on(name, handler) { subscriptions.push({ name, handler }); return () => {} } }
    return initialize(
      fn => fn, value => stableRef || (stableRef = { current: value }),
      fn => { const cleanup = fn(); if (cleanup) cleanups.push(cleanup) },
      audioRef, ttsRequestRef, value => { state.speaking = value }, value => { state.status = value },
      value => { state.source = value }, voice, auto, 'test-profile', 'chat-1',
      (url, init) => { requests.push({ url, init }); return fetchImpl(url, init) },
      AudioStub, browser, UtteranceStub, feed, value => { state.lastReply = value },
    )
  }
  const runtime = render()
  return { state, audio, native, requests, runtime, render, cleanups, subscriptions, setPlay: fn => { playImpl = fn } }
}
const cases = []
const test = (name, fn) => cases.push({ name, fn })
test('cloud error is visible and does not trigger browser fallback', async () => {
  const f = fixture(async () => { throw new Error('stub cloud unavailable') })
  await f.runtime.speakWithXiaoxi('hello')
  assert.equal(f.native.length, 0)
  assert.equal(f.audio.length, 0)
  assert.equal(f.state.speaking, false)
  assert.match(f.state.status, /Edge.*stub cloud unavailable/)
})
test('successful cloud playback sends JSON and shows verified source and voice', async () => {
  const f = fixture()
  await f.runtime.speakWithXiaoxi('hello')
  assert.equal(f.audio.length, 1)
  assert.equal(f.native.length, 0)
  assert.equal(f.requests[0].init.headers['Content-Type'], 'application/json')
  assert(f.requests[0].init.signal instanceof AbortSignal)
  assert.match(f.requests[0].url, /profile=test-profile.*voice=zh-CN-XiaoxiaoNeural/)
  assert.match(f.state.source, /Edge.*zh-CN-XiaoxiaoNeural/)
  f.audio[0].onended()
  assert.equal(f.state.speaking, false)
})
test('wrong server provider or voice never plays audio', async () => {
  for (const result of [{ ...edgeResult('zh-CN-XiaoxiaoNeural'), provider: 'neutts' }, edgeResult('zh-CN-YunxiNeural')]) {
    const f = fixture(async () => result)
    await f.runtime.speakWithXiaoxi('hello')
    assert.equal(f.audio.length + f.native.length, 0)
    assert.match(f.state.status, /不一致/)
  }
})
test('play rejection remains visible without browser fallback', async () => {
  const f = fixture()
  f.setPlay(async () => { throw new Error('stub autoplay blocked') })
  await f.runtime.speakWithXiaoxi('hello')
  assert.equal(f.native.length, 0)
  assert.equal(f.state.speaking, false)
  assert.match(f.state.status, /stub autoplay blocked/)
})
test('stop aborts and ignores an eventual old server response', async () => {
  const old = deferred()
  const f = fixture(() => old.promise)
  const pending = f.runtime.speakWithXiaoxi('hello')
  f.runtime.stopSpeaking()
  assert.equal(f.requests[0].init.signal.aborted, true)
  old.resolve(edgeResult('zh-CN-XiaoxiaoNeural'))
  await pending
  assert.equal(f.audio.length + f.native.length, 0)
  assert.equal(f.state.speaking, false)
  assert.equal(f.state.status, null)
})
test('new selection wins when old requests or play promises finish later', async () => {
  const old = deferred()
  let count = 0
  const f = fixture(() => ++count === 1 ? old.promise : Promise.resolve(edgeResult('zh-CN-YunxiNeural')))
  const pending = f.runtime.speakWithXiaoxi('old')
  await f.runtime.speakWithXiaoxi('new', 'zh-CN-YunxiNeural')
  old.resolve(edgeResult('zh-CN-XiaoxiaoNeural'))
  await pending
  assert.equal(f.audio.length, 1)
  assert.equal(f.requests[0].init.signal.aborted, true)
  assert.match(f.state.source, /Yunxi/)
  const oldAudio = f.audio[0]
  const play = deferred()
  f.setPlay(() => play.promise)
  const pendingPlay = f.runtime.speakWithXiaoxi('slow play', 'zh-CN-YunxiNeural')
  await tick()
  const slowAudio = f.audio[1]
  f.setPlay(async () => {})
  await f.runtime.speakWithXiaoxi('latest', 'zh-CN-YunxiNeural')
  const latestStatus = f.state.status
  oldAudio.onended()
  slowAudio.onerror()
  play.reject(new Error('stopped old audio'))
  await pendingPlay
  assert.equal(slowAudio.paused, true)
  assert.equal(f.state.speaking, true)
  assert.equal(f.state.status, latestStatus)
  assert.equal(f.native.length, 0)
})
test('browser speech synthesis runs only after explicit native selection', async () => {
  const f = fixture(async () => { throw new Error('must not fetch') })
  await f.runtime.speakWithXiaoxi('hello', 'browser-native')
  assert.equal(f.requests.length, 0)
  assert.equal(f.native.length, 1)
  assert.match(f.state.source, /浏览器系统朗读.*Stub 中文声线/)
  f.runtime.stopSpeaking()
  f.native[0].onerror({ error: 'old cancelled utterance' })
  assert.equal(f.state.status, null)
})
test('cloud and browser receive complete Chinese measurements with signed decimals and ranges', async () => {
  const measurements = [
    ['室内湿度51.5%，温度23.9°C；室外湿度65％，体感−5.2℃，华氏+32.5°F。',
      '室内湿度百分之51.5，温度23.9摄氏度；室外湿度百分之65，体感负5.2摄氏度，华氏正32.5华氏度。'],
    ['天气：humidity 51.5%, temperature -2.3°C; range −5℃～+2℃，湿度40-60％，华氏-5--1℉。',
      '天气：humidity 百分之51.5, temperature 负2.3摄氏度; range 负5摄氏度至正2摄氏度，湿度百分之40至百分之60，华氏负5华氏度至负1华氏度。'],
    ['变化-5.25%或+0.5％，误差−.75%，范围45%—51.5%。',
      '变化百分之负5.25或百分之正0.5，误差百分之负.75，范围百分之45至百分之51.5。'],
    ['风速12.5km/h，降水2mm，积雪3cm，能见度500m；频率5MHz，速度3m/s，重量7mg。',
      '风速12.5公里每小时，降水2毫米，积雪3厘米，能见度500米；频率5MHz，速度3m/s，重量7mg。'],
  ]
  for (const voice of ['zh-CN-XiaoxiaoNeural', 'browser-native']) {
    for (const [text, expected] of measurements) {
      const f = fixture()
      await f.runtime.speakWithXiaoxi(text, voice)
      const spoken = voice === 'browser-native' ? f.native[0].text : JSON.parse(f.requests[0].init.body).text
      assert.equal(spoken, expected)
      assert.doesNotMatch(spoken, /percent|degrees/)
    }
  }
})
test('speech omits fenced code and encoded URL targets while retaining link labels', async () => {
  const text = '查看[天气51.5%](https://example.invalid/a%20b?q=23%C2%B0C) 和 https://example.invalid/65%20percent ```const x = "99% -99°C"``` 温度23.9°C。'
  for (const voice of ['zh-CN-XiaoxiaoNeural', 'browser-native']) {
    const f = fixture()
    await f.runtime.speakWithXiaoxi(text, voice)
    const spoken = voice === 'browser-native' ? f.native[0].text : JSON.parse(f.requests[0].init.body).text
    assert.equal(spoken, '查看天气百分之51.5 和 温度23.9摄氏度。')
  }
})
test('already Chinese speech is idempotent and English keeps existing symbol wording', async () => {
  for (const voice of ['zh-CN-XiaoxiaoNeural', 'browser-native']) {
    for (const text of [
      '湿度百分之51.5，温度23.9摄氏度，体感负5.2摄氏度。',
      'Humidity 51.5%, temperature -2.3°C, range 11–17°F.',
    ]) {
      const f = fixture()
      await f.runtime.speakWithXiaoxi(text, voice)
      const spoken = voice === 'browser-native' ? f.native[0].text : JSON.parse(f.requests[0].init.body).text
      assert.equal(spoken, text)
    }
  }
})
test('auto playback normalizes speech without changing the original reply text', async () => {
  const f = fixture()
  const text = '室内湿度51.5%，温度−5.2°C。'
  f.subscriptions[0].handler({ payload: { text, status: 'complete' } })
  await tick()
  assert.equal(f.state.lastReply, text)
  assert.equal(JSON.parse(f.requests[0].init.body).text, '室内湿度百分之51.5，温度负5.2摄氏度。')
})
test('existing event subscriber uses latest voice and auto-play toggle', async () => {
  const f = fixture(async url => edgeResult(new URL(`https://offline.invalid${url}`).searchParams.get('voice')))
  const initialHandler = f.subscriptions[0].handler
  f.render('zh-CN-YunxiNeural')
  initialHandler({ payload: { text: 'auto reply', status: 'complete' } })
  await tick()
  assert.equal(f.requests.length, 1)
  assert.match(f.requests[0].url, /voice=zh-CN-YunxiNeural/)
  f.render('zh-CN-XiaoxiaoNeural', false)
  initialHandler({ payload: { text: 'muted reply', status: 'complete' } })
  await tick()
  assert.equal(f.requests.length, 1)
  assert.equal(f.state.lastReply, 'muted reply')
})
test('channel/profile/unmount cleanup cancels pending playback', async () => {
  const old = deferred()
  const f = fixture(() => old.promise)
  const pending = f.runtime.speakWithXiaoxi('hello')
  f.cleanups.forEach(fn => fn())
  old.reject(new Error('stub request cancelled'))
  await pending
  assert.equal(f.requests[0].init.signal.aborted, true)
  assert.equal(f.audio.length + f.native.length, 0)
  assert.equal(f.state.status, null)
})
;(async () => {
  for (const { name, fn } of cases) {
    await fn()
    console.log(`PASS ${name}`)
  }
  console.log(`${cases.length} offline playback callback tests passed; TypeScript transpilation passed`)
})().catch(error => { console.error(error); process.exitCode = 1 })
