const canvas = document.querySelector('cropper-canvas');
const image = document.querySelector('cropper-image');
const selection = document.querySelector('cropper-selection');
let loadedImage = null;
let loadRevision = 0;

// Expose readiness even when the CDN is slow or fails, so the parent can report it.
window.cropperReady = import('https://unpkg.com/cropperjs@2.0.0-beta.4/dist/cropper.min.js').then(() => {
    canvas.disabled = true;
    // The server edits axis-aligned rectangles, so rotation/skew would be misleading.
    image.rotatable = false;
    image.skewable = false;
});
window.cropperReady.catch(() => {}); // The parent displays the error.

function captureSelection() {
    if (!loadedImage || selection.hidden || canvas.disabled) return null;
    const { x, y, width, height } = selection;
    const canvasRect = canvas.getBoundingClientRect();
    const imageRect = image.getBoundingClientRect();
    if (![x, y, width, height, imageRect.width, imageRect.height].every(Number.isFinite)
        || width <= 0 || height <= 0 || imageRect.width <= 0 || imageRect.height <= 0) return null;

    // Selection coordinates are in canvas pixels. Account for image pan and zoom
    // before converting into the original image's pixel coordinates.
    const scaleX = loadedImage.naturalWidth / imageRect.width;
    const scaleY = loadedImage.naturalHeight / imageRect.height;
    const left = (canvasRect.left + x - imageRect.left) * scaleX;
    const top = (canvasRect.top + y - imageRect.top) * scaleY;
    const right = left + width * scaleX;
    const bottom = top + height * scaleY;
    const epsilon = 0.01; // Allow subpixel layout rounding at the page edge.
    if (left < -epsilon || top < -epsilon || right > loadedImage.naturalWidth + epsilon
        || bottom > loadedImage.naturalHeight + epsilon) return null;

    return {
        x: Math.max(0, left),
        y: Math.max(0, top),
        secondX: Math.min(loadedImage.naturalWidth, right),
        secondY: Math.min(loadedImage.naturalHeight, bottom)
    };
}

function resetSelection() {
    selection.$reset();
    selection.hidden = true;
}

window.loadImage = async (src) => {
    const revision = ++loadRevision;
    loadedImage = null;
    await window.cropperReady;
    if (revision !== loadRevision) return null;
    resetSelection();
    image.setAttribute('src', src);
    const original = await image.$ready();
    if (revision !== loadRevision) return null;
    loadedImage = original;
    window.fitImage();
    return original;
};

window.clearImage = () => {
    ++loadRevision;
    loadedImage = null;
    image.setAttribute('src', '');
    resetSelection();
    canvas.disabled = true;
};

window.fitImage = () => {
    if (!loadedImage) return;
    image.$resetTransform();
    image.$center('contain');
    resetSelection();
};

window.setSelectionEnabled = (enabled) => { canvas.disabled = !enabled; };
window.captureSelection = captureSelection;
