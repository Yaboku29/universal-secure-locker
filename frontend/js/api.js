async function callApi(method, ...args) {
  if (!window.pywebview?.api) {
    await new Promise((resolve, reject) => {
      const timeout = window.setTimeout(
        () => reject(new Error("Koneksi ke aplikasi Python tidak tersedia.")),
        10000,
      );
      window.addEventListener(
        "pywebviewready",
        () => {
          window.clearTimeout(timeout);
          resolve();
        },
        { once: true },
      );
    });
  }

  const apiMethod = window.pywebview?.api?.[method];
  if (typeof apiMethod !== "function") {
    throw new Error(`Fungsi aplikasi "${method}" tidak tersedia.`);
  }
  return apiMethod(...args);
}

function showMessage(element, message, kind = "") {
  element.textContent = message;
  element.classList.toggle("is-error", kind === "error");
  element.classList.toggle("is-success", kind === "success");
}