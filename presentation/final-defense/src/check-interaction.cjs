'use strict';
// Execute the delivered HTML script with a small DOM adapter.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const base=path.resolve(__dirname,'..'),html=fs.readFileSync(path.join(base,'index.html'),'utf8');
const data=id=>JSON.parse(html.match(new RegExp('<script id="'+id+'"[^>]*>([\\s\\S]*?)<\\/script>'))[1]);
const led=data('led-data'),meta=data('slide-data');
const script=[...html.matchAll(/<script(?: [^>]*)?>([\s\S]*?)<\/script>/g)].at(-1)[1];
class Element{
  constructor(dataset={}){this.dataset=dataset;this.attrs={};this.style={};this.hidden=false;this.textContent='';this.innerHTML='';this.offsetHeight=68;this.clientWidth=1440;this.classes=new Set();this.classList={contains:n=>this.classes.has(n),toggle:(n,v)=>{if(v??!this.classes.has(n))this.classes.add(n);else this.classes.delete(n)}}}
  setAttribute(k,v){this.attrs[k]=v}
  focus(){this.focused=true}
  matches(){return false}
  get clientHeight(){return parseFloat(this.style.height)||832}
}
function environment(reduced=false){
  const ids=Object.fromEntries(['prev','next','jump','notes','matrix-toggle','fullscreen','counter','note-panel','note-content','close-notes','toast','announcement','play','step','carousel'].map(k=>[k,new Element()]));
  ids['note-panel'].hidden=true;
  ids['led-data']={textContent:JSON.stringify(led)};ids['slide-data']={textContent:JSON.stringify(meta)};
  const deck=new Element(),toolbar=new Element(),controls=new Element();controls.offsetHeight=112;
  const slides=Array.from({length:40},(_,i)=>new Element({index:String(i%20)}));
  const buttons=Object.keys(led.states).map(state=>new Element({state}));
  const groups=[...html.matchAll(/<g data-led="([^"]+)" data-state="([^"]+)" data-x="([^"]+)" data-y="([^"]+)" data-w="([^"]+)"/g)].map(m=>new Element({led:m[1],state:m[2],x:m[3],y:m[4],w:m[5]}));
  assert(groups.some(g=>g.dataset.led==='main'));
  const listeners={},timers=[];
  const document={hidden:false,documentElement:{style:{setProperty(){}}},getElementById:id=>ids[id],querySelector:s=>s[0]==='#'?ids[s.slice(1)]:({'.deck':deck,'.toolbar':toolbar,'.led-controls':controls})[s],querySelectorAll:s=>({'.slide,.phone-slide':slides,'[data-led]':groups,'.led-controls [data-state]':buttons})[s]||[]};
  const context={document,innerWidth:1440,innerHeight:900,location:{hash:''},history:{replaceState(){}},matchMedia:()=>({matches:reduced,addEventListener(){}}),addEventListener:(event,fn)=>{listeners[event]=fn},setInterval:fn=>timers.push(fn),setTimeout(){},clearTimeout(){},scrollTo(){},console};context.window=context;
  vm.runInNewContext(script,context,{timeout:5000});
  return {context,ids,groups,buttons,controls,deck,timers,listeners};
}
const e=environment();assert.equal(e.context.deck.index,1);assert.equal(e.ids.prev.disabled,true);
e.context.deck.go(999);assert.equal(e.context.deck.index,20);assert.equal(e.ids.next.disabled,true);
e.context.deck.go(8);assert.equal(e.controls.classList.contains('is-open'),true);assert.equal(e.deck.style.height,'720px');
const main=e.groups.find(g=>g.dataset.led==='main');
for(const button of e.buttons){button.onclick();assert.equal(main.dataset.renderedState,button.dataset.state);assert.equal((main.innerHTML.match(/<rect /g)||[]).length,97);const on=led.states[button.dataset.state][0].rows.join('').replaceAll('0','').length;assert.equal((main.innerHTML.match(/fill="#89DFFD"/g)||[]).length,on)}
e.ids.play.onclick();assert.equal(e.context.deck.running,false);const frame=main.dataset.frame;e.timers[0]();assert.equal(main.dataset.frame,frame);e.ids.step.onclick();assert.equal(main.dataset.frame,'1');
e.ids['matrix-toggle'].onclick();assert.equal(e.controls.classList.contains('is-open'),false);assert.equal(e.deck.style.height,'832px');e.ids['matrix-toggle'].onclick();assert.equal(e.controls.classList.contains('is-open'),true);
e.ids.notes.onclick();assert.equal(e.ids['note-panel'].hidden,false);e.ids['close-notes'].onclick();assert.equal(e.ids['note-panel'].hidden,true);
for(const [key,index] of [['End',20],['Home',1]]){e.listeners.keydown({key,target:new Element(),preventDefault(){}});assert.equal(e.context.deck.index,index)}
e.context.deck.go(9);e.ids.carousel.onclick();e.timers[0]();assert.equal(e.groups.find(g=>g.dataset.led==='cry').dataset.renderedState,'cry');assert.equal(e.groups.find(g=>g.dataset.led==='voice').dataset.renderedState,'voice');
assert.equal(environment(true).context.deck.running,false);
const report={method:'Node vm executing delivered HTML with a minimal DOM adapter',checks:['20-page navigation and bounds','nine manual states render 96 source pixels','pause and step behavior','LED controls fit within available slide height','notes open and close','exception panels preserve labelled states','Home and End keyboard navigation','reduced-motion starts paused'],passed:true,real_browser_verified:false};
fs.writeFileSync(path.join(base,'qa/node-interaction.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
