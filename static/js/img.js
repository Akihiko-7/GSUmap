// Shrink photos on the phone before upload: longest side 1024 px, JPEG. Saves data and makes the AI answer faster.
export async function compress(file, max = 1024, quality = 0.8) {
  let src;
  try {
    src = await createImageBitmap(file, { imageOrientation: 'from-image' });
  } catch {
    src = await new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = URL.createObjectURL(file);
    });
  }
  const w = src.width, h = src.height, k = Math.min(1, max / Math.max(w, h));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(w * k);
  canvas.height = Math.round(h * k);
  canvas.getContext('2d').drawImage(src, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality));
}

export function showPreview(el, blob) {
  el.innerHTML = '';
  const img = document.createElement('img');
  img.src = URL.createObjectURL(blob);
  img.alt = '';
  el.appendChild(img);
}
