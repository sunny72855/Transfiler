export function getActiveImagePath(imageDisplayer) {
  const iframeDocument = imageDisplayer.contentDocument;
  const imageElement = iframeDocument?.querySelector('cropper-image');
  return {
    imageElement,
    imageDir: imageElement ? imageElement.getAttribute('src') : ''
  };
}

export function buildCropPayload(selection, relativeRatio, imageDir) {
  return {
    x: selection.x * relativeRatio,
    y: selection.y * relativeRatio,
    secondX: selection.secondX * relativeRatio,
    secondY: selection.secondY * relativeRatio,
    'image-dir': imageDir
  };
}