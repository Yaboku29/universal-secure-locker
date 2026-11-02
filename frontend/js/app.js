const $ = (selector) => document.querySelector(selector);

function setPill(element, ready) {
  element.textContent = ready ? "Terdaftar" : "Belum terdaftar";
  element.classList.toggle("is-ready", ready);
}

async function initializeAccessPage() {
  const cameraButton = $("#camera-button");
  const captureButton = $("#capture-button");
  const finishFaceButton = $("#finish-face-button");
  const registerUsbButton = $("#register-usb-button");
  const refreshUsbButton = $("#refresh-usb-button");
  const unlockButton = $("#unlock-button");
  const preview = $("#camera-preview");
  const placeholder = $("#camera-placeholder");
  const usbSelect = $("#usb-select");
  const faceMessage = $("#face-message");
  const usbMessage = $("#usb-message");
  const loginMessage = $("#login-message");
  let cameraRunning = false;
  let frameTimer = null;
  let frameRequestRunning = false;
  let enrolledSampleCount = 0;

  async function refreshStatus() {
    const status = await callApi("get_status");
    setPill($("#face-status"), status.face_registered);
    setPill($("#usb-status"), status.usb_registered);
    finishFaceButton.disabled =
      status.face_registered || enrolledSampleCount < 12;
    captureButton.disabled = status.face_registered || !cameraRunning;
    registerUsbButton.disabled = status.usb_registered || !usbSelect.value;
    unlockButton.disabled = !(status.face_registered && status.usb_registered);
    return status;
  }

  async function refreshUsbDrives() {
    refreshUsbButton.disabled = true;
    try {
      const drives = await callApi("list_usb_drives");
      usbSelect.replaceChildren();
      if (drives.length === 0) {
        usbSelect.add(new Option("Tidak ada USB removable terdeteksi", ""));
      } else {
        usbSelect.add(new Option("Pilih USB Flashdisk", ""));
        for (const drive of drives) {
          usbSelect.add(new Option(drive.label, drive.id));
        }
      }
      registerUsbButton.disabled = !usbSelect.value;
      showMessage(
        usbMessage,
        drives.length
          ? `${drives.length} drive USB removable ditemukan.`
          : "Sambungkan flashdisk, lalu perbarui daftar.",
        drives.length ? "success" : "",
      );
    } catch (error) {
      showMessage(usbMessage, error.message, "error");
    } finally {
      refreshUsbButton.disabled = false;
    }
  }

  async function startCamera() {
    cameraButton.disabled = true;
    try {
      const message = await callApi("start_camera");
      cameraRunning = true;
      cameraButton.textContent = "Webcam aktif";
      captureButton.disabled = (await callApi("get_status")).face_registered;
      preview.hidden = false;
      placeholder.hidden = true;
      showMessage(faceMessage, message, "success");
      frameTimer = window.setInterval(async () => {
        if (frameRequestRunning) return;
        frameRequestRunning = true;
        try {
          preview.src = await callApi("camera_frame");
        } catch (error) {
          window.clearInterval(frameTimer);
          cameraRunning = false;
          captureButton.disabled = true;
          showMessage(faceMessage, error.message, "error");
        } finally {
          frameRequestRunning = false;
        }
      }, 250);
      return true;
    } catch (error) {
      showMessage(faceMessage, error.message, "error");
      cameraButton.disabled = false;
      return false;
    }
  }

  cameraButton.addEventListener("click", startCamera);
  captureButton.addEventListener("click", async () => {
    captureButton.disabled = true;
    try {
      const result = await callApi("capture_face_sample");
      enrolledSampleCount = result.count;
      $("#sample-count").textContent = `${result.count}/${result.required}`;
      $("#sample-progress").style.width =
        `${(result.count / result.required) * 100}%`;
      finishFaceButton.disabled = result.count < result.required;
      showMessage(
        faceMessage,
        `Sampel ${result.count} dari ${result.required} berhasil diambil. Ubah sedikit posisi wajah untuk sampel berikutnya.`,
        "success",
      );
    } catch (error) {
      showMessage(faceMessage, error.message, "error");
    } finally {
      captureButton.disabled = !cameraRunning;
    }
  });

  finishFaceButton.addEventListener("click", async () => {
    finishFaceButton.disabled = true;
    try {
      const message = await callApi("finish_face_enrollment");
      showMessage(faceMessage, message, "success");
      await refreshStatus();
    } catch (error) {
      showMessage(faceMessage, error.message, "error");
      finishFaceButton.disabled = false;
    }
  });

  refreshUsbButton.addEventListener("click", refreshUsbDrives);
  usbSelect.addEventListener("change", () => {
    registerUsbButton.disabled = !usbSelect.value;
  });

  registerUsbButton.addEventListener("click", async () => {
    if (!usbSelect.value) return;
    registerUsbButton.disabled = true;
    try {
      const message = await callApi("register_usb_key", usbSelect.value);
      showMessage(usbMessage, message, "success");
      await refreshStatus();
    } catch (error) {
      showMessage(usbMessage, error.message, "error");
      registerUsbButton.disabled = !usbSelect.value;
    }
  });

  unlockButton.addEventListener("click", async () => {
    unlockButton.disabled = true;
    $("#usb-check").textContent = "…";
    $("#face-check").textContent = "…";
    showMessage(loginMessage, "Memeriksa USB Flashdisk…");
    try {
      if (!cameraRunning && !(await startCamera())) {
        showMessage(loginMessage, "Webcam perlu aktif untuk memverifikasi wajah.", "error");
        return;
      }
      const usbVerified = await callApi("verify_usb");
      if (!usbVerified) {
        $("#usb-check").textContent = "×";
        $("#usb-check").classList.remove("is-ready");
        $("#face-check").textContent = "—";
        showMessage(
          loginMessage,
          "Kunci USB tidak ditemukan. Sambungkan flashdisk yang telah didaftarkan.",
          "error",
        );
        return;
      }
      $("#usb-check").textContent = "✓";
      $("#usb-check").classList.add("is-ready");
      showMessage(loginMessage, "USB cocok. Memeriksa wajah melalui webcam…");

      const faceResult = await callApi("verify_face");
      $("#face-check").textContent = faceResult.verified ? "✓" : "×";
      $("#face-check").classList.toggle("is-ready", faceResult.verified);
      if (!faceResult.verified) {
        showMessage(loginMessage, faceResult.message, "error");
        return;
      }

      await callApi("complete_authentication");
      showMessage(loginMessage, "Kedua kunci cocok. Membuka aplikasi…", "success");
      window.location.replace("dashboard.html");
    } catch (error) {
      $("#face-check").textContent = "×";
      showMessage(loginMessage, error.message, "error");
    } finally {
      unlockButton.disabled = false;
    }
  });

  try {
    await refreshStatus();
    await refreshUsbDrives();
  } catch (error) {
    showMessage(loginMessage, error.message, "error");
  }
}

async function initializeDashboard() {
  try {
    if (!(await callApi("is_authenticated"))) {
      window.location.replace("index.html");
      return;
    }
  } catch (error) {
    window.alert(error.message);
    window.location.replace("index.html");
    return;
  }

  $("#logout-button").addEventListener("click", async () => {
    try {
      await callApi("logout");
      window.location.replace("index.html");
    } catch (error) {
      window.alert(error.message);
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "access") initializeAccessPage();
  if (page === "dashboard") initializeDashboard();
});