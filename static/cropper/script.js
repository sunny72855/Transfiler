import 'https://unpkg.com/cropperjs@2.0.0-beta.4/dist/cropper.min.js';

const canva = document.querySelector('cropper-canvas');
const image = document.querySelector('cropper-image');
const selection = document.querySelector('cropper-selection');
let enabled = false;
canva.disabled = true; // Start with the cropper disabled

function captureSelection() {
    if (!selection) {
        console.error('No selection element found');
        return null;
    }

    const x = Number(selection.getAttribute('x'));
    const y = Number(selection.getAttribute('y'));
    const width = Number(selection.getAttribute('width'));
    const height = Number(selection.getAttribute('height'));

    return {
        x: x,
        y: y,
        secondX: x + width,
        secondY: y + height
    };
}

function toggleEnable() {
    if (enabled) {
        enabled = false;
        canva.disabled = true;
        return;
    }

    enabled = true;
    canva.disabled = false;
};

window.toggleEnable = toggleEnable;
window.captureSelection = captureSelection;