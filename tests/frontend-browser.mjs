// Optional real-browser smoke test. Uses only a fixture server, never app.py or saved user files.
// Run: node tests/frontend-browser.mjs [path-to-msedge-or-chrome]
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:http';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../static/', import.meta.url));
const browserPath = process.argv[2] || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const profile = await mkdtemp(path.join(tmpdir(), 'transfiler-frontend-browser-'));
const calls = [];
const server = createServer(async (request, response) => {
  const url = new URL(request.url, 'http://localhost');
  if (url.pathname === '/uploadfiles/') {
    request.resume();
    calls.push('upload');
    response.setHeader('Content-Type', 'application/json');
    return response.end(JSON.stringify({ images: ['page_10.png', 'page_1.png'] }));
  }
  if (url.pathname === '/cropimage/' || url.pathname === '/deletefiles/' || url.pathname === '/compilepdf/') {
    let body = '';
    for await (const chunk of request) body += chunk;
    calls.push({ path: url.pathname, body });
    response.setHeader('Content-Type', url.pathname === '/compilepdf/' ? 'application/pdf' : 'application/json');
    return response.end(url.pathname === '/compilepdf/' ? '%PDF-fixture' : JSON.stringify({ status: 'success' }));
  }
  if (url.pathname.startsWith('/saved_pages/')) {
    const wide = url.pathname.includes('page_10');
    response.setHeader('Content-Type', 'image/svg+xml');
    return response.end(`<svg xmlns="http://www.w3.org/2000/svg" width="${wide ? 1600 : 800}" height="${wide ? 400 : 1200}"><rect width="100%" height="100%" fill="white"/><text x="100" y="150" font-size="50">Fixture page</text></svg>`);
  }
  const relative = url.pathname === '/' ? 'index.html' : decodeURIComponent(url.pathname).replace(/^\/+/, '');
  const target = path.resolve(root, relative);
  if (!target.startsWith(path.resolve(root) + path.sep)) { response.statusCode = 403; return response.end(); }
  try {
    const data = await readFile(target);
    response.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' })[path.extname(target)] || 'application/octet-stream');
    response.end(data);
  } catch { response.statusCode = 404; response.end(); }
});

let browser;
let socket;
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
try {
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  browser = spawn(browserPath, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--window-size=1280,900', 'about:blank'],
  { windowsHide: true, stdio: 'ignore' });
  let spawnError;
  browser.on('error', (error) => { spawnError = error; });
  let port;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (spawnError) throw spawnError;
    try { port = Number((await readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break; }
    catch { await pause(100); }
  }
  assert.ok(port, 'Browser did not expose its debugging port');
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(targets.find((target) => target.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let commandId = 0;
  const pending = new Map();
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject, timer } = pending.get(message.id);
      clearTimeout(timer);
      pending.delete(message.id);
      if (message.error) reject(Error(message.error.message)); else resolve(message.result);
    }
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++commandId;
    const timer = setTimeout(() => { pending.delete(id); reject(Error(`${method} timed out`)); }, 45000);
    pending.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async (expression) => {
    const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  };
  await send('Page.enable');
  await send('Page.addScriptToEvaluateOnNewDocument', { source: 'window.testAlerts=[];window.alert=(message)=>window.testAlerts.push(message);' });
  await send('Page.navigate', { url: origin });
  await evaluate(`(async () => {
    const waitFor = async (condition) => { for(let i=0;i<300;i++){ if(condition()) return; await new Promise(r=>setTimeout(r,100)); } throw Error('Editor did not become ready: '+JSON.stringify(window.testAlerts)); };
    await waitFor(()=>document.querySelector('#displayImage')?.contentWindow?.cropperReady);
    await document.querySelector('#displayImage').contentWindow.cropperReady;
    await new Promise(r=>setTimeout(r,100));
    const transfer=new DataTransfer(); transfer.items.add(new File(['fixture'], 'fixture.pdf', {type:'application/pdf'}));
    document.querySelector('#fileInput').files=transfer.files;
    document.querySelector('#uploadBtn').click();
    await waitFor(()=>document.querySelectorAll('#selector button').length===2 && !document.querySelector('#uploadBtn').disabled);
    document.querySelectorAll('#selector button')[0].click();
    await waitFor(()=>!document.querySelector('#toggleModeBtn').disabled);
    const landscapeHeight=document.querySelector('#displayImage').clientHeight;
    document.querySelectorAll('#selector button')[1].click();
    await waitFor(()=>!document.querySelector('#toggleModeBtn').disabled);
    const frame=document.querySelector('#displayImage');
    if(frame.clientHeight<=landscapeHeight) throw Error('Portrait page did not grow after landscape');
    document.querySelector('#toggleModeBtn').click();
    const image=frame.contentDocument.querySelector('cropper-image');
    image.$zoom(0.5); image.$move(-20,-10);
    const selection=frame.contentDocument.querySelector('cropper-selection');
    const imageRect=image.getBoundingClientRect();
    const canvasRect=frame.contentDocument.querySelector('cropper-canvas').getBoundingClientRect();
    const scale=imageRect.width/800;
    selection.$change(imageRect.left-canvasRect.left+100*scale,imageRect.top-canvasRect.top+100*scale,200*scale,150*scale);
    const crop=frame.contentWindow.captureSelection();
    if(!crop || Math.abs(crop.x-100)>2 || Math.abs(crop.y-100)>2 || Math.abs(crop.secondX-300)>2 || Math.abs(crop.secondY-250)>2) throw Error('Incorrect crop geometry: '+JSON.stringify(crop));
    document.querySelector('#cropBtn').click();
    await waitFor(()=>!document.querySelector('#cropBtn').disabled);
    document.querySelector('#compileBtn').click();
    await waitFor(()=>!document.querySelector('#compileBtn').disabled);
    document.querySelector('#clearBtn').click();
    await waitFor(()=>document.querySelectorAll('#selector button').length===0 && !document.querySelector('#clearBtn').disabled);
    if(!document.querySelector('#cropBtn').disabled || frame.hasAttribute('style')) throw Error('Clear left a stale editor');
    if(window.testAlerts.length) throw Error('Unexpected alerts: '+JSON.stringify(window.testAlerts));
    return true;
  })()`);
  assert.equal(calls.filter((call) => call === 'upload').length, 1);
  const crop = calls.find((call) => call.path === '/cropimage/');
  assert.ok(crop, 'Crop action never reached the fixture server');
  assert.ok(Math.abs(JSON.parse(crop.body).x - 100) < 2);
  assert.ok(calls.some((call) => call.path === '/compilepdf/'));
  assert.ok(calls.some((call) => call.path === '/deletefiles/'));
  console.log('PASS: real Edge, real pinned Cropper.js, fixture upload/page switching/zoom/pan/crop/compile/clear.');
} finally {
  socket?.close();
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
  if (browser?.pid) {
    if (process.platform === 'win32') spawnSync('taskkill.exe', ['/PID', String(browser.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
    else browser.kill();
  }
  // This exact path was created above exclusively for this test.
  assert.equal(path.dirname(path.resolve(profile)), path.resolve(tmpdir()));
  assert.ok(path.basename(profile).startsWith('transfiler-frontend-browser-'));
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
