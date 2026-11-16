import { uploadFileApi, cropImageApi, deleteFilesApi, compilePdfApi } from './utils/api.js';
import { updateIframeDimensions, renderPageThumbnails } from './utils/imageDisplay.js';
import { getActiveImagePath, buildCropPayload } from './utils/cropHandler.js';

const imageDisplayer = document.getElementById('displayImage');
const selector = document.getElementById('selector');
const buttons = Object.fromEntries(['uploadBtn', 'clearBtn', 'compileBtn', 'toggleModeBtn', 'cropBtn']
    .map((id) => [id, document.getElementById(id)]));

let operation = null;
let cropperReady = false;
let activeImage = null;
let isPageLoading = false;
let isSelectionModeActive = false;
let pageRevision = 0;

buttons.uploadBtn.addEventListener('click', uploadFile);
buttons.clearBtn.addEventListener('click', deleteFiles);
buttons.compileBtn.addEventListener('click', compilePdf);
buttons.toggleModeBtn.addEventListener('click', toggleSelectionMode);
buttons.cropBtn.addEventListener('click', cropImage);

function refreshControls() {
    const busy = operation !== null;
    for (const button of Object.values(buttons)) button.disabled = busy;
    document.getElementById('fileInput').disabled = busy;
    buttons.toggleModeBtn.disabled = busy || !cropperReady || !activeImage || isPageLoading;
    buttons.cropBtn.disabled = buttons.toggleModeBtn.disabled || !isSelectionModeActive;
    selector.querySelectorAll('button').forEach((button) => { button.disabled = busy; });
    imageDisplayer.style.pointerEvents = busy ? 'none' : '';
    // Empty-state styling uses the absence of inline dimensions.
    if (!activeImage && !isPageLoading) imageDisplayer.removeAttribute('style');
    if (cropperReady) {
        imageDisplayer.contentWindow.setSelectionEnabled(!busy && !isPageLoading && isSelectionModeActive);
    }
}

function reportError(error) {
    console.error(error);
    alert(error.message || 'The operation failed. Please try again.');
}

async function runOperation(name, action) {
    // One guard covers all operations that read or change the shared pages.
    if (operation || isPageLoading) return;
    operation = name;
    refreshControls();
    try {
        return await action();
    } catch (error) {
        reportError(error);
    } finally {
        operation = null;
        refreshControls();
    }
}

function setSelectionMode(enabled) {
    isSelectionModeActive = enabled;
    buttons.toggleModeBtn.innerText = enabled ? 'Selection Mode: ON' : 'Selection Mode: OFF';
    buttons.toggleModeBtn.classList.toggle('active', enabled);
    buttons.toggleModeBtn.setAttribute('aria-pressed', String(enabled));
    refreshControls();
}

function resetEditor() {
    ++pageRevision;
    activeImage = null;
    isPageLoading = false;
    if (cropperReady) imageDisplayer.contentWindow.clearImage();
    imageDisplayer.removeAttribute('style');
    setSelectionMode(false);
}

async function uploadFile() {
    const file = document.getElementById('fileInput').files[0];
    if (!file) return;
    return runOperation('upload', async () => {
        const formData = new FormData();
        formData.append('file', file);
        const result = await uploadFileApi(formData);
        if (!Array.isArray(result.images) || result.images.some((name) => typeof name !== 'string')) {
            throw new Error('The server did not return a page list.');
        }
        resetEditor();
        renderPageThumbnails(selector, result.images, displayImage);
    });
}

async function cropImage() {
    if (operation || isPageLoading || !cropperReady || !activeImage || !isSelectionModeActive) return;
    const selection = imageDisplayer.contentWindow.captureSelection();
    if (!selection) {
        alert('Select a nonempty region entirely inside the page first.');
        return;
    }
    const { imageDir } = getActiveImagePath(imageDisplayer);
    if (!imageDir) return;
    const baseUrl = imageDir.split('?')[0];
    const payload = buildCropPayload(selection, imageDir);
    return runOperation('crop', async () => {
        const result = await cropImageApi(payload);
        if (result.status !== 'success') throw new Error(result.message || 'Image processing failed.');
        const freshUrl = `${baseUrl}?t=${Date.now()}`;
        // Exact paths avoid matching page_10 when editing page_1.
        const tab = Array.from(selector.children)
            .find((item) => item.dataset.src.split('?')[0] === baseUrl);
        if (tab) {
            tab.dataset.src = freshUrl;
            const thumbnail = tab.querySelector('img');
            if (thumbnail) thumbnail.src = freshUrl;
        }
        activeImage = await imageDisplayer.contentWindow.loadImage(freshUrl);
        if (activeImage) {
            updateIframeDimensions(imageDisplayer, activeImage);
            imageDisplayer.contentWindow.fitImage();
        }
    });
}

async function deleteFiles() {
    return runOperation('clear', async () => {
        const result = await deleteFilesApi();
        selector.innerHTML = '';
        resetEditor();
        return result;
    });
}

async function compilePdf() {
    return runOperation('compile', async () => {
        const result = await compilePdfApi();
        console.log(`PDF compiled successfully: ${result.size} bytes, type ${result.type}`);
        return result;
    });
}

async function displayImage(event) {
    if (operation) return;
    if (!cropperReady) {
        alert('The page editor is still loading. Please try again shortly.');
        return;
    }
    const revision = ++pageRevision;
    const src = event.currentTarget.dataset.src;
    activeImage = null;
    isPageLoading = true;
    setSelectionMode(false);
    try {
        const original = await imageDisplayer.contentWindow.loadImage(src);
        if (revision !== pageRevision || !original) return;
        activeImage = original;
        updateIframeDimensions(imageDisplayer, original);
        imageDisplayer.contentWindow.fitImage();
    } catch (error) {
        if (revision === pageRevision) {
            resetEditor();
            reportError(error);
        }
    } finally {
        if (revision === pageRevision) {
            isPageLoading = false;
            refreshControls();
        }
    }
}

function toggleSelectionMode() {
    if (operation || isPageLoading || !cropperReady || !activeImage) return;
    setSelectionMode(!isSelectionModeActive);
}

async function initializeCropper() {
    try {
        const ready = imageDisplayer.contentWindow.cropperReady;
        if (!ready) return; // The iframe is still on its initial about:blank document.
        await ready;
        cropperReady = true;
        resetEditor();
    } catch (error) {
        cropperReady = false;
        refreshControls();
        reportError(new Error('The page editor could not load. Check your connection and reload the page.'));
    }
}

imageDisplayer.addEventListener('load', initializeCropper);
initializeCropper();
refreshControls();

new ResizeObserver(() => {
    if (activeImage && !isPageLoading && !operation) {
        updateIframeDimensions(imageDisplayer, activeImage);
        imageDisplayer.contentWindow.fitImage();
    }
}).observe(imageDisplayer.parentElement);
