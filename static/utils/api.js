async function request(path, options) {
  // Use the origin serving the editor, including its host and port.
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    const message = typeof detail === 'string' ? detail : detail?.message;
    const error = new Error(message || `Server responded with status: ${response.status}`);
    error.code = detail?.code;
    throw error;
  }
  return response;
}

export async function uploadFileApi(formData) {
  const response = await request('/uploadfiles/', {
    method: 'POST',
    body: formData,
  });
  return await response.json();
}

export async function cropImageApi(dataObj) {
  const response = await request('/cropimage/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dataObj),
  });
  return await response.json();
}

export async function deleteFilesApi() {
  const response = await request('/deletefiles/', {
    method: 'DELETE',
  });
  return await response.json();
}

export async function compilePdfApi() {
  const response = await request('/compilepdf/', {
    method: 'POST',
  });
  // The endpoint returns the compiled PDF as a file; we only need to confirm
  // it was built, so read it as a blob to report its size rather than saving it.
  const blob = await response.blob();
  return { size: blob.size, type: blob.type };
}
