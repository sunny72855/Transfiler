import { uploadFileApi, cropImageApi, deleteFilesApi, compilePdfApi } from './utils/api.js';
import { updateIframeDimensions, renderPageThumbnails } from './utils/imageDisplay.js';
import { getActiveImagePath, buildCropPayload } from './utils/cropHandler.js';

const imageDisplayer = document.getElementById('displayImage');
const iframeWindow = imageDisplayer.contentWindow;

let relativeRatio = 1;

let isSelectionModeActive = false;
let isDeleting = false;
let isUploading = false;
let croppingProgress = false;
let isCompiling = false;

document.getElementById('uploadBtn').addEventListener('click', uploadFile);
document.getElementById('clearBtn').addEventListener('click', deleteFiles);
document.getElementById('compileBtn').addEventListener('click', compilePdf);
document.getElementById('toggleModeBtn').addEventListener('click', toggleSelectionMode);
document.getElementById('cropBtn').addEventListener('click', cropImage);

async function uploadFile() {
    if (isUploading) {
        console.log("Your files are getting uploaded!");
        return;
    }

    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    isUploading = true;
    try {
        const result = await uploadFileApi(formData);
        const selectorDiv = document.getElementById('selector');
        renderPageThumbnails(selectorDiv, result.images, displayImage);
    } catch (error) {
        console.error('Failed to upload file:', error);
    } finally {
        isUploading = false;
    }
}

// Remember to write a catch statement for catching nullPointer for activeTab query selector
async function cropImage() {
    if (croppingProgress) {
        console.log("Please wait for image processing to finish!");
        return;
    }
    if (!isSelectionModeActive) {
        console.warn("Selection mode is not active. Activate it first.");
        return;
    }

    const selection = iframeWindow.captureSelection();
    if (!selection) return console.error("Failed to capture selection.");

    const { imageElement, imageDir } = getActiveImagePath(imageDisplayer);
    if (!imageDir) return console.error("Could not determine the active image path.");

    const payload = buildCropPayload(selection, relativeRatio, imageDir);

    croppingProgress = true;
    try {
        const result = await cropImageApi(payload);
        if (result.status === "success") {
            const baseUrl = imageDir.split('?')[0];
            const freshUrl = `${baseUrl}?t=${Date.now()}`
            imageElement.setAttribute('src', freshUrl);

            const activeTab = document.querySelector(`[data-src^="${baseUrl}"]`);
            const image = activeTab.querySelector('img');

            console.log(activeTab);
            image.src = freshUrl;
            activeTab.dataset.src = freshUrl;
        }
    } finally {
        croppingProgress = false;
    }
}

async function deleteFiles() {
    if (isDeleting) {
        console.log("Files are already deleting!");
        return;
    }

    try {
        isDeleting = true;
        const result = await deleteFilesApi();
        document.getElementById('selector').innerHTML = "";
        return result;
    } catch (error) {
        console.error('Failed to delete files:', error);
    } finally {
        isDeleting = false;
    }
}

async function compilePdf() {
    if (isCompiling) {
        console.log("A PDF is already being compiled!");
        return;
    }

    try {
        isCompiling = true;
        const result = await compilePdfApi();
        console.log(`PDF compiled successfully: ${result.size} bytes, type ${result.type}`);
        return result;
    } catch (error) {
        console.error('Failed to compile PDF:', error);
    } finally {
        isCompiling = false;
    }
}

function displayImage(event) {
    const iframeDocument = imageDisplayer.contentDocument;
    const imageElement = iframeDocument.querySelector('cropper-image');
    const src = event.currentTarget.dataset.src;

    console.log(src);

    if (!imageElement) return console.error('cropper-image not found in iframe yet');

    const img = new Image();
    img.onload = () => {
        relativeRatio = updateIframeDimensions(imageDisplayer, img, src);
    };

    const baseUrl = src.split('?')[0];
    const freshUrl = `${baseUrl}?t=${Date.now()}`

    img.src = freshUrl;
    imageElement.setAttribute('src', freshUrl);
}

function toggleSelectionMode() {
    isSelectionModeActive = !isSelectionModeActive;
    const toggleBtn = document.getElementById('toggleModeBtn');

    toggleBtn.innerText = isSelectionModeActive ? "Selection Mode: ON" : "Selection Mode: OFF";
    toggleBtn.classList.toggle('active', isSelectionModeActive);
    iframeWindow.toggleEnable();
}