const $ = (selector) => document.querySelector(selector);

function guideClosure(message) {
  const dialogue = $("#closure-dialogue");
  if (dialogue) dialogue.textContent = message;

  const logMessage = window.pywebview?.api?.log_frontend_message;
  if (typeof logMessage === "function") {
    try {
      Promise.resolve(logMessage(message)).catch((error) => {
        console.error("Closure message could not be written to the terminal log.", error);
      });
    } catch (error) {
      console.error("Closure message could not be written to the terminal log.", error);
    }
  } else {
    console.info("[Closure]", message);
  }
}

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
    finishFaceButton.textContent = status.face_registered
      ? "Wajah berhasil didaftarkan"
      : enrolledSampleCount < 12
        ? `Daftarkan wajah — ambil ${12 - enrolledSampleCount} sampel lagi`
        : "Daftarkan wajah sekarang";
    captureButton.disabled = status.face_registered || !cameraRunning;
    registerUsbButton.disabled = status.usb_registered || !usbSelect.value;
    registerUsbButton.textContent = status.usb_registered
      ? "USB berhasil didaftarkan"
      : "Daftarkan USB sebagai kunci";
    unlockButton.disabled = !(status.face_registered && status.usb_registered);

    if (status.face_registered && status.usb_registered) {
      guideClosure("Kedua kunci sudah terdaftar! Sambungkan USB, aktifkan webcam, lalu tekan Verifikasi dan buka.");
    } else if (status.face_registered) {
      guideClosure("Wajah sudah terdaftar. Sekarang sambungkan USB, tekan tombol ↻, pilih flashdisk, lalu daftarkan sebagai kunci.");
    } else if (status.usb_registered) {
      guideClosure("USB sudah terdaftar. Aktifkan webcam, ambil 12 sampel wajah, lalu tekan Daftarkan wajah sekarang.");
    } else {
      guideClosure("Halo! Saya Closure, pemandu brankas ini. Mulai dengan mengaktifkan webcam dan mengambil 12 sampel wajah.");
    }
    return status;
  }

  async function refreshUsbDrives(manualRefresh = false) {
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
        drives.length && usbSelect.value
          ? `${usbSelect.selectedOptions[0].textContent} dipilih. Tekan "Daftarkan USB sebagai kunci" untuk melanjutkan.`
          : drives.length
            ? `${drives.length} drive USB ditemukan. Pilih flashdisk yang ingin didaftarkan.`
          : "Sambungkan flashdisk, lalu perbarui daftar.",
        drives.length && usbSelect.value ? "success" : "",
      );
      if (manualRefresh && drives.length && !usbSelect.value) {
        guideClosure("USB terdeteksi! Pilih flashdisk yang ingin dijadikan kunci. Tenang, isinya tidak akan diformat atau dihapus.");
      } else if (manualRefresh && !drives.length) {
        guideClosure("Saya belum melihat USB removable. Sambungkan flashdisk, lalu tekan tombol ↻ untuk mencoba lagi.");
      }
    } catch (error) {
      showMessage(usbMessage, error.message, "error");
      guideClosure(error.message);
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
      guideClosure("Webcam aktif. Posisikan wajah di tengah pratinjau, lalu tekan Ambil sampel. Ulangi 12 kali dengan sedikit perubahan sudut.");
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
          guideClosure(error.message);
        } finally {
          frameRequestRunning = false;
        }
      }, 250);
      return true;
    } catch (error) {
      showMessage(faceMessage, error.message, "error");
      guideClosure(error.message);
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
      finishFaceButton.textContent =
        result.count >= result.required
          ? "Daftarkan wajah sekarang"
          : `Daftarkan wajah — ambil ${result.required - result.count} sampel lagi`;
      finishFaceButton.disabled = result.count < result.required;
      showMessage(
        faceMessage,
        `Sampel ${result.count} dari ${result.required} berhasil diambil. Ubah sedikit posisi wajah untuk sampel berikutnya.`,
        "success",
      );
      guideClosure(
        result.count >= result.required
          ? "Sampel wajah lengkap! Tekan Daftarkan wajah sekarang untuk menyimpan pendaftaran."
          : `Sampel ${result.count} dari ${result.required} tersimpan. Ubah sedikit sudut wajah, lalu ambil sampel berikutnya.`,
      );
    } catch (error) {
      showMessage(faceMessage, error.message, "error");
      guideClosure(error.message);
    } finally {
      captureButton.disabled =
        !cameraRunning || enrolledSampleCount >= 12;
    }
  });

  finishFaceButton.addEventListener("click", async () => {
    finishFaceButton.disabled = true;
    try {
      const message = await callApi("finish_face_enrollment");
      showMessage(faceMessage, message, "success");
      guideClosure("Wajah berhasil didaftarkan. Sekarang pilih dan daftarkan USB sebagai kunci kedua.");
      await refreshStatus();
    } catch (error) {
      showMessage(faceMessage, error.message, "error");
      guideClosure(error.message);
      finishFaceButton.disabled = false;
    }
  });

  refreshUsbButton.addEventListener("click", () => refreshUsbDrives(true));
  usbSelect.addEventListener("change", () => {
    registerUsbButton.disabled = !usbSelect.value;
    if (usbSelect.value) {
      showMessage(
        usbMessage,
        `${usbSelect.selectedOptions[0].textContent} dipilih. Tekan tombol "Daftarkan USB sebagai kunci" di bawah.`,
        "success",
      );
      guideClosure("Flashdisk sudah dipilih. Tekan Daftarkan USB sebagai kunci; saya akan meminta konfirmasi sebelum membuat file token.");
    }
  });

  registerUsbButton.addEventListener("click", async () => {
    if (!usbSelect.value) return;
    const drive = usbSelect.selectedOptions[0].textContent;
    const accepted = window.confirm(
      `Daftarkan ${drive} sebagai kunci USB?\n\n` +
        "USB TIDAK akan diformat dan file yang sudah ada tidak dihapus. " +
        "Aplikasi hanya membuat satu file token kecil bernama " +
        "USL-USB-KEY.txt di folder utama USB tersebut.",
    );
    if (!accepted) return;

    registerUsbButton.disabled = true;
    try {
      const message = await callApi("register_usb_key", usbSelect.value);
      showMessage(usbMessage, message, "success");
      guideClosure("Kunci USB berhasil didaftarkan. Setelah wajah dan USB berstatus Terdaftar, tekan Verifikasi dan buka.");
      await refreshStatus();
    } catch (error) {
      showMessage(usbMessage, error.message, "error");
      guideClosure(error.message);
      registerUsbButton.disabled = !usbSelect.value;
    }
  });

  unlockButton.addEventListener("click", async () => {
    unlockButton.disabled = true;
    $("#usb-check").textContent = "…";
    $("#face-check").textContent = "…";
    showMessage(loginMessage, "Memeriksa USB Flashdisk…");
    guideClosure("Saya sedang memeriksa token pada USB. Pastikan flashdisk yang didaftarkan terhubung.");
    try {
      if (!cameraRunning && !(await startCamera())) {
        showMessage(loginMessage, "Webcam perlu aktif untuk memverifikasi wajah.", "error");
        guideClosure("Webcam belum siap. Aktifkan kamera agar saya bisa memeriksa wajah Anda.");
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
        guideClosure("Token USB belum cocok. Sambungkan flashdisk yang didaftarkan, lalu coba lagi.");
        return;
      }
      $("#usb-check").textContent = "✓";
      $("#usb-check").classList.add("is-ready");
      showMessage(loginMessage, "USB cocok. Memeriksa wajah melalui webcam…");
      guideClosure("USB cocok! Sekarang lihat ke kamera agar saya dapat memeriksa wajah Anda.");

      const faceResult = await callApi("verify_face");
      $("#face-check").textContent = faceResult.verified ? "✓" : "×";
      $("#face-check").classList.toggle("is-ready", faceResult.verified);
      if (!faceResult.verified) {
        showMessage(loginMessage, faceResult.message, "error");
        guideClosure("Wajah belum cocok. Atur pencahayaan, lihat ke kamera, lalu coba verifikasi lagi.");
        return;
      }

      await callApi("complete_authentication");
      showMessage(loginMessage, "Kedua kunci cocok. Membuka aplikasi…", "success");
      guideClosure("Berhasil! Kedua kunci cocok. Selamat datang di brankas Anda.");
      window.location.replace("dashboard.html");
    } catch (error) {
      $("#face-check").textContent = "×";
      showMessage(loginMessage, error.message, "error");
      guideClosure(error.message);
    } finally {
      unlockButton.disabled = false;
    }
  });

  try {
    await refreshStatus();
    await refreshUsbDrives();
  } catch (error) {
    showMessage(loginMessage, error.message, "error");
    guideClosure(error.message);
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
    guideClosure(error.message);
    window.location.replace("index.html");
    return;
  }

  guideClosure("Selamat datang! Akses Anda sudah terverifikasi. Pilih modul brankas yang tersedia; fitur penyimpanan masih dalam pengembangan.");

  $("#logout-button").addEventListener("click", async () => {
    try {
      await callApi("logout");
      window.location.replace("index.html");
    } catch (error) {
      window.alert(error.message);
      guideClosure(error.message);
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "access") initializeAccessPage();
  if (page === "dashboard") initializeDashboard();
});