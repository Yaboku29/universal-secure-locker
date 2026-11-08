const $ = (selector) => document.querySelector(selector);

function guideClosure(message) {
  const dialogue = $("#closure-dialogue");
  if (dialogue) dialogue.textContent = message;
  const accountDialogue = $("#account-closure-dialogue");
  if (accountDialogue) accountDialogue.textContent = message;

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
  const accountAuthPanel = $("#account-auth-panel");
  const accountLoginForm = $("#account-login-form");
  const accountSignupForm = $("#account-signup-form");
  const accountMessage = $("#account-message");
  const backToBiometricsButton = $("#back-to-biometrics-button");
  let cameraRunning = false;
  let frameTimer = null;
  let frameRequestRunning = false;
  let enrolledSampleCount = 0;
  let accountExists = false;

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

  function setAccountMode(mode, hasAccounts) {
    const signingUp = mode === "signup";
    accountLoginForm.hidden = signingUp;
    accountSignupForm.hidden = !signingUp;
    $("#account-login-mode").classList.toggle("is-selected", !signingUp);
    $("#account-signup-mode").classList.toggle("is-selected", signingUp);
    $("#account-auth-title").textContent = signingUp
      ? "Buat akun baru"
      : "Masuk ke akun";
    $("#account-auth-description").textContent = signingUp
      ? hasAccounts
        ? "Akun yang didaftarkan setelah akun pertama menjadi User biasa."
        : "Ini akun pertama, jadi otomatis mendapat peran Admin."
      : "Masuk dengan username dan password akun Anda.";
    $("#account-policy-note").textContent = hasAccounts
      ? "Pendaftaran mandiri membuat User biasa, bukan Admin. User mengakses file miliknya sendiri dan file yang dibagikan kepadanya. Admin dapat mengatur izin, tetapi tidak otomatis dapat membaca file akun lain."
      : "Akun pertama di database ini otomatis menjadi Admin agar dapat mengelola izin berbagi. Peran ditentukan aplikasi dan tidak bisa dipilih pada formulir. Admin pun tidak otomatis dapat membaca file akun lain.";
    $("#account-login-mode").hidden = !hasAccounts;
    $("#account-message").textContent = "";
    $("#account-message").classList.remove("is-error", "is-success");
  }

  async function enterAccountStep() {
    await callApi("complete_hardware_authentication");
    if (frameTimer !== null) {
      window.clearInterval(frameTimer);
      frameTimer = null;
    }
    cameraRunning = false;
    preview.hidden = true;
    placeholder.hidden = false;
    document.body.classList.remove("camera-preview-floating");
    $("#setup-card").hidden = true;
    $(".intro").hidden = true;
    $(".shell").classList.add("account-login-shell");
    $(".access-layout").classList.add("account-auth-layout");
    $("#two-factor-panel").hidden = true;
    accountAuthPanel.hidden = false;
    $(".environment-tag").hidden = true;
    backToBiometricsButton.hidden = false;
    $("#account-closure-guide").hidden = false;
    const accountState = await callApi("get_account_state");
    accountExists = accountState.has_accounts;
    setAccountMode(accountExists ? "login" : "signup", accountExists);
    guideClosure(
      accountExists
        ? "USB dan wajah cocok! Sekarang masukkan username dan password akun yang ingin Anda buka."
        : "USB dan wajah cocok! Belum ada akun. Buat akun pertama; akun tersebut akan menjadi admin.",
    );
  }

  async function openDashboard(account, verb) {
    const accountRole = account.is_admin ? "Admin" : "User biasa";
    showMessage(
      accountMessage,
      `${verb} sebagai ${account.username}${account.is_admin ? " (admin)" : ""}.`,
      "success",
    );
    guideClosure(`${accountRole} ${account.username} berhasil masuk. Membuka brankas dengan izin akun tersebut.`);
    window.setTimeout(() => window.location.replace("dashboard.html"), 250);
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
      document.body.classList.add("camera-preview-floating");
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
          document.body.classList.remove("camera-preview-floating");
          captureButton.disabled = true;
          showMessage(faceMessage, error.message, "error");
          guideClosure(error.message);
        } finally {
          frameRequestRunning = false;
        }
      }, 250);
      return true;
    } catch (error) {
      document.body.classList.remove("camera-preview-floating");
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

      await enterAccountStep();
    } catch (error) {
      showMessage(accountMessage, error.message, "error");
      if ($("#two-factor-panel").hidden) {
        accountAuthPanel.hidden = false;
      } else {
        $("#face-check").textContent = "×";
        showMessage(loginMessage, error.message, "error");
      }
      guideClosure(error.message);
    } finally {
      unlockButton.disabled = false;
    }
  });

  $("#account-login-mode").addEventListener("click", () => {
    setAccountMode("login", accountExists);
  });
  $("#account-signup-mode").addEventListener("click", () => {
    setAccountMode("signup", accountExists);
  });

  backToBiometricsButton.addEventListener("click", async () => {
    backToBiometricsButton.disabled = true;
    try {
      await callApi("logout");
      if (frameTimer !== null) {
        window.clearInterval(frameTimer);
        frameTimer = null;
      }
      cameraRunning = false;
      frameRequestRunning = false;
      document.body.classList.remove("camera-preview-floating");
      cameraButton.disabled = false;
      cameraButton.textContent = "Aktifkan webcam";
      preview.hidden = true;
      placeholder.hidden = false;
      $("#setup-card").hidden = false;
      $(".intro").hidden = false;
      $(".shell").classList.remove("account-login-shell");
      $(".access-layout").classList.remove("account-auth-layout");
      $("#two-factor-panel").hidden = false;
      accountAuthPanel.hidden = true;
      $(".environment-tag").hidden = false;
      backToBiometricsButton.hidden = true;
      $("#account-closure-guide").hidden = true;
      $("#usb-check").textContent = "—";
      $("#usb-check").classList.remove("is-ready");
      $("#face-check").textContent = "—";
      $("#face-check").classList.remove("is-ready");
      accountLoginForm.reset();
      accountSignupForm.reset();
      showMessage(loginMessage, "Kembali ke verifikasi biometrik. Verifikasi USB dan wajah kembali diperlukan.");
      await refreshStatus();
    } catch (error) {
      showMessage(accountMessage, error.message, "error");
      guideClosure(error.message);
    } finally {
      backToBiometricsButton.disabled = false;
    }
  });

  accountLoginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = accountLoginForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    try {
      const account = await callApi(
        "login_account",
        $("#login-username").value,
        $("#login-password").value,
      );
      await openDashboard(account, "Login");
    } catch (error) {
      showMessage(accountMessage, error.message, "error");
      guideClosure(error.message);
    } finally {
      submitButton.disabled = false;
    }
  });

  accountSignupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = accountSignupForm.querySelector('button[type="submit"]');
    const password = $("#signup-password").value;
    if (password !== $("#signup-confirm-password").value) {
      showMessage(accountMessage, "Konfirmasi password tidak sama.", "error");
      guideClosure("Konfirmasi password belum sama. Periksa kembali kedua kolom password.");
      return;
    }

    submitButton.disabled = true;
    try {
      const account = await callApi(
        "create_account",
        $("#signup-username").value,
        password,
      );
      await openDashboard(account, "Akun dibuat");
    } catch (error) {
      showMessage(accountMessage, error.message, "error");
      guideClosure(error.message);
    } finally {
      submitButton.disabled = false;
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

  const account = await callApi("get_current_account");
  $("#active-username").textContent =
    `${account.username}${account.is_admin ? " · ADMIN" : " · USER"}`;
  guideClosure(
    `Selamat datang, ${account.username}! Anda hanya akan melihat folder dan file yang dimiliki atau dibagikan khusus ke akun ini.`,
  );

  const resourceList = $("#resource-list");
  const vaultMessage = $("#vault-message");
  const uploadInput = $("#upload-file-input");
  const replaceInput = $("#replace-file-input");
  const shareDialog = $("#share-dialog");
  const previewDialog = $("#preview-dialog");
  let suspendPreviewCloseCleanup = false;
  let currentParentId = null;
  let currentFolderName = "";
  let itemToReplace = null;
  let itemToShare = null;
  let resourceToDownload = null;
  let previewObjectUrl = null;
  const auditPageSize = 20;
  let auditBlocks = [];
  let auditPage = 0;

  function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.addEventListener("load", () => {
        const result = reader.result;
        if (typeof result !== "string" || !result.includes(",")) {
          reject(new Error("File gagal dibaca."));
          return;
        }
        resolve(result.slice(result.indexOf(",") + 1));
      });
      reader.addEventListener("error", () => reject(new Error("File gagal dibaca.")));
      reader.readAsDataURL(file);
    });
  }

  function makeButton(label, callback, variant = "button-secondary") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `button ${variant}`;
    button.textContent = label;
    button.addEventListener("click", callback);
    return button;
  }

  function showVaultError(error) {
    showMessage(vaultMessage, error.message, "error");
    guideClosure(error.message);
  }

  function showFilePreview(file) {
    const binary = atob(file.content_base64);
    const bytes = Uint8Array.from(binary, (character) =>
      character.charCodeAt(0),
    );
    const blob = new Blob([bytes], { type: file.content_type });
    const isText =
      file.content_type.startsWith("text/") ||
      /^(application\/(json|xml|javascript))$/.test(file.content_type) ||
      /\.(csv|json|md|txt|xml|yaml|yml)$/i.test(file.name);
    const imagePreview = $("#preview-image");
    const documentPreview = $("#preview-frame");
    const textPreview = $("#preview-content");

    if (previewObjectUrl !== null) {
      URL.revokeObjectURL(previewObjectUrl);
      previewObjectUrl = null;
    }
    imagePreview.hidden = true;
    imagePreview.removeAttribute("src");
    documentPreview.hidden = true;
    documentPreview.removeAttribute("src");
    textPreview.hidden = false;
    textPreview.textContent = "";

    if (isText) {
      textPreview.textContent = new TextDecoder().decode(bytes);
    } else if (file.content_type.startsWith("image/")) {
      previewObjectUrl = URL.createObjectURL(blob);
      imagePreview.src = previewObjectUrl;
      imagePreview.alt = `Pratinjau ${file.name}`;
      imagePreview.hidden = false;
      textPreview.hidden = true;
    } else if (file.content_type === "application/pdf") {
      previewObjectUrl = URL.createObjectURL(blob);
      documentPreview.src = previewObjectUrl;
      documentPreview.hidden = false;
      textPreview.hidden = true;
    } else {
      textPreview.textContent =
        "Pratinjau tidak tersedia untuk jenis file ini. Gunakan tombol Unduh di bagian atas untuk menyimpan file.";
    }
    $("#preview-title").textContent = file.name;
    $("#download-password-form").hidden = true;
    $("#download-password-input").value = "";
    showMessage($("#download-message"), "");
    previewDialog.showModal();
    document.body.classList.add("file-preview-open");
  }

  async function loadVault() {
    resourceList.replaceChildren();
    $("#vault-location").textContent = currentParentId
      ? currentFolderName
      : "Folder utama";
    $("#vault-back-button").hidden = !currentParentId;

    try {
      const canCreate = await callApi("can_create_in", currentParentId);
      $("#create-folder-button").disabled = !canCreate;
      uploadInput.disabled = !canCreate;
      $("#vault-guidance").textContent = canCreate
        ? "Anda dapat menambahkan item di sini. Akses item lain tetap mengikuti izin masing-masing."
        : "Akun ini dapat melihat item di folder ini tetapi belum memiliki izin untuk membuat item baru.";

      const resources = await callApi("list_resources", currentParentId);
      if (resources.length === 0) {
        const empty = document.createElement("div");
        empty.className = "resource-empty";
        empty.textContent = "Belum ada folder atau file yang dapat diakses di lokasi ini.";
        resourceList.append(empty);
      }

      for (const resource of resources) {
        const row = document.createElement("article");
        row.className = "resource-row";
        const symbol = document.createElement("span");
        symbol.className = "resource-symbol";
        symbol.textContent = resource.kind === "folder" ? "▰" : "▧";
        symbol.setAttribute("aria-hidden", "true");

        const name = document.createElement("div");
        name.className = "resource-name";
        name.append(document.createTextNode(resource.name));
        const owner = document.createElement("small");
        owner.className = "resource-owner";
        owner.textContent = resource.is_owner
          ? "Milik Anda"
          : "Dibagikan kepada Anda";
        name.append(owner);

        const actions = document.createElement("div");
        actions.className = "resource-actions";
        if (resource.kind === "folder") {
          actions.append(
            makeButton("Buka", async () => {
              currentParentId = resource.id;
              currentFolderName = resource.name;
              await loadVault();
            }, "button-primary"),
          );
        } else {
          actions.append(
            makeButton("Lihat", async () => {
              try {
                const file = await callApi("read_resource", resource.id);
                resourceToDownload = resource;
                showFilePreview(file);
              } catch (error) {
                showVaultError(error);
              }
            }),
          );
        }

        if (resource.can_update) {
          actions.append(
            makeButton("Ubah", async () => {
              if (resource.kind === "file") {
                itemToReplace = resource;
                replaceInput.click();
                return;
              }
              const nextName = window.prompt("Nama baru:", resource.name);
              if (!nextName || nextName === resource.name) return;
              try {
                await callApi("update_resource", resource.id, nextName);
                showMessage(vaultMessage, "Nama folder berhasil diperbarui.", "success");
                await loadVault();
              } catch (error) {
                showVaultError(error);
              }
            }),
          );
        }

        if (resource.can_manage) {
          actions.append(
            makeButton("Atur akses", async () => openSharingDialog(resource)),
          );
        }
        row.append(symbol, name, actions);
        resourceList.append(row);
      }
      showMessage(vaultMessage, `${resources.length} item dapat diakses di sini.`);
    } catch (error) {
      showVaultError(error);
    }
  }

  function renderAuditChain() {
    const auditContainer = $("#audit-chain");
    const pagination = $("#audit-pagination");
    const startIndex = auditPage * auditPageSize;
    const visibleBlocks = auditBlocks.slice(
      startIndex,
      startIndex + auditPageSize,
    );
    auditContainer.replaceChildren();

    for (const block of visibleBlocks) {
      const card = document.createElement("article");
      card.className = "audit-block";

      const heading = document.createElement("div");
      heading.className = "audit-block-heading";
      const title = document.createElement("h3");
      title.textContent = `Blok #${block.index}`;
      const timestamp = document.createElement("time");
      timestamp.dateTime = block.timestamp;
      timestamp.textContent = block.timestamp;
      heading.append(title, timestamp);

      const action = document.createElement("p");
      action.className = "audit-action";
      action.textContent = block.action_data;

      const hashes = document.createElement("dl");
      hashes.className = "audit-hashes";
      for (const [label, value] of [
        ["Previous hash", block.previous_hash],
        ["SHA-256 hash", block.hash],
      ]) {
        const row = document.createElement("div");
        const term = document.createElement("dt");
        term.textContent = label;
        const description = document.createElement("dd");
        const code = document.createElement("code");
        code.textContent = value;
        description.append(code);
        row.append(term, description);
        hashes.append(row);
      }

      card.append(heading, action, hashes);
      auditContainer.append(card);
    }

    const endIndex = Math.min(startIndex + visibleBlocks.length, auditBlocks.length);
    $("#audit-page-label").textContent = auditBlocks.length
      ? `Blok ${startIndex + 1}–${endIndex} dari ${auditBlocks.length}`
      : "Belum ada blok";
    $("#audit-previous-button").disabled = auditPage === 0;
    $("#audit-next-button").disabled = endIndex >= auditBlocks.length;
    pagination.hidden = auditBlocks.length <= auditPageSize;
  }

  async function loadAuditChain() {
    const refreshButton = $("#refresh-audit-button");
    const integrity = $("#audit-integrity");
    refreshButton.disabled = true;
    integrity.dataset.state = "checking";
    integrity.textContent = "Memeriksa integritas…";
    showMessage($("#audit-message"), "Memuat blok audit…");

    try {
      const [chain, isValid] = await Promise.all([
        callApi("get_audit_chain"),
        callApi("is_chain_valid"),
      ]);
      if (!Array.isArray(chain) || typeof isValid !== "boolean") {
        throw new Error("Respons audit blockchain tidak valid.");
      }
      auditBlocks = chain;
      auditPage = Math.min(
        auditPage,
        Math.max(0, Math.ceil(auditBlocks.length / auditPageSize) - 1),
      );
      integrity.dataset.state = isValid ? "valid" : "invalid";
      integrity.textContent = isValid
        ? "Integritas valid"
        : "Integritas tidak valid";
      $("#audit-block-count").textContent =
        `${auditBlocks.length} blok tersimpan`;
      renderAuditChain();
      showMessage(
        $("#audit-message"),
        isValid
          ? "Hash setiap blok dan tautan antarblok berhasil diverifikasi."
          : "Pemeriksaan menemukan ketidaksesuaian. Rantai audit mungkin telah diubah.",
        isValid ? "success" : "error",
      );
    } catch (error) {
      auditBlocks = [];
      auditPage = 0;
      integrity.dataset.state = "invalid";
      integrity.textContent = "Verifikasi gagal";
      $("#audit-block-count").textContent = "Data tidak tersedia";
      renderAuditChain();
      showMessage($("#audit-message"), error.message, "error");
    } finally {
      refreshButton.disabled = false;
    }
  }

  $("#refresh-audit-button").addEventListener("click", loadAuditChain);
  $("#audit-previous-button").addEventListener("click", () => {
    if (auditPage > 0) {
      auditPage -= 1;
      renderAuditChain();
    }
  });
  $("#audit-next-button").addEventListener("click", () => {
    if ((auditPage + 1) * auditPageSize < auditBlocks.length) {
      auditPage += 1;
      renderAuditChain();
    }
  });

  async function openSharingDialog(resource) {
    itemToShare = resource;
    $("#share-dialog-title").textContent = `Izin: ${resource.name}`;
    $("#share-create-option").hidden = resource.kind !== "folder";
    $("#share-message").textContent = "";
    try {
      const result = await callApi("list_accounts_for_sharing", resource.id);
      const select = $("#share-account-select");
      select.replaceChildren();
      for (const target of result.accounts) {
        select.add(new Option(target.username, String(target.id)));
      }
      if (result.accounts.length === 0) {
        showMessage($("#share-message"), "Belum ada akun lain yang dapat diberi izin.");
        $("#share-read").checked = false;
        $("#share-create").checked = false;
        $("#share-update").checked = false;
        shareDialog.showModal();
        return;
      }

      function updateSelectedAccountPermissions() {
        const target = result.accounts.find(
          (entry) => String(entry.id) === select.value,
        );
        const permissions = target?.permissions ?? {};
        $("#share-read").checked = Boolean(permissions.read);
        $("#share-create").checked = Boolean(permissions.create);
        $("#share-update").checked = Boolean(permissions.update);
      }
      select.onchange = updateSelectedAccountPermissions;
      updateSelectedAccountPermissions();
      shareDialog.showModal();
    } catch (error) {
      showVaultError(error);
    }
  }

  $("#share-update").addEventListener("change", (event) => {
    if (event.target.checked) $("#share-read").checked = true;
  });
  $("#share-create").addEventListener("change", (event) => {
    if (event.target.checked) $("#share-read").checked = true;
  });
  $("#save-sharing-button").addEventListener("click", async () => {
    const select = $("#share-account-select");
    if (!itemToShare || !select.value) {
      showMessage($("#share-message"), "Pilih akun yang akan diberi izin.", "error");
      return;
    }
    const saveButton = $("#save-sharing-button");
    saveButton.disabled = true;
    try {
      await callApi(
        "set_resource_permissions",
        itemToShare.id,
        Number(select.value),
        $("#share-create").checked,
        $("#share-read").checked,
        $("#share-update").checked,
      );
      showMessage($("#share-message"), "Izin item berhasil disimpan.", "success");
      guideClosure(`Izin untuk ${itemToShare.name} sudah diperbarui.`);
      window.setTimeout(() => shareDialog.close(), 450);
      await loadVault();
    } catch (error) {
      showMessage($("#share-message"), error.message, "error");
      guideClosure(error.message);
    } finally {
      saveButton.disabled = false;
    }
  });

  $("#create-folder-button").addEventListener("click", async () => {
    const name = window.prompt("Nama folder baru:");
    if (!name) return;
    try {
      await callApi("create_resource", name, "folder", currentParentId);
      showMessage(vaultMessage, "Folder berhasil dibuat.", "success");
      guideClosure(`Folder ${name} berhasil dibuat. Atur izin folder jika ingin membagikannya.`);
      await loadVault();
    } catch (error) {
      showVaultError(error);
    }
  });

  $("#download-resource-button").addEventListener("click", () => {
    if (!resourceToDownload) {
      showMessage(
        $("#download-message"),
        "Pilih file melalui tombol Lihat terlebih dahulu.",
        "error",
      );
      return;
    }
    $("#download-password-form").hidden = false;
    $("#download-password-input").value = "";
    showMessage($("#download-message"), "Masukkan password akun untuk setiap unduhan.");
    $("#download-password-input").focus();
  });

  $("#download-password-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!resourceToDownload) {
      showMessage($("#download-message"), "File yang dipilih tidak tersedia.", "error");
      return;
    }
    const passwordInput = $("#download-password-input");
    const confirmButton = $("#confirm-download-button");
    const password = passwordInput.value;
    if (!password) {
      showMessage($("#download-message"), "Masukkan password akun.", "error");
      return;
    }

    confirmButton.disabled = true;
    suspendPreviewCloseCleanup = true;
    previewDialog.close();
    document.body.classList.remove("file-preview-open");
    try {
      const result = await callApi(
        "download_resource",
        resourceToDownload.id,
        password,
      );
      if (result.cancelled) {
        showMessage($("#download-message"), "Unduhan dibatalkan.");
        return;
      }
      $("#download-password-form").hidden = true;
      showMessage(
        $("#download-message"),
        `File berhasil disimpan: ${result.name}.`,
        "success",
      );
      guideClosure(`File ${result.name} berhasil disimpan setelah password akun diverifikasi.`);
    } catch (error) {
      showMessage($("#download-message"), error.message, "error");
      guideClosure(error.message);
    } finally {
      if (resourceToDownload) {
        previewDialog.showModal();
        document.body.classList.add("file-preview-open");
      }
      suspendPreviewCloseCleanup = false;
      passwordInput.value = "";
      confirmButton.disabled = false;
    }
  });

  previewDialog.addEventListener("close", () => {
    if (suspendPreviewCloseCleanup || previewDialog.open) return;
    resourceToDownload = null;
    $("#download-password-input").value = "";
    $("#download-password-form").hidden = true;
    $("#preview-image").removeAttribute("src");
    $("#preview-frame").removeAttribute("src");
    document.body.classList.remove("file-preview-open");
    if (previewObjectUrl !== null) {
      URL.revokeObjectURL(previewObjectUrl);
      previewObjectUrl = null;
    }
  });

  $("#generate-rsa-key-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      const keyPair = await callApi("generate_rsa_key_pair");
      $("#rsa-public-key").value = keyPair.public_key;
      $("#rsa-private-key").value = keyPair.private_key;
      showMessage(
        $("#crypto-message"),
        "Key pair RSA 3072-bit berhasil dibuat. Simpan cadangan private key secara aman.",
        "success",
      );
      guideClosure("Key pair RSA siap. Simpan private key di tempat aman; saya tidak menyimpannya.");
    } catch (error) {
      showMessage($("#crypto-message"), error.message, "error");
      guideClosure(error.message);
    } finally {
      button.disabled = false;
    }
  });

  function readCaesarShift() {
    const shift = $("#caesar-shift-input").valueAsNumber;
    if (!Number.isInteger(shift) || shift < 0 || shift > 25) {
      throw new Error("Caesar shift harus berupa angka antara 0 dan 25.");
    }
    return shift;
  }

  $("#encrypt-message-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    $("#encrypted-message-output").value = "";
    try {
      const ciphertext = await callApi(
        "encrypt_message",
        $("#plain-message-input").value,
        readCaesarShift(),
        $("#shared-cipher-key").value,
        $("#rsa-public-key").value,
      );
      $("#encrypted-message-output").value = ciphertext;
      showMessage(
        $("#crypto-message"),
        "Pesan berhasil dienkripsi. Ciphertext hanya berisi karakter heksadesimal.",
        "success",
      );
      guideClosure("Pesan selesai dienkripsi berlapis. Salin atau simpan ciphertext; jangan bagikan private key.");
    } catch (error) {
      showMessage($("#crypto-message"), error.message, "error");
      guideClosure(error.message);
    } finally {
      button.disabled = false;
    }
  });

  $("#decrypt-message-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    $("#decrypted-message-output").value = "";
    try {
      const plaintext = await callApi(
        "decrypt_message",
        $("#encrypted-message-input").value.trim(),
        readCaesarShift(),
        $("#shared-cipher-key").value,
        $("#rsa-private-key").value,
      );
      $("#decrypted-message-output").value = plaintext;
      showMessage($("#crypto-message"), "Ciphertext berhasil didekripsi.", "success");
      guideClosure("Pesan berhasil didekripsi menggunakan kunci dan parameter yang cocok.");
    } catch (error) {
      showMessage($("#crypto-message"), error.message, "error");
      guideClosure(error.message);
    } finally {
      button.disabled = false;
    }
  });

  $("#save-encrypted-message-button").addEventListener("click", async (event) => {
    const saveButton = event.currentTarget;
    const ciphertext = $("#encrypted-message-output").value;
    if (!ciphertext.trim()) {
      showMessage($("#crypto-message"), "Isi ciphertext terlebih dahulu.", "error");
      return;
    }

    saveButton.disabled = true;
    try {
      const filename = await callApi("save_encrypted_message", ciphertext);
      currentParentId = null;
      currentFolderName = "";
      await loadVault();
      showMessage(
        $("#crypto-message"),
        `Ciphertext disimpan di folder akun sebagai ${filename}.`,
        "success",
      );
      guideClosure(`Ciphertext disimpan sebagai ${filename} di folder akun lokal.`);
    } catch (error) {
      showMessage($("#crypto-message"), error.message, "error");
      guideClosure(error.message);
    } finally {
      saveButton.disabled = false;
    }
  });

  window.addEventListener("pagehide", () => {
    $("#shared-cipher-key").value = "";
    $("#rsa-private-key").value = "";
    $("#plain-message-input").value = "";
    $("#decrypted-message-output").value = "";
  }, { once: true });

  uploadInput.addEventListener("change", async () => {
    const file = uploadInput.files?.[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      showVaultError(new Error("Ukuran file maksimal 10 MiB."));
      uploadInput.value = "";
      return;
    }
    try {
      const content = await readFileAsBase64(file);
      await callApi(
        "create_resource",
        file.name,
        "file",
        currentParentId,
        content,
        file.type || "application/octet-stream",
      );
      showMessage(vaultMessage, `${file.name} berhasil disimpan.`, "success");
      guideClosure(`File ${file.name} berhasil disimpan. Gunakan Atur akses untuk memilih akun yang boleh melihat atau mengubahnya.`);
      await loadVault();
    } catch (error) {
      showVaultError(error);
    } finally {
      uploadInput.value = "";
    }
  });

  replaceInput.addEventListener("change", async () => {
    const file = replaceInput.files?.[0];
    const resource = itemToReplace;
    if (!file || !resource) return;
    if (file.size > 10 * 1024 * 1024) {
      showVaultError(new Error("Ukuran file maksimal 10 MiB."));
      replaceInput.value = "";
      return;
    }
    try {
      const content = await readFileAsBase64(file);
      await callApi(
        "update_resource",
        resource.id,
        file.name,
        content,
        file.type || "application/octet-stream",
      );
      showMessage(vaultMessage, `${file.name} berhasil diperbarui.`, "success");
      guideClosure(`File ${file.name} berhasil diperbarui.`);
      await loadVault();
    } catch (error) {
      showVaultError(error);
    } finally {
      itemToReplace = null;
      replaceInput.value = "";
    }
  });

  $("#vault-back-button").addEventListener("click", async () => {
    currentParentId = null;
    currentFolderName = "";
    await loadVault();
  });

  $("#logout-button").addEventListener("click", async () => {
    try {
      await callApi("logout");
      window.location.replace("index.html");
    } catch (error) {
      window.alert(error.message);
      guideClosure(error.message);
    }
  });

  await Promise.all([loadVault(), loadAuditChain()]);
}

async function initializeSteganographyPage() {
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

  const account = await callApi("get_current_account");
  $("#active-username").textContent =
    `${account.username}${account.is_admin ? " · ADMIN" : " · USER"}`;
  const hideForm = $("#steg-hide-form");
  const revealForm = $("#steg-reveal-form");
  const hideInput = $("#steg-hide-image");
  const revealInput = $("#steg-reveal-image");
  const hidePreview = $("#steg-hide-preview");
  const revealPreview = $("#steg-reveal-preview");
  const hiddenCiphertext = $("#steg-ciphertext");
  const revealedCiphertext = $("#steg-revealed-ciphertext");
  const copyButton = $("#steg-copy-button");
  const previewUrls = new Map();
  const maxImageBytes = 10 * 1024 * 1024;

  function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.addEventListener("load", () => {
        const result = reader.result;
        if (typeof result !== "string" || !result.includes(",")) {
          reject(new Error("Gambar gagal dibaca."));
          return;
        }
        resolve(result.slice(result.indexOf(",") + 1));
      });
      reader.addEventListener("error", () => reject(new Error("Gambar gagal dibaca.")));
      reader.readAsDataURL(file);
    });
  }

  function validateImage(file) {
    if (!file) throw new Error("Pilih gambar PNG terlebih dahulu.");
    if (!file.name.toLowerCase().endsWith(".png")) {
      throw new Error("Format gambar yang didukung hanya PNG.");
    }
    if (file.size > maxImageBytes) {
      throw new Error("Ukuran gambar maksimal 10 MiB.");
    }
  }

  function attachPreview(input, preview, messageElement) {
    input.addEventListener("change", () => {
      const previousUrl = previewUrls.get(preview);
      if (previousUrl) URL.revokeObjectURL(previousUrl);
      preview.removeAttribute("src");
      preview.hidden = true;
      const file = input.files?.[0];
      if (!file) return;
      try {
        validateImage(file);
        const url = URL.createObjectURL(file);
        previewUrls.set(preview, url);
        preview.src = url;
        preview.hidden = false;
        showMessage(messageElement, "");
      } catch (error) {
        input.value = "";
        showMessage(messageElement, error.message, "error");
      }
    });
  }

  attachPreview(hideInput, hidePreview, $("#steg-hide-message"));
  attachPreview(revealInput, revealPreview, $("#steg-reveal-message"));

  hideForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("#steg-hide-button");
    try {
      const image = hideInput.files?.[0];
      validateImage(image);
      const ciphertext = hiddenCiphertext.value.trim();
      if (!ciphertext || ciphertext.length % 2 !== 0 || !/^[0-9a-f]+$/i.test(ciphertext)) {
        throw new Error("Masukkan ciphertext heksadesimal dengan panjang genap.");
      }
      button.disabled = true;
      showMessage($("#steg-hide-message"), "Memproses PNG, periksa juga kapasitas gambarnya.");
      const imageBase64 = await readFileAsBase64(image);
      const result = await callApi(
        "hide_steganographic_message",
        imageBase64,
        image.name,
        ciphertext,
      );
      if (result.cancelled) {
        showMessage($("#steg-hide-message"), "Penyimpanan gambar dibatalkan.");
        return;
      }
      showMessage(
        $("#steg-hide-message"),
        `Gambar steganografi berhasil disimpan sebagai ${result.name}.`,
        "success",
      );
      guideClosure(`Ciphertext berhasil disisipkan dan disimpan sebagai ${result.name}.`);
    } catch (error) {
      showMessage($("#steg-hide-message"), error.message, "error");
      guideClosure(error.message);
    } finally {
      button.disabled = false;
    }
  });

  revealForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("#steg-reveal-button");
    try {
      const image = revealInput.files?.[0];
      validateImage(image);
      button.disabled = true;
      copyButton.disabled = true;
      revealedCiphertext.value = "";
      showMessage($("#steg-reveal-message"), "Mencari pesan tersembunyi di dalam PNG.");
      const imageBase64 = await readFileAsBase64(image);
      const ciphertext = await callApi(
        "reveal_steganographic_message",
        imageBase64,
        image.name,
      );
      revealedCiphertext.value = ciphertext;
      copyButton.disabled = false;
      showMessage(
        $("#steg-reveal-message"),
        "Ciphertext berhasil diekstrak. Gunakan halaman super enkripsi untuk mendekripsinya.",
        "success",
      );
      guideClosure("Ciphertext berhasil diekstrak. Dekripsi dengan parameter dan private key RSA yang cocok.");
    } catch (error) {
      showMessage($("#steg-reveal-message"), error.message, "error");
      guideClosure(error.message);
    } finally {
      button.disabled = false;
    }
  });

  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(revealedCiphertext.value);
    } catch {
      revealedCiphertext.focus();
      revealedCiphertext.select();
      if (!document.execCommand("copy")) {
        showMessage(
          $("#steg-reveal-message"),
          "Clipboard tidak tersedia. Pilih dan salin ciphertext secara manual.",
          "error",
        );
        return;
      }
    }
    showMessage($("#steg-reveal-message"), "Ciphertext berhasil disalin.", "success");
  });

  $("#logout-button").addEventListener("click", async () => {
    try {
      await callApi("logout");
      window.location.replace("index.html");
    } catch (error) {
      window.alert(error.message);
    }
  });

  window.addEventListener("pagehide", () => {
    for (const url of previewUrls.values()) URL.revokeObjectURL(url);
    previewUrls.clear();
    hiddenCiphertext.value = "";
    revealedCiphertext.value = "";
  }, { once: true });

  guideClosure("Pilih PNG dan ciphertext hasil super enkripsi untuk menyisipkan pesan, atau ekstrak ciphertext dari gambar yang sudah diproses.");
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "access") initializeAccessPage();
  if (page === "dashboard") initializeDashboard();
  if (page === "steganography") initializeSteganographyPage();
});