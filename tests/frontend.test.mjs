import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), 'utf8');
const [apiSource, displaySource, cropSource, editorSource, iframeSource] = await Promise.all([
  'static/utils/api.js', 'static/utils/imageDisplay.js', 'static/utils/cropHandler.js',
  'static/script.js', 'static/cropper/script.js',
].map(read));
const plain = (source) => source.replace(/^import .*;\r?\n/gm, '').replace(/export /g, '');
const settle = () => new Promise(setImmediate);
const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

class Element {
  constructor(tagName = 'div') {
    this.tagName = tagName;
    this.children = [];
    this.dataset = {};
    this.style = {};
    this.attributes = {};
    this.listeners = {};
    this.files = [];
    const classes = new Set();
    this.classList = {
      add: (value) => classes.add(value),
      toggle: (value, enabled) => enabled ? classes.add(value) : classes.delete(value),
      contains: (value) => classes.has(value),
    };
  }
  set innerHTML(value) { this.children = []; }
  append(...items) { this.children.push(...items); }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  setAttribute(key, value) { this.attributes[key] = value; }
  getAttribute(key) { return this.attributes[key] ?? null; }
  removeAttribute(key) { delete this.attributes[key]; if (key === 'style') this.style = {}; }
  querySelector(tagName) { return this.children.find((item) => item.tagName === tagName) || null; }
  querySelectorAll(tagName) { return this.children.filter((item) => item.tagName === tagName); }
}

async function editor() {
  const ids = Object.fromEntries(['displayImage', 'selector', 'uploadBtn', 'clearBtn',
    'compileBtn', 'toggleModeBtn', 'cropBtn', 'fileInput'].map((id) => [id, new Element()]));
  const alerts = [];
  const requests = [];
  const image = new Element('cropper-image');
  const stage = { clientWidth: 1000, clientHeight: 600 };
  const frame = ids.displayImage;
  const cropper = {
    cropperReady: Promise.resolve(),
    enabled: false,
    clears: 0,
    fits: 0,
    setSelectionEnabled(value) { this.enabled = value; },
    clearImage() { this.clears++; image.setAttribute('src', ''); },
    fitImage() { this.fits++; },
    captureSelection: () => ({ x: 10, y: 20, secondX: 50, secondY: 60 }),
    async loadImage(src) {
      image.setAttribute('src', src);
      return { naturalWidth: 500, naturalHeight: 1000 };
    },
  };
  frame.contentWindow = cropper;
  frame.parentElement = stage;
  frame.contentDocument = { querySelector: () => image };
  let resize;
  const context = vm.createContext({
    document: { getElementById: (id) => ids[id], createElement: (tag) => new Element(tag) },
    console: { log() {}, error() {} },
    alert: (message) => alerts.push(message),
    FormData: class { append() {} },
    ResizeObserver: class { constructor(callback) { resize = callback; } observe() {} },
    fetch: async (path, options) => {
      requests.push({ path, options });
      return { ok: true, json: async () => path === '/uploadfiles/' ? { images: ['page_1.png'] } : { status: 'success' },
        blob: async () => ({ size: 123, type: 'application/pdf' }) };
    },
  });
  vm.runInContext([apiSource, displaySource, cropSource, editorSource].map(plain).join('\n'), context);
  await settle();
  return { context, ids, alerts, requests, image, stage, cropper, resize: () => resize() };
}

test('API requests use same-origin paths and preserve HTTP error details for every endpoint', async () => {
  const { context, requests } = await editor();
  const calls = [() => context.uploadFileApi({}), () => context.cropImageApi({}),
    () => context.deleteFilesApi(), () => context.compilePdfApi()];
  for (const call of calls) await call();
  assert.deepEqual(requests.map((item) => item.path), ['/uploadfiles/', '/cropimage/', '/deletefiles/', '/compilepdf/']);
  assert.deepEqual(requests.map((item) => item.options.method), ['POST', 'POST', 'DELETE', 'POST']);
  context.fetch = async () => ({ ok: false, status: 400, json: async () => ({ detail: { code: 'BAD_INPUT', message: 'Invalid image' } }) });
  for (const call of calls) await assert.rejects(call, { message: 'Invalid image', code: 'BAD_INPUT' });
});

test('API handles string, non-JSON and network errors', async () => {
  const { context } = await editor();
  context.fetch = async () => ({ ok: false, status: 400, json: async () => ({ detail: 'Bad crop' }) });
  await assert.rejects(() => context.cropImageApi({}), { message: 'Bad crop' });
  context.fetch = async () => ({ ok: false, status: 502, json: async () => { throw Error('HTML'); } });
  await assert.rejects(() => context.compilePdfApi(), { message: 'Server responded with status: 502' });
  context.fetch = async () => { throw Error('Network unavailable'); };
  await assert.rejects(() => context.uploadFileApi({}), { message: 'Network unavailable' });
});

test('page fit uses the whole stage after a landscape page and after resize', async () => {
  const { context, ids, stage } = await editor();
  context.updateIframeDimensions(ids.displayImage, { naturalWidth: 2000, naturalHeight: 500 });
  assert.equal(ids.displayImage.style.height, '250px');
  ids.displayImage.clientHeight = 250;
  context.updateIframeDimensions(ids.displayImage, { naturalWidth: 500, naturalHeight: 2000 });
  assert.equal(ids.displayImage.style.height, '600px');
  stage.clientWidth = 100;
  context.updateIframeDimensions(ids.displayImage, { naturalWidth: 500, naturalHeight: 2000 });
  assert.equal(ids.displayImage.style.width, '100px');
  assert.equal(ids.displayImage.style.height, '400px');
});

test('no-file upload stays usable and invalid responses preserve existing thumbnails', async () => {
  const { context, ids, requests, alerts } = await editor();
  await context.uploadFile();
  assert.equal(requests.length, 0);
  ids.fileInput.files = [{}];
  await context.uploadFile();
  assert.equal(ids.selector.children.length, 1);
  const original = ids.selector.children[0];
  context.fetch = async () => ({ ok: true, json: async () => ({ message: 'oops' }) });
  await context.uploadFile();
  assert.equal(ids.selector.children[0], original);
  assert.equal(alerts.at(-1), 'The server did not return a page list.');
  assert.equal(ids.uploadBtn.disabled, false);
});

test('a shared guard blocks crop/clear/compile/upload races and restores controls after failure', async () => {
  const { context, ids, alerts } = await editor();
  const pending = deferred();
  let calls = 0;
  context.fetch = () => { calls++; return pending.promise; };
  ids.fileInput.files = [{}];
  const upload = context.uploadFile();
  assert.equal(ids.clearBtn.disabled, true);
  await context.deleteFiles();
  await context.compilePdf();
  await context.uploadFile();
  assert.equal(calls, 1);
  pending.reject(Error('Offline'));
  await upload;
  assert.deepEqual(alerts, ['Offline']);
  assert.equal(ids.uploadBtn.disabled, false);
  assert.equal(ids.clearBtn.disabled, false);
});

test('successful clear resets displayed page and selection; failed clear preserves them', async () => {
  const { context, ids, cropper } = await editor();
  context.renderPageThumbnails(ids.selector, ['page_1.png'], context.displayImage);
  await context.displayImage({ currentTarget: ids.selector.children[0] });
  context.toggleSelectionMode();
  assert.equal(cropper.enabled, true);
  const clears = cropper.clears;
  const workingFetch = context.fetch;
  context.fetch = async () => { throw Error('Offline'); };
  await context.deleteFiles();
  assert.equal(cropper.clears, clears);
  assert.equal(cropper.enabled, true);
  assert.equal(ids.selector.children.length, 1);
  context.fetch = workingFetch;
  await context.deleteFiles();
  assert.equal(cropper.clears, clears + 1);
  assert.equal(cropper.enabled, false);
  assert.equal(ids.selector.children.length, 0);
  assert.equal(ids.toggleModeBtn.disabled, true);
  assert.deepEqual(ids.displayImage.style, {});
});

test('new upload invalidates the old selected page and refreshes page URLs', async () => {
  const { context, ids, image } = await editor();
  context.renderPageThumbnails(ids.selector, ['page_1.png'], context.displayImage);
  await context.displayImage({ currentTarget: ids.selector.children[0] });
  context.toggleSelectionMode();
  ids.fileInput.files = [{}];
  await context.uploadFile();
  assert.equal(image.getAttribute('src'), '');
  assert.equal(ids.cropBtn.disabled, true);
  assert.match(ids.selector.children[0].dataset.src, /^\/saved_pages\/page_1\.png\?t=\d+$/);
});

test('empty selection sends no request; crop failure alerts and permits retry', async () => {
  const { context, ids, cropper, requests, alerts } = await editor();
  context.renderPageThumbnails(ids.selector, ['page_1.png'], context.displayImage);
  await context.displayImage({ currentTarget: ids.selector.children[0] });
  context.toggleSelectionMode();
  const capture = cropper.captureSelection;
  cropper.captureSelection = () => null;
  await context.cropImage();
  assert.equal(requests.length, 0);
  assert.match(alerts.at(-1), /nonempty region/);
  cropper.captureSelection = capture;
  context.fetch = async () => ({ ok: false, status: 502, json: async () => ({ detail: { message: 'Translation unavailable' } }) });
  await context.cropImage();
  assert.equal(alerts.at(-1), 'Translation unavailable');
  assert.equal(ids.cropBtn.disabled, false);
});

test('crop refresh targets the exact page even when page_10 precedes page_1, and tolerates a missing tab', async () => {
  const { context, ids, requests } = await editor();
  context.renderPageThumbnails(ids.selector, ['page_10.png', 'page_1.png'], context.displayImage);
  const tenth = ids.selector.children[0];
  const first = ids.selector.children[1];
  const tenthSrc = tenth.dataset.src;
  await context.displayImage({ currentTarget: first });
  context.toggleSelectionMode();
  await context.cropImage();
  assert.equal(tenth.dataset.src, tenthSrc);
  const payload = JSON.parse(requests.at(-1).options.body);
  assert.equal(payload.x, 10);
  assert.equal(payload.secondY, 60);
  assert.match(first.querySelector('img').src, /^\/saved_pages\/page_1\.png\?t=/);
  ids.selector.innerHTML = '';
  await context.cropImage();
});

test('stale page loads cannot replace the current page dimensions', async () => {
  const { context, ids, cropper } = await editor();
  const first = deferred();
  const second = deferred();
  cropper.loadImage = (src) => src === 'first' ? first.promise : second.promise;
  const older = context.displayImage({ currentTarget: { dataset: { src: 'first' } } });
  const newer = context.displayImage({ currentTarget: { dataset: { src: 'second' } } });
  second.resolve({ naturalWidth: 500, naturalHeight: 2000 });
  await newer;
  first.resolve({ naturalWidth: 2000, naturalHeight: 500 });
  await older;
  assert.equal(ids.displayImage.style.height, '600px');
  assert.equal(ids.displayImage.style.width, '150px');
});

test('failed page load restores the empty editor; resize refits current image', async () => {
  const { context, ids, cropper, resize, stage, alerts } = await editor();
  await context.displayImage({ currentTarget: { dataset: { src: 'page' } } });
  stage.clientHeight = 300;
  resize();
  assert.equal(ids.displayImage.style.height, '300px');
  cropper.loadImage = async () => { throw Error('Broken image'); };
  await context.displayImage({ currentTarget: { dataset: { src: 'broken' } } });
  assert.deepEqual(ids.displayImage.style, {});
  assert.equal(ids.cropBtn.disabled, true);
  assert.equal(alerts.at(-1), 'Broken image');
});

test('compile error preserves the upload reminder and always permits retry', async () => {
  const { context, ids, alerts } = await editor();
  context.fetch = async () => ({ ok: false, status: 400, json: async () => ({ detail: { code: 'NO_IMAGES', message: 'Upload first' } }) });
  await context.compilePdf();
  assert.equal(alerts.at(-1), 'Upload first');
  assert.equal(ids.compileBtn.disabled, false);
  context.fetch = async () => ({ ok: true, blob: async () => ({ size: 123, type: 'application/pdf' }) });
  const result = await context.compilePdf();
  assert.equal(result.size, 123);
});

async function iframe() {
  const canvas = { disabled: true, getBoundingClientRect: () => ({ left: 10, top: 20 }) };
  const selection = { hidden: true, x: 0, y: 0, width: 0, height: 0,
    $reset() { this.x = this.y = this.width = this.height = 0; } };
  const image = new Element();
  image.getBoundingClientRect = () => ({ left: -90, top: -180, width: 1000, height: 800 });
  image.$ready = async () => ({ naturalWidth: 2000, naturalHeight: 1600 });
  image.$resetTransform = () => {};
  image.$center = () => {};
  const window = {};
  const elements = { 'cropper-canvas': canvas, 'cropper-image': image, 'cropper-selection': selection };
  const context = vm.createContext({ window, document: { querySelector: (tag) => elements[tag] } });
  // Replace only the network import: execute the real iframe geometry/lifecycle code.
  vm.runInContext(iframeSource.replace(/import\('https:[^']+'\)/, 'Promise.resolve()'), context);
  await window.loadImage('/saved_pages/page_1.png');
  window.setSelectionEnabled(true);
  return { window, canvas, image, selection };
}

test('crop coordinates follow actual image pan and zoom rather than the original iframe ratio', async () => {
  const { window, selection } = await iframe();
  Object.assign(selection, { hidden: false, x: 80, y: 60, width: 100, height: 50 });
  const crop = window.captureSelection();
  assert.equal(crop.x, 360);
  assert.equal(crop.y, 520);
  assert.equal(crop.secondX, 560);
  assert.equal(crop.secondY, 620);
});

test('hidden, zero-area, nonfinite and out-of-image crop selections are rejected', async () => {
  const { window, selection } = await iframe();
  assert.equal(window.captureSelection(), null);
  Object.assign(selection, { hidden: false, x: 0, y: 0, width: 0, height: 10 });
  assert.equal(window.captureSelection(), null);
  Object.assign(selection, { x: NaN, width: 20 });
  assert.equal(window.captureSelection(), null);
  Object.assign(selection, { x: -101, y: 0, width: 20, height: 20 });
  assert.equal(window.captureSelection(), null);
  Object.assign(selection, { x: 890, y: 600, width: 20, height: 10 });
  assert.equal(window.captureSelection(), null);
});

test('cropper locks unsupported rotation/skew, resets selections on fit, and invalidates a cleared image', async () => {
  const { window, image, selection } = await iframe();
  assert.equal(image.rotatable, false);
  assert.equal(image.skewable, false);
  Object.assign(selection, { hidden: false, x: 1, y: 1, width: 20, height: 20 });
  window.fitImage();
  assert.equal(selection.hidden, true);
  const pending = deferred();
  image.$ready = () => pending.promise;
  const loading = window.loadImage('new');
  await settle();
  window.clearImage();
  pending.resolve({ naturalWidth: 500, naturalHeight: 500 });
  assert.equal(await loading, null);
  assert.equal(window.captureSelection(), null);
});
