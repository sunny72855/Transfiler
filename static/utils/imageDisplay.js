export function updateIframeDimensions(imageDisplayer, img, src) {
  const ratio = img.naturalWidth / img.naturalHeight;
  const maxAvailableWidth = imageDisplayer.parentElement.clientWidth;

  let targetWidth = imageDisplayer.clientHeight * ratio;
  let targetHeight = imageDisplayer.clientHeight;

  if (targetWidth > maxAvailableWidth) {
    targetWidth = maxAvailableWidth;
    targetHeight = targetWidth / ratio;
  }

  imageDisplayer.style.width = `${targetWidth}px`;
  imageDisplayer.style.height = `${targetHeight}px`;

  return img.naturalHeight / targetHeight; // returns calculated relativeRatio
}

export function renderPageThumbnails(container, images, onClickHandler) {
  container.innerHTML = "";

  images.forEach((imageName, i) => {
    const newDiv = document.createElement("div");
    newDiv.classList.add("selectorStyling");
    newDiv.dataset.src = `/saved_pages/${imageName}`;
    newDiv.addEventListener("click", onClickHandler);

    newDiv.innerHTML = `
      <img src="/saved_pages/${imageName}" alt="PDF Page" class="pdf-img" />
      <h3>Page ${i + 1}</h3>
    `;
    container.append(newDiv);
  });
}