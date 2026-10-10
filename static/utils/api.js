const BASE_URL = 'http://127.0.0.1:8000';

export async function uploadFileApi(formData) {
  const response = await fetch(`${BASE_URL}/uploadfiles/`, {
    method: 'POST',
    body: formData,
  });
  return await response.json();
}

export async function cropImageApi(dataObj) {
  const response = await fetch(`${BASE_URL}/cropimage/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dataObj),
  });
  return await response.json();
}

export async function deleteFilesApi() {
  const response = await fetch(`${BASE_URL}/deletefiles/`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error(`Server responded with status: ${response.status}`);
  return await response.json();
}

export async function compilePdfApi() {
  const response = await fetch(`${BASE_URL}/compilepdf/`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error(`Server responded with status: ${response.status}`);
  // The endpoint returns the compiled PDF as a file; we only need to confirm
  // it was built, so read it as a blob to report its size rather than saving it.
  const blob = await response.blob();
  return { size: blob.size, type: blob.type };
}