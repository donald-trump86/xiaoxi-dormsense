// Execute the actual reconstructed ChatPage selection hooks and event callbacks.
// Offline only: no DOM, server, history, browser storage or model is accessed.
const assert = require('node:assert/strict')
const ts = require('typescript')
const source = globalThis.__chatPageSource
const ast = ts.createSourceFile('ChatPage.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const component = ast.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'ChatPage')
assert(component?.body)
const helperNames = new Set(['durableChatId', 'readRememberedChat', 'rememberChat', 'channelForChat', 'resolveDashboardChat', 'generateChannelId'])
const helpers = ast.statements.filter(n => ts.isFunctionDeclaration(n) && helperNames.has(n.name?.text)).map(n => n.getText(ast)).join('\n')
assert.equal(ast.statements.filter(n => ts.isFunctionDeclaration(n) && helperNames.has(n.name?.text)).length, helperNames.size)
const names = new Set(['requestedResume', 'freshUrlRequested', 'freshRequested', 'chatStorageKey', 'chatSelection', 'selectedChatRef', 'freshRequestNonce', 'handledFreshNonceRef', 'handledFreshScopeRef', 'startFreshDashboardChat', 'chatSelectionReady', 'resumeParam', 'channel'])
function bindingNames(name) { return ts.isIdentifier(name) ? [name.text] : name.elements.flatMap(e => e.name ? bindingNames(e.name) : []) }
const statements = component.body.statements.filter(n => {
  if (ts.isVariableStatement(n)) return n.declarationList.declarations.some(d => bindingNames(d.name).some(name => names.has(name)))
  return ts.isExpressionStatement(n) && n.getText(ast).includes('selectedChatRef.current = null;')
})
assert.equal(statements.filter(n => ts.isExpressionStatement(n)).length, 1, 'test must execute the real selection effect')
const selectionCode = statements.map(n => n.getText(ast)).join('\n')
function compile(text) {
  const output = ts.transpileModule(text, { fileName: 'seam.ts', compilerOptions: { target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true })
  assert.equal((output.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error).length, 0)
  return output.outputText
}
const tick = () => new Promise(resolve => setImmediate(resolve))
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b }); return {promise,resolve,reject} }
class ApiError extends Error { constructor(status) { super(`stub ${status}`); this.status=status } }
function storage(map, denied = false) { return {
  getItem(key) { if (denied) throw Error('storage denied'); return map.get(key) ?? null },
  setItem(key,value) { if (denied) throw Error('storage denied'); map.set(key,value) },
  removeItem(key) { if (denied) throw Error('storage denied'); map.delete(key) },
} }
function fixture({query='', profile='p1', base='/app', lookup=async id => ({session_id:id}), denied=false, attachDenied=false}={}) {
  let props={searchParams:new URLSearchParams(query),scopedProfile:profile,HERMES_BASE_PATH:base,isActive:true}
  const local=new Map(), session=new Map(), calls=[], slots=[], effects=[]
  let cursor=0, dirty=true, output, attachCount=0
  const key=(p=props.scopedProfile,b=props.HERMES_BASE_PATH) => JSON.stringify(['hermes.chat.last-session.v1',b,p||'@serving'])
  const refs={forceFreshPtyRef:{current:false},reconnectAttemptRef:{current:0},blockedInputNoticeRef:{current:false},ptyInputLineRef:{current:''},mobileReplacementInputUntilRef:{current:0}}
  const env={...refs,api:{getSessionLatestDescendant(id,p) { calls.push([id,p]); return lookup(id,p) }},ApiError,
    localStorage:storage(local,denied),sessionStorage:storage(session,denied),crypto:require('node:crypto').webcrypto,
    dashboardServingProfile:()=>'',ptyAttachToken:async () => { if(attachDenied) throw Error('denied'); return `attach-${++attachCount}` },
    clearReconnectTimer(){},setBanner(){},setBannerAction(){},setReconnectGaveUp(){},setPtyState(){},setReconnectNonce(){},
    setSearchParams(next) { props.searchParams=typeof next==='function'?next(props.searchParams):next;dirty=true },
    searchParamsWriterRef:{current:(...args)=>env.setSearchParams(...args)},
    useCallback:fn=>fn,
    useRef(value) { const i=cursor++; if(!slots[i]) slots[i]={current:value};return slots[i] },
    useState(value) { const i=cursor++;if(!slots[i]) slots[i]={value};return [slots[i].value,next=>{const v=typeof next==='function'?next(slots[i].value):next;if(v!==slots[i].value){slots[i].value=v;dirty=true}}] },
    useEffect(fn,deps) {const i=cursor++;const previous=slots[i];if(!previous||deps.some((v,j)=>!Object.is(v,previous.deps[j]))){effects.push(()=>{previous?.cleanup?.();slots[i]={deps,cleanup:fn()}})}},
  }
  const run=new Function(...Object.keys(env),'searchParams','scopedProfile','HERMES_BASE_PATH','isActive',compile(`${helpers}\n${selectionCode}\nreturn {selection:chatSelection,ready:!!chatSelectionReady,resume:resumeParam,channel,fresh:startFreshDashboardChat};`))
  function render(next={}) {props={...props,...next};dirty=false;cursor=0;output=run(...Object.values(env),props.searchParams,props.scopedProfile,props.HERMES_BASE_PATH,props.isActive);while(effects.length) effects.shift()();return output}
  async function settle() {for(let n=0;n<12;n++){if(dirty) render();await tick();if(!dirty) return output}throw Error('hook fixture did not settle')}
  return {local,session,calls,key,render,settle,get output(){return output},unmount(){for(const slot of slots)slot?.cleanup?.()}}
}
function observation({lookup=async id=>({session_id:id}),resume=null}={}) {
  const start=source.indexOf('    let unmounting = false;')
  const end=source.indexOf('    // The implicit active-session fallback',start)
  assert(start>0&&end>start)
  const block=source.slice(start,end)
  const local=new Map(), handlers=new Map(), calls=[], params=new URLSearchParams('fresh=1')
  const feed={on(name,fn){handlers.set(name,fn);return()=>handlers.delete(name)},onClose(){return()=>{}},async connect(channel){calls.push(channel)},close(){},lastCloseCode:1000}
  const cleanupStart=source.indexOf('      unmounting = true;',end)
  const cleanupEnd=source.indexOf('      imageUploadDisposed = true;',cleanupStart)
  assert(cleanupStart>0&&cleanupEnd>cleanupStart)
  const env={api:{getSessionLatestDescendant:lookup},ApiError,localStorage:storage(local),sessionStorage:storage(new Map()),crypto:require('node:crypto').webcrypto,
    EventsFeedClient:function(){return feed},emitEvent:(name,event)=>handlers.get(name)?.(event),resumeParam:resume,scopedProfile:'p1',channel:'channel-p1',chatStorageKey:'scope-p1',isActiveRef:{current:true},
    searchParamsWriterRef:{current(fn){const next=fn(params);if(next!==params){for(const key of [...params.keys()])params.delete(key);for(const [key,value]of next)params.set(key,value)}}},
    EVENTS_MAX_RECONNECT_ATTEMPTS:3,eventsReconnectDelayMs:()=>1,shouldRetryEventsClose:()=>false}
  const run=new Function(...Object.keys(env),compile(`${helpers}\n${block}\nreturn {emit:emitEvent, close:()=>{${source.slice(cleanupStart,cleanupEnd)}}};`))
  return {runtime:run(...Object.values(env)),local,params,calls}
}
const cases=[]
const test=(name,fn)=>cases.push({name,fn})
test('default restores the remembered real ID and current descendant before PTY readiness',async()=>{
  const slow=deferred(),f=fixture({lookup:()=>slow.promise});f.local.set(f.key(),'human-A');f.render();assert.equal(f.output.ready,false)
  slow.resolve({session_id:'human-A-child'});await f.settle();assert.equal(f.output.resume,'human-A-child');assert.deepEqual(f.calls,[['human-A','p1']]);f.unmount()
})
test('explicit resume overrides the remembered daily choice',async()=>{
  const f=fixture({query:'resume=chosen'});f.local.set(f.key(),'remembered');f.render();await f.settle();assert.equal(f.output.resume,'chosen');assert.deepEqual(f.calls,[['chosen','p1']]);f.unmount()
})
test('new conversation cancels a late restore and repeated new presses stay fresh',async()=>{
  const slow=deferred(),f=fixture({lookup:()=>slow.promise});f.local.set(f.key(),'old');f.render();f.output.fresh();await f.settle();const first=f.output.selection.attach
  slow.resolve({session_id:'old-child'});await f.settle();assert.equal(f.output.resume,null);assert.equal(f.local.has(f.key()),false)
  f.output.fresh();await f.settle();assert.notEqual(f.output.selection.attach,first);assert.equal(f.output.selection.fresh,true);f.unmount()
})
test('empty New chat then explicit history selection consumes fresh intent without a message',async()=>{
  for(const waitForAttach of [false,true]) {
    const f=fixture();f.render();await f.settle();f.output.fresh();
    if(waitForAttach)await f.settle();else f.render();
    f.render({searchParams:new URLSearchParams('fresh=1&resume=human-history')});await f.settle();
    assert.equal(f.output.ready,true);assert.equal(f.output.resume,'human-history');assert.equal(f.output.selection.fresh,false);
    f.render({searchParams:new URLSearchParams()});await f.settle();assert.equal(f.output.resume,'human-history');f.unmount();
  }
})
test('profile switch invalidates an in-flight choice and isolates browser keys',async()=>{
  const a=deferred(),f=fixture({lookup:(id,p)=>p==='p1'?a.promise:Promise.resolve({session_id:id})});f.local.set(f.key(),'A');f.local.set(f.key('p2'),'B');f.render();f.render({scopedProfile:'p2'});await f.settle();assert.equal(f.output.resume,'B')
  a.resolve({session_id:'A-child'});await f.settle();assert.equal(f.output.resume,'B');assert.notEqual(f.key('p1'),f.key('p2'));assert.notEqual(f.key('p2','/other'),f.key('p2'));f.unmount()
})
test('deleted stored ID clears its key while transient backend failure preserves intent',async()=>{
  for(const [status,expected]of[[404,null],[503,'human']]){const f=fixture({lookup:async()=>{throw new ApiError(status)}});f.local.set(f.key(),'human');f.render();await f.settle();assert.equal(f.output.resume,expected);assert.equal(f.local.get(f.key())??null,expected);f.unmount()}
})
test('denied storage and native attach rejection do not block selection',async()=>{
  const f=fixture({denied:true,attachDenied:true});f.render();await f.settle();assert.equal(f.output.ready,true);assert.equal(f.output.resume,null);assert.match(f.output.selection.attach,/^[a-f0-9]{32}$/);f.unmount()
})
test('event handler stores only a confirmed payload DB ID and retries an empty draft',async()=>{
  let saved=false;const f=observation({lookup:async id=>{if(!saved)throw new ApiError(404);return {session_id:id}}})
  f.runtime.emit('session.info',{session_id:'rpc-id',payload:{session_id:'channel-id'}});await tick();assert.equal(f.local.size,0)
  f.runtime.emit('session.info',{payload:{stored_session_id:'actual-draft'}});await tick();assert.equal(f.local.size,0);assert.equal(f.params.get('fresh'),'1')
  saved=true;f.runtime.emit('message.complete',{});await tick();assert.equal(f.local.get('scope-p1'),'actual-draft');assert.equal(f.params.has('fresh'),false);assert.deepEqual(f.calls,['channel-p1']);f.runtime.close()
})
test('late observed IDs cannot overwrite a newer announcement or unmounted scope',async()=>{
  const a=deferred(),b=deferred(),f=observation({lookup:id=>id==='A'?a.promise:b.promise})
  f.runtime.emit('session.info',{payload:{stored_session_id:'A'}});f.runtime.emit('session.info',{payload:{stored_session_id:'B'}})
  b.resolve({session_id:'B'});await tick();a.resolve({session_id:'A'});await tick();assert.equal(f.local.get('scope-p1'),'B');f.runtime.close()
  const slow=deferred(),g=observation({lookup:()=>slow.promise});g.runtime.emit('session.info',{payload:{stored_session_id:'C'}});g.runtime.close();slow.resolve({session_id:'C'});await tick();assert.equal(g.local.size,0)
})
;(async()=>{for(const {name,fn}of cases){await fn();console.log(`PASS ${name}`)}console.log(`${cases.length} actual ChatPage continuation hook/callback tests passed (offline stubs; no browser or history)`)} )().catch(error=>{console.error(error);process.exitCode=1})
