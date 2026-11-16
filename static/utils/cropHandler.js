export function getActiveImagePath(imageDisplayer) {
  const iframeDocument = imageDisplayer.contentDocument;
  const imageElement = iframeDocument?.querySelector('cropper-image');
  return {
    imageElement,
    imageDir: imageElement ? imageElement.getAttribute('src') : ''
  };
}

export function buildCropPayload(selection, imageDir) {
  return {
    x: selection.x,
    y: selection.y,
    secondX: selection.secondX,
    secondY: selection.secondY,
    'image-dir': imageDir
  };
}
