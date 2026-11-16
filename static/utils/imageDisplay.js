export function updateIframeDimensions(imageDisplayer, img) {
  const stage = imageDisplayer.parentElement;
  const scale = Math.min(stage.clientWidth / img.naturalWidth, stage.clientHeight / img.naturalHeight);
  if (!Number.isFinite(scale) || scale <= 0) return false;

  const targetWidth = img.naturalWidth * scale;
  const targetHeight = img.naturalHeight * scale;

  imageDisplayer.style.width = `${targetWidth}px`;
  imageDisplayer.style.height = `${targetHeight}px`;

  return true;
}

export function renderPageThumbnails(container, images, onClickHandler) {
  container.innerHTML = "";

  const revision = Date.now();
  images.forEach((imageName, i) => {
    const newDiv = document.createElement("button");
    newDiv.type = 'button';
    newDiv.classList.add("selectorStyling");
    newDiv.dataset.src = `/saved_pages/${encodeURIComponent(imageName)}?t=${revision}`;
    newDiv.addEventListener("click", onClickHandler);

    const thumbnail = document.createElement('img');
    thumbnail.src = newDiv.dataset.src;
    thumbnail.alt = `Page ${i + 1}`;
    thumbnail.classList.add('pdf-img');
    const label = document.createElement('h3');
    label.textContent = `Page ${i + 1}`;
    newDiv.append(thumbnail, label);
    container.append(newDiv);
  });
}
